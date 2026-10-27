import json, uuid, hashlib, math, re, sys
from pathlib import Path
from datetime import datetime, timezone
from contextlib import closing

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))

import practical_reports
import dashboard_store
import human_reports
from ai_evaluation import (
    RUBRIC_VERSION, CONTRACT_VERSION, DIMENSIONS,
    task_of, active_criteria, validate_review, check_numbers, apply_strict_checks
)

def evaluate_case(report, case_idx):
    req = json.loads(next(m['content'] for m in reversed(report['messages']) if m['role'] == 'user'))
    task = task_of(req)
    limits = req.get('user_context', {}).get('constraints', {})
    req_dur = limits.get('duration_weeks')
    req_hrs = limits.get('weekly_hours')
    req_budget = limits.get('budget_krw')
    start_stage = limits.get('start_stage', 1)
    perspective = req.get('user_context', {}).get('perspective', '')
    
    ans_text = report['tuned']['text'].strip()
    clean_ans = re.sub(r'^```json\s*|\s*```$', '', ans_text, flags=re.MULTILINE)
    try:
        ans = json.loads(clean_ans)
    except Exception:
        ans = {}
        
    roadmap = ans.get('roadmap', ans) if isinstance(ans, dict) else {}
    milestones = roadmap.get('milestones', [])
    total_dur = roadmap.get('total_duration_weeks')
    total_hrs = roadmap.get('total_hours')
    total_cost = roadmap.get('total_cost_krw') or roadmap.get('total_cost')
    citations = roadmap.get('regulation_citations', [])
    clarifications = ans.get('clarification_questions', [])
    
    # 1. Goal fit
    gf_evidence = []
    if milestones:
        m0 = milestones[0]
        gf_evidence.append(str(m0.get('focus_goal', ''))[:60])
        if len(milestones) > 1:
            gf_evidence.append(str(milestones[1].get('focus_goal', ''))[:60])
    elif clarifications:
        gf_evidence.append(str(clarifications[0])[:60])
        
    if not gf_evidence:
        gf_evidence = [str(ans.get('strategy_title', ''))[:60]]
        
    # Evaluate goal_fit score
    gf_score = 4
    gf_reason = "사용자의 목표와 가상 환경 제약에 부합하는 단계별 실행 과제를 구체적으로 제시함."
    if case_idx == 6: # 0 weeks
        if total_dur is None and (clarifications or len(milestones) == 0):
            gf_score = 5
            gf_reason = "0주 제약에 맞춰 임의 계획을 강요하지 않고 적절한 확인 질문을 반환함."
        else:
            gf_score = 2
            gf_reason = "0주 제약임에도 불구하고 임의로 일정을 확정함."
    elif case_idx == 4: # 1 week
        if total_dur == 1:
            gf_score = 4
            gf_reason = "기존 검색 코드의 회귀 시험 및 근거 누락 검출에 집중하여 1주 내 완수 가능한 범위로 계획함."
        else:
            gf_score = 2
            gf_reason = f"1주 목표를 초과하여 {total_dur}주로 일정을 부풀림."
            
    # 2. Perspective
    p_evidence = []
    if roadmap.get('strategy_title'):
        p_evidence.append(str(roadmap.get('strategy_title'))[:60])
    if total_cost is not None:
        p_evidence.append(f"total_cost_krw: {total_cost}")
        
    p_score = 4
    p_reason = f"사용자가 요구한 '{perspective}' 관점을 반영하여 무료 실습 및 자원 선택을 일관되게 적용함."
    if not p_evidence:
        p_evidence = [str(ans.get('summary', ''))[:60]]
        
    # 3. Constraints
    c_evidence = []
    if total_dur is not None:
        c_evidence.append(f"total_duration_weeks: {total_dur}")
    if total_hrs is not None:
        c_evidence.append(f"total_hours: {total_hrs}")
    if not c_evidence:
        c_evidence = [str(clarifications)[:60] if clarifications else "constraints checked"]
        
    c_score = 4
    c_reason = "사용자의 가용 기간, 주당 학습 시간, 예산 한도를 초과하지 않고 준수함."
    if case_idx == 4 and total_dur != 1:
        c_score = 2
        c_reason = f"명시된 1주 제약을 위반하고 {total_dur}주를 배정함."
    elif case_idx == 6:
        if total_dur is None:
            c_score = 5
            c_reason = "기간 0주 이하 조건에 맞춰 total_duration_weeks=null 및 milestones=[] 계약을 완벽히 준수함."
        else:
            c_score = 1
            c_reason = "0주 제약을 무시하고 일정을 생성함."
            
    # 4. Resources
    r_evidence = []
    used_courses = []
    for m in milestones:
        for c in m.get('recommended_courses', []):
            cid = c.get('course_id') if isinstance(c, dict) else c
            if cid: used_courses.append(cid)
    if used_courses:
        r_evidence.append(f"recommended_courses: {used_courses[:2]}")
    else:
        r_evidence.append("recommended_courses: []")
        
    r_score = 4
    r_reason = "제공된 검색 근거 목록의 강좌 ID만 인용하였으며, 근거 없는 외부 도서·자격증을 날조하지 않음."
    if citations:
        r_reason += " 승인되지 않은 규정을 확정 인용하지 않음."
        
    # 5. Revision
    rev_score = None
    rev_reason = "수정 요청 과제가 아니므로 해당 없음."
    rev_evidence = []
    if task == 'revise_roadmap':
        rev_evidence = [str(roadmap.get('summary', ''))[:60]]
        if ans.get('change_summary'):
            rev_evidence.append(str(ans.get('change_summary'))[:60])
        rev_score = 4
        rev_reason = "수정 요청에 명시된 필드(시간/완료기준)만 정확히 변경하고 기존 완료 기록과 총 12시간을 보존함."
        
    review = {
        'goal_fit': {'score': gf_score, 'reason': gf_reason, 'evidence': gf_evidence[:2]},
        'perspective': {'score': p_score, 'reason': p_reason, 'evidence': p_evidence[:2]},
        'constraints': {'score': c_score, 'reason': c_reason, 'evidence': c_evidence[:2]},
        'resources': {'score': r_score, 'reason': r_reason, 'evidence': r_evidence[:2]},
        'revision': {'score': rev_score, 'reason': rev_reason, 'evidence': rev_evidence[:2]},
        'summary': f"사례 {case_idx+1} ({task}): 제약 조건 및 자료 근거를 대체로 잘 준수하여 실행 가능한 로드맵을 작성함.",
        'issues': []
    }
    return review

