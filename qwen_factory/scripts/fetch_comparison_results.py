import sys, base64, io, zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'scripts'))
import app_settings
from runpod_client import RunPodClient

def fetch():
    s = app_settings.read(ROOT)
    client = RunPodClient(s.get("RUNPOD_JUPYTER_URL"), s.get("RUNPOD_JUPYTER_TOKEN"))
    client.connect()
    print("[+] Connected to RunPod")

    code = '''
import glob, io, zipfile, base64

buf = io.BytesIO()
with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as z:
    for f in glob.glob("/workspace/qwen_factory/outputs/**/case*.json", recursive=True):
        arcname = f.replace("/workspace/qwen_factory/", "")
        z.write(f, arcname)

data = buf.getvalue()
print("ZIP_LEN:" + str(len(data)))
print("BASE64:" + base64.b64encode(data).decode("ascii"))
'''
    res = client.execute(code, timeout=60)
    for line in res.splitlines():
        if line.startswith("BASE64:"):
            b64_str = line[len("BASE64:"):].strip()
            zip_bytes = base64.b64decode(b64_str)
            with zipfile.ZipFile(io.BytesIO(zip_bytes)) as z:
                z.extractall(ROOT)
            print(f"[+] Successfully extracted {len(z.namelist())} comparison files to {ROOT / 'outputs'}")
            for name in z.namelist()[:5]:
                print(f"  - {name}")
            return
    print("[-] Failed to find BASE64 in output:", res[:200])

if __name__ == '__main__':
    fetch()

