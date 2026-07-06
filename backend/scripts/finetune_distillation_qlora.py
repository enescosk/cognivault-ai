"""İP-3.6 — Acil-vaka ağırlıklı QLoRA yeniden-eğitim koşumu (3. deneme).

BAĞLAM — bu makinede iki deneme zaten koşuldu ve İKİSİ DE başarısız oldu
(bkz. docs/BIGG_AKSIYON_PLANI.md 2026-07-06 girdileri):
  (v1) Naif tam fine-tune (class-balancing yok, Qwen2.5-1.5B, 3 epoch, LR 2e-4):
       acil-recall %100 → **%26,7** (catastrophic forgetting / azınlık-sınıf
       çöküşü; acil vakalar train'in ~%7'si, 31/436).
  (v2) Buna "düzeltme" olarak denenen acil/priority sabit oversample (4x/2x)
       + düşük LR (1e-4) + 2 epoch: sonuç DAHA KÖTÜ — acil-recall **%13,3**;
       model çoğu vakaya "priority" der hale geldi.
**v2'nin kritik dersi: "oversample'la düzelir" varsayımı YANLIŞ çıktı —
kaba/agresif oversample multiplier'ı azınlık sınıfına o kadar ağırlık
veriyor ki model genel ayrımı kaybediyor.** Bu yüzden bu script'in
varsayılan `--emergency-oversample-multiplier` değeri KASITLI OLARAK
ÖLÇÜLÜ tutulmuştur (v2'nin sabit 4x'inin çok altında) — agresiflik yerine
ikinci güvenlik mekanizmasına (aşağıda 2) güveniyoruz.

Bu script iki güvenlik mekanizması ekler:
  1. WeightedRandomSampler ile train örneklemesi — aciliyet sınıfı ters-frekans
     ile dengelenir VE acil sınıfına küçük, ayarlanabilir bir ekstra
     `--emergency-oversample-multiplier` çarpanı uygulanır. v2 bulgusu
     nedeniyle bunu büyütmek yerine ÖNCE varsayılanla (veya daha da düşükle)
     denemek, sonra metrics_log.jsonl'a bakıp gerekirse temkinli artırmak
     önerilir — v2'deki gibi kör biçimde büyütmek tekrar geri tepebilir.
  2. Her epoch sonunda validation split'te `app.clinical.distillation` ile
     AYNI acil-recall metriği hesaplanır ve checkpoint seçimi ÖNCE
     emergency_recall'a (birincil, yumuşatılamaz), SONRA exact_label_accuracy'e
     (ikincil) göre yapılır — v1/v2'nin İKİSİ DE bunu yapmadı, yalnızca sabit
     epoch sonunda tek seferlik değerlendirdiler. Golden `test` split'i
     checkpoint seçimine ASLA karışmaz — yalnızca en sona, seçilen checkpoint
     üstünde bir kez koşulur (bkz. distillation.py: "Golden set egitime
     karistirilmaz").

Donanım notu: RTX 2060 Super (Turing, sm_75) bf16 desteklemez → fp16 hesap
dtype'i + nf4 4-bit ağırlık (QLoRA) kullanılır. 8GB VRAM için micro-batch=1 +
gradient accumulation + gradient checkpointing varsayılan.

Kullanım (eğitim makinesinde, backend/ içinden, PYTHONPATH=. ile):
    pip install -r scripts/requirements-finetune.txt
    PYTHONPATH=. python scripts/finetune_distillation_qlora.py \\
        --output-dir ./artifacts/ip3_6_emergency_weighted

Çıktılar (`--output-dir` altında):
    best_adapter/                 — en iyi epoch'un LoRA adaptör ağırlıkları
    metrics_log.jsonl             — her epoch: train_loss + validation metrikleri
    predictions_eval.jsonl        — best checkpoint ile validation+test tahminleri
                                     (app.clinical.distillation.load_predictions
                                     ile doğrudan uyumlu id/output_json kaydı)
    final_report.json             — best checkpoint özeti + golden test sonucu

Doğrulama (repo kökünde, backend/ içinden):
    python -m app.clinical.distillation \\
        --score-predictions ./artifacts/ip3_6_emergency_weighted/predictions_eval.jsonl \\
        --json
Bu komutun çıktısında `overall_pass: true` VE her iki split için
`emergency_recall_pass: true` görülmeden model hiçbir şekilde canlıya
alınmamalıdır (bkz. İP-1.7 sıfır-tolerans acil-recall ilkesi).
"""
from __future__ import annotations

