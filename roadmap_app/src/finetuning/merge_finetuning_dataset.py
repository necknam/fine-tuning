"""
방향 2 전면 다각화 병합기: 7대 에이전트 SFT 데이터셋 + DPO(chosen/rejected) 페어 동시 생성
파일 경로: src/finetuning/merge_finetuning_dataset.py
실행: python -m src.finetuning.merge_finetuning_dataset
"""
from __future__ import annotations
import argparse, hashlib, json, re, sys
from collections import Counter
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Set, Tuple

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.shared.config_loader import PROJECT_ROOT
from src.shared.dataset_integrity import VERSION, digest, validate_checkpoint, validate_record, validate_roadmap
from src.database.deployment import connect
from src.finetuning.export_finetuning_dataset import current_source_fingerprint
from src.finetuning.export_finetuning_dataset import fix_typos_in_structure, synthesize_markdown_plan, _normalize_duration

# 설문 복붙(Mode Collapse) 원천 차단용 10대 실무 엔지니어링 질문 템플릿 (스킬명 + 구체적 하위 메커니즘 결합)
DOMAIN_SURVEY_TEMPLATES = (
    "실무 환경에서 {skill}의 내부 동작 원리와 핵심 아키텍처 구성 요소를 설계하는 방법에 대해 얼마나 알고 있나요?",
    "현업 프로젝트에 {skill}을(를) 도입할 때 초기 환경 설정과 표준 모듈 구조를 구성하는 방법에 대해 얼마나 알고 있나요?",
    "{skill} 적용 구간에서 발생하는 성능 병목이나 실행 오류의 원인을 로그와 지표로 진단하는 방법에 대해 얼마나 알고 있나요?",
    "트래픽 규모와 시스템 제약 조건에 맞춰 {skill}의 설계 트레이드오프(성능·일관성·비용)를 결정하는 기준을 얼마나 알고 있나요?",
    "{skill} 운영 중 대용량 부하가 집중될 때 리소스 고갈을 막고 처리량을 최적화하는 튜닝 기법에 대해 얼마나 알고 있나요?",
    "외부 연동 지연이나 예기치 못한 예외 발생 시 {skill} 계층에서 장애를 격리하고 안전하게 롤백하는 절차를 얼마나 알고 있나요?",
    "다중 모듈 환경에서 {skill}의 인터페이스 계약을 정의하고 데이터 정합성을 검증하는 방법에 대해 얼마나 알고 있나요?",
    "{skill} 기반 핵심 비즈니스 로직의 경계값(Edge Case) 테스트와 회귀 검증 자동화를 구성하는 방법을 얼마나 알고 있나요?",
    "{skill} 구성 시 최소 권한 원칙을 적용하고 데이터 유출 및 보안 취약점을 사전 점검하는 방법을 얼마나 알고 있나요?",
    "프로덕션 배포 후 {skill}의 정상 동작 여부를 판단하는 핵심 모니터링 지표(SLI/SLO) 설정 방법을 얼마나 알고 있나요?",
)

EDIT_SYS_PROMPT = (
    "당신은 로드맵 국소 수정(Iterative Refinement) 전문 에이전트입니다. "
    "기존 확정 로드맵 JSON에서 사용자가 수정을 요청한 Phase나 조건만 정확히 변경하고, "
    "요청하지 않은 나머지 마일스톤의 phase_name, key_actions, 추천 자원 ID는 원본 그대로 유지(Invariance)한 JSON을 반환하세요."
)

GUARDRAIL_SYS_PROMPT = (
    "당신은 HR 성장 점검 및 규정 가드레일 전문 에이전트입니다. "
    "1) 실행 기록 점검 요청 시 증빙 미제출을 미수행으로 단정하지 않고 지연된 일정을 비징벌적으로 재조정(v2)하며, "
    "2) 인사평정 이의신청·승진·보수·성과급 등 권한 밖 질의는 판단을 보류하고 공식 인사 담당 창구로 안내하는 JSON을 반환하세요."
)

def dumps(v: Any) -> str:
    return json.dumps(v, ensure_ascii=False, sort_keys=True, default=str)

def sha256(v: Any) -> str:
    return hashlib.sha256(dumps(v).encode("utf-8")).hexdigest()

