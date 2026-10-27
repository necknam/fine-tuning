"""Run real B200 GPU inference (model.generate) on the new 10 evaluation inputs
(data/eval/prompts.app_v2.jsonl) for:
1) 4B P01 (Epoch 2 & Epoch 5) — which was previously inferred on old 2-week inputs before 19:34 KST.
2) All 17 saved 27B weights (P01 Ep2/3/4/5, P02 Ep2/5, P03 Ep2/5, P03-r64 Ep5, P04 Ep2/5, P05 Ep2/5, P06 Ep2/5, v4 Ep2/5).

Designed to run automatically right after 4B P03 completes and before 4B P04 starts.
"""
import contextlib
import gc
import hashlib
import json
import os
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from compare_factory_sample import load_case, trim_generated, inference_packages
from model_runtime import configure

EVAL_PATH = ROOT / "data/eval/prompts.app_v2.jsonl"
DONE_RECEIPT = ROOT / "outputs/new_input_re_inference_done.json"
OUT_27B_DIR = ROOT / "outputs/new_input_27b_comparisons"

TARGETS_27B = [
    ("2f7ede81-6b5d-4802-95d6-ca583678c885", "27B_P01_epoch2", 2, "/workspace/qwen_factory/outputs/factory_production/8384be92-5824-584c-a762-843adec7762c/artifacts/2f7ede81-6b5d-4802-95d6-ca583678c885"),
    ("f86ac282-2bf0-4b20-a47e-20e9dc9d3fd5", "27B_P01_epoch3", 3, "/workspace/qwen_factory/outputs/B200_P01_epoch3/adapter"),
    ("1fab6e79-6832-49ba-91d5-4b590b51dd71", "27B_P01_epoch4", 4, "/workspace/qwen_factory/outputs/B200_P01_epoch4/adapter"),
    ("79fc310b-7fda-417e-add8-2a392aeb1885", "27B_P01_epoch5", 5, "/workspace/qwen_factory/outputs/factory_production/8384be92-5824-584c-a762-843adec7762c/artifacts/79fc310b-7fda-417e-add8-2a392aeb1885"),
    ("b00e9fe3-bce1-4976-b73a-6b1b539bb9eb", "27B_P02_epoch2", 2, "/workspace/qwen_factory/outputs/factory_production/e1e9e419-6d96-460d-accd-dc3360294bf1/artifacts/b00e9fe3-bce1-4976-b73a-6b1b539bb9eb"),
    ("4c9ca4c9-7a26-4ff6-a3a1-027f7b67e05c", "27B_P02_epoch5", 5, "/workspace/qwen_factory/outputs/factory_production/e1e9e419-6d96-460d-accd-dc3360294bf1/artifacts/4c9ca4c9-7a26-4ff6-a3a1-027f7b67e05c"),
    ("967a3477-0997-4c4c-9732-c1a2710b5a5a", "27B_P03_epoch2", 2, "/workspace/qwen_factory/outputs/factory_production/cbf1bb00-9661-4e66-a1f7-26828c6178c8/artifacts/967a3477-0997-4c4c-9732-c1a2710b5a5a"),
    ("8428230a-085d-4f57-97a3-acee17d8668f", "27B_P03_epoch5", 5, "/workspace/qwen_factory/outputs/factory_production/cbf1bb00-9661-4e66-a1f7-26828c6178c8/artifacts/8428230a-085d-4f57-97a3-acee17d8668f"),
    ("85a7ff8c-ecc2-48f8-806c-cec8c3932483", "27B_P03_r64_epoch5", 5, "/workspace/qwen_factory/outputs/factory_production/9be70cef-a989-4166-8184-0f2a2aff66d1/artifacts/85a7ff8c-ecc2-48f8-806c-cec8c3932483"),
    ("f4db302c-63de-4403-a33d-623d89c73fd8", "27B_P04_epoch2", 2, "/workspace/qwen_factory/outputs/factory_production/1b116b03-d4fd-4b14-bcaa-77e025f3b68b/artifacts/f4db302c-63de-4403-a33d-623d89c73fd8"),
    ("9bbe9002-2b19-455b-b223-a4737b5fa3c1", "27B_P04_epoch5", 5, "/workspace/qwen_factory/outputs/factory_production/1b116b03-d4fd-4b14-bcaa-77e025f3b68b/artifacts/9bbe9002-2b19-455b-b223-a4737b5fa3c1"),
    ("d27d098b-2de7-44e7-bded-404984038277", "27B_P05_epoch2", 2, "/workspace/qwen_factory/outputs/factory_production/ddae8105-46b5-45c5-b566-02a41a090a60/artifacts/d27d098b-2de7-44e7-bded-404984038277"),
    ("0277b2b8-7534-4dde-8e6d-aba5f9b2828c", "27B_P05_epoch5", 5, "/workspace/qwen_factory/outputs/factory_production/ddae8105-46b5-45c5-b566-02a41a090a60/artifacts/0277b2b8-7534-4dde-8e6d-aba5f9b2828c"),
    ("949ec748-3558-4cf2-b98a-63e28f1d982e", "27B_P06_epoch2", 2, "/workspace/qwen_factory/outputs/factory_production/db9fe7cd-0ee1-4421-ae54-4f79fb96c5af/artifacts/949ec748-3558-4cf2-b98a-63e28f1d982e"),
    ("cf1bc031-5992-40bd-8fb1-b430efa4eebe", "27B_P06_epoch5", 5, "/workspace/qwen_factory/outputs/factory_production/db9fe7cd-0ee1-4421-ae54-4f79fb96c5af/artifacts/cf1bc031-5992-40bd-8fb1-b430efa4eebe"),
    ("4166f3e6-18ac-4421-8cb8-1e557eba5c6c", "27B_v4_epoch2", 2, "/workspace/qwen_factory/outputs/factory_production/720d63a1-f0ee-4078-af09-db3159357660/artifacts/4166f3e6-18ac-4421-8cb8-1e557eba5c6c"),
    ("6514b194-9e41-4071-afc3-9184a4b9a7a1", "27B_v4_epoch5", 5, "/workspace/qwen_factory/outputs/factory_production/720d63a1-f0ee-4078-af09-db3159357660/artifacts/6514b194-9e41-4071-afc3-9184a4b9a7a1"),
]


