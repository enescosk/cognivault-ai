"""F1 ön koşulu — gerçek +90 numara gelmeden telefon akışını uçtan uca sür.

Neden var: telefon kodu (`phone_flow_service`, voice webhook'ları, TTS cache,
kanal→klinik çözümlemesi) yazıldı ve birim testleri var, ama **hiç kimse gerçek
bir çağrının yaptığı şeyi yapmadı**: imzalı HTTP isteği at, dönen TwiML'i oku,
`<Play>` sesini indir, bir sonraki turu aynı CallSid ile gönder, sonunda
randevunun gerçekten yazıldığını doğrula. Birim testi TestClient ile çalışır ve
imza doğrulamasını, gerçek TTS sentezini, ağ gecikmesini ATLAR.

Bu araç ÇALIŞAN bir backend'e karşı koşar (`./scripts/run_demo.sh`) ve Twilio'nun
yapacağı şeyin aynısını yapar. F1'in "ilk gerçek arama" maddesine kadar olan her
şeyi numara tedariki beklemeden kanıtlanabilir hâle getirir.

NE KANITLAR
  · Webhook imza doğrulaması gerçek bir imzayla geçiyor (TestClient bunu atlar).
  · Çok turlu slot pazarlığı telefonda KAPANIYOR (teklif → sözlü seçim → randevu).
  · Yanıt sesi gerçekten üretiliyor ve indirilebiliyor (<Play> 200 + bayt sayısı).
  · Acil turda eskalasyon slot akışını EZİYOR.
  · Bağlanmamış numara veri yazmadan reddediliyor (multi-tenant güvenliği).
  · Tur başına ve toplam gecikme — F1'in "90 saniye" kabul kapısının ölçümü.

NE KANITLAMAZ
  · Gerçek STT doğruluğu. Twilio `SpeechResult`'ı burada metin olarak verilir;
    mikrofon, gürültü ve tanıma hatası kapsam dışı (o F2 — gerçek cihaz QA'i).
  · Gerçek SMS teslimi. Sağlayıcı mock modundayken onay SMS'i yalnız log'a
    düşer; araç bunu "gönderildi" diye raporlamaz, sağlayıcı modunu yazar.
  · Telefon şebekesi/SIP gecikmesi. Ölçülen süre uygulama tarafıdır.

KULLANIM (backend/ dizininden, backend ayaktayken)
    python -m app.ops.simulate_call --list
    python -m app.ops.simulate_call --scenario randevu --auto-bind
    python -m app.ops.simulate_call --all --auto-bind
    python -m app.ops.simulate_call --all --json        # makine okunur çıktı

Çıkış kodu 0=GEÇTİ, 1=KALDI → CI'da ya da kurulum sonrası duman testi olarak
kapı gibi kullanılabilir.
"""
from __future__ import annotations

import argparse
import base64
from dataclasses import dataclass, field
import hashlib
import hmac
import json
import re
import time
from typing import Any
import urllib.error
import urllib.parse
import urllib.request
import uuid

DEFAULT_BASE_URL = "http://localhost:8000"
DEFAULT_TO = "+903120000000"
DEFAULT_FROM = "+905557001122"

# F1 kabul kapısı: insan telefonu kapattığında randevu kapanmış olmalı.
F1_CALL_BUDGET_SECONDS = 90.0


@dataclass
class Turn:
    """Tek bir konuşma turu ve ölçümü."""

    said: str
    status_code: int
    latency_ms: float
    spoken: str            # hastanın duyduğu metin (Play anahtarı ya da Say metni)
    audio_bytes: int | None  # <Play> indirildiyse bayt; <Say> fallback ise None
    has_gather: bool       # çağrı devam ediyor mu
    raw: str


@dataclass
class ScenarioResult:
    name: str
    call_sid: str
    turns: list[Turn] = field(default_factory=list)
    # ok=None → "ölçülemedi": kapı ne geçti ne kaldı. Yeşil saymak yalan olur,
    # kırmızı saymak aracı kullanılmaz hale getirir; ayrı durum tek dürüst yol.
    checks: list[tuple[str, bool | None, str]] = field(default_factory=list)
    total_seconds: float = 0.0

    def check(self, label: str, ok: bool, detail: str = "") -> None:
        self.checks.append((label, bool(ok), detail))

    def skip(self, label: str, reason: str) -> None:
        self.checks.append((label, None, reason))

    @property
    def passed(self) -> bool:
        return all(ok for _, ok, _ in self.checks if ok is not None)


