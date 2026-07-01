"""Dış ses rıza kapısı kanıt panosu (KVKK sınır-ötesi transfer).

`voice_factory.external_voice_permitted` üç-koşullu kapısının tüm doğruluk
tablosunu deterministik olarak koşturur ve tek bir güvensiz kombinasyonun bile
ses verisini buluta (OpenAI/ElevenLabs) çıkarmadığını kanıtlar.

ElevenLabs (Flash/Turbo TTS + Scribe v2 Realtime STT) yalnızca bu kapı
geçilince devreye girer; varsayılan yol tamamen yereldir (Piper + faster-whisper).
"""

from __future__ import annotations

import argparse
from itertools import product
import json
from pathlib import Path

from app.ai.voice_factory import external_voice_permitted


ARTIFACT_PATH = Path(__file__).resolve().parent / "data" / "voice_routing.json"


def _truth_table() -> list[dict]:
    rows: list[dict] = []
    for external_enabled, consent_granted, has_credentials in product([False, True], repeat=3):
        permitted = external_voice_permitted(
            external_enabled=external_enabled,
            consent_granted=consent_granted,
            has_credentials=has_credentials,
        )
        rows.append({
            "external_enabled": external_enabled,
            "consent_granted": consent_granted,
            "has_credentials": has_credentials,
            "permitted": permitted,
            "expected": external_enabled and consent_granted and has_credentials,
        })
    return rows


def build_report() -> dict:
    rows = _truth_table()
    permitted_rows = [r for r in rows if r["permitted"]]
    gates = {
        "only_all_three_permits": {
            "target": "yalnızca (dış-izin ∧ rıza ∧ anahtar) buluta izin verir",
            "permitted_count": len(permitted_rows),
            "pass": len(permitted_rows) == 1 and permitted_rows[0]["external_enabled"]
            and permitted_rows[0]["consent_granted"] and permitted_rows[0]["has_credentials"],
        },
        "default_denies": {
            "target": "hiçbir koşul yokken (varsayılan) bulut reddedilir → yerel",
            "pass": external_voice_permitted(
                external_enabled=False, consent_granted=False, has_credentials=False
            ) is False,
        },
        "consent_required": {
            "target": "dış-izin + anahtar var ama hasta rızası yoksa reddedilir",
            "pass": external_voice_permitted(
                external_enabled=True, consent_granted=False, has_credentials=True
            ) is False,
        },
        "dpa_required": {
            "target": "hasta rızası + anahtar var ama klinik dış-izni (DPA) yoksa reddedilir",
            "pass": external_voice_permitted(
                external_enabled=False, consent_granted=True, has_credentials=True
            ) is False,
        },
        "truth_table_consistent": {
            "target": "tüm 8 kombinasyon beklenen sonucu verir",
            "pass": all(r["permitted"] == r["expected"] for r in rows),
        },
    }
    return {
        "name": "external_voice_consent_gate",
        "purpose": "kvkk_cross_border_voice_gate",
        "providers_behind_gate": ["openai", "elevenlabs"],
        "default_local_providers": ["faster-whisper", "piper"],
        "truth_table": rows,
        "gates": gates,
        "overall_pass": all(gate["pass"] for gate in gates.values()),
        "remaining": [
            "Canlı çağrı yolunun (public.py/voice.py) per-hasta VOICE_RECORDING rızasını get_stt/tts_provider'a taşıması.",
            "ElevenLabs sözleşmesi/DPA imzası ve API anahtarı temini.",
            "Gerçek Türkçe kalite/gecikme A/B ölçümü (yerel vs ElevenLabs).",
        ],
    }


def render(report: dict) -> str:
    ok = lambda value: "PASS" if value else "FAIL"  # noqa: E731
    lines = [
        "Dış Ses Rıza Kapısı — KVKK Sınır-Ötesi Transfer",
        "=" * 60,
    ]
    for key, gate in report["gates"].items():
        lines.append(f"{ok(gate['pass']):<5} {key:<24} {gate['target']}")
    lines += ["-" * 60, f"GENEL: {ok(report['overall_pass'])}", "Kalan:"]
    lines.extend(f"- {item}" for item in report["remaining"])
    return "\n".join(lines)


def write_artifact(report: dict, path: Path = ARTIFACT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Dış ses rıza kapısı kanıt panosu")
    parser.add_argument("--no-save", action="store_true", help="artefakt yazma")
    parser.add_argument("--json", action="store_true", help="JSON çıktısı")
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