import argparse
import json
import random
import sys
from collections import Counter
from dataclasses import dataclass
from pathlib import Path

# Bu script backend/ kökünden PYTHONPATH=. ile çalıştırılmalı ki
# `app.clinical.distillation` içe aktarılabilsin — böylece eğitim/skorlama,
# üretim harness'iyle (ve onun EMERGENCY_RECALL_MIN yumuşatılamaz kapısıyla)
# birebir aynı mantığı kullanır; script kendi ayrı metrik tanımını icat etmez.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.clinical.distillation import (  # noqa: E402
    EMERGENCY_RECALL_MIN,
    EVAL_SPLITS,
    DistillationExample,
    build_examples,
    score_predictions,
)

INVALID_SENTINEL = {
    "specialty_code": "__invalid__",
    "urgency": "__invalid__",
    "channel": "__invalid__",
}


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    # Qwen2.5-1.5B-Instruct varsayılan: bu tam GPU'da (RTX 2060 Super, 8GB) v1/v2
    # denemeleriyle zaten çalıştığı kanıtlanmış boyut. 3B de 4-bit'te sığmalı;
    # denemek isterseniz --base-model Qwen/Qwen2.5-3B-Instruct verin, ama önce
    # kanıtlanmış 1.5B ile checkpoint-seçim mekanizmasını doğrulamak daha güvenli.
    p.add_argument("--base-model", default="Qwen/Qwen2.5-1.5B-Instruct")
    p.add_argument("--output-dir", type=Path, required=True)
    p.add_argument("--epochs", type=int, default=6)
    p.add_argument("--lr", type=float, default=2e-4)
    p.add_argument("--lora-r", type=int, default=16)
    p.add_argument("--lora-alpha", type=int, default=32)
    p.add_argument("--lora-dropout", type=float, default=0.05)
    p.add_argument("--max-seq-len", type=int, default=512)
    p.add_argument("--micro-batch-size", type=int, default=1)
    p.add_argument("--grad-accum", type=int, default=8)
    p.add_argument(
        "--emergency-oversample-multiplier",
        type=float,
        default=1.5,
        help=(
            "Ters-frekans dengelemesinin ÜSTÜNE acil sınıfına uygulanan ekstra çarpan. "
            "KASITLI OLARAK ÖLÇÜLÜ (v2 denemesindeki sabit 4x'in çok altında) — "
            "v2 bulgusu agresif oversample'ın recall'u DAHA DA kötüleştirebildiğini "
            "gösterdi. Büyütmeden önce metrics_log.jsonl'daki epoch eğrisine bakın."
        ),
    )
    p.add_argument("--max-new-tokens", type=int, default=40)
    p.add_argument("--seed", type=int, default=42)
    p.add_argument(
        "--eval-only-from",
        type=Path,
        default=None,
        help="Eğitimi atla; verilen adaptör dizininden yükleyip doğrudan eval/tahmin üret.",
    )
    return p.parse_args(argv)


def set_seed(seed: int) -> None:
    import numpy as np
    import torch

    random.seed(seed)
    np.random.seed(seed)
    torch.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)


# ─────────────────────────────────────────────────────────────────────────────
# Veri hazırlığı — chat-template + assistant-only loss masking
# ─────────────────────────────────────────────────────────────────────────────
def _chat_messages(example: DistillationExample) -> list[dict]:
    return example.to_training_record()["messages"]


