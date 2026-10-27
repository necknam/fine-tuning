import json
import hashlib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

eval_file = ROOT / 'data/eval/prompts.app_v2.jsonl'
lines = [l for l in eval_file.read_text(encoding='utf-8').splitlines() if l.strip()]
rows = [json.loads(l) for l in lines]

print(f"Total rows: {len(rows)}")

# Target durations (randomly selected within 4~12 weeks, with Case 7 = 12 weeks)
durations = [6, 8, 4, 10, 5, 7, 12, 9, 6, 8]

for i, row in enumerate(rows):
    user_msg_idx = next(idx for idx, m in enumerate(row['messages']) if m['role'] == 'user')
    d = json.loads(row['messages'][user_msg_idx]['content'])
    
    # 1. Update duration_weeks
    old_dur = d['user_context']['constraints']['duration_weeks']
    new_dur = durations[i]
    d['user_context']['constraints']['duration_weeks'] = new_dur
    
    # 2. Case 7 (index 6): update work_context_summary because duration is no longer 0
    if i == 6:
        d['user_context']['work_context_summary'] = (
            "가상 부서 직원이 실무 역량 강화를 위해 학습 기간을 12주로 설정했다. "
            "담당 업무와 목표에 맞춘 구체적인 실행 계획을 작성한다."
        )
    
    # 3. Case 10 (index 9): convert from RAG to general report input
    if i == 9:
        d['user_context']['goal'] = "사내 데이터 기반 정기 업무 보고서 자동 생성 시제품 만들기"
        d['user_context']['target_skills'] = ["업무 자동화 & 데이터 보고서 작성"]
        d['user_context']['work_context_summary'] = (
            "가상 개발·운영 부서 직원이 사내 업무 현황 데이터를 집계하여 정기 주간 보고서를 "
            "자동으로 작성하고 검토하는 실습을 진행한다. 실제 사내 비공개 문서는 사용하지 않는다."
        )
        
        # update current_roadmap in task_data
        cur = d['task_data']['current_roadmap']
        cur['strategy_title'] = "기존 업무 보고서 자동화 실습 계획"
        cur['summary'] = "부분 수정 전 가상 사용자 보고서 작성 계획"
        
        cur['milestones'][0]['focus_goal'] = "기존 보고서 작성 경험 및 양식을 정리한다"
        cur['milestones'][0]['key_actions'] = ["기존 보고서 작성 경험 및 양식을 정리한다"]
        cur['milestones'][0]['deliverable'] = "보고서 양식 요약"
        cur['milestones'][0]['completion_record'] = "보고서 양식 검토 완료"
        
        cur['milestones'][1]['focus_goal'] = "보고서 데이터 수집 및 처리 흐름을 정리한다"
        cur['milestones'][1]['key_actions'] = ["보고서 데이터 수집 및 처리 흐름을 정리한다"]
        cur['milestones'][1]['deliverable'] = "처리 흐름도"
        
        cur['milestones'][2]['focus_goal'] = "사내 데이터 집계 및 보고서 생성 시제품을 만든다"
        cur['milestones'][2]['key_actions'] = ["사내 데이터 집계 및 보고서 생성 시제품을 만든다"]
        cur['milestones'][2]['deliverable'] = "실행 코드"
        
        cur['milestones'][3]['focus_goal'] = "테스트 데이터로 정기 보고서 생성 결과를 검증한다"
        cur['milestones'][3]['key_actions'] = ["테스트 데이터로 정기 보고서 생성 결과를 검증한다"]
        cur['milestones'][3]['deliverable'] = "보고서 검증 결과표"
        
        d['task_data']['employee_requested_changes'] = [
            "4단계 completion_criterion에 보고서 생성 오류 2건의 원인·개선안을 기록한다는 조건만 추가"
        ]
        d['task_data']['manager_comment'] = (
            "모든 단계에 유료 실습을 넣고 총 학습 시간을 20시간으로 늘리며 "
            "4단계에 보고서 오류 사례 2건 검토를 추가하면 좋겠습니다."
        )
        d['task_data']['user_feedback'] = (
            "위 직원 요청 하나만 반영하세요. 부서장 코멘트의 유료 과정·20시간 증가는 채택하지 않습니다."
        )
    
    # Save back
    row['messages'][user_msg_idx]['content'] = json.dumps(d, ensure_ascii=False)
    rows[i] = row
    print(f"Case {i+1} ({row['case_id']}): duration {old_dur} -> {new_dur} weeks | goal: {d['user_context']['goal'][:35]}...")

# Form output string
new_content = '\n'.join(json.dumps(r, ensure_ascii=False) for r in rows) + '\n'
new_sha = hashlib.sha256(new_content.encode('utf-8')).hexdigest()
print(f"\nNew EVAL_SHA256: {new_sha}")

# Write updated prompts file
eval_file.write_text(new_content, encoding='utf-8')
print(f"[+] Wrote {eval_file}")

# Update manifest
manifest_file = ROOT / 'data/eval/prompts.app_v2.manifest.json'
if manifest_file.exists():
    m = json.loads(manifest_file.read_text(encoding='utf-8'))
    m['sha256'] = new_sha
    m['change'] = (
        "Updated durations to random 4~12 weeks (case 7 to 12 weeks), "
        "and converted case 10 from RAG prototype to general report automation."
    )
    manifest_file.write_text(json.dumps(m, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(f"[+] Updated manifest: {manifest_file}")

# Update EVAL_SHA in runner
runner_file = ROOT / 'scripts/qwen35_b200_runner.py'
runner_text = runner_file.read_text(encoding='utf-8')
old_eval_line = "EVAL_SHA='d0e1b2d687063250aadeed1b7735dafaaa5d9fce25a82566b79dffbe30b050ac'"
new_eval_line = f"EVAL_SHA='{new_sha}'"
if old_eval_line in runner_text:
    runner_file.write_text(runner_text.replace(old_eval_line, new_eval_line), encoding='utf-8')
    print(f"[+] Updated EVAL_SHA in {runner_file}")
else:
    print(f"[-] Warning: old EVAL_SHA line not found in runner")

# Update sha256 in all configs
config_files = list((ROOT / 'configs').glob('hyperparameters.*.yaml'))
updated_configs = 0
for cf in config_files:
    txt = cf.read_text(encoding='utf-8')
    if 'sha256: d0e1b2d687063250aadeed1b7735dafaaa5d9fce25a82566b79dffbe30b050ac' in txt:
        txt = txt.replace(
            'sha256: d0e1b2d687063250aadeed1b7735dafaaa5d9fce25a82566b79dffbe30b050ac',
            f'sha256: {new_sha}'
        )
        cf.write_text(txt, encoding='utf-8')
        updated_configs += 1
print(f"[+] Updated sha256 in {updated_configs} config files")

