"""İP-3.7 — Turn-taking + barge-in + endpointing durum makinesi (gerçek-zamanlı ses).

Akustik VAD (kare enerjisi / konuşma-olasılığı) her ~20 ms'de bir `is_speech` üretir;
bu makine o kare akışını konuşma-sırası kararlarına çevirir:

- **Onset debounce** — kısa gürültü patlamaları (< onset eşiği) sırayı BAŞLATMAZ
  (gürültü toleransının kontrol-katmanı payı).
- **Endpointing** — kullanıcı bitişini, iz-düşük sessizlik eşiğiyle saptar.
- **Min-utterance** — eşiği geçse de çok kısa (seslendirilmiş) söylemler gürültü
  sayılıp yok sayılır.
- **Barge-in** — ajan (TTS) konuşurken kullanıcı yeterince konuşursa kesinti üretir
  (TTS durdurulur, söz sırası kullanıcıya geçer).
- **Max-utterance** — güvenlik tavanı; takılı kalmayı önler.

Saf Python, tamamen deterministik → birim testlerle kilitlenir. Akustik VAD/DSP ve
gerçek-ses gecikme ölçümü ses altyapısı gerektirir (bu modülün kapsamı dışında).

CLI: python -m app.voice.turn_taking
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Sequence

ARTIFACT_PATH = Path(__file__).resolve().parent / "data" / "turn_taking.json"


class TurnState(str, Enum):
    LISTENING = "listening"          # ajan sessiz, kullanıcı sırası bekleniyor
    USER_SPEAKING = "user_speaking"  # kullanıcı söz sırasında
    AGENT_SPEAKING = "agent_speaking"  # TTS çalıyor (barge-in izlenir)


class TurnEvent(str, Enum):
    USER_TURN_START = "user_turn_start"
    USER_TURN_END = "user_turn_end"      # endpoint saptandı (geçerli söylem)
    NOISE_IGNORED = "noise_ignored"      # sıra başladı ama söylem çok kısa
    BARGE_IN = "barge_in"                # kullanıcı ajanı kesti → TTS durdur
    AGENT_TURN_END = "agent_turn_end"    # ajan doğal bitirdi (kesinti yok)


@dataclass(frozen=True)
class TurnTakingConfig:
    frame_ms: int = 20          # VAD kare süresi
    onset_ms: int = 120         # sırayı başlatmak için gereken kesintisiz konuşma
    endpoint_ms: int = 600      # bitişi ilan eden iz-düşük sessizlik
    min_utterance_ms: int = 200 # bunun altındaki seslendirilmiş süre gürültü sayılır
    barge_in_ms: int = 200      # ajan konuşurken kesinti için gereken konuşma
    max_utterance_ms: int = 30000  # güvenlik tavanı

    def __post_init__(self) -> None:
        for name in ("frame_ms", "onset_ms", "endpoint_ms", "min_utterance_ms", "barge_in_ms", "max_utterance_ms"):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} pozitif olmalı")


class TurnTakingController:
    """VAD kare akışını konuşma-sırası olaylarına çeviren deterministik durum makinesi."""

    def __init__(self, config: TurnTakingConfig | None = None) -> None:
        self.cfg = config or TurnTakingConfig()
        self.state: TurnState = TurnState.LISTENING
        self.clock_ms: int = 0
        self._speech_run_ms: int = 0        # kesintisiz konuşma (onset/barge-in için)
        self._silence_run_ms: int = 0       # söylem içi iz-düşük sessizlik
        self._utterance_voiced_ms: int = 0  # söylemdeki seslendirilmiş toplam

    # ── Ajan (TTS) kontrolü ────────────────────────────────────────────────
    def agent_speaking_started(self) -> list[TurnEvent]:
        self.state = TurnState.AGENT_SPEAKING
        self._reset_runs()
        return []

    def agent_speaking_stopped(self) -> list[TurnEvent]:
        # Yalnızca ajan hâlâ konuşuyorken doğal bitiş sayılır; barge-in olduysa
        # zaten USER_SPEAKING'e geçilmiştir ve ajan-turu kesilmiştir.
        if self.state == TurnState.AGENT_SPEAKING:
            self.state = TurnState.LISTENING
            self._reset_runs()
            return [TurnEvent.AGENT_TURN_END]
        return []

    # ── VAD kare işleme ────────────────────────────────────────────────────
    def process_frame(self, is_speech: bool) -> list[TurnEvent]:
        self.clock_ms += self.cfg.frame_ms
        if self.state == TurnState.AGENT_SPEAKING:
            return self._on_agent_speaking(is_speech)
        if self.state == TurnState.LISTENING:
            return self._on_listening(is_speech)
        return self._on_user_speaking(is_speech)

    def process_stream(self, frames: Sequence[bool]) -> list[TurnEvent]:
        events: list[TurnEvent] = []
        for f in frames:
            events.extend(self.process_frame(f))
        return events

    # ── Durum işleyicileri ─────────────────────────────────────────────────
    def _on_listening(self, is_speech: bool) -> list[TurnEvent]:
        if is_speech:
            self._speech_run_ms += self.cfg.frame_ms
        else:
            self._speech_run_ms = 0
        if self._speech_run_ms >= self.cfg.onset_ms:
            self._begin_user_turn()
            return [TurnEvent.USER_TURN_START]
        return []

    def _on_agent_speaking(self, is_speech: bool) -> list[TurnEvent]:
        if is_speech:
            self._speech_run_ms += self.cfg.frame_ms
        else:
            self._speech_run_ms = 0
        if self._speech_run_ms >= self.cfg.barge_in_ms:
            self._begin_user_turn()
            return [TurnEvent.BARGE_IN]
        return []

    def _on_user_speaking(self, is_speech: bool) -> list[TurnEvent]:
        if is_speech:
            self._utterance_voiced_ms += self.cfg.frame_ms
            self._silence_run_ms = 0
        else:
            self._silence_run_ms += self.cfg.frame_ms

        total_ms = self._utterance_voiced_ms + self._silence_run_ms
        if self._silence_run_ms >= self.cfg.endpoint_ms:
            valid = self._utterance_voiced_ms >= self.cfg.min_utterance_ms
            self._reset_to_listening()
            return [TurnEvent.USER_TURN_END if valid else TurnEvent.NOISE_IGNORED]
        if total_ms >= self.cfg.max_utterance_ms:
            self._reset_to_listening()
            return [TurnEvent.USER_TURN_END]  # güvenlik: uzun söylemi zorla kapat
        return []

    # ── Yardımcılar ────────────────────────────────────────────────────────
    def _begin_user_turn(self) -> None:
        self.state = TurnState.USER_SPEAKING
        # Onset/barge-in sırasında biriken konuşma söylemin seslendirilmiş başıdır.
        self._utterance_voiced_ms = self._speech_run_ms
        self._silence_run_ms = 0
        self._speech_run_ms = 0

    def _reset_to_listening(self) -> None:
        self.state = TurnState.LISTENING
        self._reset_runs()

    def _reset_runs(self) -> None:
        self._speech_run_ms = 0
        self._silence_run_ms = 0
        self._utterance_voiced_ms = 0


# ── Deterministik senaryo + denetim panosu ──────────────────────────────────
def _frames(is_speech: bool, ms: int, frame_ms: int = 20) -> list[bool]:
    return [is_speech] * (ms // frame_ms)


def synthetic_events(cfg: TurnTakingConfig | None = None) -> list[TurnEvent]:
    """Tüm geçişleri tetikleyen betiklenmiş senaryo → olay dizisi."""
    cfg = cfg or TurnTakingConfig()
    fm = cfg.frame_ms
    c = TurnTakingController(cfg)
    ev: list[TurnEvent] = []

    # 1) Gerçek kullanıcı söylemi: 400 ms konuşma → 700 ms sessizlik (endpoint)
    ev += c.process_stream(_frames(True, 400, fm))
    ev += c.process_stream(_frames(False, 700, fm))

    # 2) Sıra başlatan ama çok kısa (160 ms) söylem → gürültü sayılır
    ev += c.process_stream(_frames(True, 160, fm))
    ev += c.process_stream(_frames(False, 700, fm))

    # 3) Salt gürültü patlaması (80 ms) → onset'i geçmez, hiç sıra başlamaz
    ev += c.process_stream(_frames(True, 80, fm))
    ev += c.process_stream(_frames(False, 200, fm))

    # 4) Ajan konuşurken kesinti (barge-in): 100 ms sessizlik + 300 ms konuşma
    ev += c.agent_speaking_started()
    ev += c.process_stream(_frames(False, 100, fm))
    ev += c.process_stream(_frames(True, 300, fm))     # barge-in
    ev += c.process_stream(_frames(False, 700, fm))    # sonra endpoint

    # 5) Ajan doğal bitiş (kesinti yok) → agent_turn_end
    ev += c.agent_speaking_started()
    ev += c.process_stream(_frames(False, 200, fm))
    ev += c.agent_speaking_stopped()

    return ev


def build_report(cfg: TurnTakingConfig | None = None) -> dict:
    cfg = cfg or TurnTakingConfig()
    events = synthetic_events(cfg)
    seen = [e.value for e in events]
    counts: dict[str, int] = {}
    for e in seen:
        counts[e] = counts.get(e, 0) + 1

    def has(ev: TurnEvent) -> bool:
        return ev in events

    gates = {
        "user_turn_detected": {"target": "geçerli söylemde start+end", "pass": has(TurnEvent.USER_TURN_START) and has(TurnEvent.USER_TURN_END)},
        "noise_rejected": {"target": "kısa söylem gürültü sayılır", "pass": has(TurnEvent.NOISE_IGNORED)},
        "barge_in_detected": {"target": "ajan konuşurken kesinti", "pass": has(TurnEvent.BARGE_IN)},
        "agent_turn_end_on_natural_stop": {"target": "kesintisiz bitişte agent_turn_end", "pass": has(TurnEvent.AGENT_TURN_END)},
    }
    report = {
        "name": "turn_taking_state_machine",
        "ip": "3.7",
        "config": {
            "frame_ms": cfg.frame_ms, "onset_ms": cfg.onset_ms, "endpoint_ms": cfg.endpoint_ms,
            "min_utterance_ms": cfg.min_utterance_ms, "barge_in_ms": cfg.barge_in_ms,
            "max_utterance_ms": cfg.max_utterance_ms,
        },
        "event_sequence": seen,
        "event_counts": dict(sorted(counts.items())),
        "gates": gates,
    }
    report["overall_pass"] = all(g["pass"] for g in gates.values())
    return report


def render(report: dict) -> str:
    ok = lambda b: "✅" if b else "❌"  # noqa: E731
    lines = [
        "İP-3.7 — Turn-taking + barge-in durum makinesi",
        "=" * 48,
        f"Olay dizisi ({len(report['event_sequence'])}):",
        "  " + " → ".join(report["event_sequence"]),
        "-" * 48,
    ]
    for g in report["gates"].values():
        lines.append(f"{ok(g['pass'])} {g['target']}")
    lines += ["=" * 48, f"{ok(report['overall_pass'])} GENEL: {'GEÇTİ' if report['overall_pass'] else 'KALDI'}"]
    return "\n".join(lines)


def write_artifact(report: dict, path: Path = ARTIFACT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="İP-3.7 turn-taking durum makinesi")
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
