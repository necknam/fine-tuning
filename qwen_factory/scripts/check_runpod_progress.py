"""Check the live execution progress of Qwen3.5-4B batch training on RunPod."""
import sys
from pathlib import Path

ROOT = Path("C:/final_team2/project/qwen_factory")
sys.path.insert(0, str(ROOT / "scripts"))

import app_settings
from runpod_client import RunPodClient


def check():
    settings = app_settings.read(ROOT)
    client = RunPodClient(settings.get("RUNPOD_JUPYTER_URL"), settings.get("RUNPOD_JUPYTER_TOKEN"))
    client.connect()

    try:
        code = """
import os, subprocess

print('--- RUNNING PROCESSES ---')
ps = subprocess.run(['ps', 'aux'], capture_output=True, text=True)
for line in ps.stdout.splitlines():
    if 'qwen' in line or 'python' in line:
        if 'ipykernel' not in line:
            print(line[:120])

print('--- GPU USAGE ---')
try:
    smi = subprocess.check_output(['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw', '--format=csv,noheader,nounits'], text=True)
    print('GPU Util (%), Mem Used (MB), Mem Total (MB), Temp (C), Power (W):')
    print(smi.strip())
except Exception as e:
    print('nvidia-smi error:', e)

print('--- LOG TAIL ---')
log_file = '/workspace/qwen_factory/outputs/run_all_presets.log'
if os.path.exists(log_file):
    with open(log_file, 'r', encoding='utf-8') as f:
        lines = f.readlines()
        print(''.join(lines[-25:]))
else:
    print('Log file not found yet.')

print('--- PROGRESS JSON ---')
prog_file = '/workspace/qwen_factory/outputs/all_presets_progress.json'
if os.path.exists(prog_file):
    with open(prog_file, 'r', encoding='utf-8') as f:
        print(f.read())
"""
        res = client.execute(code, timeout=30)
        print("RunPod Status:\n" + res)
    finally:
        if client.kernel_id:
            try:
                client.api("/api/kernels/" + client.kernel_id, method="DELETE")
            except Exception:
                pass


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    check()