# ─── Senaryolar ──────────────────────────────────────────────────────────────
# Her senaryo: hastanın sırayla söyledikleri + bu akışın neyi kanıtlaması
# gerektiği. Cümleler bilinçli olarak "temiz STT çıktısı" gibi yazıldı; bozuk
# tanıma senaryoları F2'nin (gerçek cihaz QA) işi.

SCENARIOS: dict[str, dict[str, Any]] = {
    "randevu": {
        "why": "Çok turlu slot pazarlığı telefonda kapanıyor mu?",
        "says": [
            "Merhaba, diş ağrım var randevu almak istiyorum.",
            "Yarın öğleden sonra uygun olur.",
            "Birincisi olsun.",
        ],
        "expect_booked": True,
    },
    "acil": {
        "why": "Acil sinyali randevu akışını eziyor mu?",
        "says": [
            "Randevu almak istiyorum.",
            "Aslında şu an nefes almakta zorlanıyorum.",
        ],
        "expect_emergency": True,
    },
    "anlasilmadi": {
        "why": "Boş/anlamsız STT çıktısı çağrıyı düşürmeden toparlanıyor mu?",
        "says": ["", "asdf qwer zxcv"],
        "expect_recovers": True,
    },
    "baglanmamis-numara": {
        "why": "Hiçbir kliniğe bağlı olmayan numara veri yazmadan reddediliyor mu?",
        "says": ["Randevu almak istiyorum."],
        "unbound": True,
        "expect_rejected": True,
    },
}


# ─── Twilio taklidi ──────────────────────────────────────────────────────────

def twilio_signature(auth_token: str, url: str, params: dict[str, str]) -> str:
    """Twilio'nun `X-Twilio-Signature` üretimi: URL + sıralı alanlar, HMAC-SHA1.

    `app.core.webhook_security.verify_twilio_signature`'ın tam aynası. Kasten
    o modülden import EDİLMEDİ: doğrulayıcıyla üretici aynı koddan gelirse test
    kendi hatasını doğrular. Bu bir sözleşme testi, birbirinden bağımsız iki
    uygulamanın aynı sonuca varması gerekiyor.
    """
    canonical = url + "".join(f"{k}{v}" for k, v in sorted(params.items()))
    digest = hmac.new(auth_token.encode("utf-8"), canonical.encode("utf-8"), hashlib.sha1).digest()
    return base64.b64encode(digest).decode("ascii")


def post_form(base_url: str, path: str, params: dict[str, str], auth_token: str,
              timeout: float = 30.0) -> tuple[int, str]:
    url = base_url.rstrip("/") + path
    body = urllib.parse.urlencode(params).encode("utf-8")
    headers = {"Content-Type": "application/x-www-form-urlencoded"}
    if auth_token:
        # İmza gerekmiyorsa sunucu başlığı yok sayar; gerekiyorsa bu geçerli imza
        # doğrulamayı GERÇEKTEN egzersiz eder.
        headers["X-Twilio-Signature"] = twilio_signature(auth_token, url, params)
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as response:
            return response.status, response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def fetch_audio(base_url: str, path: str, timeout: float = 30.0) -> int | None:
    """<Play> sesini gerçekten indir — TwiML'de URL olması sesin ÜRETİLDİĞİ
    anlamına gelmez; cache'te yoksa sunucu 404 döner ve hasta sessizlik duyar."""
    try:
        with urllib.request.urlopen(base_url.rstrip("/") + path, timeout=timeout) as response:
            return len(response.read())
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError):
        return None


_PLAY = re.compile(r"<Play>([^<]+)</Play>")
_SAY = re.compile(r"<Say[^>]*>([^<]*)</Say>")


def parse_twiml(base_url: str, xml: str) -> tuple[str, int | None, bool]:
    """TwiML → (hastanın duyduğu metin, indirilen ses baytı, çağrı sürüyor mu)."""
    has_gather = "<Gather" in xml
    play = _PLAY.search(xml)
    if play:
        path = play.group(1).strip()
        return f"[ses] {path}", fetch_audio(base_url, path), has_gather
    says = _SAY.findall(xml)
    return (" ".join(s.strip() for s in says) if says else "(ses yok)"), None, has_gather


# ─── Çağrı sürücüsü ──────────────────────────────────────────────────────────

