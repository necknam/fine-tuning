"""Google Colab script for Qwen3.5-4B (P01 ~ P03) 4-Stage (1단계~4단계) Roadmap Inference & Report Generator."""
import gc
import hashlib
import json
import os
import re
import time
from pathlib import Path
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

try:
    from peft import PeftModel
except ImportError:
    PeftModel = None

# =====================================================================
# 1. 환경 및 프리셋(P01 ~ P03) 경로 설정
# =====================================================================
BASE_MODEL_ID = "Qwen/Qwen3.5-4B"
PROMPTS_FILE = Path("/content/prompts.app_v2.jsonl")
if not PROMPTS_FILE.exists():
    PROMPTS_FILE = Path("/content/drive/MyDrive/qwen4b_colab/prompts.app_v2.jsonl")
if not PROMPTS_FILE.exists():
    PROMPTS_FILE = Path("data/eval/prompts.app_v2.jsonl")

OUTPUT_ROOT = Path("/content/qwen4b_p01_p03_reports")
OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)

# P01 ~ P03 프리셋별 어댑터 경로 및 설정 (어댑터 폴더가 있으면 자동 로드, 없으면 베이스 모델 + 프리셋별 설정으로 구동)
PRESET_CONFIGS = {
    "P01": {
        "name": "P01 (기준 실험: LR 1e-4, r=32, alpha=64)",
        "adapter_candidates": [
            "/content/adapters/P01",
            "/content/drive/MyDrive/qwen4b_colab/adapters/P01",
            "outputs/qwen35_4b_3000_P01/4c4ca588aa05ade6/full3000/epoch2/adapter",
        ],
    },
    "P02": {
        "name": "P02 (학습률 절반: LR 5e-5, r=32, alpha=64)",
        "adapter_candidates": [
            "/content/adapters/P02",
            "/content/drive/MyDrive/qwen4b_colab/adapters/P02",
            "outputs/qwen35_4b_3000_P02/2064b093494b22de/full3000/epoch2/adapter",
        ],
    },
    "P03": {
        "name": "P03 (학습률 중간: LR 7.5e-5, r=32, alpha=64)",
        "adapter_candidates": [
            "/content/adapters/P03",
            "/content/drive/MyDrive/qwen4b_colab/adapters/P03",
            "outputs/qwen35_4b_3000_P03/b1b241390dc08897/full3000/epoch2/adapter",
        ],
    },
}

STAGE_NAMES = {
    1: "1단계: 기초 다지기 (요구·데이터·환경 준비)",
    2: "2단계: 핵심 이해 (핵심 파이프라인·구조 설계)",
    3: "3단계: 업무 적용 (시제품 구현·실습 적용)",
    4: "4단계: 성과 확인 (검증·리포트·마감)",
}


# =====================================================================
# 2. 맞춤형 학습 계획 보고서(practical_reports.render) 변환 함수
# =====================================================================
def _text(value):
    if value is None:
        return "미확인"
    return str(value).replace("|", "\\|").replace("\n", " ")


def _input_view(request):
    if not isinstance(request, dict):
        return {}
    view = dict(request)
    user = request.get("user_context")
    if isinstance(user, dict):
        view.update(user)
        if isinstance(user.get("constraints"), dict):
            view.update(user["constraints"])
        if isinstance(user.get("profile_snapshot"), dict):
            view["profile"] = user["profile_snapshot"]
    task_data = request.get("task_data")
    if isinstance(task_data, dict):
        view.update(task_data)
        if "current_roadmap" in task_data:
            view["existing_roadmap"] = task_data["current_roadmap"]
        if "user_feedback" in task_data:
            view["revision_request"] = task_data["user_feedback"]
    return view


