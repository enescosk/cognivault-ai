"""Güven kalibrasyonu — İP-1.5.

Kural-tabanlı branş yönlendirici (`ontology.match_specialty`) ham olasılık
üretmez; bu modül eşleşme gücünden türetilen bir *ham güven sinyali* ile
isotonic regresyon kalibrasyonunu birleştirip [0,1] aralığında **kalibre
güven** üretir: kalibre güven değeri, o güven seviyesindeki gerçek doğruluk
oranına eşit olmaya çalışır (P(doğru | güven=p) ≈ p).

Başarı ölçütü (İP-1.5): Beklenen Kalibrasyon Hatası (ECE) < 0,05.

Saf Python — numpy/scikit-learn yok (KVKK local-first, minimal bağımlılık):
  * ECE      → standart eşit-genişlikli binleme.
  * Isotonic → Pool-Adjacent-Violators (PAV) algoritması, adım fonksiyonu.
  * Kalıcılık → JSON (pickle/sklearn artefaktı yok; denetlenebilir, taşınabilir).
"""

from __future__ import annotations

import json
from bisect import bisect_right
from dataclasses import dataclass
from pathlib import Path

from app.clinical.ontology import rank_specialties

# Kalibratörün diske yazıldığı varsayılan konum (calibrate.py üretir).
CALIBRATION_ARTIFACT = Path(__file__).resolve().parent / "data" / "calibration.json"


# ── Ham güven sinyali ────────────────────────────────────────────────────────


def raw_confidence_signal(text: str) -> float:
    """Eşleşme gücünden monotonik ham güven sinyali türetir ([0, ∞)).

    Not: argo terimler (örn. "apse") ancak normalizer genişletmesinden sonra
    ontolojiye eşlenir; bu yüzden bu fonksiyon **zenginleştirilmiş metinle**
    çağrılmalıdır (triage() öyle yapar). Ham argo metin 0.0 verebilir.

    Sinyalin tek şartı P(doğru) ile *monotonik* ilişkili olması (isotonic
    kalibrasyon mutlak değeri değil sıralamayı kullanır). Bileşenler:

      * Hiç anahtar kelime eşleşmezse (genel diş'e düşüş) → ``0.0``: bunlar en
        riskli, en düşük güvenli tahminlerdir.
      * Aksi halde en iyi branşın eşleşme sayısı (doygunlukla, 3'te tavan) +
        en yakın rakibe olan **marj**. İki branş eşit eşleşirse (belirsizlik)
        marj 0 olur ve sinyal düşer; tek-anlamlı güçlü eşleşme yüksek çıkar.
    """
    ranked = rank_specialties(text)
    if not ranked:
        return 0.0
    top = ranked[0].match_count
    second = ranked[1].match_count if len(ranked) > 1 else 0
    margin = top - second
    return float(min(top, 3)) + float(margin)


# ── Beklenen Kalibrasyon Hatası (ECE) ────────────────────────────────────────


def expected_calibration_error(
    pairs: list[tuple[float, bool]], n_bins: int = 10
) -> float:
    """Beklenen Kalibrasyon Hatası (ECE).

    pairs: ``(kalibre_güven ∈ [0,1], doğru_mu)`` ikilileri. Güvenler
    eşit-genişlikli ``n_bins`` bine ayrılır; her binde tahmin güveni ile
    gözlenen doğruluk arasındaki mutlak fark, bindeki örnek payıyla ağırlıklı
    olarak toplanır:  ``ECE = Σ_b (|b|/N) · |acc(b) − conf(b)|``.
    """
    if not pairs:
        return 0.0
    bins: list[list[tuple[float, bool]]] = [[] for _ in range(n_bins)]
    for conf, correct in pairs:
        idx = min(int(conf * n_bins), n_bins - 1)  # conf == 1.0 → son bin
        bins[idx].append((conf, correct))
    n = len(pairs)
    ece = 0.0
    for b in bins:
        if not b:
            continue
        avg_conf = sum(c for c, _ in b) / len(b)
        accuracy = sum(1 for _, ok in b if ok) / len(b)
        ece += (len(b) / n) * abs(accuracy - avg_conf)
    return ece


# ── Isotonic regresyon kalibratörü (Pool-Adjacent-Violators) ─────────────────


@dataclass
class IsotonicCalibrator:
    """Saf Python isotonic regresyon kalibratörü (monotonik-azalmayan adım).

    Ham (monotonik) güven sinyalini [0,1] kalibre olasılığa eşler. ``fit``
    aynı ham skorları havuzlar, PAV ile monotonik-azalmayan blok ortalamaları
    öğrenir; ``predict`` sorgu skorunu içeren bloğun değerini döndürür
    (uçlarda kırpar). JSON'a serileştirilebilir.

    thresholds: Blokların artan alt sınırları (ham skor uzayında).
    values:     Karşılık gelen kalibre olasılıklar (monotonik azalmayan, [0,1]).
    """

    thresholds: list[float]
    values: list[float]

    @classmethod
    def fit(cls, pairs: list[tuple[float, bool]]) -> "IsotonicCalibrator":
        """(ham_skor, doğru_mu) ikililerinden isotonic eşlemeyi öğrenir."""
        if not pairs:
            return cls(thresholds=[0.0], values=[0.0])

        # 1) Aynı ham skoru olan örnekleri birleştir (ağırlıklı ortalama doğruluk).
        agg: dict[float, list[int]] = {}  # ham_skor -> [doğru_sayısı, toplam]
        for raw, correct in pairs:
            slot = agg.setdefault(raw, [0, 0])
            slot[0] += 1 if correct else 0
            slot[1] += 1

        # 2) Artan ham skora göre PAV: ardışık azalan blokları havuzla.
        lowers: list[float] = []  # blok alt sınırı (bloktaki en küçük ham skor)
        vals: list[float] = []    # blok ortalama doğruluğu
        weights: list[float] = []  # blok ağırlığı (örnek sayısı)
        for raw in sorted(agg):
            hits, total = agg[raw]
            lowers.append(raw)
            vals.append(hits / total)
            weights.append(float(total))
            while len(vals) >= 2 and vals[-2] > vals[-1]:
                w = weights[-2] + weights[-1]
                merged = (vals[-2] * weights[-2] + vals[-1] * weights[-1]) / w
                vals[-2:] = [merged]
                weights[-2:] = [w]
                lowers[-2:] = [lowers[-2]]  # birleşik blok alt sınırı = küçük olan
        return cls(thresholds=lowers, values=vals)

    def predict_one(self, raw: float) -> float:
        """Tek ham skoru kalibre olasılığa çevirir."""
        idx = bisect_right(self.thresholds, raw) - 1
        if idx < 0:
            idx = 0  # ilk eşikten küçük → en düşük blok
        return self.values[idx]

    def predict(self, raws: list[float]) -> list[float]:
        return [self.predict_one(r) for r in raws]

    # ── Kalıcılık ────────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        return {"thresholds": self.thresholds, "values": self.values}

    @classmethod
    def from_dict(cls, data: dict) -> "IsotonicCalibrator":
        return cls(thresholds=list(data["thresholds"]), values=list(data["values"]))

    def save(self, path: Path = CALIBRATION_ARTIFACT) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(self.to_dict(), indent=2), encoding="utf-8")

    @classmethod
    def load(cls, path: Path = CALIBRATION_ARTIFACT) -> "IsotonicCalibrator | None":
        if not path.exists():
            return None
        return cls.from_dict(json.loads(path.read_text(encoding="utf-8")))
