"""İP-3.7 — Enerji tabanlı VAD (Voice Activity Detection), adaptif gürültü tabanı.

Ham PCM (int16) kare dizisi üzerinde çalışır — mikrofon/ses altyapısı GEREKTİRMEZ,
saf-Python DSP'dir. Her kare için kısa-süreli RMS enerjisini (dBFS) hesaplar ve
**adaptif gürültü tabanının** belirli bir marj üstündeyse konuşma sayar. Sabit
arka-plan gürültüsü zamanla tabana çekilir → sürekli uğultu konuşma tetiklemez
(gürültü toleransı). Sıfır-geçiş oranı (ZCR) çok-düşük-enerjili tıkırtıları eler.

Çıktısı (`is_speech`) doğrudan `turn_taking.TurnTakingController`'a beslenir.
Gerçek mikrofon yakalama ve gerçek-ses uçtan-uca gecikme ölçümü ses altyapısı ister
(bu modülün kapsamı dışında).

Saf Python (yalnızca `math`), deterministik. CLI: python -m app.voice.vad
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from pathlib import Path
from typing import Sequence

ARTIFACT_PATH = Path(__file__).resolve().parent / "data" / "vad.json"
_INT16_MAX = 32768.0
_DB_FLOOR = -100.0


@dataclass(frozen=True)
class EnergyVadConfig:
    sample_rate: int = 16000
    frame_ms: int = 20
    speech_margin_db: float = 10.0    # taban üstü bu marj → konuşma
    noise_adapt: float = 0.05         # gürültü tabanı EMA hızı (sessizken)
    init_noise_db: float = -55.0      # başlangıç gürültü tahmini
    max_noise_db: float = -25.0       # taban bu üstüne tırmanamaz (konuşmayı kovalamasın)
    min_zcr: float = 0.02             # bunun altındaki ZCR + düşük enerji → gürültü/DC
    warmup_ms: int = 200              # başlangıç ortam kalibrasyonu (bu süre konuşma sayılmaz)
    warmup_adapt: float = 0.5         # warmup sırasında hızlı taban EMA'sı

    @property
    def frame_len(self) -> int:
        return self.sample_rate * self.frame_ms // 1000

    def __post_init__(self) -> None:
        if self.frame_len <= 0:
            raise ValueError("frame_len pozitif olmalı (sample_rate/frame_ms)")


def rms_dbfs(samples: Sequence[int]) -> float:
    """Kare RMS enerjisi, dBFS (tam ölçek = 0 dB). Sessizlik → _DB_FLOOR."""
    n = len(samples)
    if n == 0:
        return _DB_FLOOR
    acc = 0.0
    for s in samples:
        acc += float(s) * float(s)
    rms = math.sqrt(acc / n)
    if rms <= 1e-9:
        return _DB_FLOOR
    return max(_DB_FLOOR, 20.0 * math.log10(rms / _INT16_MAX))


def zero_crossing_rate(samples: Sequence[int]) -> float:
    """İşaret değiştiren ardışık örnek oranı (0..1)."""
    n = len(samples)
    if n < 2:
        return 0.0
    crossings = 0
    prev = samples[0]
    for s in samples[1:]:
        if (s >= 0) != (prev >= 0):
            crossings += 1
        prev = s
    return crossings / (n - 1)


class EnergyVad:
    """Adaptif gürültü tabanlı enerji VAD. Kare başına is_speech üretir."""

    def __init__(self, config: EnergyVadConfig | None = None) -> None:
        self.cfg = config or EnergyVadConfig()
        self.noise_db: float = self.cfg.init_noise_db
        self._warmup_left: int = self.cfg.warmup_ms // self.cfg.frame_ms
        self._seen_first: bool = False

    def is_speech(self, samples: Sequence[int]) -> bool:
        db = rms_dbfs(samples)

        # İlk kare tabanı doğrudan ortama oturtur (keyfi -55'ten başlamamak için).
        if not self._seen_first:
            self.noise_db = min(self.cfg.max_noise_db, db)
            self._seen_first = True

        # Warmup: ortam sesini hızla tabana kalibre et, bu süre konuşma sayma.
        if self._warmup_left > 0:
            self._warmup_left -= 1
            a = self.cfg.warmup_adapt
            self.noise_db = min(self.cfg.max_noise_db, (1 - a) * self.noise_db + a * db)
            return False

        threshold = self.noise_db + self.cfg.speech_margin_db
        speech = db >= threshold

        if speech and zero_crossing_rate(samples) < self.cfg.min_zcr and db < self.cfg.init_noise_db:
            # Çok düşük enerjili + neredeyse DC → gürültü/tıkırtı, konuşma değil.
            speech = False

        if not speech:
            # Yalnızca sessizken tabanı yavaşça güncelle; konuşmayı kovalama.
            a = self.cfg.noise_adapt
            self.noise_db = min(self.cfg.max_noise_db, (1 - a) * self.noise_db + a * db)
        return speech

    def process(self, samples: Sequence[int]) -> list[bool]:
        """Sürekli örnek dizisini karelere bölüp kare başına is_speech döndürür."""
        fl = self.cfg.frame_len
        out: list[bool] = []
        for i in range(0, len(samples) - fl + 1, fl):
            out.append(self.is_speech(samples[i : i + fl]))
        return out


# ── Deterministik sentetik sinyaller (test + pano) ──────────────────────────
def _silence(ms: int, cfg: EnergyVadConfig) -> list[int]:
    return [0] * (cfg.sample_rate * ms // 1000)


def _tone(ms: int, cfg: EnergyVadConfig, amp: int = 8000, freq: float = 220.0) -> list[int]:
    n = cfg.sample_rate * ms // 1000
    w = 2 * math.pi * freq / cfg.sample_rate
    return [int(amp * math.sin(w * i)) for i in range(n)]


def _hum(ms: int, cfg: EnergyVadConfig, amp: int = 300, freq: float = 60.0) -> list[int]:
    """Sabit düşük-seviyeli arka-plan uğultusu (gürültü toleransı testi)."""
    n = cfg.sample_rate * ms // 1000
    w = 2 * math.pi * freq / cfg.sample_rate
    return [int(amp * math.sin(w * i)) for i in range(n)]


def build_report(cfg: EnergyVadConfig | None = None) -> dict:
    cfg = cfg or EnergyVadConfig()
    vad = EnergyVad(cfg)
    # Senaryo: 300ms uğultu (warmup) + 400ms konuşma-tonu + 300ms sessizlik
    signal = _hum(300, cfg) + _tone(400, cfg) + _silence(300, cfg)
    flags = vad.process(signal)

    frames_per = lambda ms: ms // cfg.frame_ms  # noqa: E731
    hum_flags = flags[: frames_per(300)]
    tone_flags = flags[frames_per(300) : frames_per(700)]
    sil_flags = flags[frames_per(700) :]

    hum_speech_ratio = sum(hum_flags) / len(hum_flags) if hum_flags else 0.0
    tone_speech_ratio = sum(tone_flags) / len(tone_flags) if tone_flags else 0.0
    sil_speech_ratio = sum(sil_flags) / len(sil_flags) if sil_flags else 0.0

    gates = {
        "speech_detected_in_tone": {"target": "konuşma-tonunda çoğunluk konuşma", "pass": tone_speech_ratio >= 0.8},
        "silence_not_speech": {"target": "sessizlikte konuşma yok", "pass": sil_speech_ratio == 0.0},
        "noise_tolerated": {"target": "sabit uğultu konuşma tetiklemez", "pass": hum_speech_ratio <= 0.2},
    }
    report = {
        "name": "energy_vad",
        "ip": "3.7",
        "config": {"sample_rate": cfg.sample_rate, "frame_ms": cfg.frame_ms, "speech_margin_db": cfg.speech_margin_db},
        "ratios": {
            "hum_speech_ratio": round(hum_speech_ratio, 4),
            "tone_speech_ratio": round(tone_speech_ratio, 4),
            "silence_speech_ratio": round(sil_speech_ratio, 4),
        },
        "gates": gates,
    }
    report["overall_pass"] = all(g["pass"] for g in gates.values())
    return report


def render(report: dict) -> str:
    ok = lambda b: "✅" if b else "❌"  # noqa: E731
    r = report["ratios"]
    lines = [
        "İP-3.7 — Enerji VAD (adaptif gürültü tabanı)",
        "=" * 46,
        f"Konuşma oranı  → ton {r['tone_speech_ratio']:.2f} · uğultu {r['hum_speech_ratio']:.2f} · sessizlik {r['silence_speech_ratio']:.2f}",
        "-" * 46,
    ]
    for g in report["gates"].values():
        lines.append(f"{ok(g['pass'])} {g['target']}")
    lines += ["=" * 46, f"{ok(report['overall_pass'])} GENEL: {'GEÇTİ' if report['overall_pass'] else 'KALDI'}"]
    return "\n".join(lines)


def write_artifact(report: dict, path: Path = ARTIFACT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="İP-3.7 enerji VAD")
    parser.add_argument("--no-save", action="store_true")
    parser.add_argument("--json", action="store_true")
    args = parser.parse_args(argv)

    report = build_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render(report))
    if not args.no_save:
        path = write_artifact(report)
        if not args.json:
            print(f"\nArtefakt: {path}")
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
