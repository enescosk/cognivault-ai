"""Ses demosu — bir senaryoyu seçtiğin sesle konuştur, mp3'leri ve görüşme
metnini (script) dosyaya yaz.

Neden var: Voice Studio tarayıcıda canlı denemek için iyi, ama müşteriye
gösterilecek/gönderilecek bir çıktı bırakmıyor. Bu araç ÇALIŞAN bir backend'e
karşı koşar, asistanın repliklerini seçilen ElevenLabs sesiyle sentezler ve
yanına insanın okuyabileceği bir görüşme metni bırakır. Aynı komut `--yerel`
ile Piper'ı kullanır; ikisini yan yana dinleyip farkı gösterebilirsin.

NE KANITLAR
  · Seçilen ses/model/hız gerçekten sentezleniyor (HTTP 200 + bayt + süre).
  · Karşılayan (receiver) ve arayan (caller) taraf ayrı ayarlarla çalışıyor.
  · İstenirse aynı ayarlar kliniğin canlı profiline yazılıyor (--kaydet).

NE KANITLAMAZ
  · Gerçek çağrıda STT doğruluğunu ve şebeke gecikmesini (o `simulate_call`).
  · Replikler senaryodan gelir; burada LLM çalışmaz, model cümle uydurmaz.

KULLANIM (backend/ dizininden, backend ayaktayken)
    python -m app.ops.voice_demo --senaryolar
    python -m app.ops.voice_demo --sesler
    python -m app.ops.voice_demo --senaryo randevu --ses-ara meloxia --oynat
    python -m app.ops.voice_demo --senaryo giden-tanisma --model flash --hiz 1.05
    python -m app.ops.voice_demo --senaryo randevu --yerel      # Piper ile aynı metin
    python -m app.ops.voice_demo --senaryo randevu --ses-ara meloxia --kaydet

Giriş: --eposta ile kullanıcı, parola COGNIVAULT_PAROLA ortam değişkeninden ya
da terminalde sorularak alınır (ekrana yazılmaz, dosyaya kaydedilmez).
"""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import json
import os
import shutil
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_EMAIL = "admin@cognivault.com"

# CLI kısaltması → ElevenLabs model kimliği.
MODELS = {
    "multilingual": "eleven_multilingual_v2",
    "flash": "eleven_flash_v2_5",
    "turbo": "eleven_turbo_v2_5",
}
# CLI'da "karsilayan/arayan", sunucuda "receiver/caller".
SIDES = {"karsilayan": "receiver", "arayan": "caller"}

# Senaryolar. Replikler sabittir: demo her koşuda aynı çıksın ve müşteriye
# gönderilen metin ile duyulan ses birebir aynı olsun diye model konuşturulmaz.
SCENARIOS: dict[str, dict[str, Any]] = {
    "randevu": {
        "baslik": "Randevu talebi — gelen arama",
        "taraf": "karsilayan",
        "replikler": [
            ("asistan", "Demo Klinik, merhaba. Ben klinik asistanıyım, size nasıl yardımcı olabilirim?"),
            ("hasta", "Merhaba, diş ağrım var. Bugün bir randevu alabilir miyim?"),
            ("asistan", "Geçmiş olsun. Ağrınız için bugün saat on beşte ya da on yedi otuzda yerimiz var. Hangisi size uygun?"),
            ("hasta", "On yedi otuz daha iyi olur."),
            ("asistan", "Tamamdır, bugün saat on yedi otuza randevunuzu oluşturdum. Adınızı ve soyadınızı alabilir miyim?"),
            ("hasta", "Elif Demir."),
            ("asistan", "Teşekkür ederim Elif Hanım. Randevunuz kayıtlı, kısa bir onay mesajı göndereceğim. Geçmiş olsun, iyi günler."),
        ],
    },
    "acil": {
        "baslik": "Acil durum — insana aktarma",
        "taraf": "karsilayan",
        "replikler": [
            ("asistan", "Demo Klinik, merhaba. Size nasıl yardımcı olabilirim?"),
            ("hasta", "Dişim kırıldı ve kanama durmuyor."),
            ("asistan", "Anladım, bu acil bir durum. Sizi hemen kliniğimizdeki yetkiliye aktarıyorum. Hattan ayrılmayın; kanama için temiz bir gazlı bezle bastırmaya devam edin."),
        ],
    },
    "mesaj": {
        "baslik": "Mesaj bırakma — çalışma saati dışında",
        "taraf": "karsilayan",
        "replikler": [
            ("asistan", "Demo Klinik, merhaba. Şu anda çalışma saatlerimizin dışındayız. Dilerseniz mesajınızı alabilirim."),
            ("hasta", "Dolgu fiyatlarını öğrenmek istiyorum, yarın beni arayabilir misiniz?"),
            ("asistan", "Mesajınızı aldım: dolgu fiyatları hakkında bilgi ve geri arama talebi. Yarın mesai başında ekibimiz sizi arayacak. İyi akşamlar dilerim."),
        ],
    },
    "giden-tanisma": {
        "baslik": "Tanışma araması — giden arama",
        "taraf": "arayan",
        "replikler": [
            ("asistan", "Merhaba, Atlas Teknoloji ile mi görüşüyorum? Ben CogniVault adına arayan yapay zekâ asistanıyım."),
            ("yetkili", "Evet, buyurun."),
            ("asistan", "Teşekkür ederim. Gelen aramalarınızı ve mesajlarınızı karşılayan bir yapay zekâ resepsiyon hizmeti sunuyoruz. Kısaca anlatmam için müsait misiniz?"),
            ("yetkili", "Tabii, dinliyorum."),
            ("asistan", "Kısa bir tanışma görüşmesi için hangi gün ve saat size uygun olur?"),
        ],
    },
}

