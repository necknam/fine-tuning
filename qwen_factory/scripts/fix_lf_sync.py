from pathlib import Path
import hashlib
import sys

root = Path(__file__).resolve().parent.parent
p = root / 'data/eval/prompts.app_v2.jsonl'
raw = p.read_bytes().replace(b'\r\n', b'\n')
p.write_bytes(raw)
sha = hashlib.sha256(p.read_bytes()).hexdigest()
print('Local LF sha:', sha)

sys.path.insert(0, str(root / 'scripts'))
import app_settings
from runpod_client import RunPodClient
settings = app_settings.read(root)
url = settings.get('RUNPOD_JUPYTER_URL')
token = settings.get('RUNPOD_JUPYTER_TOKEN')
client = RunPodClient(url, token, 'workspace/qwen_factory')
client.connect()

code = """
from pathlib import Path
import hashlib
p = Path('/workspace/qwen_factory/data/eval/prompts.app_v2.jsonl')
raw = p.read_bytes().replace(b'\\r\\n', b'\\n')
p.write_bytes(raw)
print('RUNPOD_FIXED_SHA:', hashlib.sha256(p.read_bytes()).hexdigest())
"""
print(client.execute(code, timeout=15))
