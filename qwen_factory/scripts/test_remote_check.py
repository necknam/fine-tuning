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
out = subprocess.check_output(
    ['/workspace/qwen_factory/.venv-runpod/bin/python', 'scripts/qwen35_b200_runner.py', '--config', 'configs/hyperparameters.qwen35_4b_3000.P01.yaml', '--phase', 'check'],
    cwd='/workspace/qwen_factory',
    text=True
)
print('CHECK_OUTPUT=' + out)
"""
    res = c.execute(code, timeout=30)
    print("Remote result:\n" + res)
finally:
    if c.kernel_id:
        c.api("/api/kernels/" + c.kernel_id, method="DELETE")
