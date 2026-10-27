import sys
from pathlib import Path

ROOT = Path("C:/final_team2/project/qwen_factory")
sys.path.insert(0, str(ROOT / "scripts"))
import app_settings
from runpod_client import RunPodClient

s = app_settings.read(ROOT)
c = RunPodClient(s.get("RUNPOD_JUPYTER_URL"), s.get("RUNPOD_JUPYTER_TOKEN"))
c.login()

files_to_sync = [
    "scripts/qwen35_b200_runner.py",
    "configs/hyperparameters.qwen35_4b_3000.P01.yaml",
    "configs/hyperparameters.qwen35_4b_3000.P02.yaml",
    "configs/hyperparameters.qwen35_4b_3000.P03.yaml",
    "configs/hyperparameters.qwen35_4b_3000.P04.yaml",
    "configs/hyperparameters.qwen35_4b_3000.P05.yaml",
    "configs/hyperparameters.qwen35_4b_3000.P06.yaml",
]

for rel in files_to_sync:
    content = (ROOT / rel).read_text(encoding="utf-8")
    c.contents(rel, content)
    print(f"[+] Synced {rel}")

print("All files synced to RunPod!")