def run_scenario(name: str, spec: dict[str, Any], *, base_url: str, to_number: str,
                 from_number: str, auth_token: str) -> ScenarioResult:
    call_sid = f"CA{uuid.uuid4().hex[:30]}"
    result = ScenarioResult(name=name, call_sid=call_sid)
    started = time.perf_counter()

    # 1) Çağrı açılışı — KVKK anonsu burada okunur.
    code, xml = post_form(base_url, "/api/webhooks/voice/incoming",
                          {"From": from_number, "To": to_number, "CallSid": call_sid,
                           "CallStatus": "ringing"}, auth_token)
    spoken, audio, has_gather = parse_twiml(base_url, xml)
    result.turns.append(Turn("(çağrı açıldı)", code, 0.0, spoken, audio, has_gather, xml))
    result.check("Açılış 200 döndü", code == 200, f"HTTP {code}")
    if code == 401:
        result.check("İmza doğrulandı", False, "401 — TWILIO_AUTH_TOKEN eşleşmiyor")
        result.total_seconds = time.perf_counter() - started
        return result
    result.check("Açılışta KVKK anonsu + dinleme açık", has_gather, "Gather yok")

    # 2) Konuşma turları — hepsi aynı CallSid, gerçek çağrıdaki gibi.
    for said in spec["says"]:
        turn_started = time.perf_counter()
        code, xml = post_form(base_url, "/api/webhooks/voice/gather",
                              {"From": from_number, "To": to_number, "CallSid": call_sid,
                               "SpeechResult": said, "Confidence": "0.95"}, auth_token)
        latency = (time.perf_counter() - turn_started) * 1000
        spoken, audio, has_gather = parse_twiml(base_url, xml)
        result.turns.append(Turn(said, code, latency, spoken, audio, has_gather, xml))
        if code != 200:
            result.check(f"Tur 200 döndü: {said[:32]!r}", False, f"HTTP {code}")
            break
        if not has_gather:
            break  # çağrı kapandı (randevu bitti ya da numara reddedildi)

    # 3) Twilio'nun kapanış bildirimi.
    post_form(base_url, "/api/webhooks/voice/status",
              {"CallSid": call_sid, "CallStatus": "completed",
               "CallDuration": str(int(time.perf_counter() - started))}, auth_token)
    result.total_seconds = time.perf_counter() - started

    _apply_expectations(result, spec)
    return result


def _apply_expectations(result: ScenarioResult, spec: dict[str, Any]) -> None:
    """Senaryoya özel kapılar. Transkript hep yazılır; kapı kararı burada verilir."""
    turns = result.turns
    spoken_all = " ".join(t.spoken for t in turns).lower()
    raw_all = " ".join(t.raw for t in turns).lower()

    result.check("Her tur 200 döndü", all(t.status_code == 200 for t in turns),
                 ", ".join(str(t.status_code) for t in turns))

    if spec.get("expect_rejected"):
        # Bu kapı yalnız CLINICAL_CHANNEL_BINDING_STRICT=true iken anlamlı.
        # Strict kapalıyken `resolve_webhook_clinic` varsayılan kliniğe düşer —
        # yani çağrı reddedilmez. Bunu "geçti" saymak F1.4'ü yalan kanıtlar.
        from app.core.config import get_settings

        if not get_settings().clinical_channel_binding_strict:
            result.skip("Bağlanmamış numara reddedildi",
                        "CLINICAL_CHANNEL_BINDING_STRICT=false — çağrı varsayılan "
                        "kliniğe düşer. Canlıya çıkmadan önce AÇILMALI (F1.4).")
            return
        closed = not turns[-1].has_gather
        result.check("Bağlanmamış numarada çağrı kapatıldı", closed)
        result.check("Hizmet dışı anonsu verildi", "hizmet dışı" in raw_all or "hizmet disi" in raw_all)
        return

    # Ses gerçekten üretildi mi? <Play> varsa indirilebilmeli; <Say> fallback'i de
    # kabul (arama sessiz kalmıyor) ama ayrıca raporlanır.
    played = [t for t in turns if t.spoken.startswith("[ses]")]
    if played:
        result.check("Üretilen ses indirilebildi",
                     all(t.audio_bytes and t.audio_bytes > 0 for t in played),
                     f"{len(played)} <Play>, "
                     + ", ".join(str(t.audio_bytes) for t in played) + " bayt")
    else:
        result.check("Yanıt sesi var (Say fallback)", "(ses yok)" not in spoken_all,
                     "lokal TTS devrede değil — <Say> fallback kullanıldı")

    if spec.get("expect_emergency"):
        result.check("Acil eskalasyonu devrede",
                     "112" in raw_all or "doktor ekranına" in raw_all or "acil" in raw_all)

    if spec.get("expect_recovers"):
        result.check("Anlaşılmayan girdide çağrı düşmedi", turns[-1].has_gather)

    if spec.get("expect_booked"):
        booked = not turns[-1].has_gather
        result.check("Randevu telefonda kapandı (çağrı sonlandı)", booked,
                     "son turda hâlâ Gather var — akış kapanmadı")
        result.check(f"Toplam süre < {F1_CALL_BUDGET_SECONDS:.0f} sn",
                     result.total_seconds < F1_CALL_BUDGET_SECONDS,
                     f"{result.total_seconds:.1f} sn")


