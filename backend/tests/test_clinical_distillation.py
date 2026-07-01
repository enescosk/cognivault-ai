"""İP-3.6 distillation veri paketi testleri (saf-import, DB gerektirmez).

Kosum: pytest backend/tests/test_clinical_distillation.py --noconftest
"""

import json

from app.clinical.distillation import (
    build_examples,
    build_report,
    load_predictions,
    main,
    render,
    score_predictions,
    write_dataset,
    write_eval_inputs,
)
from app.clinical.ontology import SPECIALTY_BY_CODE, UrgencyLevel


def test_examples_use_synthetic_for_train_validation_and_golden_for_test():
    examples = build_examples()

    assert examples
    assert {ex.split for ex in examples} == {"train", "validation", "test"}
    assert all(ex.source == "synthetic_template" for ex in examples if ex.split != "test")
    assert all(ex.source == "golden_curated" for ex in examples if ex.split == "test")


def test_report_gates_pass():
    report = build_report()

    assert report["overall_pass"] is True
    for gate in report["gates"].values():
        assert gate["pass"] is True


def test_label_coverage_is_complete():
    coverage = build_report()["coverage"]

    assert set(coverage["specialties"]) == set(SPECIALTY_BY_CODE)
    assert set(coverage["urgencies"]) == {level.value for level in UrgencyLevel}
    assert set(coverage["channels"]) == {"whatsapp", "phone", "web", "form"}


def test_output_contract_is_label_only_json():
    for example in build_examples():
        assert set(example.output_json) == {"specialty_code", "urgency", "channel"}
        assert all(isinstance(value, str) for value in example.output_json.values())
        assert "tani" not in json.dumps(example.output_json, ensure_ascii=False).lower()
        assert "tedavi" not in json.dumps(example.output_json, ensure_ascii=False).lower()


def test_training_record_contract_is_jsonl_export_ready(tmp_path):
    examples = build_examples()
    path = write_dataset(examples, tmp_path / "distillation_dataset.jsonl")

    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == len(examples)
    first = rows[0]
    assert set(first) == {"id", "split", "messages", "metadata"}
    assert [message["role"] for message in first["messages"]] == ["system", "user", "assistant"]
    assert first["messages"][1]["content"].startswith("Kanal: ")
    assert "\nHasta mesajı: " in first["messages"][1]["content"]
    assert json.loads(first["messages"][-1]["content"]) == examples[0].output_json
    assert first["metadata"]["label_schema"] == "triage_labels_v1"


def test_report_mentions_dataset_artifact():
    report = build_report()

    assert report["dataset_artifact"] == "distillation_dataset.jsonl"
    assert report["eval_input_artifact"] == "distillation_eval_inputs.jsonl"
    assert report["gates"]["training_export_contract"]["pass"] is True
    assert report["gates"]["eval_input_contract"]["pass"] is True


def test_baseline_protocol_records_comparison_targets():
    report = build_report()

    assert report["gates"]["baseline_protocol"]["pass"] is True
    assert report["baseline"]["validation"]["specialty_accuracy"] >= 0.90
    assert report["baseline"]["test"]["total"] == report["splits"]["test"]
    assert report["improvement_targets"]["test_exact_label_accuracy_min"] == report["baseline"]["test"]["exact_label_accuracy"]


def test_eval_inputs_are_truthless_validation_and_test_records(tmp_path):
    examples = build_examples()
    path = write_eval_inputs(examples, tmp_path / "eval_inputs.jsonl")
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]

    assert rows
    assert {row["split"] for row in rows} == {"validation", "test"}
    assert all([message["role"] for message in row["messages"]] == ["system", "user"] for row in rows)
    assert all("output_json" not in row for row in rows)


def test_score_predictions_requires_beating_baseline():
    examples = build_examples()
    perfect_predictions = {
        example.id: example.output_json
        for example in examples
        if example.split in {"validation", "test"}
    }

    score = score_predictions(perfect_predictions, examples)

    assert score["overall_pass"] is True
    assert score["splits"]["validation"]["beats_baseline"] is True
    assert score["splits"]["test"]["beats_baseline"] is True


def test_score_predictions_fails_when_missing_or_not_better():
    examples = build_examples()
    empty_score = score_predictions({}, examples)

    assert empty_score["overall_pass"] is False
    assert empty_score["missing_ids"]


def test_prediction_loader_accepts_output_json(tmp_path):
    examples = [ex for ex in build_examples() if ex.split in {"validation", "test"}][:2]
    path = tmp_path / "predictions.jsonl"
    path.write_text(
        "\n".join(
            json.dumps({"id": ex.id, "output_json": ex.output_json}, ensure_ascii=False, sort_keys=True)
            for ex in examples
        )
        + "\n",
        encoding="utf-8",
    )

    loaded = load_predictions(path)

    assert loaded == {ex.id: ex.output_json for ex in examples}


def test_deterministic_report():
    first = build_report()
    second = build_report()

    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_render_and_cli():
    assert "Distillation Veri Paketi" in render(build_report())
    assert main(["--no-save"]) == 0