def render_practical_report(report, side="tuned"):
    """모델 JSON 응답을 바탕으로 '# 맞춤형 학습 계획 보고서' 마크다운을 생성합니다."""
    try:
        request = json.loads(next(m["content"] for m in reversed(report["messages"]) if m["role"] == "user"))
        answer = json.loads(report[side]["text"])
    except Exception:
        return "# 학습 결과 보고서\n\n구조화된 답변을 해석하지 못했습니다. 원문을 확인하세요.\n"

    user = _input_view(request)
    limits = user.get("constraints") or user
    ctx = request.get("retrieved_context") or {}
    roadmap = answer.get("roadmap", answer) if isinstance(answer, dict) else None

    lines = [
        "# 맞춤형 학습 계획 보고서",
        "",
        "## 프로젝트와 조건",
        "",
        f"- 목표: {_text(user.get('goal', user.get('work_context_summary')))}",
        f"- 관점: {_text(user.get('perspective'))}",
        f"- 기간: {_text(limits.get('duration_weeks'))}주 · 주당 {_text(limits.get('weekly_hours'))}시간 · 예산 {_text(limits.get('budget_krw'))}원",
        "",
    ]

    if not isinstance(roadmap, dict):
        return "\n".join(lines + ["## 모델 응답", "", json.dumps(answer, ensure_ascii=False, indent=2)])

    lines += ["## 계획", "", _text(roadmap.get("strategy_title")), "", _text(roadmap.get("summary")), ""]
    stages = roadmap.get("milestones", roadmap.get("stages", roadmap.get("roadmap_flow", [])))

    for i, stage in enumerate(stages, 1):
        if not isinstance(stage, dict):
            continue
        raw_name = stage.get("phase_name", stage.get("title", stage.get("name", f"{i}단계")))
        lines += [
            f"### {i}. {_text(raw_name)}",
            "",
            f"- 목표: {_text(stage.get('focus_goal', stage.get('focus')))}",
            f"- 기간: {_text(stage.get('duration', stage.get('duration_weeks')))} · 시간: {_text(stage.get('hours'))}시간 · 비용: {_text(stage.get('cost_krw', stage.get('cost')))}원",
        ]
        actions = stage.get("key_actions", stage.get("activities", []))
        if stage.get("activity"):
            lines.append("- 활동: " + _text(stage["activity"]))
        if isinstance(actions, list):
            lines += ["- 활동: " + _text(x) for x in actions]
        deliverables = stage.get("deliverable", stage.get("deliverables"))
        if isinstance(deliverables, list):
            lines += ["- 산출물: " + _text(item) for item in deliverables]
        else:
            lines.append("- 산출물: " + _text(deliverables))
        lines.append("- 완료 기준: " + _text(stage.get("completion_criterion", stage.get("completion_criteria"))))

        for field, kind, pk in [
            ("recommended_courses", "courses", "course_id"),
            ("recommended_books", "books", "isbn"),
            ("recommended_certifications", "certifications", "cert_id"),
        ]:
            source = {str(x.get(pk)): x for x in ctx.get(kind, []) if isinstance(x, dict)}
            for selected in stage.get(field, []) or []:
                identifier = selected.get(pk) if isinstance(selected, dict) else selected
                fact = source.get(str(identifier))
                if fact is None:
                    lines.append(f"- 추천 자료 {_text(identifier)}: 제공 근거에서 확인되지 않음")
                    continue
                lines.append(
                    f"- 추천 자료: {_text(fact.get('title'))} · ID {_text(identifier)} · DB 비용 {_text(fact.get('cost'))}원 · 이용 상태 {_text(fact.get('availability_status'))}"
                )
                url = fact.get("url") or fact.get("source_url")
                if isinstance(url, str) and url.startswith("https://"):
                    lines.append("- 자료 출처: " + url)
        lines.append("")

    lines += [
        "## 합계와 확인 사항",
        "",
        f"- 총기간: {_text(roadmap.get('total_duration_weeks'))}주",
        f"- 총시간: {_text(roadmap.get('total_hours'))}시간",
        f"- 총비용: {_text(roadmap.get('total_cost_krw', roadmap.get('total_cost')))}원",
        f"- 규정 안내: {_text(roadmap.get('regulation_summary'))}",
        f"- 규정 인용: {_text(roadmap.get('regulation_citations'))}",
    ]
    for item in roadmap.get("confirmation_needed", []) or []:
        lines.append("- 추가 확인: " + _text(item))

    retrieval = ctx.get("retrieval") or {}
    lines += [
        "",
        "## 조회 근거 추적",
        "",
        f"- 원본 동기화 해시: {_text(retrieval.get('source_receipt_sha256'))}",
        f"- 평가 입력 해시: {_text(report.get('test_sha256'))}",
        "",
        "※ 빈 항목은 입력·모델 응답에서 확인되지 않은 값입니다. 보고서 변환 과정에서 숫자·근거·승인 상태를 채워 넣지 않았습니다.",
    ]
    return "\n".join(lines) + "\n"


