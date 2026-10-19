"""Reload a sample factory adapter and generate one fixed evaluation input."""
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


def trim_generated(ids,eos_token_id):
    """Discard padding added after an individual sequence's EOS in a batch."""
    return ids[:ids.index(eos_token_id)+1] if eos_token_id in ids else ids


def load_case(path, index):
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8-sig").splitlines() if line.strip()]
    if index < 0 or index >= len(rows):
        raise ValueError("case-index is outside the test dataset")
    messages = rows[index]["messages"]
    if not isinstance(messages,list) or not messages:
        raise ValueError("Expected a non-empty messages list")
    reference=messages[-1]["content"] if messages[-1]["role"]=="assistant" else None
    prompt = messages[:-1] if reference is not None else messages
    if not prompt:
        raise ValueError("Evaluation input needs a user message")
    if prompt[-1]["role"] != "user":
        raise ValueError("Prompt must end with a user message")
    return prompt, reference


def save_report(output, result):
    output.mkdir(parents=True, exist_ok=False)
    (output / "comparison.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    sections = ["# GrowPath · 간이 어댑터 재로드 비교", "",
        "> 고정 입력의 기본 모델·어댑터 답변입니다. 품질 점수는 Streamlit에서 사람이 별도로 평가합니다.", "",
        f"- 기본 모델: {result['model']['base_model_id']}",
        f"- 모델 버전: {result['model']['revision']}",
        "- 평가 정밀도: 원본 BF16 (4비트 양자화 없음)",
        "- 학습 방식: 4비트 QLoRA 어댑터",
        f"- 어댑터: {result['adapter_path']}",
        f"- 최대 생성 토큰: {result['generation']['max_new_tokens']}",
        "- 비교 방식: 같은 원본 BF16 모델에서 어댑터 비활성화 / 활성화", "",
        "## 입력", "", json.dumps(result["messages"], ensure_ascii=False, indent=2), ""]
    for label, key in [("기본 모델", "base"), ("어댑터 적용", "tuned")]:
        item = result[key]
        sections += [f"## {label}", "",
            f"생성 토큰: {item['tokens']} / 시간: {item['seconds']:.2f}초 / 길이 제한 도달: {item['hit_token_limit']}",
            "", item["text"], ""]
    sections += ["## 해석", "", "출력이 같아도 로드 실패를 뜻하지 않습니다. 답변 생성 성공만으로 품질 향상을 판단할 수 없습니다.",
                 "길이 제한에 도달한 결과는 잘렸을 수 있습니다. 생성 시간에는 첫 호출 초기화 차이가 있으므로 속도 비교 근거로 사용하지 않습니다."]
    (output / "comparison.md").write_text("\n".join(sections) + "\n", encoding="utf-8")



def inference_packages():
    packages={}
    for name in ("torch","transformers","peft","bitsandbytes","causal-conv1d","flash-linear-attention","fla-core","einops","triton"):
        try:packages[name]=importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:pass
    return packages


