"""5-epoch sample/production factory: separate snapshots, HF commits and Neon registry."""
import argparse
from concurrent.futures import ThreadPoolExecutor
import importlib.metadata
import inspect
import json
import math
import os
import re
import sys
import time
import uuid
from pathlib import Path

import yaml
from dotenv import load_dotenv
from sqlalchemy import create_engine, select

from db_registry import factory_output, sample_mode, artifacts, build_plans, digest, metadata, runs
from factory_state import (RunLease, artifact_rows, set_local_saved,
                           set_run_status, set_uploaded)


def verify_snapshot(path, record, plan, run_id):
    manifest = json.loads((path / "factory_manifest.json").read_text(encoding="utf-8"))
    if (manifest["run_id"] != run_id or manifest["weight_id"] != record["weight_id"]
        or manifest["config_hash"] != plan["config_hash"]
        or manifest["trained_epoch"] != record["trained_epoch"]):
        raise ValueError("Local snapshot identity mismatch")
    if not {"adapter_model.safetensors", "adapter_config.json"} <= set(manifest["file_sha256"]):
        raise ValueError("Required adapter files missing from snapshot manifest")
    for name, expected in manifest["file_sha256"].items():
        if Path(name).name != name or digest(path / name) != expected:
            raise ValueError("Local snapshot file hash mismatch")
    return manifest


def upload_snapshot(api, engine, lease, repo_id, path, record, plan):
    verify_snapshot(path, record, plan, lease.run_id)
    subfolder = ("sample" if plan["config"]["is_sample"] else "production")+"/"+record["weight_id"]
    for attempt in range(1, 4):
        lease.assert_owned()
        try:
            commit = api.upload_folder(folder_path=str(path), repo_id=repo_id,
                repo_type="model", path_in_repo=subfolder,
                commit_message=f"Adapter {record['weight_id']} epoch {record['trained_epoch']}")
            revision = commit.oid
            uploaded = set(api.list_repo_files(repo_id=repo_id, repo_type="model", revision=revision))
            required = {f"{subfolder}/{name}" for name in
                        ("adapter_config.json", "adapter_model.safetensors", "factory_manifest.json")}
            if not required <= uploaded:
                raise RuntimeError("Required files not found in uploaded commit")
            set_uploaded(engine, lease, record["weight_id"], repo_id, revision, subfolder)
            print(f"UPLOADED epoch={record['trained_epoch']} weight_id={record['weight_id']} commit={revision}", flush=True)
            return
        except Exception as error:
            # Avoid printing DB URLs or token-bearing HTTP exception details.
            print(f"Upload/registry retry {attempt}/3: {type(error).__name__}", flush=True)
            if attempt == 3:
                raise RuntimeError("Upload/DB update failed; local snapshot preserved. Use --sync-only after checking connectivity.") from None
            time.sleep(2 ** attempt)


def encode_all(path, tokenizer, max_length, loss_policy="all_tokens"):
    if loss_policy not in ("all_tokens", "final_assistant_only"):
        raise ValueError("Unsupported loss policy")
    encoded = []
    for number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), 1):
        if not line.strip():
            continue
        row = json.loads(line)
        ids = tokenizer.apply_chat_template(row["messages"], tokenize=True,
            add_generation_prompt=False, enable_thinking=False, return_dict=False)
        if not isinstance(ids, list) or not ids or not all(type(i) is int for i in ids):
            raise ValueError(f"Unexpected tokens at line {number}")
        if len(ids) > max_length:
            raise ValueError(f"Line {number} has {len(ids)} tokens > {max_length}; no truncation performed")
        labels = ids.copy()
        if loss_policy == "final_assistant_only":
            messages = row["messages"]
            if len(messages) < 2 or messages[-1]["role"] != "assistant" or messages[-2]["role"] != "user":
                raise ValueError(f"Final user/assistant pair required at line {number}")
            if not isinstance(messages[-1]["content"], str) or not messages[-1]["content"].strip():
                raise ValueError(f"Empty assistant at line {number}")
            prefix = tokenizer.apply_chat_template(messages[:-1], tokenize=True,
                add_generation_prompt=True, enable_thinking=False, return_dict=False)
            if not prefix or len(prefix) >= len(ids) or ids[:len(prefix)] != prefix:
                raise ValueError(f"Template prefix mismatch at line {number}; refusing an incorrect loss mask")
            labels[:len(prefix)] = [-100] * len(prefix)
            if not any(value != -100 for value in labels):
                raise ValueError(f"No assistant supervision at line {number}")
        encoded.append(dict(input_ids=ids, attention_mask=[1] * len(ids), labels=labels))
    if not encoded:
        raise ValueError("Empty tokenized dataset")
    return encoded