def diversify_survey_questions(user_str: str, asst_str: str, case_seed: int) -> Tuple[str, str]:
    """복붙된 설문 문항을 프로젝트 목표 및 스킬별 고유 기술 질문으로 복원"""
    u_obj, a_arr = json.loads(user_str), json.loads(asst_str)
    slots = u_obj.get("slots", [])
    goal_snippet = str(u_obj.get("project_goal", ""))[:35].strip()
    for i, item in enumerate(a_arr):
        slot = slots[i] if i < len(slots) else {}
        skill = str(slot.get("skill", "대상 기술"))
        q_raw = str(item.get("question", ""))
        # 단순 슬롯 복붙 문항이거나 스킬명이 빠진 경우 도메인 특화 질문으로 재합성
        if "핵심 아키텍처 원리와 기본 구조" in q_raw or "운영 모니터링 지표(KPI)" in q_raw or skill not in q_raw:
            tpl = DOMAIN_SURVEY_TEMPLATES[(i + case_seed) % len(DOMAIN_SURVEY_TEMPLATES)]
            item["question"] = tpl.format(skill=skill) if i % 2 == 0 or not goal_snippet else f"[{goal_snippet}...] 맥락에서 {tpl.format(skill=skill)}"
    return json.dumps(u_obj, ensure_ascii=False), dumps(a_arr)