def find_base_cache(root,cfg,messages,generation,manifest,batch_context):
    """Reuse only the identical BF16 base comparison, independent of the adapter."""
    names=("tokenizer.json","tokenizer_config.json","chat_template.jinja")
    hashes=manifest.get("file_sha256",{})
    if not batch_context or any(not hashes.get(name) for name in names):
        return None
    packages=inference_packages()
    for path in sorted((root/"reports").glob("smoke_compare_*/comparison.json"),reverse=True):
        data=json.loads(path.read_text(encoding="utf-8"))
        other=data.get("factory_manifest",{}).get("file_sha256",{})
        base=data.get("base",{})
        if (data.get("batch_context_sha256")==batch_context
            and data.get("packages")==packages
            and data.get("model")==cfg["model"]
            and data.get("quantization")=={"load_in_4bit":False,"dtype":"bfloat16"}
            and data.get("messages")==messages and data.get("generation")==generation
            and all(other.get(name)==hashes[name] for name in names)
            and base.get("text") and base.get("ended_with_eos") is True
            and base.get("hit_token_limit") is False):
            return path,base
    return None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", default="configs/hyperparameters.sample.pinned.yaml")
    parser.add_argument("--adapter", default="outputs/smoke_002/adapter-step-4")
    parser.add_argument("--case-index", type=int, default=0)
    parser.add_argument("--case-indices", type=int, nargs="+", help="Generate these cases with one shared BF16 model load")
    parser.add_argument("--max-new-tokens", type=int, default=512)
    parser.add_argument("--batch-size", type=int, choices=(1,2,4,8), default=None, help="Concurrent BF16 generation inputs")
    args = parser.parse_args()
    if not 1 <= args.max_new_tokens <= 2048:
        raise ValueError("max-new-tokens must be 1..2048")
    root = Path(__file__).resolve().parents[1]
    import yaml
    from dotenv import load_dotenv
    load_dotenv(root / ".env")
    config_path = (root / args.config).resolve()
    cfg = yaml.safe_load(config_path.read_text(encoding="utf-8-sig"))
    args.batch_size=args.batch_size or cfg.get("inference",{}).get("batch_size",1)
    if type(args.batch_size) is not int or args.batch_size not in (1,2,4,8):
        raise ValueError("inference.batch_size must be 1, 2, 4 or 8")
    revision = cfg["model"]["revision"]
    if not re.fullmatch(r"[0-9a-f]{40}", revision):
        raise ValueError("Use a pinned model revision")
    adapter = (root / args.adapter).resolve()
    adapter.relative_to(root / "outputs")
    for name in ("adapter_config.json", "adapter_model.safetensors"):
        if not (adapter / name).is_file():
            raise ValueError(f"Missing saved adapter file: {name}")
    manifest = json.loads(
        (adapter / "factory_manifest.json").read_text(encoding="utf-8")
    )
    runtime = json.loads(
        (adapter.parent.parent / "runtime_manifest.json")
        .read_text(encoding="utf-8")
    )
    from db_registry import sample_mode, build_plans
    if manifest.get("is_sample") is not sample_mode(cfg):
        raise ValueError("Sample/production adapter does not match this experiment")
    if cfg.get('experiment_id') or not sample_mode(cfg):
        plan=build_plans(root,config_path,sample_mode(cfg))[0]
        if manifest['config_hash']!=plan['config_hash']:
            raise ValueError("Adapter belongs to different training data or experiment")
    if manifest["model"] != cfg["model"] or runtime["model"] != cfg["model"]:
        raise ValueError("Base model/revision differs from training")
    if manifest["config_hash"] != runtime["config_hash"]:
        raise ValueError("Factory/runtime config hashes differ")
    if manifest["weight_id"] != adapter.name:
        raise ValueError("Adapter directory and weight_id differ")
    if manifest["run_id"] != adapter.parent.parent.name:
        raise ValueError("Adapter directory and run_id differ")
    for name, expected in manifest["file_sha256"].items():
        path = (adapter / name).resolve()
        path.relative_to(adapter)
        if sha256(path) != expected:
            raise ValueError(f"Saved artifact hash mismatch: {name}")
    print(
        f"Factory adapter verified: epoch={manifest['trained_epoch']} "
        f"weight_id={manifest['weight_id']}",
        flush=True,
    )
    test_path = (root / cfg["data"].get("test_file", "data/sample/eval/test.jsonl")).resolve()
    test_path.relative_to(root / "data")
    total_cases=sum(bool(line.strip()) for line in test_path.read_text(encoding="utf-8-sig").splitlines())
    indices=list(dict.fromkeys(args.case_indices if args.case_indices is not None else [args.case_index]))
    cases=[(index,*load_case(test_path,index)) for index in indices]
    adapter_digest=sha256(adapter/"adapter_model.safetensors")
    test_digest=sha256(test_path)

    import torch
    from peft import PeftModel
    from transformers import AutoModelForImageTextToText, AutoTokenizer
    if not torch.cuda.is_available() or torch.cuda.device_count() != 1:
        raise ValueError("Run in the existing single-GPU RunPod environment")
    evaluation_precision = {"load_in_4bit": False, "dtype": "bfloat16"}
    if not torch.cuda.is_bf16_supported():
        raise ValueError("BF16 evaluation requires a BF16-capable GPU")
    common = dict(revision=revision, token=os.getenv("HF_TOKEN"), trust_remote_code=False)
    tokenizer = AutoTokenizer.from_pretrained(str(adapter), trust_remote_code=False)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    tokenizer.padding_side = "left"
    print("진행 안내: 원본 BF16 기본 모델을 불러오고 저장한 LoRA 어댑터를 적용합니다.", flush=True)
    base = AutoModelForImageTextToText.from_pretrained(cfg["model"]["base_model_id"],
        dtype=torch.bfloat16, device_map={"": 0}, attn_implementation="sdpa", **common)
    model = PeftModel.from_pretrained(base, str(adapter), is_trainable=False)
    model.eval()
    print(f"BF16 MODEL READY: allocated={torch.cuda.memory_allocated()/2**30:.2f} GiB; reserved={torch.cuda.memory_reserved()/2**30:.2f} GiB; cases={len(cases)}",flush=True)
    layers = model.get_layer_status()
    if not layers or any(not layer.enabled or "default" not in layer.active_adapters for layer in layers):
        raise ValueError("Adapter is not active in every target layer")
    print(f"Adapter reload OK; active LoRA layers: {len(layers)}", flush=True)
    generation = {"max_new_tokens": args.max_new_tokens, "do_sample": False,
                  "num_beams": 1, "use_cache": True,
                  "pad_token_id": tokenizer.pad_token_id,
                  "eos_token_id": tokenizer.eos_token_id}

    def generate_batch(selected):
        texts=[tokenizer.apply_chat_template(messages,tokenize=False,
            add_generation_prompt=True,enable_thinking=False) for _,messages,_ in selected]
        inputs=tokenizer(texts,add_special_tokens=False,padding=True,return_tensors="pt").to("cuda:0")
        lengths=inputs["attention_mask"].sum(dim=1).tolist()
        if max(lengths)>cfg["experiments"][0]["training"]["max_length"]:
            raise ValueError("Selected test prompt exceeds the configured length; no truncation performed")
        torch.cuda.synchronize();start=time.perf_counter()
        with torch.inference_mode():answer=model.generate(**inputs,**generation)
        torch.cuda.synchronize();elapsed=time.perf_counter()-start
        responses=[]
        for row in answer[:,inputs["input_ids"].shape[1]:].tolist():
            ids=trim_generated(row,tokenizer.eos_token_id)
            responses.append({"text":tokenizer.decode(ids,skip_special_tokens=True),"tokens":len(ids),
                "hit_token_limit":len(ids)>=args.max_new_tokens,
                "ended_with_eos":bool(ids and ids[-1]==tokenizer.eos_token_id),
                "seconds":elapsed,"generation_batch_size":len(selected)})
        return responses,lengths

    for offset in range(0,len(cases),args.batch_size):
        selected=cases[offset:offset+args.batch_size]
        print(f"진행 안내: {manifest['trained_epoch']}에포크 · 입력 {offset+1}~{offset+len(selected)}/{len(cases)} · {len(selected)}개 동시 생성",flush=True)
        torch.cuda.reset_peak_memory_stats()
        batch_context=hashlib.sha256(json.dumps([messages for _,messages,_ in selected],
            sort_keys=True,ensure_ascii=False,separators=(",",":")).encode()).hexdigest()
        cached=[find_base_cache(root,cfg,messages,generation,manifest,batch_context) for _,messages,_ in selected]
        base_results={}
        if not all(cached):
            # Partial reuse would change batch shape/neighbours for the missing cases.
            cached=[None]*len(selected)
            with model.disable_adapter():responses,_=generate_batch(selected)
            base_results={case[0]:response for case,response in zip(selected,responses)}
        tuned_results,lengths=generate_batch(selected)
        for (case_index,messages,reference),cached_base,tuned_response,input_length in zip(selected,cached,tuned_results,lengths):
            base_response=cached_base[1] if cached_base else base_results[case_index]
            result={"purpose":"fixed-input BF16 comparison; human evaluation scored separately",
                "created_at":datetime.now(timezone.utc).isoformat(),"model":cfg["model"],
                "quantization":evaluation_precision,"training_quantization":cfg["quantization"],"adapter_path":args.adapter,
                "factory_manifest":manifest,"adapter_sha256":adapter_digest,
                "test_sha256":test_digest,"case_index":case_index,"evaluation_total":total_cases,
                "messages":messages,"reference_unreviewed":reference,"generation":generation,"input_tokens":input_length,
                "inference_batch_size":len(selected),
                "batch_context_sha256":batch_context,
                "packages":inference_packages(),
                "inference_memory":{"peak_allocated_gib":torch.cuda.max_memory_allocated()/2**30,"peak_reserved_gib":torch.cuda.max_memory_reserved()/2**30},
                "base_reused":cached_base is not None,"base_source_report":str(cached_base[0].relative_to(root)) if cached_base else None,
                "base":base_response,"tuned":tuned_response,"texts_identical":base_response["text"]==tuned_response["text"]}
            output=root/"reports"/("smoke_compare_"+datetime.now().strftime("%Y%m%d_%H%M%S")+"_"+uuid4().hex[:6])
            save_report(output,result)
            print(f"진행 안내: 입력 {case_index+1}/{total_cases} 저장 완료",flush=True)
            print(f"COMPARE PASSED: {output}",flush=True)
    print(f"BF16 BATCH COMPLETE: cases={len(cases)}; model_loads=1; batch_size={args.batch_size}",flush=True)
    print("No training, HF upload, DB writes or quality verdict performed.",flush=True)


if __name__ == "__main__":
    main()