def build_sample_weights(train_examples: list[DistillationExample], emergency_multiplier: float) -> list[float]:
    """Aciliyet sınıfına göre ters-frekans dengelemesi + acil sınıfına ekstra çarpan.

    Yalnızca 3 sınıfı (routine/priority/emergency) dengelemek yeterli DEĞİL:
    2026-07-06 regresyonunda acil sınıfı zaten azınlıktı ve dengesiz kaldı.
    Bu yüzden ters-frekans ağırlığının üstüne acil sınıfına ekstra pay veriyoruz
    ki model her epoch'ta acil örnekleri orantısız az görmesin.
    """
    counts = Counter(ex.output_json["urgency"] for ex in train_examples)
    total = len(train_examples)
    num_classes = len(counts)
    base_weight = {urgency: total / (num_classes * n) for urgency, n in counts.items()}
    weights = []
    for ex in train_examples:
        urgency = ex.output_json["urgency"]
        w = base_weight[urgency]
        if urgency == "emergency":
            w *= emergency_multiplier
        weights.append(w)
    return weights


@dataclass
class TokenizedExample:
    input_ids: list[int]
    labels: list[int]


def tokenize_example(tokenizer, example: DistillationExample, max_seq_len: int) -> TokenizedExample:
    messages = _chat_messages(example)
    prompt_messages = messages[:-1]  # system + user, assistant hariç
    prompt_ids = tokenizer.apply_chat_template(
        prompt_messages, tokenize=True, add_generation_prompt=True
    )
    full_ids = tokenizer.apply_chat_template(messages, tokenize=True, add_generation_prompt=False)
    if tokenizer.eos_token_id is not None and (not full_ids or full_ids[-1] != tokenizer.eos_token_id):
        full_ids = full_ids + [tokenizer.eos_token_id]
    full_ids = full_ids[:max_seq_len]
    prompt_len = min(len(prompt_ids), len(full_ids))
    labels = [-100] * prompt_len + full_ids[prompt_len:]
    return TokenizedExample(input_ids=full_ids, labels=labels)


class TriageDataset:
    def __init__(self, tokenizer, examples: list[DistillationExample], max_seq_len: int):
        self.tokenizer = tokenizer
        self.examples = examples
        self.max_seq_len = max_seq_len

    def __len__(self) -> int:
        return len(self.examples)

    def __getitem__(self, idx: int) -> dict:
        tok = tokenize_example(self.tokenizer, self.examples[idx], self.max_seq_len)
        return {"input_ids": tok.input_ids, "labels": tok.labels}


def collate(batch: list[dict], pad_token_id: int) -> dict:
    import torch

    max_len = max(len(item["input_ids"]) for item in batch)
    input_ids, labels, attention_mask = [], [], []
    for item in batch:
        pad_len = max_len - len(item["input_ids"])
        input_ids.append(item["input_ids"] + [pad_token_id] * pad_len)
        labels.append(item["labels"] + [-100] * pad_len)
        attention_mask.append([1] * len(item["input_ids"]) + [0] * pad_len)
    return {
        "input_ids": torch.tensor(input_ids, dtype=torch.long),
        "labels": torch.tensor(labels, dtype=torch.long),
        "attention_mask": torch.tensor(attention_mask, dtype=torch.long),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Model kurulumu — QLoRA (nf4 4-bit + fp16 hesap; Turing bf16 desteklemez)
# ─────────────────────────────────────────────────────────────────────────────
def load_base_model(base_model: str):
    import torch
    from transformers import AutoModelForCausalLM, AutoTokenizer, BitsAndBytesConfig

    tokenizer = AutoTokenizer.from_pretrained(base_model)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    bnb_config = BitsAndBytesConfig(
        load_in_4bit=True,
        bnb_4bit_quant_type="nf4",
        bnb_4bit_use_double_quant=True,
        bnb_4bit_compute_dtype=torch.float16,  # Turing/sm_75: bf16 YOK
    )
    model = AutoModelForCausalLM.from_pretrained(
        base_model,
        quantization_config=bnb_config,
        device_map="auto",
        torch_dtype=torch.float16,
    )
    return model, tokenizer


def attach_lora(model, args: argparse.Namespace):
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training

    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True)
    lora_config = LoraConfig(
        r=args.lora_r,
        lora_alpha=args.lora_alpha,
        lora_dropout=args.lora_dropout,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "k_proj", "v_proj", "o_proj", "gate_proj", "up_proj", "down_proj"],
    )
    model = get_peft_model(model, lora_config)
    model.print_trainable_parameters()
    return model