SPEAKER_LABELS = {"asistan": "Asistan", "hasta": "Hasta", "yetkili": "Yetkili"}


# ── HTTP (bağımlılıksız; araç kurulu olmayan makinede de koşsun) ─────────────
class ApiError(RuntimeError):
    pass


def request(base_url: str, path: str, *, token: str | None = None, method: str = "GET",
            payload: dict | None = None, timeout: float = 90.0) -> tuple[bytes, str]:
    """Backend'e istek atar; (gövde, content-type) döner."""
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(base_url.rstrip("/") + path, data=data, method=method)
    if data is not None:
        req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", "Bearer " + token)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read(), resp.headers.get("Content-Type", "")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", "replace")
        try:
            detail = json.loads(body).get("detail", body)
        except ValueError:
            detail = body
        raise ApiError(f"{method} {path} → HTTP {exc.code}: {detail}") from None
    except urllib.error.URLError as exc:
        raise ApiError(f"{base_url} adresine ulaşılamadı ({exc.reason}). Backend ayakta mı?") from None


def login(base_url: str, email: str) -> str:
    password = os.environ.get("COGNIVAULT_PAROLA") or getpass.getpass(f"{email} parolası: ")
    body, _ = request(base_url, "/api/auth/login", method="POST",
                      payload={"email": email, "password": password})
    return json.loads(body)["access_token"]


# ── Saf yardımcılar (ağsız test edilir) ─────────────────────────────────────
def pick_voice(voices: list[dict], query: str) -> dict:
    """İsim/kimlik parçasına göre ses seçer; tek eşleşme yoksa açıkça hata verir."""
    q = query.strip().lower()
    exact = [v for v in voices if v["id"].lower() == q]
    if exact:
        return exact[0]
    matches = [v for v in voices if q in v["name"].lower()]
    if not matches:
        raise ApiError(f"'{query}' ile eşleşen ses yok. --sesler ile listeyi gör.")
    if len(matches) > 1:
        names = ", ".join(v["name"] for v in matches[:5])
        raise ApiError(f"'{query}' birden fazla sese uyuyor: {names}. Daha belirgin yaz.")
    return matches[0]


def assistant_lines(scenario: dict, *, iki_taraf: bool) -> list[tuple[int, str, str]]:
    """Seslendirilecek replikler: (sıra, konuşan, metin)."""
    lines = []
    for index, (speaker, text) in enumerate(scenario["replikler"], start=1):
        if speaker == "asistan" or iki_taraf:
            lines.append((index, speaker, text))
    return lines


def build_transcript(scenario_key: str, scenario: dict, settings: dict,
                     results: dict[int, dict]) -> str:
    """Müşteriye gösterilebilir görüşme metni (Markdown)."""
    when = settings.get("tarih") or dt.datetime.now().strftime("%d.%m.%Y %H:%M")
    side = "Karşılayan asistan (gelen arama)" if scenario["taraf"] == "karsilayan" else "Arayan asistan (giden arama)"
    head = [
        f"# {scenario['baslik']}",
        "",
        f"- **Klinik:** {settings.get('klinik', '—')}",
        f"- **Taraf:** {side}",
        f"- **Ses:** {settings.get('ses_adi', '—')} · {settings.get('model', '—')}",
        f"- **Hız / kararlılık / ifade:** {settings.get('hiz')}× · {settings.get('stability')} · {settings.get('style')}",
        f"- **Tarih:** {when}",
        "",
        "---",
        "",
    ]
    body = []
    for index, (speaker, text) in enumerate(scenario["replikler"], start=1):
        label = SPEAKER_LABELS.get(speaker, speaker.title())
        audio = results.get(index)
        suffix = f"  \n<sub>🔊 `{audio['dosya']}` · {audio['ms']} ms</sub>" if audio else ""
        body.append(f"**{label}:** {text}{suffix}")
        body.append("")
    foot = [
        "---",
        "",
        "<sub>Bu bir demo kaydıdır: gerçek bir arama yapılmamış, takvime randevu yazılmamıştır. "
        "Replikler sabit senaryodan gelir; ses seçilen ayarlarla üretilmiştir.</sub>",
        "",
    ]
    return "\n".join(head + body + foot)