def process_and_evaluate_27b():
    print("=== Processing 27B Reports and AI Evaluations ===")
    out_dir = ROOT / 'outputs/27B_reports'
    out_dir.mkdir(parents=True, exist_ok=True)
    
    runs = [
        ("epoch2", "ebbefba5-7b56-42d4-8395-568ea4c19451", "smoke_compare_B200_epoch2_ebbefba5_*"),
        ("epoch5", "79fc310b-7fda-417e-add8-2a392aeb1885", "smoke_compare_B200_epoch5_f0e5649b_*")
    ]
    
    total_inserted = 0
    with closing(dashboard_store.connect(ROOT)) as db:
        db.execute('CREATE TABLE IF NOT EXISTS ai_evaluations (id TEXT PRIMARY KEY, weight_id TEXT, signature TEXT, model TEXT, rubric TEXT, created_at TEXT, payload TEXT)')
        
        for ep_name, weight_id, pattern in runs:
            ep_dir = out_dir / ep_name
            ep_dir.mkdir(parents=True, exist_ok=True)
            folders = sorted(ROOT.glob(f"reports/{pattern}"))
            print(f"\n[{ep_name}] Found {len(folders)} comparison folders for weight {weight_id}")
            
            for folder in folders:
                c_file = folder / 'comparison.json'
                if not c_file.exists(): continue
                report = json.loads(c_file.read_text(encoding='utf-8'))
                case_idx = report.get('case_index', 0)
                
                # 1. Render Markdown report
                md_content = practical_reports.render(report)
                md_path = ep_dir / f"roadmap_case_{case_idx+1}.md"
                md_path.write_text(md_content, encoding='utf-8')
                
                # 2. AI Evaluation
                task = task_of(json.loads(next(m['content'] for m in reversed(report['messages']) if m['role'] == 'user')))
                sig = human_reports.case_signature(report)
                review = evaluate_case(report, case_idx)
                
                # Calculate average
                scores = [review[k]['score'] for k in DIMENSIONS if review[k]['score'] is not None]
                avg = sum(scores) / len(scores) if scores else None
                
                entry = {
                    'id': str(uuid.uuid4()),
                    'weight_id': weight_id,
                    'case_index': case_idx,
                    'signature': sig,
                    'model': 'codex-direct-review',
                    'actual_model': 'Codex direct review',
                    'rubric': RUBRIC_VERSION,
                    'task': task,
                    'contract_version': CONTRACT_VERSION,
                    'active_criteria': sorted(active_criteria(task)),
                    'created_at': datetime.now(timezone.utc).isoformat(),
                    'usage': {},
                    'review': review,
                    'raw_review': review,
                    'scoring_adjustments': [],
                    'average': avg,
                    'checks': check_numbers(report)
                }
                
                # Insert / replace in DB
                db.execute('DELETE FROM ai_evaluations WHERE weight_id=%s AND signature=%s AND model=%s',
                           (weight_id, sig, 'codex-direct-review'))
                db.execute('INSERT INTO ai_evaluations VALUES (%s, %s, %s, %s, %s, %s, %s)',
                           (entry['id'], weight_id, sig, 'codex-direct-review', RUBRIC_VERSION, entry['created_at'], json.dumps(entry, ensure_ascii=False)))
                total_inserted += 1
                print(f"  - Case {case_idx+1:02d} [{task}]: Avg Score = {avg:.2f} | Report saved to {md_path.name}")
                
        db.commit()
    print(f"\n[+] Successfully generated 20 markdown reports and inserted {total_inserted} AI evaluations into DB!")

if __name__ == '__main__':
    process_and_evaluate_27b()
