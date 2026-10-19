"""Reload a local smoke adapter and compare one held-out synthetic input."""
import argparse
import hashlib
import importlib.metadata
import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4


def sha256(path):
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def load_case(path, index):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if index < 0 or index >= len(rows):
        raise ValueError("case-index is outside the test dataset")
    messages = rows[index]["messages"]
    if len(messages) < 2 or messages[-1]["role"] != "assistant":
        raise ValueError("Expected messages ending in an assistant reference answer")
    prompt = messages[:-1]
    if prompt[-1]["role"] != "user":
        raise ValueError("Prompt must end with a user message")
    return prompt, messages[-1]["content"]


def save_report(output, result):
    output.mkdir(parents=True, exist_ok=False)
    (output / "comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sections = ["# GrowPath · 간이 어댑터 재로드 비교", "",
        "> 기능 시험용 가상 입력입니다. 최종 평가용 입력과 점수는 아직 정하지 않았습니다.", "",
        f"- 기본 모델: {result['model']['base_model_id']}",
        f"- 모델 버전: {result['model']['revision']}",
        f"- 어댑터: {result['adapter_path']}",
        f"- 최대 생성 토큰: {result['generation']['max_new_tokens']}",
        "- 비교 방식: 같은 양자화 모델에서 어댑터 비활성화 / 활성화", "",
        "## 입력", "", json.dumps(result["messages"], ensure_ascii=False, indent=2), ""]
    for label, key in [("기본 모델", "base"), ("어댑터 적용", "tuned")]:
        item = result[key]
        sections += [f"## {label}", "",
            f"생성 토큰: {item['tokens']} / 시간: {item['seconds']:.2f}초 / 길이 제한 도달: {item['hit_token_limit']}",
            "", item["text"], ""]
    sections += ["## 해석", "", "출력이 같아도 로드 실패를 뜻하지 않습니다. 4스텝 학습으로 품질 향상을 판단할 수 없습니다.",
                 "길이 제한에 도달한 결과는 잘렸을 수 있습니다. 생성 시간에는 첫 호출 초기화 차이가 있으므로 속도 비교 근거로 사용하지 않습니다."]
    (output / "comparison.md").write_text("\n".join(sections) + "\n", encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/hyperparameters.sample.pinned.yaml")
    parser.add_argument("--adapter", default="outputs/smoke_002/adapter-step-4")
    parser.add_argument("--case-index", type=int, default=0)
    parser.add_argument("--max-new-tokens", type=int, default=512)
    args = parser.parse_args()
    if not 1 <= args.max_new_tokens <= 2048:
        raise ValueError("max-new-tokens must be 1..2048")
    root = Path(__file__).resolve().parents[1]
    import yaml
    from dotenv import load_dotenv
    load_dotenv(root / ".env")
    config_path = (root / args.config).resolve()
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8-sig"))
    revision = cfg["model"]["revision"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Use a pinned model revision")
    adapter = (root / args.adapter).resolve()
    adapter.relative_to(root / "outputs")
    for name in ("adapter_config.json", "adapter_model.safetensors"):
        if not (adapter / name).is_file():
            raise ValueError(f"Missing saved adapter file: {name}")
    manifest = json.loads((adapter.parent / "smoke_manifest.json").read_text(encoding="utf-8"))
    if manifest["model"] != cfg["model"] or manifest["config_sha256"] != sha256(config_path):
        raise ValueError("Config/model differs from this adapter's training manifest")
    test_path = root / "data/sample/eval/test.jsonl"
    messages, reference = load_case(test_path, args.case_index)

    import torch
    from peft import PeftModel
    from transformers import AutoModelForImageTextToText, AutoTokenizer, BitsAndBytesConfig
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise ValueError("Run in the existing single-GPU RunPod environment")
    q = cfg["quantization"]
    if not q["load_in_4bit"] or q["bnb_4bit_compute_dtype"] != "bfloat16":
        raise ValueError("Expected the 4-bit BF16 smoke configuration")
    common = dict(revision=revision, token=os.getenv("HF_TOKEN"), trust_remote_code=False)
    tokenizer = AutoTokenizer.from_pretrained(str(adapter), trust_remote_code=False)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    text = tokenizer.apply_chat_template(messages, tokenize=False,
        add_generation_prompt=True, enable_thinking=False)
    inputs = tokenizer(text, add_special_tokens=False, return_tensors="pt").to("cuda:0")
    if inputs["input_ids"].shape[1] > cfg["experiments"][0]["training"]["max_length"]:
        raise ValueError("Selected test prompt exceeds the configured length; no truncation performed")
    print("Loading pinned 4-bit base and saved step-4 adapter...", flush=True)
    base = AutoModelForImageTextToText.from_pretrained(cfg["model"]["base_model_id"],
        quantization_config=BitsAndBytesConfig(load_in_4bit=True,
            bnb_4bit_quant_type=q["bnb_4bit_quant_type"],
            bnb_4bit_compute_dtype=torch.bfloat16,
            bnb_4bit_use_double_quant=q["bnb_4bit_use_double_quant"]),
        dtype=torch.bfloat16, device_map={"": 0}, attn_implementation="sdpa", **common)
    model = PeftModel.from_pretrained(base, str(adapter), is_trainable=False)
    model.eval()
    layers = model.get_layer_status()
    if not layers or any(not layer.enabled or "default" not in layer.active_adapters for layer in layers):
        raise ValueError("Adapter is not active in every target layer")
    print(f"Adapter reload OK; active LoRA layers: {len(layers)}", flush=True)
    generation = {"max_new_tokens": args.max_new_tokens, "do_sample": False,
                  "num_beams": 1, "use_cache": True,
                  "pad_token_id": tokenizer.pad_token_id,
                  "eos_token_id": tokenizer.eos_token_id}

    def generate():
        torch.cuda.synchronize()
        start = time.perf_counter()
        with torch.inference_mode():
            answer = model.generate(**inputs, **generation)
        torch.cuda.synchronize()
        elapsed = time.perf_counter() - start
        ids = answer[0, inputs["input_ids"].shape[1]:].tolist()
        return {"text": tokenizer.decode(ids, skip_special_tokens=True), "tokens": len(ids),
                "hit_token_limit": len(ids) >= args.max_new_tokens,
                "ended_with_eos": bool(ids and ids[-1] == tokenizer.eos_token_id),
                "seconds": elapsed}

    print("Generating base response (adapter disabled)...", flush=True)
    with model.disable_adapter():
        base_response = generate()
    print("Generating tuned response (adapter enabled)...", flush=True)
    tuned_response = generate()
    result = {"purpose": "synthetic smoke only; no human evaluation score",
        "created_at": datetime.now(timezone.utc).isoformat(), "model": cfg["model"],
        "quantization": q, "adapter_path": args.adapter,
        "adapter_sha256": sha256(adapter / "adapter_model.safetensors"),
        "test_sha256": sha256(test_path), "case_index": args.case_index,
        "messages": messages, "reference_unreviewed": reference,
        "generation": generation, "input_tokens": inputs["input_ids"].shape[1],
        "packages": {name: importlib.metadata.version(name) for name in
                     ("torch", "transformers", "peft", "bitsandbytes")},
        "base": base_response, "tuned": tuned_response,
        "texts_identical": base_response["text"] == tuned_response["text"]}
    output = root / "reports" / ("smoke_compare_" + datetime.now().strftime("%Y%m%d_%H%M%S") + "_" + uuid4().hex[:6])
    save_report(output, result)
    print("\n=== BASE ===\n" + base_response["text"], flush=True)
    print("\n=== TUNED ===\n" + tuned_response["text"], flush=True)
    print(f"\nCOMPARE PASSED: {output}")
    print("No training, HF upload, DB writes or quality verdict performed.")


if __name__ == "__main__":
    main()