def digest(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def atomic(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)


def run_4b_p01_reinference():
    import torch
    from transformers import AutoModelForImageTextToText, AutoTokenizer
    from peft import PeftModel
    from huggingface_hub import snapshot_download

    p01_folder = ROOT / "outputs/qwen35_4b_3000_P01/4c4ca588aa05ade6/full3000"
    if not p01_folder.exists():
        print("[!] 4B P01 folder not found, skipping 4B P01 re-inference.", flush=True)
        return

    print("\n=== [Step 1/2] Starting 4B P01 (Epoch 2 & 5) Real GPU Inference on New 10 Inputs ===", flush=True)
    configure({"runtime": {"linear_attention_backend": "installed"}})
    os.environ.setdefault("TRITON_CACHE_DIR", "/tmp/qwen35_4b_triton_cache")
    os.environ.setdefault("TORCHINDUCTOR_CACHE_DIR", "/tmp/qwen35_4b_inductor_cache")

    staged = snapshot_download(
        "Qwen/Qwen3.5-4B",
        revision="851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a",
        cache_dir="/dev/shm/qwen35_4b_model_cache",
        token=False,
    )
    tok = AutoTokenizer.from_pretrained(staged, local_files_only=True, trust_remote_code=False)
    if tok.pad_token_id is None:
        tok.pad_token = tok.eos_token
    tok.padding_side = "right"

    base = AutoModelForImageTextToText.from_pretrained(
        staged,
        local_files_only=True,
        trust_remote_code=False,
        dtype=torch.bfloat16,
        device_map={"": 0},
        attn_implementation="sdpa",
    )

    eval_sha = digest(EVAL_PATH)
    # Generate base outputs once on the 10 new inputs so Epoch 2 and Epoch 5 share identical BF16 base responses
    base_outputs = {}
    base.eval()
    print("[4B P01] Generating BF16 Base responses for 10 new cases...", flush=True)
    for i in range(10):
        messages, reference = load_case(EVAL_PATH, i)
        inputs = tok.apply_chat_template(
            messages,
            tokenize=True,
            enable_thinking=False,
            add_generation_prompt=True,
            return_dict=True,
            return_tensors="pt",
        ).to(base.device)
        started = time.perf_counter()
        with torch.inference_mode():
            ids = base.generate(**inputs, do_sample=False, max_new_tokens=4096, pad_token_id=tok.pad_token_id)
        gen = ids[0, inputs["input_ids"].shape[-1] :]
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - started
        base_outputs[i] = {
            "text": tok.decode(gen, skip_special_tokens=True),
            "tokens": len(gen),
            "hit_token_limit": len(gen) >= 4096,
            "seconds": elapsed,
        }
        print(f"  [4B Base] Case {i+1}/10 done ({len(gen)} tokens in {elapsed:.1f}s)", flush=True)

    for epoch in (2, 5):
        adapter = p01_folder / f"epoch{epoch}" / "adapter"
        snap = json.loads((adapter / "snapshot.json").read_text(encoding="utf-8"))
        contract = dict(snap["contract"])
        contract["evaluation_sha256"] = eval_sha

        comp_dir = p01_folder / f"epoch{epoch}" / "comparison"
        backup_dir = p01_folder / f"epoch{epoch}" / "comparison_old_2week_backup"
        if comp_dir.exists() and not backup_dir.exists():
            shutil.copytree(comp_dir, backup_dir)

        model = PeftModel.from_pretrained(base, adapter, is_trainable=False)
        model.eval()
        print(f"[4B P01 Epoch {epoch}] Generating tuned responses for 10 new cases...", flush=True)
        for i in range(10):
            out = comp_dir / f"case{i:02d}.json"
            messages, reference = load_case(EVAL_PATH, i)
            inputs = tok.apply_chat_template(
                messages,
                tokenize=True,
                enable_thinking=False,
                add_generation_prompt=True,
                return_dict=True,
                return_tensors="pt",
            ).to(model.device)
            started = time.perf_counter()
            with torch.inference_mode():
                ids = model.generate(**inputs, do_sample=False, max_new_tokens=4096, pad_token_id=tok.pad_token_id)
            gen = ids[0, inputs["input_ids"].shape[-1] :]
            torch.cuda.synchronize()
            elapsed = time.perf_counter() - started
            tuned_out = {
                "text": tok.decode(gen, skip_special_tokens=True),
                "tokens": len(gen),
                "hit_token_limit": len(gen) >= 4096,
                "seconds": elapsed,
            }
            atomic(
                out,
                {
                    "contract": contract,
                    "epoch": epoch,
                    "case_index": i,
                    "messages": messages,
                    "reference_unreviewed": reference,
                    "adapter_sha256": digest(adapter / "adapter_model.safetensors"),
                    "base": base_outputs[i],
                    "tuned": tuned_out,
                    "semantic_review": "PENDING_ACTUAL_CONTENT_REVIEW",
                },
            )
            atomic(
                p01_folder / f"epoch{epoch}" / "comparison_status.json",
                {"completed": i + 1, "total": 10, "contract": contract},
            )
            print(f"  [4B P01 Ep{epoch}] Case {i+1}/10 done ({len(gen)} tokens in {elapsed:.1f}s)", flush=True)
        base = model.unload()
        del model

    del base
    gc.collect()
    torch.cuda.empty_cache()
    print("[+] 4B P01 (Epoch 2 & 5) Real GPU Inference Completed and Memory Cleared!\n", flush=True)


def run_27b_all_weights_reinference():
    import torch
    from transformers import AutoModelForImageTextToText, AutoTokenizer
    from peft import PeftModel

    print("\n=== [Step 2/2] Starting 27B All 17 Weights Real GPU Inference on New 10 Inputs ===", flush=True)
    os.environ["HF_HOME"] = "/workspace/.cache/huggingface"
    configure({"runtime": {"linear_attention_backend": "installed"}})

    model_snap = "/workspace/.cache/huggingface/hub/models--Qwen--Qwen3.8-27B/snapshots/1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0"
    if not os.path.exists(model_snap):
        model_snap = "Qwen/Qwen3.8-27B"

    first_adapter_path = TARGETS_27B[0][3]
    tokenizer = AutoTokenizer.from_pretrained(first_adapter_path, trust_remote_code=False)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"

    print(f"[27B] Loading BF16 Base Model from {model_snap}...", flush=True)
    base = AutoModelForImageTextToText.from_pretrained(
        model_snap,
        local_files_only=os.path.exists(model_snap),
        trust_remote_code=False,
        dtype=torch.bfloat16,
        device_map={"": 0},
        attn_implementation="sdpa",
    )
    base.eval()
    print(
        f"[27B] BF16 Base Model Ready: allocated={torch.cuda.memory_allocated()/2**30:.2f} GiB",
        flush=True,
    )

    max_new_tokens = 4096
    batch_size = 4
    generation = {
        "max_new_tokens": max_new_tokens,
        "do_sample": False,
        "num_beams": 1,
        "use_cache": True,
        "pad_token_id": tokenizer.pad_token_id,
        "eos_token_id": tokenizer.eos_token_id,
    }

    cases = [(idx, *load_case(EVAL_PATH, idx)) for idx in range(10)]
    test_digest = digest(EVAL_PATH)
    pkgs = inference_packages()

    def generate_batch_on(active_model, selected, disable_ctx=False):
        texts = [
            tokenizer.apply_chat_template(
                messages, tokenize=False, add_generation_prompt=True, enable_thinking=False
            )
            for _, messages, _ in selected
        ]
        inputs = tokenizer(texts, add_special_tokens=False, padding=True, return_tensors="pt").to("cuda:0")
        lengths = inputs["attention_mask"].sum(dim=1).tolist()
        torch.cuda.synchronize()
        start = time.perf_counter()
        ctx = active_model.disable_adapter() if disable_ctx else contextlib.nullcontext()
        with torch.inference_mode(), ctx:
            answer = active_model.generate(**inputs, **generation)
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - start
        responses = []
        for row in answer[:, inputs["input_ids"].shape[1] :].tolist():
            ids = trim_generated(row, tokenizer.eos_token_id)
            responses.append(
                {
                    "text": tokenizer.decode(ids, skip_special_tokens=True),
                    "tokens": len(ids),
                    "hit_token_limit": len(ids) >= max_new_tokens,
                    "ended_with_eos": bool(ids and ids[-1] == tokenizer.eos_token_id),
                    "seconds": elapsed,
                    "generation_batch_size": len(selected),
                }
            )
        return responses, lengths

    # Step 2A: Generate 27B Base responses once across the 10 new inputs
    OUT_27B_DIR.mkdir(parents=True, exist_ok=True)
    base_cache_file = OUT_27B_DIR / "base_27b_new_inputs.json"
    if base_cache_file.exists():
        print("[27B Base] Loading cached 27B base responses for new 10 inputs...", flush=True)
        cached_data = json.loads(base_cache_file.read_text(encoding="utf-8"))
        base_responses = {int(k): v for k, v in cached_data["responses"].items()}
        input_lengths = {int(k): v for k, v in cached_data["lengths"].items()}
    else:
        print("[27B Base] Generating 27B BF16 Base responses for new 10 inputs (batch_size=4)...", flush=True)
        base_responses = {}
        input_lengths = {}
        for offset in range(0, len(cases), batch_size):
            selected = cases[offset : offset + batch_size]
            resps, lens = generate_batch_on(base, selected, disable_ctx=False)
            for (c_idx, _, _), r, l in zip(selected, resps, lens):
                base_responses[c_idx] = r
                input_lengths[c_idx] = l
            print(
                f"  [27B Base] Cases {offset+1}~{offset+len(selected)}/10 done in {resps[0]['seconds']:.1f}s",
                flush=True,
            )
        atomic(
            base_cache_file,
            {"test_sha256": test_digest, "responses": base_responses, "lengths": input_lengths},
        )

    # Step 2B: Iterate through all 17 saved 27B adapters
    for idx_w, (wid, label, epoch, adapter_str) in enumerate(TARGETS_27B, 1):
        adapter_dir = Path(adapter_str)
        weight_out_dir = OUT_27B_DIR / wid
        if weight_out_dir.exists() and len(list(weight_out_dir.glob("case*.json"))) == 10:
            print(f"[{idx_w}/{len(TARGETS_27B)}] {label} ({wid[:8]}) already has 10 new-input cases. Skipping.", flush=True)
            continue

        if not (adapter_dir / "adapter_model.safetensors").exists():
            print(f"[!] Adapter missing at {adapter_dir}, skipping {wid}", flush=True)
            continue

        print(f"\n[{idx_w}/{len(TARGETS_27B)}] Loading 27B Adapter: {label} (epoch={epoch}, wid={wid[:8]})...", flush=True)
        manifest_path = adapter_dir / "factory_manifest.json"
        if manifest_path.exists():
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        else:
            manifest = {
                "weight_id": wid,
                "trained_epoch": epoch,
                "model": {
                    "base_model_id": "Qwen/Qwen3.8-27B",
                    "revision": "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0",
                },
            }
        manifest["weight_id"] = wid
        manifest["trained_epoch"] = epoch

        adapter_digest = digest(adapter_dir / "adapter_model.safetensors")
        model = PeftModel.from_pretrained(base, str(adapter_dir), is_trainable=False)
        model.eval()

        w_start = time.perf_counter()
        for offset in range(0, len(cases), batch_size):
            selected = cases[offset : offset + batch_size]
            torch.cuda.reset_peak_memory_stats()
            batch_context = hashlib.sha256(
                json.dumps(
                    [messages for _, messages, _ in selected],
                    sort_keys=True,
                    ensure_ascii=False,
                    separators=(",", ":"),
                ).encode()
            ).hexdigest()
            tuned_resps, lens = generate_batch_on(model, selected, disable_ctx=False)
            for (c_idx, messages, reference), tuned_r, in_len in zip(selected, tuned_resps, lens):
                base_r = base_responses[c_idx]
                result = {
                    "purpose": "fixed-input BF16 comparison; human evaluation scored separately",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "model": {
                        "base_model_id": "Qwen/Qwen3.8-27B",
                        "revision": "1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0",
                    },
                    "quantization": {"load_in_4bit": False, "dtype": "bfloat16"},
                    "training_quantization": {
                        "load_in_4bit": False,
                        "bnb_4bit_quant_type": "nf4",
                        "bnb_4bit_compute_dtype": "bfloat16",
                        "bnb_4bit_use_double_quant": True,
                    },
                    "adapter_path": adapter_str,
                    "factory_manifest": manifest,
                    "adapter_sha256": adapter_digest,
                    "test_sha256": test_digest,
                    "case_index": c_idx,
                    "evaluation_total": 10,
                    "evaluation_cohort": "report",
                    "messages": messages,
                    "reference_unreviewed": reference,
                    "reference_sha256": hashlib.sha256(reference.encode("utf-8")).hexdigest()
                    if reference is not None
                    else None,
                    "training_config_hash": manifest.get("config_hash"),
                    "reference_status": "fixed_dataset_answer_not_expert_validated"
                    if reference is not None
                    else "no_reference_output_comparison_only",
                    "generation": generation,
                    "input_tokens": in_len,
                    "inference_batch_size": len(selected),
                    "batch_context_sha256": batch_context,
                    "packages": pkgs,
                    "inference_runtime": {
                        "linear_attention_backend": "installed",
                        "requested_linear_attention_backend": "torch_reference",
                        "kernel_profile": "b200_triton360_verified",
                    },
                    "inference_memory": {
                        "peak_allocated_gib": torch.cuda.max_memory_allocated() / 2**30,
                        "peak_reserved_gib": torch.cuda.max_memory_reserved() / 2**30,
                    },
                    "base_reused": True,
                    "base_source_report": "outputs/new_input_27b_comparisons/base_27b_new_inputs.json",
                    "base": base_r,
                    "tuned": tuned_r,
                    "texts_identical": base_r["text"] == tuned_r["text"],
                }
                atomic(weight_out_dir / f"case{c_idx:02d}.json", result)
            print(
                f"  [{label}] Cases {offset+1}~{offset+len(selected)}/10 generated in {tuned_resps[0]['seconds']:.1f}s",
                flush=True,
            )

        base = model.unload()
        del model
        print(
            f"[+] Completed {label} ({wid[:8]}) in {time.perf_counter() - w_start:.1f}s",
            flush=True,
        )

    del base
    gc.collect()
    torch.cuda.empty_cache()
    print("\n[+] All 17 27B Weights Real GPU Inference Completed and Memory Cleared!", flush=True)


def main():
    if DONE_RECEIPT.exists():
        print(f"[+] Re-inference receipt already exists at {DONE_RECEIPT}. Skipping.", flush=True)
        return 0

    t0 = time.perf_counter()
    print("======================================================================", flush=True)
    print("  Starting Pre-P04 Full Real GPU Re-Inference on New 10 Eval Inputs", flush=True)
    print("======================================================================", flush=True)

    run_4b_p01_reinference()
    run_27b_all_weights_reinference()

    elapsed = time.perf_counter() - t0
    atomic(
        DONE_RECEIPT,
        {
            "status": "COMPLETED",
            "completed_at": datetime.now(timezone.utc).isoformat(),
            "elapsed_seconds": elapsed,
            "eval_sha256": digest(EVAL_PATH),
            "re_inferred_4b": ["P01_epoch2", "P01_epoch5"],
            "re_inferred_27b_count": len(TARGETS_27B),
        },
    )
    print(f"\n=== ALL NEW INPUT GPU INFERENCE COMPLETED IN {elapsed/60:.1f} MIN ===", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())

