import json, glob, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def evaluate_run(preset_id, epoch):
    files = sorted(ROOT.glob(f"outputs/qwen35_4b_3000_{preset_id}/**/epoch{epoch}/comparison/case*.json"))
    if not files:
        return None
    
    results = []
    for f in files:
        data = json.loads(f.read_text(encoding='utf-8'))
        case_idx = data.get('case_index')
        user_msg = next(m['content'] for m in data['messages'] if m['role'] == 'user')
        req = json.loads(user_msg)
        
        # Base & Tuned texts
        base_raw = data.get('base', {}).get('text', '')
        tuned_raw = data.get('tuned', {}).get('text', '')
        
        # Parse JSON
        base_json = None
        tuned_json = None
        base_valid_json = False
        tuned_valid_json = False
        
        try:
            # Strip potential markdown fences
            clean_b = re.sub(r'^```json\s*|\s*```$', '', base_raw.strip(), flags=re.MULTILINE)
            base_json = json.loads(clean_b)
            base_valid_json = True
        except Exception:
            pass
            
        try:
            clean_t = re.sub(r'^```json\s*|\s*```$', '', tuned_raw.strip(), flags=re.MULTILINE)
            tuned_json = json.loads(clean_t)
            tuned_valid_json = True
        except Exception:
            pass
            
        results.append({
            'case_index': case_idx,
            'task': req.get('task'),
            'req_constraints': req.get('user_context', {}).get('constraints', {}),
            'req_goal': req.get('user_context', {}).get('goal'),
            'base_valid_json': base_valid_json,
            'tuned_valid_json': tuned_valid_json,
            'base_tokens': data.get('base', {}).get('tokens', 0),
            'tuned_tokens': data.get('tuned', {}).get('tokens', 0),
            'base_json': base_json,
            'tuned_json': tuned_json,
        })
    return results

def analyze(preset_id, epoch, eval_results):
    print(f"\n========================================================")
    print(f"  EVALUATION REPORT: {preset_id} (Epoch {epoch})")
    print(f"========================================================")
    print(f"Total Cases Evaluated: {len(eval_results)}/10\n")
    
    for r in eval_results:
        idx = r['case_index']
        task = r['task']
        c = r['req_constraints']
        req_dur = c.get('duration_weeks')
        req_hrs = c.get('weekly_hours')
        req_budget = c.get('budget_krw')
        
        t_json = r['tuned_json']
        t_valid = r['tuned_valid_json']
        
        print(f"--- Case {idx+1:02d} [{task}] (Req: dur={req_dur}w, hrs={req_hrs}h, budget={req_budget}원) ---")
        if not t_valid:
            print("  [!] Tuned output failed to parse as valid JSON!")
            continue
            
        t_dur = t_json.get('total_duration_weeks')
        t_hrs = t_json.get('total_hours')
        t_cost = t_json.get('total_cost_krw') or t_json.get('total_cost')
        t_flow = t_json.get('roadmap_flow', [])
        t_milestones = t_json.get('milestones', [])
        t_clarifications = t_json.get('clarification_questions', [])
        t_citations = t_json.get('regulation_citations', [])
        t_strategy = t_json.get('strategy_title')
        
        # Check Case 5 regression (1 week)
        dur_status = "PASS"
        if idx == 4: # Case 5
            if t_dur != 1:
                dur_status = f"FAIL (Expected 1w, got {t_dur}w)"
        elif idx == 6: # Case 7 (0 weeks)
            if t_dur is None and (len(t_clarifications) > 0 or len(t_milestones) == 0):
                dur_status = "PASS (Clarification questions requested, null duration)"
            else:
                dur_status = f"FAIL (Expected null/clarification, got dur={t_dur}, milestones={len(t_milestones)})"
        else:
            if req_dur is not None and t_dur != req_dur:
                dur_status = f"MISMATCH (Req: {req_dur}w, Got: {t_dur}w)"

        print(f"  Duration Status: {dur_status} | total_dur={t_dur}w, total_hrs={t_hrs}h, cost={t_cost}원")
        print(f"  Milestones count: {len(t_milestones)}, Flow steps: {len(t_flow)}")
        if t_clarifications:
            print(f"  Clarification questions ({len(t_clarifications)}): {t_clarifications}")
        if t_citations:
            print(f"  Regulation citations: {t_citations}")
            
        # Revision checks
        if task == 'revise_roadmap':
            t_changes = t_json.get('change_summary') or t_json.get('changes')
            print(f"  Revision summary: {t_changes}")

if __name__ == '__main__':
    # 1. P01 Epoch 2
    r_p01_e2 = evaluate_run("P01", 2)
    if r_p01_e2: analyze("P01", 2, r_p01_e2)
    
    # 2. P01 Epoch 5
    r_p01_e5 = evaluate_run("P01", 5)
    if r_p01_e5: analyze("P01", 5, r_p01_e5)
    
    # 3. P02 Epoch 2
    r_p02_e2 = evaluate_run("P02", 2)
    if r_p02_e2: analyze("P02", 2, r_p02_e2)