def get_run(engine, plan):
    with engine.connect() as c:
        row = c.execute(select(runs).where(runs.c.config_hash == plan["config_hash"])).mappings().first()
        if not row:
            raise ValueError("No registered run matches this config and dataset. Register this dataset and config first.")
        return dict(row)


def check_settings(cfg):
    if not re.fullmatch(r"[0-9a-f]{40}", cfg["model"]["revision"]):
        raise ValueError("Pinned model revision required")
    if cfg["data"]["format"] != "messages" or len(cfg["experiments"]) != 1:
        raise ValueError("Expected one messages-format recipe")
    if not sample_mode(cfg) and cfg["data"].get("loss_policy", "final_assistant_only") != "final_assistant_only":
        raise ValueError("Production requires final_assistant_only loss")
    recipe = cfg["experiments"][0]
    t, q, lora, cp = recipe["training"], cfg["quantization"], recipe["lora"], recipe["checkpoints"]
    epochs=t['num_train_epochs'];saved=recipe['artifacts']['save_epochs']
    if type(epochs) is not int or not 1<=epochs<=50 or not saved or any(type(x)is not int or not 1<=x<=epochs for x in saved) or len(saved)!=len(set(saved)):
        raise ValueError('Invalid epoch/save plan')
    expected_eval = "no" if cfg["data"].get("training_scope") == "all_1500_fixed10" else "epoch"
    if t["packing"] or not t["bf16"] or type(t["gradient_checkpointing"]) is not bool or t["eval_strategy"] != expected_eval:
        raise ValueError("Expected packing=false, bf16=true, boolean gradient_checkpointing and matching validation policy")
    if not t["gradient_checkpointing"] and t["per_device_train_batch_size"] != 1:
        raise ValueError("Disabling activation checkpointing is validated only with GPU batch 1; larger batches exhausted A100 memory")
    if type(q.get('load_in_4bit')) is not bool or q["bnb_4bit_compute_dtype"] != "bfloat16":
        raise ValueError("Expected an explicit BF16 LoRA/QLoRA mode")
    if lora["scope"] != "language_model" or lora["target_modules"] != "all-linear" or lora["bias"] != "none":
        raise ValueError("Expected language_model/all-linear LoRA with bias=none")
    if cp["save_strategy"] != "steps" or cp["save_only_model"] or cp["save_total_limit"] < 2:
        raise ValueError("Expected full step checkpoints and save_total_limit >= 2")
    if not 0 <= t["warmup_ratio"] < 1 or cp["save_steps"] < 1:
        raise ValueError("Invalid warmup_ratio or checkpoint interval")
    return recipe


