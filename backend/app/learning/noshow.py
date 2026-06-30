"""İP-4.5 — No-show / süreklilik risk modeli (hedef AUC ≥ 0,75).

Randevuya gelmeme olasılığını hasta/randevu özelliklerinden tahmin eden saf-Python
lojistik regresyon (numpy/sklearn yok — KVKK local-first, minimal bağımlılık).
Öngörücü geri-çağırma (İP-4.7) ve dinamik slot önerisi (İP-4.6) bu riski tüketir.

Determinizm: sentetik veri sabit tohumla üretilir; eğitim (sıfır başlangıç, sabit
epoch) deterministiktir → AUC ve katsayılar yeniden üretilebilir (artefakt donar).

CLI: python -m app.learning.noshow
"""

from __future__ import annotations

import json
import math
import random
from dataclasses import dataclass, field
from pathlib import Path
from typing import Sequence

AUC_TARGET = 0.75
ARTIFACT_PATH = Path(__file__).resolve().parent / "data" / "noshow.json"

# Özellik sırası (vektörleştirme bu sıraya göre sabit).
FEATURES = [
    "lead_time_days",     # rezervasyon ile randevu arası gün (uzun → risk ↑)
    "prior_no_shows",     # geçmiş gelmeme sayısı (güçlü → risk ↑)
    "prior_completed",    # geçmiş tamamlanan randevu (sadakat → risk ↓)
    "reminder_sent",      # hatırlatma gönderildi mi (0/1 → risk ↓)
    "is_first_visit",     # ilk ziyaret mi (0/1 → risk ↑)
    "days_since_last",    # son ziyaretten beri gün (kopukluk → risk ↑)
    "age",                # yaş (zayıf sinyal)
    "slot_hour",          # randevu saati 8–18 (zayıf sinyal)
]


@dataclass(frozen=True)
class NoShowModel:
    """Eğitilmiş model — ham özellik sözlüğünden risk olasılığı üretir."""
    feature_order: list[str]
    means: list[float]
    stds: list[float]
    weights: list[float]
    bias: float

    def risk_score(self, features: dict[str, float]) -> float:
        x = _vectorize(features, self.feature_order)
        z = self.bias
        for i, v in enumerate(x):
            std = self.stds[i] or 1.0
            z += self.weights[i] * ((v - self.means[i]) / std)
        return _sigmoid(z)

    def as_dict(self) -> dict:
        return {
            "feature_order": self.feature_order,
            "means": [round(m, 4) for m in self.means],
            "stds": [round(s, 4) for s in self.stds],
            "weights": [round(w, 4) for w in self.weights],
            "bias": round(self.bias, 4),
        }


def _sigmoid(z: float) -> float:
    if z >= 0:
        ez = math.exp(-z)
        return 1.0 / (1.0 + ez)
    ez = math.exp(z)
    return ez / (1.0 + ez)


def _vectorize(features: dict[str, float], order: Sequence[str]) -> list[float]:
    return [float(features.get(name, 0.0)) for name in order]


# ── Sentetik veri (deterministik, bilinen sinyal) ───────────────────────────
def synthetic_dataset(n: int = 1600, seed: int = 7) -> list[tuple[dict, int]]:
    """Gerçekçi dağılımlı, etiketi gizli bir logit'ten örneklenmiş randevu seti."""
    rng = random.Random(seed)
    data: list[tuple[dict, int]] = []
    for _ in range(n):
        prior_completed = rng.randint(0, 12)
        prior_no_shows = rng.randint(0, min(5, prior_completed + 2))
        is_first = 1 if prior_completed == 0 and rng.random() < 0.7 else 0
        feats = {
            "lead_time_days": rng.randint(0, 30),
            "prior_no_shows": prior_no_shows,
            "prior_completed": prior_completed,
            "reminder_sent": 1 if rng.random() < 0.6 else 0,
            "is_first_visit": is_first,
            "days_since_last": 0 if is_first else rng.randint(0, 365),
            "age": rng.randint(18, 78),
            "slot_hour": rng.randint(8, 18),
        }
        # Gizli risk (gerçek-dünya yön/şiddetine yakın katsayılar):
        logit = (
            -2.6
            + 0.05 * (feats["lead_time_days"] - 10)
            + 0.85 * feats["prior_no_shows"]
            - 0.13 * feats["prior_completed"]
            - 0.9 * feats["reminder_sent"]
            + 0.7 * feats["is_first_visit"]
            + 0.002 * feats["days_since_last"]
        )
        p = _sigmoid(logit)
        label = 1 if rng.random() < p else 0
        data.append((feats, label))
    return data


def train_test_split(data: list, frac: float = 0.7, seed: int = 13) -> tuple[list, list]:
    rng = random.Random(seed)
    idx = list(range(len(data)))
    rng.shuffle(idx)
    cut = int(len(data) * frac)
    train = [data[i] for i in idx[:cut]]
    test = [data[i] for i in idx[cut:]]
    return train, test


# ── Lojistik regresyon (saf Python, standardize + GD) ───────────────────────
def _standardize_params(rows: list[list[float]]) -> tuple[list[float], list[float]]:
    m = len(rows[0])
    means = [0.0] * m
    for r in rows:
        for j in range(m):
            means[j] += r[j]
    means = [v / len(rows) for v in means]
    stds = [0.0] * m
    for r in rows:
        for j in range(m):
            stds[j] += (r[j] - means[j]) ** 2
    stds = [math.sqrt(v / len(rows)) or 1.0 for v in stds]
    stds = [s if s > 1e-9 else 1.0 for s in stds]
    return means, stds