def merge_audio(files: list[Path], target: Path, *, gap_seconds: float = 0.6) -> Path | None:
    """Replikleri tek dosyada birleştirir (ffmpeg varsa; yoksa sessizce atlanır)."""
    if not files or shutil.which("ffmpeg") is None:
        return None
    inputs: list[str] = []
    filters: list[str] = []
    for i, path in enumerate(files):
        inputs += ["-i", str(path)]
    # Her parçanın ardına sessizlik ekle ki replikler üst üste binmesin.
    inputs += ["-f", "lavfi", "-t", str(gap_seconds), "-i", "anullsrc=r=44100:cl=mono"]
    gap_index = len(files)
    for i in range(len(files)):
        filters.append(f"[{i}:a]")
        if i < len(files) - 1:
            filters.append(f"[{gap_index}:a]")
    chain = "".join(filters) + f"concat=n={len(filters)}:v=0:a=1[out]"
    cmd = ["ffmpeg", "-y", *inputs, "-filter_complex", chain, "-map", "[out]", str(target)]
    result = subprocess.run(cmd, capture_output=True, timeout=180)
    return target if result.returncode == 0 and target.exists() else None


# ── Akış ────────────────────────────────────────────────────────────────────
def synthesize(base_url: str, token: str, *, text: str, local: bool, voice_id: str,
               model: str, speed: float, stability: float, style: float) -> tuple[bytes, str, int]:
    payload = {"text": text, "provider": "local" if local else "elevenlabs",
               "voice_id": voice_id if not local else "local-piper", "model": model,
               "speed": speed, "stability": stability, "style": style, "cloud_consent": True}
    started = time.monotonic()
    body, content_type = request(base_url, "/api/voice-studio/speech", token=token,
                                 method="POST", payload=payload)
    return body, content_type, round((time.monotonic() - started) * 1000)


