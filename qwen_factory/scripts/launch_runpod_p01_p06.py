"""Launch Qwen3.5-4B P01~P06 batch training and comparison on RunPod in the background."""
import sys
import time
from pathlib import Path

ROOT = Path("C:/final_team2/project/qwen_factory")
sys.path.insert(0, str(ROOT / "scripts"))

import app_settings
from runpod_client import RunPodClient


def launch():
    settings = app_settings.read(ROOT)
    client = RunPodClient(settings.get("RUNPOD_JUPYTER_URL"), settings.get("RUNPOD_JUPYTER_TOKEN"))
    client.connect()

    try:
        code = """
import os, subprocess, time

project = '/workspace/qwen_factory'
venv_py = project + '/.venv-runpod/bin/python'
log_file = project + '/outputs/run_all_presets.log'
os.makedirs(project + '/outputs', exist_ok=True)

# Check if already running
check_ps = subprocess.run(['pgrep', '-f', 'run_all_qwen35_presets.py'], capture_output=True, text=True)
pids = [p.strip() for p in check_ps.stdout.splitlines() if p.strip()]

if pids:
    print('ALREADY_RUNNING: PIDs ' + ', '.join(pids))
else:
    cmd = f'nohup {venv_py} -u scripts/run_all_qwen35_presets.py --presets P01 P02 P03 P04 P05 P06 --phase all --execute > outputs/run_all_presets.log 2>&1 &'
    subprocess.Popen(cmd, shell=True, cwd=project, start_new_session=True)
    time.sleep(3)
    check_ps = subprocess.run(['pgrep', '-f', 'run_all_qwen35_presets.py'], capture_output=True, text=True)
    pids = [p.strip() for p in check_ps.stdout.splitlines() if p.strip()]
    print('LAUNCHED: PIDs ' + ', '.join(pids))

# Read initial log
if os.path.exists(log_file):
    with open(log_file, 'r', encoding='utf-8') as f:
        print('--- INITIAL LOG ---')
        print(f.read()[-2000:])
"""
        res = client.execute(code, timeout=30)
        print("RunPod Launch Result:\n" + res)
    finally:
        if client.kernel_id:
            try:
                client.api("/api/kernels/" + client.kernel_id, method="DELETE")
            except Exception:
                pass


if __name__ == "__main__":
    launch()
