"""Sequentially run Qwen3.5-4B B200 presets P01 to P06 on RunPod.

Usage:
  python scripts/run_all_qwen35_presets.py [--presets P01 P02 P03 P04 P05 P06] [--phase all] [--execute]
"""
import argparse
import json
from pathlib import Path
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]

ALL_PRESETS = [f"P{i:02d}" if i < 100 else f"P{i}" for i in range(1, 112)]


def main():
    parser = argparse.ArgumentParser(description="Batch runner for Qwen3.5-4B presets P01~P06")
    parser.add_argument('--presets', nargs='+', default=ALL_PRESETS, choices=ALL_PRESETS, help="Presets to run")
    parser.add_argument('--phase', choices=['check', 'sample', 'train', 'compare', 'all'], default='all', help="Phase to execute")
    parser.add_argument('--execute', action='store_true', help="Execute on GPU (required for training/inference)")
    parser.add_argument('--resume', action='store_true', help="Resume full training if checkpoint exists")
    args = parser.parse_args()

    status_file = ROOT / "outputs" / "all_presets_progress.json"
    status_file.parent.mkdir(parents=True, exist_ok=True)

    summary = {
        "started_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "phase": args.phase,
        "execute": args.execute,
        "presets": {}
    }

    print(f"=== Qwen3.5-4B Batch Preset Execution ({', '.join(args.presets)}) ===")
    print(f"Phase: {args.phase}, Execute: {args.execute}")

    for pid in args.presets:
        cfg_path = ROOT / f"configs/hyperparameters.qwen35_4b_3000.{pid}.yaml"
        if not cfg_path.is_file():
            print(f"[-] Config {cfg_path.name} not found. Skipping {pid}.")
            summary["presets"][pid] = {"status": "CONFIG_NOT_FOUND"}
            continue

        print(f"\n[{time.strftime('%H:%M:%S')}] >>> Starting Preset {pid} ({cfg_path.name}) <<<")
        start_t = time.perf_counter()

        cmd = [
            sys.executable,
            "-u",
            str(ROOT / "scripts/qwen35_b200_runner.py"),
            "--config", str(cfg_path.relative_to(ROOT)),
            "--phase", args.phase
        ]
        if args.execute:
            cmd.append("--execute")
        if args.resume:
            cmd.append("--resume")

        ret = subprocess.run(cmd)
        elapsed = time.perf_counter() - start_t

        if ret.returncode == 0:
            print(f"[{time.strftime('%H:%M:%S')}] [+] Preset {pid} COMPLETED in {elapsed/60:.1f} min.")
            summary["presets"][pid] = {"status": "SUCCESS", "elapsed_seconds": elapsed}
        else:
            print(f"[{time.strftime('%H:%M:%S')}] [!] Preset {pid} FAILED (code {ret.returncode}) after {elapsed/60:.1f} min.")
            summary["presets"][pid] = {"status": "FAILED", "returncode": ret.returncode, "elapsed_seconds": elapsed}
            # Stop batch on failure so user can inspect and not waste GPU time
            break

        status_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")

    summary["finished_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    status_file.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n=== Batch Run Finished. Summary written to {status_file} ===")


if __name__ == '__main__':
    main()

