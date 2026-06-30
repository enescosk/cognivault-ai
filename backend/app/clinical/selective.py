"""Çekimser tahmin / selective prediction katmanı — İP-1.6.

Triyaj yönlendiricisi (İP-1.4) + kalibre güven (İP-1.5) her zaman bir branş
tahmini üretir. Bu katman, tahminin **kabul edilip otomatik yönlendirileceğine**
mi yoksa **çekimser kalınıp insana yükseltileceğine** mi karar verir.

Çekimser kalma (abstain) tetikleyicileri — "düşük güven VEYA tutarsız kanıt":
  * NO_EVIDENCE       — hiçbir branş anahtarı eşleşmedi (genel diş'e düşüş).
                        Genel-amaçlı bir şikâyet de olabilir, kaçırılmış bir
                        branş da; router ayırt edemez → insan teyit etsin.
  * AMBIGUOUS_EVIDENCE— ilk iki branş eşit skorla yarışıyor (çelişkili kanıt).
  * LOW_CONFIDENCE    — kalibre güven (İP-1.5) risk-kontrollü eşiğin altında.

Eşik seçimi konformal (conformal) risk kontrolüdür: kalibrasyon kümesinde,
KABUL edilen tahminlerin ampirik hata oranı hedef riski (varsayılan 0,05)
aşmayacak en küçük güven eşiği seçilir (`fit_threshold`). Böylece otomatik
yönlendirilen vakalarda hata oranına üst sınır konur; gerisi insana gider.

NON-SaMD: Bu katman teşhis üretmez; yalnızca "bu vakayı otomatik mi
yönlendireyim yoksa hekime mi devredeyim" operasyonel kararını verir.

Saf Python, KVKK local-first: artefakt `data/selective.json` (denetlenebilir).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from enum import Enum
from functools import lru_cache
from pathlib import Path

from app.clinical.normalizer import TriageResult, triage
from app.clinical.ontology import rank_specialties

# Risk-kontrollü güven eşiğinin diske yazıldığı konum (selective_report.py üretir).
SELECTIVE_ARTIFACT = Path(__file__).resolve().parent / "data" / "selective.json"

# Konformal hedef risk: kabul edilen tahminlerde izin verilen azami hata oranı.
DEFAULT_TARGET_RISK = 0.05

# Artefakt yoksa kullanılacak temkinli varsayılan eşik. Kalibre güven [0,1]
# uzayındadır; yapısal kurallar (no-evidence/ambiguous) asıl güvenlik ağıdır.
DEFAULT_CONFIDENCE_THRESHOLD = 0.5


class AbstainReason(str, Enum):
    """Çekimser kalma (insana yükseltme) gerekçeleri — denetim izi için."""

    NO_EVIDENCE = "no_evidence"
    AMBIGUOUS_EVIDENCE = "ambiguous_evidence"
    LOW_CONFIDENCE = "low_confidence"


@dataclass(frozen=True)
class SelectiveDecision:
    """Bir şikâyetin çekimser-tahmin kararı.

    triage:          Altta yatan tam triyaj sonucu (branş + aciliyet + güven).
    accepted:        True → otomatik yönlendir; False → branş için insana yükselt.
    threshold:       Kullanılan kalibre-güven eşiği.
    abstain_reasons: Çekimser kalındıysa tetikleyen gerekçeler (boşsa kabul).
    """

    triage: TriageResult
    accepted: bool
    threshold: float
    abstain_reasons: tuple[str, ...] = field(default_factory=tuple)

    @property
    def specialty_code(self) -> str:
        return self.triage.specialty_code

    @property
    def confidence(self) -> float:
        return self.triage.confidence

    @property
    def escalate_to_human(self) -> bool:
        """Vaka insana gitmeli mi? Branş-çekimserliği VEYA aciliyet yükseltmesi.

        İki bağımsız yükseltme yolu birleşir: (1) bu katmanın branş-güven
        kararı, (2) aciliyet taksonomisinin (acil/öncelikli) zaten gerektirdiği
        insan yükseltmesi. İkisinden biri yeterli.
        """
        return (not self.accepted) or self.triage.requires_escalation


def _evidence_reasons(enriched_text: str, is_default: bool) -> list[str]:
    """Kanıt-yapısı temelli çekimser gerekçeleri (güven eşiğinden bağımsız)."""
    reasons: list[str] = []
    if is_default:
        reasons.append(AbstainReason.NO_EVIDENCE.value)
    ranked = rank_specialties(enriched_text)
    if len(ranked) >= 2 and ranked[0].match_count == ranked[1].match_count:
        reasons.append(AbstainReason.AMBIGUOUS_EVIDENCE.value)
    return reasons


def decide(text: str, *, threshold: float | None = None) -> SelectiveDecision:
    """Ham şikâyet metni için çekimser-tahmin kararı üretir.

    threshold verilmezse üretim artefaktı (data/selective.json) ya da temkinli
    varsayılan kullanılır.
    """
    if threshold is None:
        threshold = load_threshold()
    result = triage(text)

    reasons = _evidence_reasons(result.enriched_text, result.specialty.is_default)
    if result.confidence < threshold:
        reasons.append(AbstainReason.LOW_CONFIDENCE.value)

    # Sırayı koruyarak tekilleştir.
    deduped = tuple(dict.fromkeys(reasons))
    return SelectiveDecision(
        triage=result,
        accepted=not deduped,
        threshold=threshold,
        abstain_reasons=deduped,
    )


# ── Konformal risk-kontrollü eşik seçimi ─────────────────────────────────────


def fit_threshold(
    pairs: list[tuple[float, bool]], target_risk: float = DEFAULT_TARGET_RISK
) -> float:
    """Kabul edilen tahminlerde hata ≤ target_risk olacak en küçük güven eşiği.

    pairs: ``(kalibre_güven ∈ [0,1], tahmin_doğru_mu)`` ikilileri. Aday eşikler
    gözlenen güven değerleridir; her aday τ için {güven ≥ τ} alt kümesinin
    ampirik hatası hesaplanır. Hatayı target_risk altına indiren en küçük τ
    döner (kapsamı en yükseğe çıkarır). Hiçbir alt küme riski sağlamazsa
    tüm güvenlerin üstünde bir değer döner (her şeyi reddet — güvenli taraf).
    """
    if not pairs:
        return DEFAULT_CONFIDENCE_THRESHOLD

    candidates = sorted({c for c, _ in pairs})
    for tau in candidates:
        accepted = [ok for c, ok in pairs if c >= tau]
        if not accepted:
            continue
        # Tamsayı hata sayısıyla karşılaştır (kayan-nokta sınır kararsızlığından kaçın).
        errors = len(accepted) - sum(accepted)
        if errors <= target_risk * len(accepted) + 1e-9:
            return tau
    # Hiçbir eşik riski sağlamadı → en yüksek güvenin de üstü (hepsini reddet).
    return candidates[-1] + 1e-9


# ── Selektif metrikler (kapsam / selektif doğruluk / risk) ───────────────────


@dataclass(frozen=True)
class SelectiveMetrics:
    """Bir korpus üzerinde çekimser katmanın risk-kapsam özeti.

    total:             Toplam senaryo.
    accepted:          Otomatik yönlendirilen (kabul) senaryo sayısı.
    accepted_correct:  Kabul edilenlerden doğru branşa gidenler.
    coverage:          Kabul oranı (accepted / total).
    selective_accuracy:Kabul edilenlerde doğruluk (1 - selektif risk).
    """

    total: int
    accepted: int
    accepted_correct: int

    @property
    def coverage(self) -> float:
        return self.accepted / self.total if self.total else 0.0

    @property
    def selective_accuracy(self) -> float:
        return self.accepted_correct / self.accepted if self.accepted else 1.0

    @property
    def selective_risk(self) -> float:
        return 1.0 - self.selective_accuracy

    @property
    def abstained(self) -> int:
        return self.total - self.accepted


def evaluate_selective(
    items: list[tuple[str, str]], *, threshold: float
) -> SelectiveMetrics:
    """``(metin, gerçek_branş_kodu)`` listesinde çekimser katmanı ölçer."""
    accepted = 0
    accepted_correct = 0
    for text, truth in items:
        decision = decide(text, threshold=threshold)
        if decision.accepted:
            accepted += 1
            if decision.specialty_code == truth:
                accepted_correct += 1
    return SelectiveMetrics(
        total=len(items), accepted=accepted, accepted_correct=accepted_correct
    )


# ── Eşik artefaktı kalıcılığı ────────────────────────────────────────────────


def save_threshold(
    threshold: float, target_risk: float, path: Path = SELECTIVE_ARTIFACT
) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = {"confidence_threshold": threshold, "target_risk": target_risk}
    path.write_text(json.dumps(payload, indent=2), encoding="utf-8")


@lru_cache(maxsize=1)
def load_threshold(path: Path = SELECTIVE_ARTIFACT) -> float:
    """Üretim güven eşiğini yükler; artefakt yoksa temkinli varsayılan."""
    if not path.exists():
        return DEFAULT_CONFIDENCE_THRESHOLD
    data = json.loads(path.read_text(encoding="utf-8"))
    return float(data.get("confidence_threshold", DEFAULT_CONFIDENCE_THRESHOLD))