# ─────────────────────────────────────────────────────────────────────────────
# Inference — üretilen metni distillation.py kontratına uygun JSON'a çevirir
# ─────────────────────────────────────────────────────────────────────────────
def _extract_json(text: str) -> dict:
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end < start:
        return dict(INVALID_SENTINEL)
    try:
        parsed = json.loads(text[start : end + 1])
    except json.JSONDecodeError:
        return dict(INVALID_SENTINEL)
    if not isinstance(parsed, dict):
        return dict(INVALID_SENTINEL)
    return parsed


def generate_predictions(model, tokenizer, examples: list[DistillationExample], max_new_tokens: int) -> dict[str, dict]:
    import torch

    model.eval()
    predictions: dict[str, dict] = {}
    with torch.no_grad():
        for ex in examples:
            messages = ex.to_inference_record()["messages"]
            input_ids = tokenizer.apply_chat_template(
                messages, tokenize=True, add_generation_prompt=True, return_tensors="pt"
            ).to(model.device)
            output = model.generate(
                input_ids,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                num_beams=1,
                pad_token_id=tokenizer.pad_token_id,
            )
            generated = output[0][input_ids.shape[1] :]
            text = tokenizer.decode(generated, skip_special_tokens=True)
            predictions[ex.id] = _extract_json(text)
    model.train()
    return predictions