def train(root, cfg, config_path, plan, record, engine, lease, api, repo_id, args):
    import torch
    import bitsandbytes as bnb
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import (AutoModelForImageTextToText, AutoTokenizer, BitsAndBytesConfig,
                              Trainer, TrainerCallback, TrainingArguments, set_seed)
    from transformers.trainer_utils import get_last_checkpoint
    from model_runtime import configure
    configure(cfg)
    recipe = cfg["experiments"][0]
    t = recipe["training"]
    output = factory_output(root,record["run_id"],plan["config"]["is_sample"])
    loss_policy = cfg["data"].get("loss_policy", "all_tokens" if sample_mode(cfg) else "final_assistant_only")
    versions = {name: importlib.metadata.version(name) for name in
                ("torch", "transformers", "peft", "accelerate", "bitsandbytes", "huggingface_hub", "SQLAlchemy", "psycopg")}
    # Kernel changes affect numerical execution and must invalidate incompatible resumes.
    for name in ("causal-conv1d","flash-linear-attention","fla-core","einops","triton"):
        try:versions[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:pass
    runtime = {"pipeline": "sample_factory_v1" if plan["config"]["is_sample"] else "production_factory_v1", "loss": loss_policy,
        "config_hash": plan["config_hash"], "model": cfg["model"], "packages": versions,
        "cuda": torch.version.cuda, "execution_backend": cfg.get("runtime", {}),
        "script_sha256": {name: digest(root / "scripts" / name) for name in
                          ("runpod_factory_sample.py", "factory_state.py", "db_registry.py", "model_runtime.py")},
        "safety_override": "full checkpoint at every epoch in addition to configured step checkpoints"}
    resume = None
    if output.exists():
        old = json.loads((output / "runtime_manifest.json").read_text(encoding="utf-8"))
        if old != runtime:
            raise ValueError("Runtime/config changed; do not resume with different code or packages")
        if not args.resume:
            raise ValueError("This run already has a local directory. Use --resume; nothing overwritten.")
        resume = get_last_checkpoint(str(output / "checkpoints")) if (output / "checkpoints").is_dir() else None
        if not resume:
            raise ValueError("No resumable checkpoint exists. Preserve this folder; do not restart blindly.")
        for name in ("trainer_state.json", "optimizer.pt", "scheduler.pt"):
            if not (Path(resume) / name).is_file():
                raise ValueError("Incomplete resume checkpoint")
    elif args.resume:
        raise ValueError("No local run directory to resume")
    set_seed(t["seed"])
    common = dict(revision=cfg["model"]["revision"], token=os.environ["HF_TOKEN"], trust_remote_code=False)
    tokenizer = AutoTokenizer.from_pretrained(cfg["model"]["base_model_id"], **common)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "right"
    training = encode_all(root / cfg["data"]["train_file"], tokenizer, t["max_length"], loss_policy=loss_policy)
    validation = (encode_all(root / cfg["data"]["validation_file"], tokenizer, t["max_length"], loss_policy=loss_policy)
                  if cfg["data"].get("validation_file") else None)
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise ValueError("Exactly one visible CUDA GPU required")
    gpu = torch.cuda.get_device_properties(0)
    if gpu.total_memory < 75 * 2**30 or not torch.cuda.is_bf16_supported():
        raise ValueError("A single BF16-capable GPU with at least 75GiB is required; actual memory fit still needs measurement")
    print(f"{'SAMPLE' if sample_mode(cfg) else 'PRODUCTION'}: train={len(training)} validation={len(validation) if validation is not None else 0}; epochs={t['num_train_epochs']}; effective_batch={t['per_device_train_batch_size'] * t['gradient_accumulation_steps']}", flush=True)
    print("Loss policy: "+loss_policy+"; "+("synthetic integration test." if sample_mode(cfg) else "production dataset; assess quality using the configured report inputs."), flush=True)
    if not output.exists():
        output.mkdir(parents=True, exist_ok=False)
        (output / "runtime_manifest.json").write_text(json.dumps(runtime, indent=2), encoding="utf-8")
        (output / "config.yaml").write_bytes(config_path.read_bytes())
    q = cfg["quantization"]
    load_kwargs={}
    if q['load_in_4bit']:
        load_kwargs['quantization_config']=BitsAndBytesConfig(load_in_4bit=True,
            bnb_4bit_quant_type=q['bnb_4bit_quant_type'],bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=q['bnb_4bit_use_double_quant'])
    model=AutoModelForImageTextToText.from_pretrained(cfg['model']['base_model_id'],
        device_map={'':0},dtype=torch.bfloat16,attn_implementation='sdpa',**load_kwargs,**common)
    model.config.use_cache=False
    model.config.text_config.use_cache=False
    if q['load_in_4bit']:
        model=prepare_model_for_kbit_training(model,use_gradient_checkpointing=t['gradient_checkpointing'],
            gradient_checkpointing_kwargs={'use_reentrant':False})
    elif t['gradient_checkpointing']:
        model.enable_input_require_grads()
    targets = [name for name, module in model.named_modules()
        if "language_model" in name.split(".") and isinstance(module, (torch.nn.Linear, bnb.nn.Linear4bit))
        and not name.endswith("lm_head")]
    if not targets:
        raise ValueError("No valid language-model LoRA targets")
    hp = recipe["lora"]
    model = get_peft_model(model, LoraConfig(r=hp["r"], lora_alpha=hp["lora_alpha"],
        lora_dropout=hp["lora_dropout"], bias=hp["bias"], target_modules=targets, task_type="CAUSAL_LM"))
    trainable = [name for name, p in model.named_parameters() if p.requires_grad]
    if not trainable or any("lora_" not in name or "language_model" not in name.split(".") for name in trainable):
        raise ValueError("Unexpected trainable parameter scope")
    model.print_trainable_parameters()
    (output / "lora_targets.json").write_text(json.dumps(targets, indent=2), encoding="utf-8")

    class Export(TrainerCallback):
        def on_step_begin(self, args, state, control, **kwargs):
            lease.assert_healthy()
            return control

        def on_epoch_end(self, args, state, control, **kwargs):
            lease.assert_owned()
            # Full optimizer/scheduler/RNG checkpoints are saved at every epoch.
            control.should_save = True
            return control

        def on_save(self, args, state, control, **kwargs):
            lease.assert_owned()
            epoch = round(state.epoch or 0)
            if abs((state.epoch or 0) - epoch) > 1e-5:
                return control
            current = {r["trained_epoch"]: r for r in artifact_rows(engine, record["run_id"])}
            if epoch not in current or current[epoch]["status"] in ("TRAINED", "EVALUATED"):
                return control
            artifact = current[epoch]
            path = output / "artifacts" / artifact["weight_id"]
            if not path.exists():
                temporary = path.with_name(path.name + ".tmp_" + uuid.uuid4().hex)
                temporary.mkdir(parents=True, exist_ok=False)
                kwargs["model"].save_pretrained(str(temporary))
                tokenizer.save_pretrained(str(temporary))
                files = {p.name: digest(p) for p in temporary.iterdir() if p.is_file()}
                snapshot = {"run_id": record["run_id"], "weight_id": artifact["weight_id"],
                    "trained_epoch": epoch, "global_step": state.global_step,
                    "config_hash": plan["config_hash"], "is_sample": plan["config"]["is_sample"],
                    "dataset": plan["config"]["data"], "experiment_id": cfg.get("experiment_id"),
                    "model": cfg["model"], "file_sha256": files,
                    "runtime": runtime}
                (temporary / "factory_manifest.json").write_text(json.dumps(snapshot, ensure_ascii=False, indent=2), encoding="utf-8")
                temporary.rename(path)
            verify_snapshot(path, artifact, plan, record["run_id"])
            set_local_saved(engine, lease, artifact["weight_id"])
            # Only immutable, verified files are handed to the CPU uploader.
            if artifact["weight_id"] not in pending_uploads:
                pending_uploads[artifact["weight_id"]] = uploader.submit(
                    upload_snapshot, api, engine, lease, repo_id, path, artifact, plan)
                print(f"UPLOAD QUEUED: epoch={epoch}; training continues", flush=True)
            return control

    def collate(batch):
        length = max(len(row["input_ids"]) for row in batch)
        return {key: torch.tensor([row[key] + [pad] * (length-len(row[key])) for row in batch])
                for key, pad in (("input_ids", tokenizer.pad_token_id), ("attention_mask", 0), ("labels", -100))}

    cp = recipe["checkpoints"]
    # New Transformers versions represent warmup ratios through warmup_steps.
    warmup = ({"warmup_ratio": float(t["warmup_ratio"])}
              if "warmup_ratio" in inspect.signature(TrainingArguments).parameters
              else {"warmup_steps": float(t["warmup_ratio"])})
    training_args = TrainingArguments(output_dir=str(output / "checkpoints"),
        num_train_epochs=t["num_train_epochs"],
        learning_rate=float(t["learning_rate"]), lr_scheduler_type=t["lr_scheduler_type"],
        **warmup, weight_decay=t["weight_decay"],
        per_device_train_batch_size=t["per_device_train_batch_size"],
        gradient_accumulation_steps=t["gradient_accumulation_steps"],
        per_device_eval_batch_size=t["per_device_eval_batch_size"],
        bf16=True, gradient_checkpointing=t["gradient_checkpointing"],
        gradient_checkpointing_kwargs={"use_reentrant": False}, optim=t["optim"],
        logging_steps=t["logging_steps"], eval_strategy=t["eval_strategy"],
        prediction_loss_only=True, save_strategy="steps", save_steps=cp["save_steps"],
        save_total_limit=cp["save_total_limit"], save_only_model=False,
        report_to="none", seed=t["seed"], data_seed=t["data_seed"],
        remove_unused_columns=False, dataloader_num_workers=0)
    trainer = Trainer(model=model, args=training_args, train_dataset=training,
        eval_dataset=validation, processing_class=tokenizer,
        data_collator=collate, callbacks=[Export()])
    set_run_status(engine, lease, "TRAINING")
    pending_uploads = {}
    # Keep the lease alive until every upload has finished; surface errors before success.
    with ThreadPoolExecutor(max_workers=1, thread_name_prefix="snapshot-upload") as uploader:
        trainer.train(resume_from_checkpoint=resume)
        for future in pending_uploads.values():
            future.result()
    if not math.isclose(trainer.state.epoch or 0, 5, abs_tol=1e-5):
        raise RuntimeError("Training did not finish epoch 5")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/hyperparameters.sample.pinned.yaml")
    actions = parser.add_mutually_exclusive_group()
    actions.add_argument("--check-connections", action="store_true")
    actions.add_argument("--execute", action="store_true")
    actions.add_argument("--sync-only", action="store_true")
    parser.add_argument("--resume", action="store_true")
    args = parser.parse_args()
    if args.resume and not args.execute:
        raise ValueError("--resume requires --execute")
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root / ".env")
    config_path = (root / args.config).resolve()
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8-sig"))
    check_settings(cfg)
    plan = build_plans(root, config_path, sample_mode(cfg))[0]
    print(f"{'SAMPLE' if sample_mode(cfg) else 'PRODUCTION'} plan hash={plan['config_hash']}; epochs={cfg['experiments'][0]['training']['num_train_epochs']}; snapshots={cfg['experiments'][0]['artifacts']['save_epochs']}", flush=True)
    if not (args.check_connections or args.execute or args.sync_only):
        print("PREVIEW: no database connection, download, training or upload.")
        return
    for name in ("HF_TOKEN", "HF_REPO_ID", "DATABASE_URL"):
        if not os.getenv(name):
            raise ValueError(f"Missing environment variable: {name}")
    from huggingface_hub import HfApi
    api = HfApi(token=os.environ["HF_TOKEN"])
    api.whoami()
    repo_id = os.environ["HF_REPO_ID"]
    if not api.repo_info(repo_id=repo_id, repo_type="model").private:
        raise ValueError("Expected a private HF adapter repository")
    api.auth_check(repo_id=repo_id, repo_type="model", write=True)
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True,
                           connect_args={"connect_timeout": 15} if os.environ["DATABASE_URL"].startswith("postgres") else {})
    lease = None
    try:
        record = get_run(engine, plan)
        if record["is_sample"] != sample_mode(cfg):
            raise ValueError("Registered run dataset mode differs from this request")
        rows = artifact_rows(engine, record["run_id"])
        if {row["trained_epoch"] for row in rows} != set(cfg["experiments"][0]["artifacts"]["save_epochs"]):
            raise ValueError("Expected registered epoch-4 and epoch-5 artifacts")
        print(f"RUN {record['run_id']} status={record['status']}")
        for row in rows:
            print(f"  epoch={row['trained_epoch']} weight_id={row['weight_id']} status={row['status']}")
        if args.check_connections:
            print("CONNECTIONS PASSED: HF read/write authorization and existing Neon records. No writes/training/upload.")
            return
        metadata.create_all(engine)  # Adds lease table; existing run/artifact tables are preserved.
        lease = RunLease(engine, record["run_id"]).acquire()
        if all(row["status"] in ("TRAINED", "EVALUATED") for row in rows):
            if args.execute and not args.resume:
                raise ValueError("This experiment is already trained. Submit a NEW experiment or explicitly evaluate the existing weights.")
            set_run_status(engine, lease, "TRAINED")
            print("SKIP: both epoch artifacts are already uploaded.")
            return
        output = factory_output(root,record["run_id"],plan["config"]["is_sample"])
        # Recover completed local snapshots first, including upload-success/DB-failure cases.
        for row in rows:
            path = output / "artifacts" / row["weight_id"]
            if row["status"] not in ("TRAINED", "EVALUATED") and path.is_dir():
                set_local_saved(engine, lease, row["weight_id"])
                upload_snapshot(api, engine, lease, repo_id, path, row, plan)
        rows = artifact_rows(engine, record["run_id"])
        if not all(row["status"] in ("TRAINED", "EVALUATED") for row in rows) and not args.sync_only:
            train(root, cfg, config_path, plan, record, engine, lease, api, repo_id, args)
        rows = artifact_rows(engine, record["run_id"])
        done = all(row["status"] in ("TRAINED", "EVALUATED") for row in rows)
        set_run_status(engine, lease, "TRAINED" if done else "INCOMPLETE")
        for row in rows:
            print(f"FINAL epoch={row['trained_epoch']} weight_id={row['weight_id']} status={row['status']} repo={row['hf_repo_id']} path={row['hf_subfolder']} revision={row['hf_revision']}")
        print(("FACTORY SAMPLE PASSED" if sample_mode(cfg) else "FACTORY PRODUCTION PASSED") if done else "SYNC FINISHED; training/checkpoints still required")
    except BaseException:
        if lease:
            try:
                set_run_status(engine, lease, "FAILED")
            except Exception:
                pass
        raise
    finally:
        if lease:
            try:
                lease.release()
            except Exception:
                print("Lease cleanup unavailable; it will expire automatically.")
        engine.dispose()


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Database exception tracebacks may contain credentials. Never emit them.
        print(f"FAILED ({type(error).__name__}). Local files were preserved.")
        if isinstance(error, (ValueError, RuntimeError, FileNotFoundError)):
            message = str(error)
            if not any(secret in message for secret in ("postgresql", "npg_", "hf_")):
                print(message)
        print("Check package versions, dataset lengths, HF/DB connectivity and the run's local files before retrying.")
        sys.exit(1)