def run(args: argparse.Namespace) -> int:
    scenario_key = args.senaryo
    scenario = SCENARIOS[scenario_key]
    token = args.token or login(args.base_url, args.eposta)

    voice = {"id": "local-piper", "name": "Piper · yerel Türkçe"}
    if not args.yerel:
        body, _ = request(args.base_url, "/api/voice-studio/voices", token=token)
        voices = json.loads(body).get("voices", [])
        if not voices:
            raise ApiError("Hesapta ses bulunamadı. ELEVENLABS_API_KEY doğru mu?")
        voice = pick_voice(voices, args.ses or args.ses_ara) if (args.ses or args.ses_ara) else voices[0]

    side = args.taraf or scenario["taraf"]
    model_id = MODELS[args.model]
    out_dir = Path(args.cikti or f"../tmp/ses-demo/{scenario_key}-{dt.datetime.now():%Y%m%d-%H%M%S}")
    out_dir.mkdir(parents=True, exist_ok=True)

    print(f"Senaryo : {scenario['baslik']}")
    print(f"Taraf   : {side} ({SIDES[side]})")
    print(f"Ses     : {voice['name']} · {'Piper (yerel)' if args.yerel else model_id}")
    print(f"Çıktı   : {out_dir}\n")

    results: dict[int, dict] = {}
    produced: list[Path] = []
    for index, speaker, text in assistant_lines(scenario, iki_taraf=args.iki_taraf):
        audio, content_type, ms = synthesize(
            args.base_url, token, text=text, local=args.yerel, voice_id=voice["id"],
            model=model_id, speed=args.hiz, stability=args.stability, style=args.stil)
        ext = "wav" if "wav" in content_type else "mp3"
        name = f"{index:02d}-{speaker}.{ext}"
        (out_dir / name).write_bytes(audio)
        produced.append(out_dir / name)
        results[index] = {"dosya": name, "ms": ms, "bayt": len(audio)}
        print(f"  {name:<20} {ms:>5} ms  {len(audio)/1024:>7.1f} KB  {text[:52]}…")

    settings = {"klinik": args.klinik, "taraf": side, "ses_adi": voice["name"], "ses_id": voice["id"],
                "model": "piper-yerel" if args.yerel else model_id, "hiz": args.hiz,
                "stability": args.stability, "style": args.stil,
                "tarih": dt.datetime.now().strftime("%d.%m.%Y %H:%M")}
    (out_dir / "gorusme.md").write_text(build_transcript(scenario_key, scenario, settings, results), encoding="utf-8")
    (out_dir / "ayarlar.json").write_text(
        json.dumps({"senaryo": scenario_key, **settings, "replikler": results}, ensure_ascii=False, indent=2),
        encoding="utf-8")

    merged = merge_audio(produced, out_dir / "birlesik.mp3") if not args.yerel else None
    total_ms = sum(r["ms"] for r in results.values())
    print(f"\nGörüşme metni : {out_dir / 'gorusme.md'}")
    if merged:
        print(f"Birleşik ses  : {merged}")
    print(f"Toplam sentez : {total_ms} ms ({len(results)} replik)")

    if args.kaydet:
        if args.yerel:
            print("\n--kaydet yoksayıldı: yerel ses profili klinik ayarına yazılmaz.")
        else:
            body, _ = request(args.base_url, "/api/voice-studio/profile", token=token, method="PUT",
                              payload={"role": SIDES[side], "voice_id": voice["id"], "model": model_id,
                                       "speed": args.hiz, "stability": args.stability, "style": args.stil,
                                       "use_in_calls": args.canli})
            state = json.loads(body)["roles"][SIDES[side]]
            print(f"\nKlinik profiline yazıldı ({SIDES[side]}). Canlı: {'evet' if state['live'] else 'hayır'}")
            for blocker in state["blockers"]:
                print(f"  eksik: {blocker}")

    if args.oynat and produced:
        target = merged or produced[0]
        if shutil.which("afplay"):
            subprocess.run(["afplay", str(target)], timeout=600)
        else:
            print("(afplay yok; dosyaları kendi oynatıcınla aç)")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Senaryoyu seçilen sesle konuştur; mp3 + görüşme metni üret.")
    parser.add_argument("--senaryo", choices=sorted(SCENARIOS), default="randevu")
    parser.add_argument("--senaryolar", action="store_true", help="senaryoları listele ve çık")
    parser.add_argument("--sesler", action="store_true", help="hesaptaki sesleri listele ve çık")
    parser.add_argument("--ses", help="ElevenLabs voice_id")
    parser.add_argument("--ses-ara", dest="ses_ara", help="ses adında geçen kelime (ör. meloxia)")
    parser.add_argument("--taraf", choices=sorted(SIDES), help="karsilayan | arayan (varsayılan: senaryonunki)")
    parser.add_argument("--model", choices=sorted(MODELS), default="multilingual")
    parser.add_argument("--hiz", type=float, default=1.0, help="0.7–1.2")
    parser.add_argument("--stability", type=float, default=0.45, help="0–1; düşük = daha tonlamalı")
    parser.add_argument("--stil", type=float, default=0.0, help="0–1; yükseldikçe gecikme artar")
    parser.add_argument("--iki-taraf", dest="iki_taraf", action="store_true",
                        help="hasta/yetkili repliklerini de aynı sesle seslendir")
    parser.add_argument("--yerel", action="store_true", help="ElevenLabs yerine Piper ile üret")
    parser.add_argument("--kaydet", action="store_true", help="ayarları kliniğin ilgili tarafına yaz")
    parser.add_argument("--canli", action="store_true", help="--kaydet ile: canlı görüşmelerde kullan (yönetici)")
    parser.add_argument("--oynat", action="store_true", help="bitince sesi çal (macOS afplay)")
    parser.add_argument("--cikti", help="çıktı klasörü (varsayılan tmp/ses-demo/...)")
    parser.add_argument("--klinik", default="demo-klinik")
    parser.add_argument("--base-url", dest="base_url", default=DEFAULT_BASE_URL)
    parser.add_argument("--eposta", default=DEFAULT_EMAIL)
    parser.add_argument("--token", default=os.environ.get("COGNIVAULT_TOKEN"),
                        help="hazır JWT (parola sorulmasın diye)")
    args = parser.parse_args(argv)

    if args.senaryolar:
        for key, scenario in sorted(SCENARIOS.items()):
            print(f"{key:<16} {scenario['baslik']}  [{scenario['taraf']}, {len(scenario['replikler'])} replik]")
        return 0
    try:
        if args.sesler:
            token = args.token or login(args.base_url, args.eposta)
            body, _ = request(args.base_url, "/api/voice-studio/voices", token=token)
            for v in json.loads(body).get("voices", []):
                print(f"{v['id']}  {v['name']}  {v.get('labels', {}).get('language', '')}")
            return 0
        return run(args)
    except ApiError as exc:
        print(f"HATA: {exc}")
        return 1
    except KeyboardInterrupt:
        return 130


if __name__ == "__main__":
    raise SystemExit(main())