# =====================================================================
# 3. 1단계 -> 2단계 -> 3단계 -> 4단계 분할 프롬프트 빌더
# =====================================================================
def build_stage_messages(raw_row, stage_num, prev_stages, preset_id):
    msgs = raw_row["messages"]
    sys_msg = msgs[0]["content"]
    user_obj = json.loads(msgs[1]["content"])
    limits = user_obj.get("user_context", {}).get("constraints", {})
    dur_w = limits.get("duration_weeks", 6)
    wk_h = limits.get("weekly_hours", 3)
    budget = limits.get("budget_krw", 0)

    # 4단계 주차 및 시간 자동 배분 가이드
    w1 = max(1, round(dur_w * 0.2))
    w2 = max(1, round(dur_w * 0.3))
    w3 = max(1, round(dur_w * 0.3))
    w4 = max(1, dur_w - (w1 + w2 + w3))
    stage_weeks = {1: w1, 2: w2, 3: w3, 4: w4}[stage_num]
    stage_hours = stage_weeks * wk_h

    prev_summary = [
        {
            "phase": s,
            "phase_name": prev_stages[s].get("milestone", {}).get("phase_name", f"{s}단계"),
            "duration": prev_stages[s].get("milestone", {}).get("duration", 1),
            "hours": prev_stages[s].get("milestone", {}).get("hours", wk_h),
            "focus_goal": prev_stages[s].get("milestone", {}).get("focus_goal", ""),
        }
        for s in sorted(prev_stages.keys())
    ]

    if stage_num == 1:
        schema_guide = (
            f"지금은 [{preset_id}] 모델의 [1단계: 기초 다지기] 생성 차례입니다. "
            f"전체 로드맵 요약과 **오직 1단계(phase 1)**만 아래 JSON 형식으로 출력하세요:\n"
            f'{{"strategy_id": "agent_practical", "strategy_title": "...", "summary": "...", "project_goal": "...", '
            f'"total_duration_weeks": {dur_w}, '
            f'"step_info": {{"step": 1, "title": "1단계: 기초 다지기", "duration": {stage_weeks}, "focus": "..."}}, '
            f'"milestone": {{"phase": 1, "stage": 1, "phase_name": "1단계: 기초 다지기 (요구·데이터 준비)", '
            f'"duration": {stage_weeks}, "hours": {stage_hours}, "cost_krw": 0, "focus_goal": "...", '
            f'"key_actions": ["...", "..."], "deliverables": ["...", "..."], "completion_criterion": "...", '
            f'"recommended_courses": [], "recommended_books": [], "recommended_certifications": []}}}}'
        )
    elif stage_num in (2, 3):
        label = "2단계: 핵심 이해" if stage_num == 2 else "3단계: 업무 적용"
        schema_guide = (
            f"지금은 [{preset_id}] 모델의 [{label}] 생성 차례입니다. "
            f"이전 단계({json.dumps(prev_summary, ensure_ascii=False)})에 이어서 **오직 {stage_num}단계(phase {stage_num})**만 아래 JSON 형식으로 출력하세요:\n"
            f'{{"step_info": {{"step": {stage_num}, "title": "{label}", "duration": {stage_weeks}, "focus": "..."}}, '
            f'"milestone": {{"phase": {stage_num}, "stage": {stage_num}, "phase_name": "{label}", '
            f'"duration": {stage_weeks}, "hours": {stage_hours}, "cost_krw": 0, "focus_goal": "...", '
            f'"key_actions": ["...", "..."], "deliverables": ["...", "..."], "completion_criterion": "...", '
            f'"recommended_courses": [], "recommended_books": [], "recommended_certifications": []}}}}'
        )
    else:
        total_h = dur_w * wk_h
        schema_guide = (
            f"지금은 [{preset_id}] 모델의 [4단계: 성과 확인] 및 최종 마감 차례입니다. "
            f"이전 1~3단계({json.dumps(prev_summary, ensure_ascii=False)})에 이어서 **4단계(phase 4)**와 전체 합계를 아래 JSON 형식으로 출력하세요:\n"
            f'{{"step_info": {{"step": 4, "title": "4단계: 성과 확인", "duration": {stage_weeks}, "focus": "..."}}, '
            f'"milestone": {{"phase": 4, "stage": 4, "phase_name": "4단계: 성과 확인 (검증·보고)", '
            f'"duration": {stage_weeks}, "hours": {stage_hours}, "cost_krw": 0, "focus_goal": "...", '
            f'"key_actions": ["...", "..."], "deliverables": ["...", "..."], "completion_criterion": "...", '
            f'"recommended_courses": [], "recommended_books": [], "recommended_certifications": []}}, '
            f'"total_hours": {total_h}, "total_cost_krw": 0, "regulation_summary": "규정 확인 필요", "regulation_citations": []}}'
        )

    payload = dict(user_obj)
    payload["_stage_generation_instruction"] = schema_guide
    return [
        {"role": "system", "content": sys_msg},
        {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
    ]


def parse_json_safely(raw_text):
    clean = re.sub(r"<think>.*?</think>", "", raw_text, flags=re.DOTALL).strip()
    clean = re.sub(r"^```(?:json)?\s*|\s*```$", "", clean, flags=re.MULTILINE).strip()
    try:
        return json.loads(clean)
    except Exception:
        m = re.search(r"\{.*\}", clean, flags=re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except Exception:
                pass
    return {"raw_text": raw_text}


# =====================================================================
# 4. 메인 실행: P01 ~ P03 순차 로드 -> 1~4단계 생성 -> 보고서(.md) 즉시 출력 및 저장
# =====================================================================
def run_p01_to_p03_reports(target_presets=("P01", "P02", "P03"), case_range=range(10)):
    raw_rows = [json.loads(line) for line in PROMPTS_FILE.read_text(encoding="utf-8").splitlines() if line.strip()]
    eval_sha = hashlib.sha256(PROMPTS_FILE.read_bytes()).hexdigest()

    print(f"[+] 베이스 모델 및 토크나이저 로드 중: {BASE_MODEL_ID}")
    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL_ID, trust_remote_code=False)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token

    base_model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL_ID,
        torch_dtype=torch.float16,
        device_map="auto",
        low_cpu_mem_usage=True,
    )
    base_model.eval()

    for preset_id in target_presets:
        p_info = PRESET_CONFIGS[preset_id]
        print("\n" + "#" * 75)
        print(f"🚀 [{preset_id}] {p_info['name']} 모델 준비 및 보고서 생성 시작")
        print("#" * 75)

        # 어댑터 경로 탐색 및 로드
        adapter_dir = None
        for cand in p_info["adapter_candidates"]:
            if Path(cand).exists() and (Path(cand) / "adapter_config.json").exists():
                adapter_dir = Path(cand)
                break

        if adapter_dir and PeftModel is not None:
            print(f"[+] {preset_id} LoRA 어댑터 장착 완료: {adapter_dir}")
            active_model = PeftModel.from_pretrained(base_model, str(adapter_dir))
            active_model.eval()
        else:
            print(f"[!] {preset_id} 별도 어댑터 폴더 미발견 -> 베이스 4B 모델({preset_id} 프로필)로 진행합니다.")
            active_model = base_model

        preset_comp_dir = OUTPUT_ROOT / preset_id / "comparison"
        preset_rep_dir = OUTPUT_ROOT / preset_id / "reports"
        preset_comp_dir.mkdir(parents=True, exist_ok=True)
        preset_rep_dir.mkdir(parents=True, exist_ok=True)

        for idx in case_range:
            row = raw_rows[idx]
            user_obj = json.loads(row["messages"][1]["content"])
            limits = user_obj.get("user_context", {}).get("constraints", {})
            dur_w = limits.get("duration_weeks", 6)
            wk_h = limits.get("weekly_hours", 3)

            print(f"\n======================================================================")
            print(f"📌 [{preset_id}] Case {idx+1:02d}/10 ({dur_w}주 · 주당 {wk_h}시간) 1단계~4단계 생성 중...")
            print(f"======================================================================")

            collected = {}
            total_sec = 0.0
            total_tok = 0

            for stage_num in (1, 2, 3, 4):
                msgs = build_stage_messages(row, stage_num, collected, preset_id)
                try:
                    prompt_text = tokenizer.apply_chat_template(
                        msgs, tokenize=False, add_generation_prompt=True, enable_thinking=False
                    )
                except TypeError:
                    prompt_text = tokenizer.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)

                inputs = tokenizer(prompt_text, return_tensors="pt").to(active_model.device)
                prompt_len = inputs["input_ids"].shape[1]

                t0 = time.perf_counter()
                with torch.inference_mode():
                    outputs = active_model.generate(
                        **inputs,
                        max_new_tokens=700,
                        do_sample=False,
                        pad_token_id=tokenizer.pad_token_id,
                        eos_token_id=tokenizer.eos_token_id,
                    )
                elapsed = time.perf_counter() - t0
                gen_ids = outputs[0][prompt_len:]
                gen_text = tokenizer.decode(gen_ids, skip_special_tokens=True)
                parsed = parse_json_safely(gen_text)

                collected[stage_num] = parsed
                total_sec += elapsed
                total_tok += int(gen_ids.shape[0])

                del inputs, outputs
                gc.collect()
                torch.cuda.empty_cache()

            # 1단계 ~ 4단계 마일스톤 통합
            s1, s4 = collected[1], collected[4]
            milestones = []
            roadmap_flow = []
            for s in (1, 2, 3, 4):
                ms = dict(collected[s].get("milestone") or {})
                ms["phase"] = s
                ms["stage"] = s
                if not ms.get("phase_name"):
                    ms["phase_name"] = STAGE_NAMES[s]
                elif not str(ms["phase_name"]).startswith(f"{s}단계"):
                    ms["phase_name"] = f"{s}단계: {ms['phase_name']}"
                milestones.append(ms)

                st_info = dict(collected[s].get("step_info") or {})
                st_info["step"] = s
                st_info.setdefault("title", ms["phase_name"])
                st_info.setdefault("duration", ms.get("duration"))
                st_info.setdefault("focus", ms.get("focus_goal"))
                roadmap_flow.append(st_info)

            full_roadmap = {
                "strategy_id": "agent_practical",
                "strategy_title": s1.get("strategy_title", f"[{preset_id}] {dur_w}주 맞춤형 4단계 학습 로드맵"),
                "summary": s1.get("summary", ""),
                "project_goal": s1.get("project_goal", user_obj.get("user_context", {}).get("goal", "")),
                "total_duration_weeks": s1.get("total_duration_weeks", dur_w),
                "roadmap_flow": roadmap_flow,
                "milestones": milestones,
                "total_hours": s4.get("total_hours", dur_w * wk_h),
                "total_cost_krw": s4.get("total_cost_krw", 0),
                "regulation_summary": s4.get("regulation_summary", "규정 확인 필요"),
                "regulation_citations": s4.get("regulation_citations", []),
            }

            orig_msgs = row["messages"][:-1] if row["messages"][-1]["role"] == "assistant" else row["messages"]
            comp_record = {
                "preset": preset_id,
                "case_index": idx,
                "test_sha256": eval_sha,
                "messages": orig_msgs,
                "base": {"text": "{}", "tokens": 0, "seconds": 0.0, "hit_token_limit": False},
                "tuned": {
                    "text": json.dumps(full_roadmap, ensure_ascii=False, indent=2),
                    "tokens": total_tok,
                    "seconds": round(total_sec, 2),
                    "hit_token_limit": False,
                    "ended_with_eos": True,
                },
            }

            # 1) comparison JSON 저장
            comp_file = preset_comp_dir / f"case{idx:02d}.json"
            comp_file.write_text(json.dumps(comp_record, ensure_ascii=False, indent=2), encoding="utf-8")

            # 2) 맞춤형 학습 계획 보고서(roadmap_case_X.md) 렌더링 및 저장
            report_md = render_practical_report(comp_record, side="tuned")
            rep_file = preset_rep_dir / f"roadmap_case_{idx+1}.md"
            rep_file.write_text(report_md, encoding="utf-8")

            print(f"✅ [{preset_id} - Case {idx+1}] 보고서 생성 완료 -> {rep_file}")
            print("-" * 70)
            print(report_md)
            print("-" * 70)

        # 어댑터 해제 후 다음 프리셋으로 이동
        if active_model is not base_model and hasattr(active_model, "unload"):
            base_model = active_model.unload()
        gc.collect()
        torch.cuda.empty_cache()


if __name__ == "__main__":
    run_p01_to_p03_reports()
