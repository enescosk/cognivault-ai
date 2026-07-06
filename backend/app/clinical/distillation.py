"""İP-3.6 — Kucuk on-prem model icin distillation veri paketi.

Bu modul gercek fine-tune kosumu degildir; onu baslatmadan once gereken
deterministik, PII-temiz, sozlesmeli egitim paketini uretir. Cikti serbest
klinik yanit degil, yalnizca denetlenebilir JSON etiketleridir:

    specialty_code, urgency, channel

Golden set egitime karistirilmaz; yalnizca test/eval split'i olarak tutulur.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path

from app.clinical.corpus.schema import CorpusEntry, corpus_data_dir, load_corpus, scan_pii
from app.clinical.normalizer import triage
from app.clinical.ontology import SPECIALTY_BY_CODE, UrgencyLevel


ARTIFACT_PATH = Path(__file__).resolve().parent / "data" / "distillation_report.json"
DATASET_PATH = Path(__file__).resolve().parent / "data" / "distillation_dataset.jsonl"
EVAL_INPUT_PATH = Path(__file__).resolve().parent / "data" / "distillation_eval_inputs.jsonl"
TRAIN_FRACTION = 0.8
MIN_TRAIN_EXAMPLES = 400
MIN_VALIDATION_SPECIALTY_BASELINE = 0.90
EVAL_SPLITS = ("validation", "test")
EMERGENCY_URGENCY = "emergency"
# İP-1.7 deterministik motor acil-korpusta %100 recall kanıtladı (76/76, kaçan acil 0).
# Herhangi bir fine-tune edilmiş modelin bu sıfır-tolerans çıtasının altına düşmesi
# (bkz. 2026-07-06 naif fine-tune regresyonu: %26,7 recall) yaşam-güvenliği ihlalidir —
# bu yüzden emergency recall, genel exact-match'ten AYRI ve YUMUŞATILAMAZ bir kapıdır.
EMERGENCY_RECALL_MIN = 1.0


@dataclass(frozen=True)
class DistillationExample:
    id: str
    split: str
    input_text: str
    output_json: dict
    source: str

    def to_dict(self) -> dict:
        return asdict(self)

    @property
    def prompt_text(self) -> str:
        return f"Kanal: {self.output_json['channel']}\nHasta mesajı: {self.input_text}"

    def to_training_record(self) -> dict:
        """OpenAI-compatible/local SFT runtimes icin dar kontratli JSONL kaydi."""
        return {
            "id": self.id,
            "split": self.split,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Sen Turkce dis klinigi triyaj etiketleyicisisin. "
                        "Yalniz gecerli JSON dondur: specialty_code, urgency, channel."
                    ),
                },
                {"role": "user", "content": self.prompt_text},
                {
                    "role": "assistant",
                    "content": json.dumps(self.output_json, ensure_ascii=False, sort_keys=True),
                },
            ],
            "metadata": {
                "source": self.source,
                "label_schema": "triage_labels_v1",
            },
        }

    def to_inference_record(self) -> dict:
        """Validation/test icin etiketsiz inference girdisi."""
        return {
            "id": self.id,
            "split": self.split,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Sen Turkce dis klinigi triyaj etiketleyicisisin. "
                        "Yalniz gecerli JSON dondur: specialty_code, urgency, channel."
                    ),
                },
                {"role": "user", "content": self.prompt_text},
            ],
            "metadata": {
                "label_schema": "triage_labels_v1",
            },
        }


def _example(entry: CorpusEntry, split: str) -> DistillationExample:
    return DistillationExample(
        id=f"distill-{entry.id}",
        split=split,
        input_text=entry.text,
        output_json={
            "specialty_code": entry.specialty_code,
            "urgency": entry.urgency,
            "channel": entry.channel,
        },
        source=entry.source,
    )


def build_examples() -> list[DistillationExample]:
    """Sentetik train/validation + golden test orneklerini deterministik kurar."""
    synthetic = sorted(load_corpus(corpus_data_dir() / "dental_tr.jsonl"), key=lambda e: e.id)
    golden = sorted(load_corpus(corpus_data_dir() / "golden.jsonl"), key=lambda e: e.id)
    train_cut = int(len(synthetic) * TRAIN_FRACTION)
    examples: list[DistillationExample] = []
    examples.extend(_example(entry, "train") for entry in synthetic[:train_cut])
    examples.extend(_example(entry, "validation") for entry in synthetic[train_cut:])
    examples.extend(_example(entry, "test") for entry in golden)
    return examples


def _split_counts(examples: list[DistillationExample]) -> dict[str, int]:
    return {
        split: sum(1 for ex in examples if ex.split == split)
        for split in ("train", "validation", "test")
    }


def _coverage(examples: list[DistillationExample]) -> dict:
    return {
        "specialties": sorted({ex.output_json["specialty_code"] for ex in examples}),
        "urgencies": sorted({ex.output_json["urgency"] for ex in examples}),
        "channels": sorted({ex.output_json["channel"] for ex in examples}),
    }


def _ids_by_split(examples: list[DistillationExample]) -> dict[str, set[str]]:
    return {
        split: {ex.id for ex in examples if ex.split == split}
        for split in ("train", "validation", "test")
    }


def _output_contract_ok(examples: list[DistillationExample]) -> bool:
    allowed_keys = {"specialty_code", "urgency", "channel"}
    valid_urgencies = {level.value for level in UrgencyLevel}
    for ex in examples:
        output = ex.output_json
        if set(output) != allowed_keys:
            return False
        if output["specialty_code"] not in SPECIALTY_BY_CODE:
            return False
        if output["urgency"] not in valid_urgencies:
            return False
        if not isinstance(output["channel"], str) or not output["channel"]:
            return False
    return True


def _training_record_contract_ok(examples: list[DistillationExample]) -> bool:
    for ex in examples:
        record = ex.to_training_record()
        if set(record) != {"id", "split", "messages", "metadata"}:
            return False
        if record["id"] != ex.id or record["split"] != ex.split:
            return False
        messages = record["messages"]
        if [m.get("role") for m in messages] != ["system", "user", "assistant"]:
            return False
        if messages[1]["content"] != ex.prompt_text:
            return False
        try:
            parsed_output = json.loads(messages[-1]["content"])
        except json.JSONDecodeError:
            return False
        if parsed_output != ex.output_json:
            return False
        if record["metadata"]["label_schema"] != "triage_labels_v1":
            return False
    return True


def _inference_record_contract_ok(examples: list[DistillationExample]) -> bool:
    eval_examples = [ex for ex in examples if ex.split in EVAL_SPLITS]
    if not eval_examples:
        return False
    for ex in eval_examples:
        record = ex.to_inference_record()
        if set(record) != {"id", "split", "messages", "metadata"}:
            return False
        if record["id"] != ex.id or record["split"] != ex.split:
            return False
        messages = record["messages"]
        if [m.get("role") for m in messages] != ["system", "user"]:
            return False
        if messages[1]["content"] != ex.prompt_text:
            return False
        # Eval input truth/assistant cevabi tasimaz; model bu dosyaya tahmin uretir.
        if any(m.get("role") == "assistant" for m in messages):
            return False
    return True


def _urgency_recall(
    truth_examples: list[DistillationExample],
    predicted_by_id: dict[str, str],
    urgency_value: str = EMERGENCY_URGENCY,
) -> float | None:
    """Belirli bir aciliyet sinifinin recall'u: gercekte `urgency_value` olan orneklerin
    kacinin dogru tahmin edildigi. Sinifin hic ornegi yoksa None (recall tanimsiz).

    Bu, genel `urgency_accuracy`den KASITLI olarak ayridir: azinlik sinif (acil vakalar
    korpusun ~%7-17'si) genel dogrulukta bogulabilir — tam da 2026-07-06 naif fine-tune
    regresyonunda oldugu gibi (genel metrikler makul gorunse de acil recall %26,7'ye
    dustu). Guvenlik-kritik siniflar kendi basina olculmeli.
    """
    truth_positive = [ex for ex in truth_examples if ex.output_json["urgency"] == urgency_value]
    if not truth_positive:
        return None
    correct = sum(1 for ex in truth_positive if predicted_by_id.get(ex.id) == urgency_value)
    return correct / len(truth_positive)


def _baseline_metrics(examples: list[DistillationExample]) -> dict:
    """Mevcut deterministic triyaj motorunu fine-tune karsilastirma baseline'i yapar."""
    by_split: dict[str, dict] = {}
    for split in ("train", "validation", "test"):
        split_examples = [ex for ex in examples if ex.split == split]
        total = len(split_examples)
        specialty_correct = 0
        urgency_correct = 0
        channel_correct = 0
        exact_correct = 0
        predicted_urgency_by_id: dict[str, str] = {}
        for ex in split_examples:
            pred = triage(ex.input_text)
            predicted = {
                "specialty_code": pred.specialty_code,
                "urgency": pred.urgency.value,
                "channel": ex.output_json["channel"],  # kanal metinden degil, runtime metadata'dan gelir.
            }
            predicted_urgency_by_id[ex.id] = predicted["urgency"]
            specialty_ok = predicted["specialty_code"] == ex.output_json["specialty_code"]
            urgency_ok = predicted["urgency"] == ex.output_json["urgency"]
            channel_ok = predicted["channel"] == ex.output_json["channel"]
            specialty_correct += int(specialty_ok)
            urgency_correct += int(urgency_ok)
            channel_correct += int(channel_ok)
            exact_correct += int(specialty_ok and urgency_ok and channel_ok)
        by_split[split] = {
            "total": total,
            "specialty_accuracy": specialty_correct / total if total else 0.0,
            "urgency_accuracy": urgency_correct / total if total else 0.0,
            "channel_accuracy": channel_correct / total if total else 0.0,
            "exact_label_accuracy": exact_correct / total if total else 0.0,
            "emergency_recall": _urgency_recall(split_examples, predicted_urgency_by_id),
        }
    return by_split


def _truth_by_id(examples: list[DistillationExample]) -> dict[str, DistillationExample]:
    return {ex.id: ex for ex in examples}


def _parse_prediction_output(raw: dict) -> dict | None:
    if isinstance(raw.get("output_json"), dict):
        return raw["output_json"]
    if isinstance(raw.get("prediction"), dict):
        return raw["prediction"]
    assistant_content = raw.get("assistant_content")
    if isinstance(assistant_content, str):
        try:
            parsed = json.loads(assistant_content)
        except json.JSONDecodeError:
            return None
        return parsed if isinstance(parsed, dict) else None
    messages = raw.get("messages")
    if isinstance(messages, list):
        assistant_messages = [m for m in messages if isinstance(m, dict) and m.get("role") == "assistant"]
        if assistant_messages:
            content = assistant_messages[-1].get("content")
            if isinstance(content, str):
                try:
                    parsed = json.loads(content)
                except json.JSONDecodeError:
                    return None
                return parsed if isinstance(parsed, dict) else None
    return None


def load_predictions(path: Path) -> dict[str, dict]:
    predictions: dict[str, dict] = {}
    with path.open("r", encoding="utf-8") as handle:
        for line_no, line in enumerate(handle, start=1):
            line = line.strip()
            if not line:
                continue
            raw = json.loads(line)
            pred_id = str(raw.get("id") or "")
            if not pred_id:
                raise ValueError(f"{path.name}:{line_no} id eksik")
            output = _parse_prediction_output(raw)
            if output is None:
                raise ValueError(f"{path.name}:{line_no} tahmin JSON kontrati gecersiz")
            predictions[pred_id] = output
    return predictions


def score_predictions(predictions: dict[str, dict], examples: list[DistillationExample] | None = None) -> dict:
    examples = examples or build_examples()
    truth = _truth_by_id(examples)
    eval_examples = [ex for ex in examples if ex.split in EVAL_SPLITS]
    baseline = _baseline_metrics(examples)
    valid_keys = {"specialty_code", "urgency", "channel"}
    unknown_ids = sorted(set(predictions) - {ex.id for ex in eval_examples})
    missing_ids = sorted(ex.id for ex in eval_examples if ex.id not in predictions)
    invalid_ids = sorted(
        pred_id
        for pred_id, output in predictions.items()
        if pred_id in truth and (set(output) != valid_keys or not _output_contract_ok([
            DistillationExample(
                id=pred_id,
                split=truth[pred_id].split,
                input_text=truth[pred_id].input_text,
                output_json=output,
                source=truth[pred_id].source,
            )
        ]))
    )

    by_split: dict[str, dict] = {}
    for split in EVAL_SPLITS:
        split_examples = [ex for ex in eval_examples if ex.split == split]
        scored = [ex for ex in split_examples if ex.id in predictions and ex.id not in invalid_ids]
        total = len(split_examples)
        specialty_correct = urgency_correct = channel_correct = exact_correct = 0
        predicted_urgency_by_id: dict[str, str] = {}
        for ex in scored:
            output = predictions[ex.id]
            specialty_ok = output.get("specialty_code") == ex.output_json["specialty_code"]
            urgency_ok = output.get("urgency") == ex.output_json["urgency"]
            channel_ok = output.get("channel") == ex.output_json["channel"]
            specialty_correct += int(specialty_ok)
            urgency_correct += int(urgency_ok)
            channel_correct += int(channel_ok)
            exact_correct += int(specialty_ok and urgency_ok and channel_ok)
            predicted_urgency_by_id[ex.id] = output.get("urgency")
        # Recall paydasi TUM split_examples uzerinden hesaplanir (yalniz `scored` degil):
        # skorlanmamis (missing/invalid) bir acil-vaka kimligi `predicted_urgency_by_id`de
        # hic yer almaz -> `.get(ex.id)` None doner -> "emergency" ile eslesmez -> otomatik
        # "kacirilmis" sayilir. Yani eksik/gecersiz tahmin acil recall'u sessizce sise-mez.
        emergency_recall = _urgency_recall(split_examples, predicted_urgency_by_id)
        by_split[split] = {
            "total": total,
            "scored": len(scored),
            "missing": total - len(scored),
            "specialty_accuracy": specialty_correct / len(scored) if scored else 0.0,
            "urgency_accuracy": urgency_correct / len(scored) if scored else 0.0,
            "channel_accuracy": channel_correct / len(scored) if scored else 0.0,
            "exact_label_accuracy": exact_correct / len(scored) if scored else 0.0,
            "baseline_exact_label_accuracy": baseline[split]["exact_label_accuracy"],
            "beats_baseline": (
                len(scored) == total
                and exact_correct / len(scored) > baseline[split]["exact_label_accuracy"]
                if scored
                else False
            ),
            "emergency_recall": emergency_recall,
            "baseline_emergency_recall": baseline[split]["emergency_recall"],
            "emergency_recall_pass": (
                emergency_recall is None or emergency_recall >= EMERGENCY_RECALL_MIN
            ),
        }
    return {
        "name": "ip3_6_distillation_prediction_score",
        "splits": by_split,
        "unknown_ids": unknown_ids,
        "missing_ids": missing_ids,
        "invalid_ids": invalid_ids,
        "overall_pass": (
            not unknown_ids
            and not missing_ids
            and not invalid_ids
            and all(by_split[split]["beats_baseline"] for split in EVAL_SPLITS)
            and all(by_split[split]["emergency_recall_pass"] for split in EVAL_SPLITS)
        ),
    }


def build_report() -> dict:
    examples = build_examples()
    counts = _split_counts(examples)
    coverage = _coverage(examples)
    split_ids = _ids_by_split(examples)
    overlaps = {
        "train_validation": len(split_ids["train"] & split_ids["validation"]),
        "train_test": len(split_ids["train"] & split_ids["test"]),
        "validation_test": len(split_ids["validation"] & split_ids["test"]),
    }
    baseline = _baseline_metrics(examples)
    pii_hits = [
        {"id": ex.id, "hits": scan_pii(ex.input_text)}
        for ex in examples
        if scan_pii(ex.input_text)
    ]
    specialty_target = set(SPECIALTY_BY_CODE)
    urgency_target = {level.value for level in UrgencyLevel}
    channel_target = {"whatsapp", "phone", "web", "form"}
    gates = {
        "train_size": {
            "target": f"train >= {MIN_TRAIN_EXAMPLES}",
            "train_n": counts["train"],
            "pass": counts["train"] >= MIN_TRAIN_EXAMPLES,
        },
        "pii_clean": {
            "target": "egitim paketinde PII yok",
            "hits": pii_hits,
            "pass": not pii_hits,
        },
        "label_coverage": {
            "target": "tum brans, aciliyet ve kanal etiketleri temsil edilir",
            "missing_specialties": sorted(specialty_target - set(coverage["specialties"])),
            "missing_urgencies": sorted(urgency_target - set(coverage["urgencies"])),
            "missing_channels": sorted(channel_target - set(coverage["channels"])),
            "pass": (
                set(coverage["specialties"]) == specialty_target
                and set(coverage["urgencies"]) == urgency_target
                and set(coverage["channels"]) == channel_target
            ),
        },
        "split_integrity": {
            "target": "train/validation/test kimlikleri ayrik",
            "overlaps": overlaps,
            "pass": all(value == 0 for value in overlaps.values()),
        },
        "output_contract": {
            "target": "cikti yalniz JSON etiket kontrati; serbest tani/tedavi metni yok",
            "keys": ["channel", "specialty_code", "urgency"],
            "pass": _output_contract_ok(examples),
        },
        "training_export_contract": {
            "target": "JSONL kaydi system/user/assistant mesajlari ve triage_labels_v1 metadata tasir",
            "dataset_file": DATASET_PATH.name,
            "pass": _training_record_contract_ok(examples),
        },
        "eval_input_contract": {
            "target": "validation/test icin etiketsiz inference JSONL girdisi hazir",
            "eval_file": EVAL_INPUT_PATH.name,
            "pass": _inference_record_contract_ok(examples),
        },
        "baseline_protocol": {
            "target": "fine-tune sonrasi karsilastirma icin validation/test baseline metrikleri kayitli",
            "validation_specialty_accuracy": baseline["validation"]["specialty_accuracy"],
            "test_exact_label_accuracy": baseline["test"]["exact_label_accuracy"],
            "pass": (
                baseline["validation"]["total"] > 0
                and baseline["test"]["total"] > 0
                and baseline["validation"]["specialty_accuracy"] >= MIN_VALIDATION_SPECIALTY_BASELINE
            ),
        },
    }
    report = {
        "name": "ip3_6_distillation_data_pack",
        "purpose": "small_on_prem_triage_model_distillation",
        "dataset_artifact": DATASET_PATH.name,
        "eval_input_artifact": EVAL_INPUT_PATH.name,
        "baseline": baseline,
        "improvement_targets": {
            "validation_exact_label_accuracy_min": baseline["validation"]["exact_label_accuracy"],
            "test_exact_label_accuracy_min": baseline["test"]["exact_label_accuracy"],
            "note": "Fine-tuned model bu baseline'i gecmeli; test split golden settir ve egitime karismamalidir.",
        },
        "splits": counts,
        "total_examples": len(examples),
        "coverage": coverage,
        "sample_examples": [ex.to_dict() for ex in examples[:5]],
        "gates": gates,
        "overall_pass": all(gate["pass"] for gate in gates.values()),
        "remaining": [
            "Baseline kucuk model secimi ve local training runtime hazirligi.",
            "Distillation/fine-tune kosumu.",
            "Fine-tuned modelin baseline exact-label ve mevcut klinik kalite/latency panolarina karsi karsilastirmasi.",
        ],
    }
    return report


def render(report: dict) -> str:
    ok = lambda value: "PASS" if value else "FAIL"  # noqa: E731
    lines = [
        "İP-3.6 — Distillation Veri Paketi",
        "=" * 58,
        f"Ornekler: {report['total_examples']} "
        f"(train {report['splits']['train']} / validation {report['splits']['validation']} / test {report['splits']['test']})",
    ]
    for key, gate in report["gates"].items():
        lines.append(f"{ok(gate['pass']):<5} {key:<18} {gate['target']}")
    base = report["baseline"]
    lines.append(
        f"Baseline validation exact: {base['validation']['exact_label_accuracy']:.3f} "
        f"· test exact: {base['test']['exact_label_accuracy']:.3f}"
    )
    lines += [
        "-" * 58,
        f"GENEL: {ok(report['overall_pass'])}",
        "Kalan:",
    ]
    lines.extend(f"- {item}" for item in report["remaining"])
    return "\n".join(lines)


def write_artifact(report: dict, path: Path = ARTIFACT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return path


def write_dataset(examples: list[DistillationExample], path: Path = DATASET_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for example in examples:
            handle.write(json.dumps(example.to_training_record(), ensure_ascii=False, sort_keys=True) + "\n")
    return path


def write_eval_inputs(examples: list[DistillationExample], path: Path = EVAL_INPUT_PATH) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        for example in examples:
            if example.split in EVAL_SPLITS:
                handle.write(json.dumps(example.to_inference_record(), ensure_ascii=False, sort_keys=True) + "\n")
    return path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="İP-3.6 distillation veri paketi")
    parser.add_argument("--no-save", action="store_true", help="artefakt yazma")
    parser.add_argument("--json", action="store_true", help="JSON çıktısı")
    parser.add_argument("--score-predictions", type=Path, help="model tahmin JSONL dosyasini baseline'a karsi puanla")
    args = parser.parse_args(argv)

    examples = build_examples()
    if args.score_predictions is not None:
        score = score_predictions(load_predictions(args.score_predictions), examples)
        if args.json:
            print(json.dumps(score, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(json.dumps(score, ensure_ascii=False, indent=2, sort_keys=True))
        return 0 if score["overall_pass"] else 1

    report = build_report()
    if args.json:
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    else:
        print(render(report))
    if not args.no_save:
        dataset_path = write_dataset(examples)
        eval_path = write_eval_inputs(examples)
        path = write_artifact(report)
        if not args.json:
            print(f"\nDataset: {dataset_path}")
            print(f"Eval input: {eval_path}")
            print(f"Artefakt: {path}")
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
