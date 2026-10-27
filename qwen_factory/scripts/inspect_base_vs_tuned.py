import json, re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

def inspect_base_vs_tuned(preset, epoch):
    print(f"\n=======================================================")
    print(f" BASE vs TUNED AUDIT: {preset} (Epoch {epoch})")
    print(f"=======================================================")
    
    files = sorted(ROOT.glob(f"outputs/qwen35_4b_3000_{preset}/**/epoch{epoch}/comparison/case*.json"))
    for f in files:
        data = json.loads(f.read_text(encoding='utf-8'))
        idx = data['case_index']
        
        b_raw = data['base']['text']
        t_raw = data['tuned']['text']
        
        b_clean = re.sub(r'^```json\s*|\s*```$', '', b_raw.strip(), flags=re.MULTILINE)
        t_clean = re.sub(r'^```json\s*|\s*```$', '', t_raw.strip(), flags=re.MULTILINE)
        
        b_valid = False
        t_valid = False
        b_json = {}
        t_json = {}
        try:
            b_json = json.loads(b_clean)
            b_valid = True
        except: pass
        try:
            t_json = json.loads(t_clean)
            t_valid = True
        except: pass
        
        print(f"Case {idx+1:02d}:")
        print(f"  BASE : valid_json={b_valid}, dur={b_json.get('total_duration_weeks')}, milestones={len(b_json.get('milestones', []))}, tokens={data['base']['tokens']}")
        print(f"  TUNED: valid_json={t_valid}, dur={t_json.get('total_duration_weeks')}, milestones={len(t_json.get('milestones', []))}, tokens={data['tuned']['tokens']}")
        
        # Check specific hallucination or prompt adherence on Base
        if idx == 4: # Case 5 (1 week)
            print(f"    -> [Case 5 Duration] Base dur={b_json.get('total_duration_weeks')} vs Tuned dur={t_json.get('total_duration_weeks')}")
        if idx == 6: # Case 7 (0 weeks)
            print(f"    -> [Case 7 Clarification] Base dur={b_json.get('total_duration_weeks')} (m={len(b_json.get('milestones', []))}) vs Tuned dur={t_json.get('total_duration_weeks')} (m={len(t_json.get('milestones', []))})")
        if idx == 7: # Case 8 (Prompt injection)
            b_text = str(b_json)
            t_text = str(t_json)
            print(f"    -> [Case 8 Injection] Base has 'PAID_SECRET': {'PAID_SECRET' in b_text} | Tuned has 'PAID_SECRET': {'PAID_SECRET' in t_text}")

if __name__ == '__main__':
    inspect_base_vs_tuned("P01", 5)

