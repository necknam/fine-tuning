import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def inspect_details(preset, epoch):
    print(f"\n=======================================================")
    print(f" DETAILED CONTENT AUDIT: {preset} (Epoch {epoch})")
    print(f"=======================================================")
    
    files = sorted(ROOT.glob(f"outputs/qwen35_4b_3000_{preset}/**/epoch{epoch}/comparison/case*.json"))
    for f in files:
        data = json.loads(f.read_text(encoding='utf-8'))
        idx = data['case_index']
        raw = data['tuned']['text']
        clean = re.sub(r'^```json\s*|\s*```$', '', raw.strip(), flags=re.MULTILINE)
        try:
            d = json.loads(clean)
        except Exception as e:
            print(f"Case {idx+1}: JSON parse error: {e}")
            continue
            
        print(f"\n--- [Case {idx+1:02d}] ---")
        print(f"Strategy: {d.get('strategy_title')}")
        print(f"Summary: {d.get('summary')[:100]}...")
        print(f"Total Weeks: {d.get('total_duration_weeks')} | Flow Steps: {len(d.get('roadmap_flow', []))} | Milestones: {len(d.get('milestones', []))}")
        
        # Check milestones durations & focus
        for m_idx, m in enumerate(d.get('milestones', [])):
            c_ids = [c.get('course_id') if isinstance(c, dict) else c for c in m.get('recommended_courses', [])]
            b_ids = [b.get('isbn') if isinstance(b, dict) else b for b in m.get('recommended_books', [])]
            print(f"  Milestone {m_idx+1} ({m.get('phase_name')}): {m.get('duration')} | Goal: {m.get('focus_goal')[:40]} | Courses: {c_ids} | Books: {b_ids}")
            
        if d.get('clarification_questions'):
            print(f"  Clarification Questions: {d.get('clarification_questions')}")
        if d.get('regulation_citations'):
            print(f"  Regulation Citations: {d.get('regulation_citations')}")
        if d.get('change_summary'):
            print(f"  Change Summary: {d.get('change_summary')}")

if __name__ == '__main__':
    inspect_details("P01", 5)

