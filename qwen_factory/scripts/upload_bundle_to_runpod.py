"""Upload bundle ZIP to RunPod in safe chunks, verify SHA256, and extract into /workspace."""
import base64
import hashlib
import json
import math
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import app_settings
from runpod_client import RunPodClient


def digest(path):
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def upload_bundle(zip_path):
    zip_path = Path(zip_path)
    if not zip_path.is_file():
        raise FileNotFoundError(f"Bundle not found: {zip_path}")

    expected_sha = digest(zip_path)
    total_bytes = zip_path.stat().st_size
    print(f"[+] Bundle: {zip_path.name} ({total_bytes / (1024*1024):.2f} MB, SHA: {expected_sha[:16]}...)")

    settings = app_settings.read(ROOT)
    client = RunPodClient(settings.get("RUNPOD_JUPYTER_URL"), settings.get("RUNPOD_JUPYTER_TOKEN"))
    client.login()

    chunk_size = 3 * 1024 * 1024  # 3 MB per chunk
    total_chunks = math.ceil(total_bytes / chunk_size)
    print(f"[+] Uploading in {total_chunks} chunks...")

    with open(zip_path, "rb") as f:
        for idx in range(total_chunks):
            data = f.read(chunk_size)
            b64_data = base64.b64encode(data).decode("ascii")
            endpoint = f"/api/contents/workspace/bundle_chunk_{idx:02d}.bin"
            payload = {"type": "file", "format": "base64", "content": b64_data}
            t0 = time.perf_counter()
            client.api(endpoint, data=payload, method="PUT")
            dt = time.perf_counter() - t0
            print(f"    Chunk {idx+1}/{total_chunks} ({len(data)/(1024*1024):.2f} MB) uploaded in {dt:.2f}s")

    print("[+] Assembling and verifying on RunPod...")
    client.connect()
    try:
        assemble_code = f"""
import glob, hashlib, os, shutil, zipfile

chunks = sorted(glob.glob('/workspace/bundle_chunk_*.bin'))
target = '/workspace/{zip_path.name}'
with open(target, 'wb') as out_f:
    for c in chunks:
        with open(c, 'rb') as in_f:
            shutil.copyfileobj(in_f, out_f)
        os.remove(c)

h = hashlib.sha256()
with open(target, 'rb') as f:
    for chunk in iter(lambda: f.read(1024*1024), b''):
        h.update(chunk)

actual_sha = h.hexdigest()
print('ASSEMBLE_SHA=' + actual_sha)
if actual_sha != '{expected_sha}':
    raise ValueError(f'SHA mismatch: expected {expected_sha}, got ' + actual_sha)

print('Extracting into /workspace...')
with zipfile.ZipFile(target, 'r') as z:
    z.extractall('/workspace')

print('EXTRACT_OK')
"""
        res = client.execute(assemble_code, timeout=60)
        print("RunPod Output:\n" + res)
        if "EXTRACT_OK" not in res:
            raise RuntimeError("Extraction failed on RunPod")
        print("[+] Bundle successfully uploaded, verified, and extracted on RunPod!")
    finally:
        if client.kernel_id:
            try:
                client.api('/api/kernels/' + client.kernel_id, method='DELETE')
            except Exception:
                pass


if __name__ == "__main__":
    bundle_file = sys.argv[1] if len(sys.argv) > 1 else "D:/qwen_factory_local/bundles/qwen35_4b_3000_P01_P06_final.zip"
    upload_bundle(bundle_file)
