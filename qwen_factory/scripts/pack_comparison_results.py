"""Pack Qwen3.5-4B comparison outputs into a single JSON snapshot or ZIP bundle.

Usage:
  python scripts/pack_comparison_results.py [--output dashboard/current_4b_results.json]
  python scripts/pack_comparison_results.py --zip outputs/qwen35_4b_reports.zip
"""
import argparse
import json
from pathlib import Path
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def collect_snapshot(root):
    from qwen35_comparison_dashboard import scan_local_results
    return scan_local_results(root)


def main():
    parser = argparse.ArgumentParser(description="Pack comparison results")
    parser.add_argument("--output", type=Path, default=ROOT / "dashboard/current_4b_results.json", help="Path to output snapshot JSON")
    parser.add_argument("--zip", type=Path, default=None, help="Optional ZIP path to package comparison JSON files")
    args = parser.parse_args()

    data = collect_snapshot(ROOT)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"[+] Snapshot saved to: {args.output}")

    if args.zip:
        args.zip.parent.mkdir(parents=True, exist_ok=True)
        count = 0
        with zipfile.ZipFile(args.zip, "w", zipfile.ZIP_DEFLATED) as z:
            # Add snapshot
            z.write(args.output, "dashboard/current_4b_results.json")
            # Add all comparison JSONs from outputs
            for p in ROOT.glob("outputs/qwen35_4b_3000_*/**/comparison/*.json"):
                z.write(p, str(p.relative_to(ROOT)))
                count += 1
            for p in ROOT.glob("outputs/qwen35_4b_3000_*/full3000/result.json"):
                z.write(p, str(p.relative_to(ROOT)))
                count += 1
        print(f"[+] ZIP bundle saved to: {args.zip} ({count} files included)")


if __name__ == "__main__":
    main()