# ─── Veritabanı doğrulaması ──────────────────────────────────────────────────

def verify_in_db(call_sid: str) -> list[tuple[str, bool, str]]:
    """Webhook 200 dönmesi randevunun YAZILDIĞI anlamına gelmez; kaydı doğrula.

    F1 kabul kapısı "randevu operatör panelinde slot'a bağlı görünüyor" diyor —
    yani asıl kanıt burada, TwiML'de değil.
    """
    from sqlalchemy import select

    from app.db.session import SessionLocal
    from app.models import ClinicalAppointment, ClinicConversation

    checks: list[tuple[str, bool, str]] = []
    with SessionLocal() as db:
        conversation = db.scalars(
            select(ClinicConversation)
            .where(ClinicConversation.external_thread_id == call_sid)
            .order_by(ClinicConversation.id.desc())
        ).first()
        checks.append(("Görüşme kaydedildi", conversation is not None, call_sid))
        if conversation is None:
            return checks

        appointment = db.scalars(
            select(ClinicalAppointment)
            .where(ClinicalAppointment.conversation_id == conversation.id)
            .order_by(ClinicalAppointment.id.desc())
        ).first()
        checks.append(("Randevu kaydı oluştu", appointment is not None, ""))
        if appointment is None:
            return checks

        # "Slot'a bağlı" olması kritik: slot_id yoksa randevu gerçek hekim
        # takvimini tutmuyor demektir ve çift rezervasyon mümkün olur.
        checks.append(("Randevu gerçek takvim slot'una bağlı", appointment.slot_id is not None,
                       f"slot_id={appointment.slot_id} starts_at={appointment.starts_at}"))
        source = (appointment.metadata_json or {}).get("source")
        checks.append(("Kaynak telefon olarak işaretli", source == "phone_call", f"source={source}"))
    return checks


def sms_provider_mode() -> str:
    try:
        from app.services.sms_service import sms_capabilities
        caps = sms_capabilities()
        suffix = "GERÇEK TESLİM" if caps.get("real_delivery") else "yalnız log"
        return f"{caps.get('active_provider')} — {suffix}"
    except Exception as exc:  # pragma: no cover - teşhis amaçlı
        return f"bilinmiyor ({type(exc).__name__})"


# ─── Çıktı ───────────────────────────────────────────────────────────────────

def render(results: list[ScenarioResult], db_checks: dict[str, list[tuple[str, bool, str]]]) -> str:
    mark = lambda ok: "⏭️ " if ok is None else ("✅" if ok else "❌")  # noqa: E731
    lines = ["", "CogniVault — Simüle Edilmiş Telefon Çağrısı (F1 ön koşulu)",
             "=" * 62]
    for r in results:
        lines.append(f"\n▶ Senaryo: {r.name}   ({SCENARIOS[r.name]['why']})")
        lines.append(f"  CallSid: {r.call_sid}")
        for turn in r.turns:
            if turn.said == "(çağrı açıldı)":
                lines.append(f"    ☎  açılış                    → {turn.spoken[:58]}")
                continue
            said = turn.said or "(sessizlik)"
            lines.append(f"    🗣  {said[:40]:<40} ({turn.latency_ms:6.0f} ms)")
            lines.append(f"    🔊 {turn.spoken[:58]}")
        lines.append(f"  Toplam: {r.total_seconds:.1f} sn · {len(r.turns) - 1} tur")
        for label, ok, detail in r.checks:
            suffix = f"  — {detail}" if detail and ok is not True else ""
            lines.append(f"  {mark(ok)} {label}{suffix}")
        for label, ok, detail in db_checks.get(r.name, []):
            suffix = f"  — {detail}" if detail else ""
            lines.append(f"  {mark(ok)} [DB] {label}{suffix}")

    all_checks = [ok for r in results for _, ok, _ in r.checks]
    all_checks += [ok for checks in db_checks.values() for _, ok, _ in checks]
    measured = [ok for ok in all_checks if ok is not None]
    skipped = len(all_checks) - len(measured)
    lines += ["", "-" * 62,
              f"Kapılar: {sum(measured)}/{len(measured)} geçti"
              + (f"   ·   {skipped} ölçülemedi" if skipped else ""),
              f"SMS sağlayıcı modu: {sms_provider_mode()}",
              "NOT: mock modda onay SMS'i yalnız log'a düşer — teslim kanıtı değildir.",
              "=" * 62,
              ("✅ SİMÜLE ÇAĞRI: GEÇTİ" if all(measured) else "❌ SİMÜLE ÇAĞRI: KALDI"), ""]
    return "\n".join(lines)


