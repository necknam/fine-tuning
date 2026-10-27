import sys
from pathlib import Path
ROOT = Path("C:/final_team2/project/qwen_factory")
sys.path.insert(0, str(ROOT / "scripts"))
import app_settings
from runpod_client import RunPodClient

s = app_settings.read(ROOT)
c = RunPodClient(s.get("RUNPOD_JUPYTER_URL"), s.get("RUNPOD_JUPYTER_TOKEN"))
c.connect()
try:
    code = """
import subprocess
runner = '''
import json, glob
from transformers import AutoTokenizer

staged = glob.glob('/dev/shm/qwen35_4b_model_cache/models--Qwen--Qwen3.5-4B/snapshots/*')
if not staged:
    staged = glob.glob('/root/.cache/huggingface/hub/models--Qwen--Qwen3.5-4B/snapshots/*')
staged = staged[0]

tok = AutoTokenizer.from_pretrained(staged, local_files_only=True)

with open('/workspace/qwen_factory/data/production/expanded_3000/all.jsonl', 'r', encoding='utf-8') as f:
    rows = [json.loads(line) for line in f if line.strip()]

lengths = []
for i, r in enumerate(rows):
    m = r['messages']
    ids = tok.apply_chat_template(m, tokenize=True, enable_thinking=False, add_generation_prompt=False)
    lengths.append(len(ids))

print('Total rows:', len(lengths))
print('Max length:', max(lengths))
print('Rows > 7168:', sum(1 for x in lengths if x > 7168))
print('Rows > 8192:', sum(1 for x in lengths if x > 8192))
print('Rows > 10240:', sum(1 for x in lengths if x > 10240))
top_10 = sorted(lengths, reverse=True)[:10]
print('Top 10 lengths:', top_10)
'''
with open('/workspace/measure.py', 'w') as f:
    f.write(runner)

out = subprocess.check_output(['/workspace/qwen_factory/.venv-runpod/bin/python', '/workspace/measure.py'], text=True)
print(out)
"""
    res = c.execute(code, timeout=120)
    print("Measurement result:\n" + res)
finally:
    if c.kernel_id:
        c.api("/api/kernels/" + c.kernel_id, method="DELETE")
