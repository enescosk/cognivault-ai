"""İP-1.8 — Konsolide kalibrasyon/metrik panosu (ECE · recall · branş doğruluğu).

İP-1.4–1.7'de üretilen tekil metrik üreticilerini tek bir denetlenebilir panoda
toplar. Hiçbir metriği yeniden hesaplamaz; mevcut public fonksiyonları orkestre
eder ve tek bir JSON-hazır sözlük üretir:

  * Branş yönlendirme doğruluğu   (`evaluate.py`)
  * Güven kalibrasyonu — ECE       (`calibrate.py` + `calibration.py`)
  * Acil-recall kapsaması          (`emergency_report.py`)
  * Çekimser tahmin risk-kapsamı   (`selective.py`)

Her metrik bloğu kendi **hedefini** ve **pass** bayrağını taşır; `overall_pass`
hepsinin VE'sidir. Artefakt `data/metrics_report.json`'a yazılır — deterministik
(duvar-saati zaman damgası yok), böylece git'te diff'lenebilir ve denetlenebilir.

Saf Python, KVKK local-first (numpy/sklearn yok); sentetik/anonim korpus.

Çalıştırma:
    python -m app.clinical.report             # pano + artefakt kaydet
    python -m app.clinical.report --no-save   # sadece raporla, yazma yok
    python -m app.clinical.report --json      # JSON'u stdout'a bas
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.clinical.calibrate import SEED, TRAIN_FRACTION, build_pairs, split
from app.clinical.calibration import IsotonicCalibrator, expected_calibration_error
from app.clinical.emergency_report import CORPUS_FILES, evaluate_recall
from app.clinical.evaluate import evaluate_file
from app.clinical.corpus.schema import corpus_data_dir, load_corpus
from app.clinical.selective import evaluate_selective, load_threshold

# Konsolide panonun yazıldığı denetim artefaktı.
METRICS_ARTIFACT = Path(__file__).resolve().parent / "data" / "metrics_report.json"

SYNTHETIC_FILE = "dental_tr.jsonl"
GOLDEN_FILE = "golden.jsonl"

# Pano kabul hedefleri (İP-1 başarı ölçütleri, tek kaynak).
SPECIALTY_ACCURACY_TARGET = 0.90  # sentetik branş doğruluğu (İP-1.4)
ECE_TARGET = 0.05                 # TEST seti kalibrasyon hatası (İP-1.5)
SELECTIVE_RISK_TARGET = 0.05      # kabul edilenlerde azami risk (İP-1.6)
EMERGENCY_RECALL_TARGET = 1.0     # kaçan acil = 0 (İP-1.7)


def _specialty_block() -> dict:
    """Branş yönlendirme doğruluğu — sentetik (kapı) + golden (teşhis)."""
    synth = evaluate_file(corpus_data_dir() / SYNTHETIC_FILE)
    golden = evaluate_file(corpus_data_dir() / GOLDEN_FILE)
    return {
        "target": SPECIALTY_ACCURACY_TARGET,
        "synthetic": {
            "accuracy": synth.accuracy,
            "correct": synth.correct,
            "total": synth.total,
            "per_specialty": {
                code: {"accuracy": s.accuracy, "correct": s.correct, "total": s.total}
                for code, s in synth.per_specialty.items()
            },
            "top_confusions": [
                {"truth": gt, "predicted": pred, "count": count}
                for (gt, pred), count in synth.confusion.most_common(8)
            ],
        },
        "golden": {
            "accuracy": golden.accuracy,
            "correct": golden.correct,
            "total": golden.total,
        },
        "pass": synth.accuracy >= SPECIALTY_ACCURACY_TARGET,
    }


def _calibration_block() -> dict:
    """Güven kalibrasyonu ECE — sızıntısız train/test bölmesiyle (İP-1.5)."""
    pairs = build_pairs(SYNTHETIC_FILE)
    train, test = split(pairs)
    calibrator = IsotonicCalibrator.fit(train)

    test_calibrated = [(calibrator.predict_one(r), ok) for r, ok in test]
    max_raw = max((r for r, _ in pairs), default=1.0) or 1.0
    test_naive = [(min(r / max_raw, 1.0), ok) for r, ok in test]

    golden_pairs = build_pairs(GOLDEN_FILE)
    golden_calibrated = [(calibrator.predict_one(r), ok) for r, ok in golden_pairs]

    ece_after = expected_calibration_error(test_calibrated)
    return {
        "target": ECE_TARGET,
        "seed": SEED,
        "train_fraction": TRAIN_FRACTION,
        "train_n": len(train),
        "test_n": len(test),
        "test_ece": ece_after,
        "test_ece_naive": expected_calibration_error(test_naive),
        "golden_ece": expected_calibration_error(golden_calibrated),
        "pass": ece_after < ECE_TARGET,
    }


def _emergency_block() -> dict:
    """Acil-recall kapsaması — tüm korpus dosyaları (İP-1.7)."""
    per_file: list[dict] = []
    tot_emg = tot_detected = tot_fp = tot_non = 0
    for fname in CORPUS_FILES:
        rep = evaluate_recall(load_corpus(corpus_data_dir() / fname), fname)
        tot_emg += rep.emergencies
        tot_detected += rep.detected
        tot_fp += rep.false_positives
        tot_non += rep.non_emergencies
        per_file.append({
            "name": fname,
            "emergencies": rep.emergencies,
            "detected": rep.detected,
            "recall": rep.recall,
            "false_positives": rep.false_positives,
            "non_emergencies": rep.non_emergencies,
            "false_positive_rate": rep.false_positive_rate,
            "missed": [m.text for m in rep.missed],
        })
    recall = tot_detected / tot_emg if tot_emg else 1.0
    return {
        "target": EMERGENCY_RECALL_TARGET,
        "emergencies": tot_emg,
        "detected": tot_detected,
        "missed": tot_emg - tot_detected,
        "recall": recall,
        "false_positives": tot_fp,
        "false_positive_rate": tot_fp / tot_non if tot_non else 0.0,
        "per_file": per_file,
        "pass": tot_detected == tot_emg,
    }


def _selective_block() -> dict:
    """Çekimser tahmin risk-kapsamı — üretim eşiğiyle (İP-1.6)."""
    threshold = load_threshold()
    synth = [(e.text, e.specialty_code) for e in load_corpus(corpus_data_dir() / SYNTHETIC_FILE)]
    golden = [(e.text, e.specialty_code) for e in load_corpus(corpus_data_dir() / GOLDEN_FILE)]
    synth_m = evaluate_selective(synth, threshold=threshold)
    golden_m = evaluate_selective(golden, threshold=threshold)

    def _m(m) -> dict:
        return {
            "total": m.total,
            "accepted": m.accepted,
            "abstained": m.abstained,
            "coverage": m.coverage,
            "selective_accuracy": m.selective_accuracy,
            "selective_risk": m.selective_risk,
        }

    return {
        "target_risk": SELECTIVE_RISK_TARGET,
        "threshold": threshold,
        "synthetic": _m(synth_m),
        "golden": _m(golden_m),
        "pass": synth_m.selective_risk <= SELECTIVE_RISK_TARGET,
    }


def overall_pass(metrics: dict) -> bool:
    """Genel kapı: her metrik bloğunun ``pass`` bayrağının VE'si.

    Korpustan bağımsız saf fonksiyon — bir hedef bile karşılanmazsa pano
    bütün olarak başarısızdır. Bu ayrıklık, kapı mantığının gerçek veriye
    ihtiyaç duymadan (sentetik başarısız blokla) test edilmesini sağlar.
    """
    return all(block["pass"] for block in metrics.values())


def build_dashboard() -> dict:
    """Dört metrik üreticisini tek JSON-hazır panoda toplar.

    Dönen sözlük tamamen serileştirilebilir (tuple/Counter yok) ve
    deterministiktir — aynı korpus + artefaktlarla aynı çıktıyı verir.
    """
    metrics = {
        "specialty_accuracy": _specialty_block(),
        "calibration_ece": _calibration_block(),
        "emergency_recall": _emergency_block(),
        "selective": _selective_block(),
    }
    return {
        "ip": "1.8",
        "title": "CogniVault Türkçe Diş Triyaj — Kalibrasyon/Metrik Panosu",
        "corpus": {
            "synthetic": SYNTHETIC_FILE,
            "golden": GOLDEN_FILE,
            "emergency_files": list(CORPUS_FILES),
        },
        "metrics": metrics,
        "overall_pass": overall_pass(metrics),
    }


def render(dashboard: dict) -> str:
    """Panoyu okunabilir konsol metnine çevirir (diğer raporların stilinde)."""
    def gate(ok: bool) -> str:
        return "✅" if ok else "❌"

    sp = dashboard["metrics"]["specialty_accuracy"]
    cal = dashboard["metrics"]["calibration_ece"]
    emg = dashboard["metrics"]["emergency_recall"]
    sel = dashboard["metrics"]["selective"]

    lines = [
        "=" * 72,
        "İP-1.8 — Konsolide Kalibrasyon/Metrik Panosu",
        "=" * 72,
        "",
        f"{gate(sp['pass'])} Branş doğruluğu (sentetik): "
        f"{sp['synthetic']['accuracy'] * 100:.1f}% "
        f"({sp['synthetic']['correct']}/{sp['synthetic']['total']}) "
        f"· hedef ≥{sp['target'] * 100:.0f}%  "
        f"| golden {sp['golden']['accuracy'] * 100:.1f}% "
        f"({sp['golden']['correct']}/{sp['golden']['total']}, teşhis)",
        "",
        f"{gate(cal['pass'])} Kalibrasyon ECE (TEST, isotonic): "
        f"{cal['test_ece']:.4f} · hedef <{cal['target']}  "
        f"| naif {cal['test_ece_naive']:.4f} "
        f"| golden {cal['golden_ece']:.4f}  "
        f"(train {cal['train_n']}/test {cal['test_n']}, tohum={cal['seed']})",
        "",
        f"{gate(emg['pass'])} Acil-recall (3 korpus): "
        f"{emg['detected']}/{emg['emergencies']} = {emg['recall'] * 100:.1f}% "
        f"· kaçan {emg['missed']} · hedef recall {emg['target'] * 100:.0f}%  "
        f"| yanlış-pozitif {emg['false_positive_rate'] * 100:.1f}%",
        "",
        f"{gate(sel['pass'])} Selektif risk (sentetik, kabul edilenler): "
        f"{sel['synthetic']['selective_risk'] * 100:.1f}% · hedef ≤{sel['target_risk'] * 100:.0f}%  "
        f"| kapsam {sel['synthetic']['coverage'] * 100:.1f}% "
        f"({sel['synthetic']['accepted']}/{sel['synthetic']['total']}) "
        f"· eşik {sel['threshold']:.4f}",
        f"   golden: selektif doğruluk {sel['golden']['selective_accuracy'] * 100:.1f}% "
        f"· kapsam {sel['golden']['coverage'] * 100:.1f}% "
        f"({sel['golden']['accepted']}/{sel['golden']['total']})",
        "",
        "-" * 72,
        f"{gate(dashboard['overall_pass'])} GENEL: "
        + ("tüm hedefler karşılandı" if dashboard["overall_pass"] else "bir veya daha fazla hedef karşılanmadı"),
    ]
    return "\n".join(lines)


def save_dashboard(dashboard: dict, path: Path = METRICS_ARTIFACT) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(dashboard, indent=2, ensure_ascii=False), encoding="utf-8"
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="İP-1.8 konsolide metrik panosu")
    parser.add_argument("--no-save", action="store_true", help="Artefaktı yazma, sadece raporla")
    parser.add_argument("--json", action="store_true", help="JSON'u stdout'a bas")
    args = parser.parse_args()

    dashboard = build_dashboard()

    if args.json:
        print(json.dumps(dashboard, indent=2, ensure_ascii=False))
    else:
        print(render(dashboard))

    if not args.no_save:
        save_dashboard(dashboard)
        print(f"\n💾 Metrik panosu kaydedildi: {METRICS_ARTIFACT}")


if __name__ == "__main__":
    main()