# ─── CLI ─────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Gerçek numara olmadan telefon akışını uçtan uca sür.")
    parser.add_argument("--scenario", choices=sorted(SCENARIOS), help="tek senaryo koş")
    parser.add_argument("--all", action="store_true", help="tüm senaryoları koş")
    parser.add_argument("--list", action="store_true", help="senaryoları listele")
    parser.add_argument("--base-url", default=DEFAULT_BASE_URL)
    parser.add_argument("--clinic", default="demo-klinik")
    parser.add_argument("--to", default=DEFAULT_TO, help="aranan numara (klinik bu numaraya bağlı olmalı)")
    parser.add_argument("--from", dest="from_number", default=DEFAULT_FROM, help="arayan numara")
    parser.add_argument("--auto-bind", action="store_true",
                        help="aranan numarayı kliniğe bağla (bind_channel ile, idempotent)")
    parser.add_argument("--json", action="store_true", help="makine okunur çıktı")
    args = parser.parse_args(argv)

    if args.list:
        for name, spec in sorted(SCENARIOS.items()):
            print(f"  {name:<22} {spec['why']}")
        return 0

    names = sorted(SCENARIOS) if args.all else ([args.scenario] if args.scenario else ["randevu"])

    if args.auto_bind:
        from app.db.session import SessionLocal
        from app.models import ClinicChannel
        from app.ops.bind_channel import bind_channel
        with SessionLocal() as db:
            if bind_channel(db, clinic_slug=args.clinic, phone=args.to,
                            channel=ClinicChannel.PHONE, deactivate=False) != 0:
                return 2

    from app.core.config import get_settings
    auth_token = get_settings().twilio_auth_token.strip()

    results: list[ScenarioResult] = []
    db_checks: dict[str, list[tuple[str, bool, str]]] = {}
    for name in names:
        spec = SCENARIOS[name]
        # Bağlanmamış-numara senaryosu kasten bağlı OLMAYAN bir numarayı arar.
        to_number = f"+9031299{uuid.uuid4().hex[:6]}" if spec.get("unbound") else args.to
        result = run_scenario(name, spec, base_url=args.base_url, to_number=to_number,
                              from_number=args.from_number, auth_token=auth_token)
        results.append(result)
        if spec.get("expect_booked"):
            db_checks[name] = verify_in_db(result.call_sid)

    if args.json:
        print(json.dumps({
            "scenarios": [{
                "name": r.name, "call_sid": r.call_sid, "total_seconds": round(r.total_seconds, 3),
                "turns": [{"said": t.said, "status": t.status_code,
                           "latency_ms": round(t.latency_ms, 1), "spoken": t.spoken,
                           "audio_bytes": t.audio_bytes, "has_gather": t.has_gather}
                          for t in r.turns],
                "checks": [{"label": l, "pass": ok, "detail": d} for l, ok, d in r.checks],
                "db_checks": [{"label": l, "pass": ok, "detail": d}
                              for l, ok, d in db_checks.get(r.name, [])],
            } for r in results],
            "sms_provider_mode": sms_provider_mode(),
        }, ensure_ascii=False, indent=2))
    else:
        print(render(results, db_checks))

    ok = all(r.passed for r in results) and all(
        ok for checks in db_checks.values() for _, ok, _ in checks if ok is not None)
    return 0 if ok else 1


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