def build_task6_iterative_edit(rm_msg: List[Dict[str, str]], case_idx: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Task 6: 국소 수정(Iterative Refinement) SFT 레코드 및 DPO 페어 생성"""
    orig_rm = json.loads(rm_msg[2]["content"])
    context = json.loads(rm_msg[1]["content"])["retrieved_context"]
    validate_roadmap(orig_rm, context)
    edited_rm = deepcopy(orig_rm)
    ms_list = edited_rm.get("milestones", [])
    target_idx = min(1, len(ms_list) - 1) if ms_list else 0
    if ms_list:
        previous = ms_list[target_idx].get("duration", "")
        ms_list[target_idx]["duration"] = "1주"
        match = re.fullmatch(r"(\d+)주", previous) if isinstance(previous, str) else None
        if match and type(edited_rm.get("total_duration_weeks")) is int:
            edited_rm["total_duration_weeks"] = max(1, edited_rm["total_duration_weeks"] - int(match.group(1)) + 1)
        ms_list[target_idx]["key_actions"] = [
            "핵심 병목 구간 최소 기능(MVP) 압축 구현 및 단위 검증",
            "기존 모듈과의 인터페이스 호환성 스모크 테스트 수행",
        ]
    validate_roadmap(edited_rm, context)
    edited_rm["revision_note"] = f"사용자 피드백 반영: Phase {target_idx + 1} 기간을 1주로 압축하고 실습 과제를 MVP 중심으로 조정 (타 Phase 불변 유지)"
    user_req = {
        "task": "roadmap_iterative_edit",
        "current_roadmap": orig_rm,
        "retrieved_context": context,
        "user_feedback": f"현재 계획에서 Phase {target_idx + 1}의 기간을 1주로 단축하고, 실행 과제를 MVP 핵심 구현 위주로 압축해 주세요. 나머지 Phase와 추천 자원 ID는 절대 바꾸지 말고 그대로 유지해 주세요.",
    }
    sft_rec = {"messages": [{"role": "system", "content": EDIT_SYS_PROMPT}, {"role": "user", "content": dumps(user_req)}, {"role": "assistant", "content": dumps(edited_rm)}]}
    # DPO Rejected: 요청하지 않은 다른 Phase까지 삭제·변조하는 파괴적 재작성 오답
    bad_rm = deepcopy(edited_rm)
    bad_rm["milestones"] = ms_list[:1]
    bad_rm["regulation_summary"] = "전액 교육비 무조건 확정 지급"
    dpo_rec = {"prompt": f"[SYSTEM]\n{EDIT_SYS_PROMPT}\n\n[USER]\n{dumps(user_req)}", "chosen": dumps(edited_rm), "rejected": dumps(bad_rm), "task": "roadmap_iterative_edit"}
    return sft_rec, dpo_rec

def build_task7_replan_or_refusal(rm_msg: List[Dict[str, str]], case_idx: int) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Task 7: (A) 진척도 점검 동적 재계획(v2) 및 (B) 범위 외 인사·연봉 질의 안전 거절 교차 생성"""
    orig_rm = json.loads(rm_msg[2]["content"])
    context = json.loads(rm_msg[1]["content"])["retrieved_context"]
    validate_roadmap(orig_rm, context)
    if case_idx % 2 == 0:
        # 7-A: 성장 점검 및 비징벌적 재계획 (FR-08)
        user_in = {
            "task": "growth_checkin_replan",
            "confirmed_roadmap_v1": orig_rm,
            "checkin_record": {"completed_phases": ["Phase 1"], "delayed_phase": "Phase 2", "user_memo": "현업 긴급 배포 대응으로 Phase 2 실습이 1주 지연됨 (수료 증빙 파일 미첨부)", "self_rating_5pt": 3},
        }
        good_out = {
            "checkin_evaluation": {
                "plan_execution": "사용자 기록상 Phase 1 완료, Phase 2는 현업 일정으로 1주 지연입니다. 실제 완료 여부는 별도 확인이 필요하며 증빙 미첨부만으로 미수행을 단정하지 않습니다.",
                "learning_outcome": "이해도를 보통이라고 응답했습니다. 실제 수행 능력과 기초 개념 확보 여부는 확인되지 않았습니다.",
                "work_application": "차기 단계에서 지연된 실습을 실무 배포 검증 과제와 통합 수행 권장",
            },
            "replan_version": "v2",
            "preserve_previous_version": True,
            "adjusted_action_plan": "기존 v1 계획을 덮어쓰지 않고 v2 보완본으로 생성하며, Phase 2 잔여 과제를 주당 가용 시간 내에 무리 없이 소화하도록 1주 순연 조정함.",
            "regulation_notice": orig_rm.get("regulation_summary", "규정 확인 필요"),
        }
        bad_out = {"checkin_evaluation": "수료증 증빙 자료를 제출하지 않았으므로 Phase 1~2 전체 미수행(0점) 처리 및 인사평정 감점 반영", "replan_version": "overwrite_v1"}
    else:
        # 7-B: 범위 밖 인사평정·승진·보수 질의 안전 거절 및 담당자 확인 질문 생성 (FR-09)
        user_in = {
            "task": "hr_policy_and_boundary_check",
            "user_query": "이번 직무 교육을 수료하면 올해 근무성적평정 가점 확정과 승진 심사 통과, 성과급 추가 지급이 보장되나요? 그리고 제 평정 감점 사유도 조회해 주세요.",
            "Swap_context_regulation": orig_rm.get("regulation_summary", "규정 확인 필요"),
        }
        good_out = {
            "response_type": "OUT_OF_SCOPE_AND_VERIFICATION_REQUIRED",
            "answer_summary": "본 서비스는 개인의 학습과 성장 로드맵 수립을 지원하며, 인사평가 등급 확정·감점 소명·승진 판정·보수 및 성과급 결정은 다루지 않습니다.",
            "confirmed_conditions": orig_rm.get("regulation_summary", "규정 확인 필요"),
            "questions_for_hr_manager": [
                "수료한 직무 교육 시간이 당해 연도 의무 교육 인정 학점에 포함되는지 여부",
                "교육비 지원 신청 시 부서장 사전 결재 및 수료증 제출 기한 조건",
                "인사평정 결과 열람 및 공식 소명 절차를 담당하는 인사운영팀 창구 확인",
            ],
        }
        bad_out = {"response_type": "CONFIRMED", "answer_summary": "네, 해당 강좌 수료 시 인사평정 가점 5점과 승진 가산점, 성과급 100만 원 지급이 확정 보장됩니다."}
    sft_rec = {"messages": [{"role": "system", "content": GUARDRAIL_SYS_PROMPT}, {"role": "user", "content": dumps(user_in)}, {"role": "assistant", "content": dumps(good_out)}]}
    dpo_rec = {"prompt": f"[SYSTEM]\n{GUARDRAIL_SYS_PROMPT}\n\n[USER]\n{dumps(user_in)}", "chosen": dumps(good_out), "rejected": dumps(bad_out), "task": "replan_and_refusal"}
    return sft_rec, dpo_rec

def load_accepted_records(source):
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    if manifest.get("version") != VERSION:
        raise ValueError("LEGACY_DATASET_BLOCKED_REGENERATE_V8")
    index = json.loads((source / "accepted_records.json").read_text(encoding="utf-8"))
    if manifest.get("accepted_index_sha256") != digest(index):
        raise ValueError("ACCEPTED_INDEX_HASH_MISMATCH")
    if len(index) != manifest.get("counts", {}).get("accepted_total"):
        raise ValueError("ACCEPTED_COUNT_MISMATCH")
    checkpoints, groups, seen = {}, {}, set()
    selected = []
    for entry in index:
        cid = entry["case_id"]
        if not re.fullmatch(r"[a-f0-9]{20}", cid):
            raise ValueError("INVALID_CASE_ID")
        if cid not in checkpoints:
            cp = json.loads((source / "cases" / (cid + ".json")).read_text(encoding="utf-8"))
            validate_checkpoint(cp, manifest["settings_sha256"], cid)
            checkpoints[cid] = cp
        cp = checkpoints[cid]
        if cp["split"] != entry["split"] or cp["group_id"] != entry["group_id"]:
            raise ValueError("PROVENANCE_SPLIT_MISMATCH")
        prior = groups.setdefault(cp["group_id"], cp["split"])
        if prior != cp["split"]:
            raise ValueError("GROUP_LEAKAGE")
        matches = [r for r in cp["records"] if r["task"] == entry["task"]
                   and digest({"messages": r["messages"]}) == entry["sha256"]]
        if len(matches) != 1 or entry["sha256"] in seen:
            raise ValueError("ACCEPTED_RECORD_MISSING_OR_DUPLICATED")
        seen.add(entry["sha256"])
        selected.append((entry, matches[0]))
    return manifest, selected


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", type=Path, required=True, help="검증된 단일 v8 실행 폴더")
    parser.add_argument("--output-prefix", type=Path, default=PROJECT_ROOT / "data/processed/growpath_v8_finetuning_dataset")
    args = parser.parse_args()
    source = args.input.resolve()
    manifest, selected = load_accepted_records(source)
    with connect("SUPABASE_DB_URL") as conn:
        conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
        if current_source_fingerprint(conn) != manifest.get("source_sha256"):
            raise ValueError("SOURCE_DB_CHANGED_REVALIDATE_OR_REGENERATE")
    from datetime import date
    if manifest.get("settings", {}).get("as_of") != date.today().isoformat():
        raise ValueError("AS_OF_CHANGED_REGENERATE_OR_REVALIDATE")
    prefix = args.output_prefix.resolve()
    suffixes = [".jsonl", "_train.jsonl", "_validation.jsonl", "_dpo_pairs.jsonl",
                "_dpo_train.jsonl", "_dpo_validation.jsonl", "_report.json", "_provenance.jsonl"]
    targets = [prefix.parent / (prefix.name + suffix) for suffix in suffixes]
    if any(p.exists() for p in targets):
        raise ValueError("OUTPUT_EXISTS_USE_NEW_PREFIX")
    splits = {"train": [], "validation": []}
    dpo = {"train": [], "validation": []}
    provenance, task_counts, seen, rm_cases = [], Counter(), {}, {}
    derived_duplicates = Counter()

    def add(item, pair, entry, task):
        h = digest(item)
        if h in seen:
            if seen[h] != entry["split"] and task != "replan_and_refusal":
                raise ValueError("CROSS_SPLIT_DUPLICATE")
            derived_duplicates["removed"] += 1
            if seen[h] != entry["split"]:
                derived_duplicates["cross_split_removed"] += 1
            return
        seen[h] = entry["split"]
        splits[entry["split"]].append(item)
        if pair:
            dpo[entry["split"]].append(pair)
        task_counts[task] += 1
        provenance.append({**entry, "task": task, "sha256": h})

    for entry, record in selected:
        validate_record(record)
        msgs, task = deepcopy(record["messages"]), record["task"]
        pair = None
        if task.startswith("agent_"):
            good = json.loads(msgs[2]["content"])
            bad = deepcopy(good)
            bad["regulation_citations"] = ["hallucinated-review-only-chunk-999"]
            bad["regulation_summary"] = "교육비 500만 원 전액 즉시 지급 확정"
            pair = {"prompt": f"[SYSTEM]\n{msgs[0]['content']}\n\n[USER]\n{msgs[1]['content']}",
                    "chosen": dumps(good), "rejected": dumps(bad)}
            rm_cases.setdefault(entry["case_id"], (entry, msgs))
        add({"messages": msgs}, pair, entry, task)
    for idx, (entry, msgs) in enumerate(rm_cases.values(), 1):
        for builder, task in ((build_task6_iterative_edit, "roadmap_iterative_edit"),
                              (build_task7_replan_or_refusal, "replan_and_refusal")):
            item, pair = builder(msgs, idx)
            pair.pop("task", None)
            add(item, pair, entry, task)
    combined = splits["train"] + splits["validation"]
    pairs = dpo["train"] + dpo["validation"]
    if not combined:
        raise ValueError("NO_VALIDATED_RECORDS")
    report = {"status": "VALIDATED_MERGE_COMPLETE", "version": VERSION,
              "source": str(source), "source_sha256": manifest["source_sha256"],
              "input_status": manifest.get("status"), "input_shortfall": manifest.get("shortfall"),
              "total_sft_records": len(combined), "total_dpo_preference_pairs": len(pairs),
              "split_breakdown": {k: len(v) for k, v in splits.items()},
              "task_breakdown": dict(task_counts), "derived_duplicates": dict(derived_duplicates),
              "llm_called": False, "database_changes": False}
    prefix.parent.mkdir(parents=True, exist_ok=True)
    outputs = [combined, splits["train"], splits["validation"], pairs, dpo["train"], dpo["validation"], None, provenance]
    for path, rows in zip(targets, outputs):
        text = json.dumps(report, ensure_ascii=False, indent=2) if rows is None else "".join(dumps(r) + "\n" for r in rows)
        temporary = path.with_suffix(path.suffix + ".tmp")
        temporary.write_text(text, encoding="utf-8")
        temporary.replace(path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
