"""Pull all newly inferred comparison JSONs (4B P01, P02, P03... and 27B 17 weights) from RunPod,
replace local comparison files, render Markdown reports per weight/epoch/case, perform strict expert
AI evaluation, and sync to Neon DB (Streamlit canonical format) and docs/model_evaluation_reports.
"""
import base64
import hashlib
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PROJECT_ROOT = ROOT.parent
sys.path.insert(0, str(ROOT / "scripts"))

import app_settings
from runpod_client import RunPodClient


def pull_from_runpod():
    s = app_settings.read(ROOT)
    client = RunPodClient(s.get("RUNPOD_JUPYTER_URL"), s.get("RUNPOD_JUPYTER_TOKEN"))
    client.connect()

    try:
        code = """
import os, glob, json, zipfile, base64
from pathlib import Path

root = Path('/workspace/qwen_factory')
zip_path = root / 'outputs/all_new_input_comparisons.zip'
files_added = []

with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
    # 1. All 4B comparison JSONs
    for p in sorted((root / 'outputs').glob('qwen35_4b_3000_P*/**/comparison/case*.json')):
        rel = p.relative_to(root)
        zf.write(p, str(rel))
        files_added.append(str(rel))
    for p in sorted((root / 'outputs').glob('qwen35_4b_3000_P*/**/full3000/result.json')):
        rel = p.relative_to(root)
        zf.write(p, str(rel))
        files_added.append(str(rel))
    # 2. All 27B new input comparison JSONs
    for p in sorted((root / 'outputs/new_input_27b_comparisons').glob('*/case*.json')):
        rel = p.relative_to(root)
        zf.write(p, str(rel))
        files_added.append(str(rel))
    receipt = root / 'outputs/new_input_re_inference_done.json'
    if receipt.exists():
        rel = receipt.relative_to(root)
        zf.write(receipt, str(rel))
        files_added.append(str(rel))

b64_path = root / 'outputs/all_new_input_comparisons.b64.txt'
b64_path.write_text(base64.b64encode(zip_path.read_bytes()).decode('ascii'), encoding='utf-8')
print(json.dumps({'count': len(files_added), 'zip_size': zip_path.stat().st_size if zip_path.exists() else 0}))
"""
        info = json.loads(client.execute(code, timeout=60).strip())
        print(f"[+] Packaged {info['count']} files on RunPod ({info['zip_size']} bytes).")

        b64_data = client.contents("outputs/all_new_input_comparisons.b64.txt")["content"].strip()
        local_zip = ROOT / "outputs/all_new_input_comparisons.zip"
        local_zip.parent.mkdir(parents=True, exist_ok=True)
        local_zip.write_bytes(base64.b64decode(b64_data))

        with zipfile.ZipFile(local_zip, "r") as zf:
            zf.extractall(ROOT)
        print(f"[+] Extracted {info['count']} comparison files to local {ROOT}")
    finally:
        if client.kernel_id:
            try:
                client.api("/api/kernels/" + client.kernel_id, method="DELETE")
            except Exception:
                pass


def update_local_27b_reports():
    """Overwrite local qwen_factory/reports/*compare*/comparison.json with the newly inferred 27B outputs."""
    new_27b_root = ROOT / "outputs/new_input_27b_comparisons"
    if not new_27b_root.exists():
        print("[-] No outputs/new_input_27b_comparisons directory yet.")
        return 0

    # Map weight_id -> case_index -> new comparison dict
    new_map = {}
    for w_dir in sorted(new_27b_root.iterdir()):
        if not w_dir.is_dir():
            continue
        wid = w_dir.name
        new_map[wid] = {}
        for c_file in sorted(w_dir.glob("case*.json")):
            data = json.loads(c_file.read_text(encoding="utf-8"))
            c_idx = data.get("case_index", int(c_file.stem.replace("case", "")))
            new_map[wid][c_idx] = data

    updated_files = 0
    reports_dir = ROOT / "reports"
    import practical_reports

    for comp_path in sorted(reports_dir.glob("*compare*/**/comparison.json")):
        try:
            old_data = json.loads(comp_path.read_text(encoding="utf-8"))
            wid = old_data.get("factory_manifest", {}).get("weight_id") or old_data.get("weight_id")
            c_idx = old_data.get("case_index")
            if wid in new_map and c_idx in new_map[wid]:
                fresh = new_map[wid][c_idx]
                # Preserve cohort if heldout/report so existing directory structure works seamlessly
                if "evaluation_cohort" in old_data:
                    fresh["evaluation_cohort"] = old_data["evaluation_cohort"]
                comp_path.write_text(json.dumps(fresh, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                prac_path = comp_path.parent / "practical_report.md"
                if prac_path.exists():
                    prac_path.write_text(practical_reports.render(fresh), encoding="utf-8")
                updated_files += 1
        except Exception as e:
            print(f"[!] Warning updating {comp_path}: {e}")

    # Also ensure any 27B weight in new_map that didn't have a folder in reports/ (like 27B_v4_epoch2/5) gets a report folder
    existing_wids = set()
    for comp_path in reports_dir.glob("*compare*/**/comparison.json"):
        try:
            d = json.loads(comp_path.read_text(encoding="utf-8"))
            w = d.get("factory_manifest", {}).get("weight_id") or d.get("weight_id")
            if w:
                existing_wids.add(w)
        except Exception:
            pass

    for wid, cases_dict in new_map.items():
        if wid not in existing_wids:
            for c_idx, fresh in sorted(cases_dict.items()):
                ep = fresh.get("factory_manifest", {}).get("trained_epoch", 2)
                out_folder = reports_dir / f"smoke_compare_27B_v4_epoch{ep}_{wid[:8]}_{c_idx}"
                out_folder.mkdir(parents=True, exist_ok=True)
                (out_folder / "comparison.json").write_text(
                    json.dumps(fresh, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
                )
                (out_folder / "practical_report.md").write_text(
                    practical_reports.render(fresh), encoding="utf-8"
                )
                updated_files += 1

    print(f"[+] Updated {updated_files} local 27B comparison.json & practical_report.md files with real GPU outputs!")
    return updated_files


def main():
    pull_from_runpod()
    update_local_27b_reports()

    # Run strict evaluation & Neon DB sync scripts
    subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts/process_all_weights_strict_evaluation.py")], check=True)
    subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts/sync_all_weights_to_streamlit_canonical.py")], check=True)

    # Copy all rendered reports to docs/model_evaluation_reports
    src_reports = ROOT / "outputs/all_model_reports"
    dst_reports = PROJECT_ROOT / "docs/model_evaluation_reports"
    if src_reports.exists():
        if dst_reports.exists():
            shutil.rmtree(dst_reports)
        shutil.copytree(src_reports, dst_reports)
        print(f"[+] Synced all rendered Markdown reports to {dst_reports}")


if __name__ == "__main__":
    main()

