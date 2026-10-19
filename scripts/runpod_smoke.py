"""A100-only SAMPLE smoke test; separate from registered 5-epoch factory runs."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import platform
import re
import sys
from pathlib import Path


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/hyperparameters.sample.pinned.yaml")
    parser.add_argument("--output", default="outputs/smoke_001")
    parser.add_argument("--execute", action="store_true", help="Download/load model and train up to 4 updates")
    parser.add_argument("--stop-after", type=int, choices=[2])
    parser.add_argument("--resume", type=Path)
    return parser.parse_args()


def checksum(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def select_examples(rows, tokenizer, limit):
    encoded = []
    for row in rows:
        ids = tokenizer.apply_chat_template(row["messages"], tokenize=True,
                                            add_generation_prompt=False, enable_thinking=False, return_dict=False)
        if not isinstance(ids, list) or not ids or not all(isinstance(i, int) for i in ids):
            raise ValueError("Unexpected chat-template token format")
        if len(ids) <= limit:
            encoded.append({"input_ids": ids, "attention_mask": [1] * len(ids), "labels": ids.copy()})
    # Smoke only: select complete shortest examples, never truncate answers.
    encoded.sort(key=lambda item: len(item["input_ids"]))
    if len(encoded) < 4:
        raise ValueError("Need at least 4 complete sample conversations within max_length")
    return encoded[:4]


def main():
    args = parse_args()
    import yaml
    from dotenv import load_dotenv
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    config_path = (root / args.config).resolve()
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8-sig"))
    revision = cfg["model"]["revision"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("A full pinned model commit is required")
    train_file = (root / cfg["data"]["train_file"]).resolve()
    if not train_file.is_relative_to(root / "data/sample"):
        raise ValueError("This script accepts data/sample only")
    rows = [json.loads(line) for line in train_file.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if len(rows) != cfg["data"]["expected_train_samples"]:
        raise ValueError("Sample training row count does not match YAML")
    if len(cfg["experiments"]) != 1:
        raise ValueError("Smoke test requires exactly one recipe")
    recipe = cfg["experiments"][0]
    if recipe["lora"]["scope"] != "language_model" or recipe["lora"]["target_modules"] != "all-linear":
        raise ValueError("Smoke test expects language_model/all-linear LoRA scope")
    q = cfg["quantization"]
    if not q["load_in_4bit"] or q["bnb_4bit_compute_dtype"] != "bfloat16":
        raise ValueError("Expected 4-bit BF16 configuration")
    output = (root / args.output).resolve()
    output.relative_to(root / "outputs")
    if output == root / "outputs":
        raise ValueError("Use a dedicated smoke subdirectory")
    if args.resume and args.stop_after:
        raise ValueError("Do not combine --resume and --stop-after")
    if not args.resume and output.exists():
        raise ValueError("Output exists; use --resume or a new --output directory")

    import torch
    import bitsandbytes as bnb
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (AutoConfig, AutoModelForImageTextToText, AutoTokenizer,
                              BitsAndBytesConfig, Trainer, TrainerCallback,
                              TrainingArguments, set_seed)
    versions = {name: importlib.metadata.version(name) for name in
                ("torch", "transformers", "peft", "accelerate", "bitsandbytes", "huggingface_hub")}
    print("Python:", platform.python_version())
    print("Packages:", json.dumps(versions, sort_keys=True))
    if platform.system() != "Linux":
        raise ValueError("Run on the Linux RunPod, not the local Windows PC")
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise ValueError("Exactly one visible CUDA GPU is required")
    gpu = torch.cuda.get_device_properties(0)
    print(f"GPU: {gpu.name}; VRAM: {gpu.total_memory / 2**30:.1f} GiB; CUDA: {torch.version.cuda}")
    if "A100" not in gpu.name or gpu.total_memory < 75 * 2**30 or not torch.cuda.is_bf16_supported():
        raise ValueError("Expected A100 80GB with BF16 support")
    if not args.execute:
        print("ENVIRONMENT CHECK PASSED. No model weights downloaded and no training started.")
        print("Use --execute only when ready for the weight download and paid GPU work.")
        return

    token = os.getenv("HF_TOKEN")
    if not token:
        raise ValueError("HF_TOKEN missing")
    identity = {"kind": "sample_smoke_v1_all_tokens_loss", "model": cfg["model"],
                "script_sha256": checksum(Path(__file__)), "cuda_runtime": torch.version.cuda,
                "config_sha256": checksum(config_path), "train_sha256": checksum(train_file),
                "packages": versions, "max_steps": 4, "batch_size": 1,
                "gradient_accumulation_steps": 1, "lr_scheduler_type": "constant"}
    resume = None
    if args.resume:
        resume = (root / args.resume).resolve()
        if resume.parent != output or resume.name != "checkpoint-2":
            raise ValueError("Resume must be this smoke output's checkpoint-2")
        for filename in ("trainer_state.json", "optimizer.pt", "scheduler.pt"):
            if not (resume / filename).is_file():
                raise ValueError(f"Incomplete resume checkpoint: missing {filename}")
        old = json.loads((output / "smoke_manifest.json").read_text())
        if old != identity:
            raise ValueError("Config/data/package identity changed; start a new smoke directory")
    else:
        output.mkdir(parents=True, exist_ok=False)
        (output / "smoke_manifest.json").write_text(json.dumps(identity, indent=2), encoding="utf-8")
    set_seed(recipe["training"]["seed"])
    common = dict(revision=revision, token=token, trust_remote_code=False)
    model_cfg = AutoConfig.from_pretrained(cfg["model"]["base_model_id"], **common)
    if model_cfg.model_type != "qwen3_5":
        raise ValueError("Unexpected architecture; inspect model loading before proceeding")
    tokenizer = AutoTokenizer.from_pretrained(cfg["model"]["base_model_id"], **common)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    examples = select_examples(rows, tokenizer, recipe["training"]["max_length"])
    print("Selected complete sample lengths:", [len(row["input_ids"]) for row in examples])
    quantization = BitsAndBytesConfig(load_in_4bit=True,
        bnb_4bit_quant_type=q["bnb_4bit_quant_type"], bnb_4bit_compute_dtype=torch.bfloat16,
        bnb_4bit_use_double_quant=q["bnb_4bit_use_double_quant"])
    model = AutoModelForImageTextToText.from_pretrained(cfg["model"]["base_model_id"],
        quantization_config=quantization, device_map={"": 0}, dtype=torch.bfloat16,
        attn_implementation="sdpa", **common)
    model.config.use_cache = False
    if hasattr(model.config, "text_config"):
        model.config.text_config.use_cache = False
    model = prepare_model_for_kbit_training(model, use_gradient_checkpointing=True,
                                           gradient_checkpointing_kwargs={"use_reentrant": False})
    targets = [name for name, module in model.named_modules()
               if "language_model" in name.split(".")
               and isinstance(module, (torch.nn.Linear, bnb.nn.Linear4bit))
               and not name.endswith("lm_head")]
    if not targets:
        raise ValueError("No language-model Linear targets found; refusing broad fallback")
    lora = recipe["lora"]
    model = get_peft_model(model, LoraConfig(r=lora["r"], lora_alpha=lora["lora_alpha"],
        lora_dropout=lora["lora_dropout"], bias=lora["bias"],
        target_modules=targets, task_type="CAUSAL_LM"))
    trainable = [name for name, param in model.named_parameters() if param.requires_grad]
    if not trainable or any("lora_" not in name or "language_model" not in name.split(".") for name in trainable):
        raise ValueError("Unexpected trainable parameter scope")
    (output / "lora_targets.json").write_text(json.dumps(targets, indent=2), encoding="utf-8")
    model.print_trainable_parameters()

    def collate(batch):
        size = max(len(item["input_ids"]) for item in batch)
        return {key: torch.tensor([item[key] + [pad] * (size-len(item[key])) for item in batch])
                for key, pad in (("input_ids", tokenizer.pad_token_id), ("attention_mask", 0), ("labels", -100))}

    class StopAtTwo(TrainerCallback):
        def on_step_end(self, args, state, control, **kwargs):
            if state.global_step >= 2:
                control.should_save = True
                control.should_training_stop = True
            return control

    # Deliberate smoke overrides: do not register these as the five-epoch DB run.
    training_args = TrainingArguments(output_dir=str(output), max_steps=4,
        per_device_train_batch_size=1, gradient_accumulation_steps=1,
        learning_rate=recipe["training"]["learning_rate"], lr_scheduler_type="constant",
        warmup_steps=0, weight_decay=recipe["training"]["weight_decay"],
        bf16=True, gradient_checkpointing=True,
        gradient_checkpointing_kwargs={"use_reentrant": False},
        optim=recipe["training"]["optim"], logging_steps=1,
        save_strategy="steps", save_steps=2, save_total_limit=3,
        save_only_model=False, eval_strategy="no", report_to="none",
        seed=recipe["training"]["seed"], data_seed=recipe["training"]["data_seed"],
        remove_unused_columns=False, dataloader_num_workers=0)
    trainer = Trainer(model=model, args=training_args, train_dataset=examples,
        data_collator=collate, processing_class=tokenizer,
        callbacks=[StopAtTwo()] if args.stop_after else [])
    torch.cuda.reset_peak_memory_stats()
    trainer.train(resume_from_checkpoint=str(resume) if resume else None)
    step = trainer.state.global_step
    if step != (2 if args.stop_after else 4):
        raise RuntimeError(f"Unexpected final step: {step}")
    trainer.save_model(str(output / f"adapter-step-{step}"))
    tokenizer.save_pretrained(output / f"adapter-step-{step}")
    print(f"SMOKE STEP {step} PASSED; peak allocated VRAM: {torch.cuda.max_memory_allocated()/2**30:.2f} GiB")
    print("No factory DB status changed; no HF upload; not a 4/5-epoch adapter.")


if __name__ == "__main__":
    main()