def train_logreg(
    data: list[tuple[dict, int]],
    feature_order: Sequence[str] = FEATURES,
    epochs: int = 400,
    lr: float = 0.3,
    l2: float = 1e-4,
) -> NoShowModel:
    X = [_vectorize(f, feature_order) for f, _ in data]
    y = [lbl for _, lbl in data]
    means, stds = _standardize_params(X)
    Xs = [[(row[j] - means[j]) / stds[j] for j in range(len(row))] for row in X]

    m = len(feature_order)
    w = [0.0] * m
    b = 0.0
    n = len(Xs)
    for _ in range(epochs):
        gw = [0.0] * m
        gb = 0.0
        for i in range(n):
            z = b + sum(w[j] * Xs[i][j] for j in range(m))
            err = _sigmoid(z) - y[i]
            for j in range(m):
                gw[j] += err * Xs[i][j]
            gb += err
        for j in range(m):
            w[j] -= lr * (gw[j] / n + l2 * w[j])
        b -= lr * (gb / n)
    return NoShowModel(list(feature_order), means, stds, w, b)


def auc_score(y_true: Sequence[int], scores: Sequence[float]) -> float:
    """Rank-temelli AUC (Mann-Whitney U); bağları ortalama rank ile çözer."""
    n_pos = sum(1 for v in y_true if v == 1)
    n_neg = len(y_true) - n_pos
    if n_pos == 0 or n_neg == 0:
        return 0.5
    order = sorted(range(len(scores)), key=lambda i: scores[i])
    ranks = [0.0] * len(scores)
    i = 0
    while i < len(order):
        j = i
        while j < len(order) and scores[order[j]] == scores[order[i]]:
            j += 1
        avg = (i + 1 + j) / 2.0
        for k in range(i, j):
            ranks[order[k]] = avg
        i = j
    sum_pos = sum(ranks[i] for i in range(len(y_true)) if y_true[i] == 1)
    return (sum_pos - n_pos * (n_pos + 1) / 2.0) / (n_pos * n_neg)


def train_and_evaluate(data: list[tuple[dict, int]] | None = None) -> dict:
    if data is None:
        data = synthetic_dataset()
    train, test = train_test_split(data)
    model = train_logreg(train)

    def eval_split(split):
        y = [lbl for _, lbl in split]
        s = [model.risk_score(f) for f, _ in split]
        return round(auc_score(y, s), 4), y

    auc_train, _ = eval_split(train)
    auc_test, ytest = eval_split(test)
    return {
        "model": model,
        "auc_train": auc_train,
        "auc_test": auc_test,
        "n_train": len(train),
        "n_test": len(test),
        "no_show_rate": round(sum(lbl for _, lbl in data) / len(data), 4),
    }


def build_report(data: list[tuple[dict, int]] | None = None) -> dict:
    res = train_and_evaluate(data)
    model: NoShowModel = res["model"]
    passed = res["auc_test"] >= AUC_TARGET
    coeff = {name: round(w, 4) for name, w in zip(model.feature_order, model.weights)}
    report = {
        "name": "no_show_risk_model",
        "ip": "4.5",
        "metrics": {
            "auc_test": res["auc_test"],
            "auc_train": res["auc_train"],
            "n_train": res["n_train"],
            "n_test": res["n_test"],
            "no_show_rate": res["no_show_rate"],
        },
        "model": model.as_dict(),
        "standardized_coefficients": dict(sorted(coeff.items())),
        "gates": {
            "auc_target": {
                "auc_test": res["auc_test"],
                "target": f"AUC ≥ {AUC_TARGET}",
                "pass": passed,
            },
        },
        "overall_pass": bool(passed),
    }
    return report


def render(report: dict) -> str:
    mtr = report["metrics"]
    g = report["gates"]["auc_target"]
    ok = "✅" if report["overall_pass"] else "❌"
    # En güçlü 3 sürücü
    drivers = sorted(report["standardized_coefficients"].items(), key=lambda kv: -abs(kv[1]))[:3]
    return "\n".join([
        "İP-4.5 — No-show risk modeli (lojistik regresyon)",
        "=" * 50,
        f"Eğitim/Test       : {mtr['n_train']} / {mtr['n_test']}",
        f"No-show oranı     : {mtr['no_show_rate']:.4f}",
        f"AUC (test)        : {mtr['auc_test']:.4f}   (eğitim {mtr['auc_train']:.4f})",
        f"En güçlü sürücüler: " + ", ".join(f"{k}={v:+.2f}" for k, v in drivers),
        "-" * 50,
        f"{ok} AUC kapısı: {g['auc_test']:.4f}  (hedef ≥ {AUC_TARGET})",
        "=" * 50,
        f"{ok} GENEL: {'GEÇTİ' if report['overall_pass'] else 'KALDI'}",
    ])


def write_artifact(report: dict, path: Path = ARTIFACT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def main(argv: list[str] | None = None) -> int:
    import argparse

    parser = argparse.ArgumentParser(description="İP-4.5 no-show risk modeli")
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
