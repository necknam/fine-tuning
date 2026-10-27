import json
from pathlib import Path

p = Path('qwen_factory/data/eval/prompts.jsonl')
rows = [json.loads(l) for l in p.read_text(encoding='utf-8').splitlines() if l.strip()]
print('Case 1 content keys:', json.loads(rows[0]['messages'][1]['content']).keys())
print('Case 1 dump:')
print(json.dumps(json.loads(rows[0]['messages'][1]['content']), ensure_ascii=False, indent=2)[:500])