# ─────────────────────────────────────────────────────────────────────────────
# Eğitim döngüsü — WeightedRandomSampler + epoch-sonu acil-recall gated seçim
# ─────────────────────────────────────────────────────────────────────────────
def train(args: argparse.Namespace) -> int:
    import torch
    from torch.utils.data import DataLoader, WeightedRandomSampler

    set_seed(args.seed)
    args.output_dir.mkdir(parents=True, exist_ok=True)

    examples = build_examples()
    train_examples = [ex for ex in examples if ex.split == "train"]
    validation_examples = [ex for ex in examples if ex.split == "validation"]
    test_examples = [ex for ex in examples if ex.split == "test"]

    print(f"train={len(train_examples)} validation={len(validation_examples)} test={len(test_examples)}")
    emergency_train_n = sum(1 for ex in train_examples if ex.output_json["urgency"] == "emergency")
    print(f"train emergency examples: {emergency_train_n} ({emergency_train_n / len(train_examples):.1%})")

    model, tokenizer = load_base_model(args.base_model)
    model = attach_lora(model, args)

    dataset = TriageDataset(tokenizer, train_examples, args.max_seq_len)
    weights = build_sample_weights(train_examples, args.emergency_oversample_multiplier)
    sampler = WeightedRandomSampler(weights, num_samples=len(weights), replacement=True)
    loader = DataLoader(
        dataset,
        batch_size=args.micro_batch_size,
        sampler=sampler,
        collate_fn=lambda batch: collate(batch, tokenizer.pad_token_id),
    )

    optimizer = torch.optim.AdamW(
        (p for p in model.parameters() if p.requires_grad), lr=args.lr
    )
    total_steps = (len(loader) // args.grad_accum) * args.epochs
    scheduler = torch.optim.lr_scheduler.CosineAnnealingLR(optimizer, T_max=max(total_steps, 1))

    metrics_log_path = args.output_dir / "metrics_log.jsonl"
    best_score: tuple[float, float] | None = None  # (emergency_recall, exact_label_accuracy) — büyük daha iyi
    best_adapter_dir = args.output_dir / "best_adapter"

    for epoch in range(1, args.epochs + 1):
        model.train()
        running_loss = 0.0
        optimizer.zero_grad()
        for step, batch in enumerate(loader, start=1):
            batch = {k: v.to(model.device) for k, v in batch.items()}
            outputs = model(**batch)
            loss = outputs.loss / args.grad_accum
            loss.backward()
            running_loss += loss.item() * args.grad_accum
            if step % args.grad_accum == 0:
                torch.nn.utils.clip_grad_norm_(
                    (p for p in model.parameters() if p.requires_grad), max_norm=1.0
                )
                optimizer.step()
                scheduler.step()
                optimizer.zero_grad()

        avg_loss = running_loss / len(loader)

        val_predictions = generate_predictions(model, tokenizer, validation_examples, args.max_new_tokens)
        # score_predictions test split icin de eksik-tahmin bekleyecegi icin overall_pass
        # buradan anlamli degil; yalniz validation split metriklerini okuyoruz.
        score = score_predictions(val_predictions, examples)
        val_metrics = score["splits"]["validation"]
        emergency_recall = val_metrics["emergency_recall"] or 0.0
        exact_acc = val_metrics["exact_label_accuracy"]

        record = {
            "epoch": epoch,
            "train_loss": avg_loss,
            "validation_exact_label_accuracy": exact_acc,
            "validation_emergency_recall": emergency_recall,
            "validation_emergency_recall_pass": val_metrics["emergency_recall_pass"],
            "validation_beats_baseline": val_metrics["beats_baseline"],
        }
        print(json.dumps(record, ensure_ascii=False))
        with metrics_log_path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

        candidate_score = (emergency_recall, exact_acc)
        if best_score is None or candidate_score > best_score:
            best_score = candidate_score
            model.save_pretrained(best_adapter_dir)
            tokenizer.save_pretrained(best_adapter_dir)
            print(f"  -> yeni en iyi checkpoint (epoch {epoch}, acil_recall={emergency_recall:.3f}, exact={exact_acc:.3f})")

    return finalize(args, model, tokenizer, examples, best_adapter_dir)


def finalize(args, model, tokenizer, examples, best_adapter_dir: Path) -> int:
    from peft import PeftModel

    if best_adapter_dir.exists():
        print(f"En iyi adaptör yükleniyor: {best_adapter_dir}")
        # base model uzerine en iyi epoch'un adaptorlerini tekrar yukle (son epoch
        # agirliklariyla degil, secilen checkpoint'le degerlendirmek icin).
        model = PeftModel.from_pretrained(model.get_base_model() if hasattr(model, "get_base_model") else model, best_adapter_dir)

    validation_examples = [ex for ex in examples if ex.split == "validation"]
    test_examples = [ex for ex in examples if ex.split == "test"]

    val_predictions = generate_predictions(model, tokenizer, validation_examples, args.max_new_tokens)
    test_predictions = generate_predictions(model, tokenizer, test_examples, args.max_new_tokens)
    all_predictions = {**val_predictions, **test_predictions}

    predictions_path = args.output_dir / "predictions_eval.jsonl"
    with predictions_path.open("w", encoding="utf-8") as fh:
        for pred_id, output_json in sorted(all_predictions.items()):
            fh.write(json.dumps({"id": pred_id, "output_json": output_json}, ensure_ascii=False, sort_keys=True) + "\n")

    final_score = score_predictions(all_predictions, examples)
    report_path = args.output_dir / "final_report.json"
    report_path.write_text(json.dumps(final_score, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    print("=" * 60)
    print(f"validation emergency_recall={final_score['splits']['validation']['emergency_recall']}")
    print(f"test emergency_recall={final_score['splits']['test']['emergency_recall']}")
    print(f"overall_pass={final_score['overall_pass']}")
    print(f"Tahminler: {predictions_path}")
    print(f"Rapor: {report_path}")
    if not final_score["overall_pass"]:
        print(
            "UYARI: overall_pass=False — bu model EMERGENCY_RECALL_MIN "
            f"({EMERGENCY_RECALL_MIN}) veya beats_baseline şartını karşılamıyor; "
            "üretime alınmamalı. metrics_log.jsonl'daki epoch'ları inceleyip "
            "--emergency-oversample-multiplier / --epochs ayarlarını gözden geçirin."
        )
    return 0 if final_score["overall_pass"] else 1


def eval_only(args: argparse.Namespace) -> int:
    """Eğitimi atlayıp verilen adaptörle doğrudan skorla (checkpoint yeniden-doğrulama)."""
    from peft import PeftModel

    examples = build_examples()
    model, tokenizer = load_base_model(args.base_model)
    model = PeftModel.from_pretrained(model, args.eval_only_from)
    return finalize(args, model, tokenizer, examples, args.eval_only_from)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if args.eval_only_from is not None:
        return eval_only(args)
    return train(args)


if __name__ == "__main__":
    raise SystemExit(main())
