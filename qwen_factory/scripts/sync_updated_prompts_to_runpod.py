import os, sys, json, base64, io, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import app_settings
from runpod_client import RunPodClient

def sync():
    s = app_settings.read(ROOT)
    client = RunPodClient(s.get("RUNPOD_JUPYTER_URL"), s.get("RUNPOD_JUPYTER_TOKEN"))
    client.connect()
    print("[+] Connected to RunPod Jupyter")

    # Create zip of updated files
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as z:
        # 1. prompts.app_v2.jsonl
        p_jsonl = ROOT / 'data/eval/prompts.app_v2.jsonl'
        z.write(p_jsonl, 'data/eval/prompts.app_v2.jsonl')
        # 2. prompts.app_v2.manifest.json
        p_man = ROOT / 'data/eval/prompts.app_v2.manifest.json'
        z.write(p_man, 'data/eval/prompts.app_v2.manifest.json')
        # 3. runner
        p_run = ROOT / 'scripts/qwen35_b200_runner.py'
        z.write(p_run, 'scripts/qwen35_b200_runner.py')
        # 4. all P01~P111 configs
        for cf in (ROOT / 'configs').glob('hyperparameters.qwen35_4b_3000.*.yaml'):
            z.write(cf, f'configs/{cf.name}')
            
    zip_bytes = buf.getvalue()
    b64 = base64.b64encode(zip_bytes).decode('ascii')
    print(f"[+] Built sync bundle: {len(zip_bytes)} bytes ({len(b64)} b64 chars)")

    remote_code = f'''
import base64, io, zipfile
from pathlib import Path

b64 = "{b64}"
data = base64.b64decode(b64)
with zipfile.ZipFile(io.BytesIO(data)) as z:
    z.extractall("/workspace/qwen_factory")

import hashlib
p = Path("/workspace/qwen_factory/data/eval/prompts.app_v2.jsonl")
h = hashlib.sha256(p.read_bytes()).hexdigest()
print("EXTRACTED_SHA256:", h)
'''
    res = client.execute(remote_code, timeout=60)
    print("[+] Remote execution output:")
    print(res)

if __name__ == '__main__':
    sync()
