"""Update Streamlit snapshot (dashboard/current_4b_results.json), export 4B P01 & P02 Epoch 2/5
into qwen_factory/reports/smoke_compare_4B_*, register candidate_versions.json & run_configs,
persist all comparison JSONs to Neon DB documents table, and refresh ai_evaluations.
"""
import hashlib
import json
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import dashboard_store
import human_reports
import practical_reports
from pack_comparison_results import collect_snapshot


def main():
    # 1. Update qwen_factory/dashboard/current_4b_results.json
    snap_path = ROOT / "dashboard/current_4b_results.json"
    snap_path.parent.mkdir(parents=True, exist_ok=True)
    snap_data = collect_snapshot(ROOT)
    snap_path.write_text(json.dumps(snap_data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"[+] Updated {snap_path} with presets: {list(snap_data.get('presets', {}).keys())}")

    # 2. Export 4B P01 & P02 (Epoch 2 & 5) into qwen_factory/reports/smoke_compare_4B_*
    # so that local_dashboard.py ("학습·실전 보고서") also lists 4B weights alongside 27B weights!
    eval_sha = hashlib.sha256((ROOT / "data/eval/prompts.app_v2.jsonl").read_bytes()).hexdigest()
    new_prompts = [
        json.loads(line)
        for line in (ROOT / "data/eval/prompts.app_v2.jsonl").read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]

    reports_dir = ROOT / "reports"
    run_configs_dir = reports_dir / "run_configs"
    run_configs_dir.mkdir(parents=True, exist_ok=True)

    exported_paths = []
    for preset in ("P01", "P02", "P03"):
        p_root = ROOT / f"outputs/qwen35_4b_3000_{preset}"
        if not p_root.exists():
            continue
        run_id = f"qwen35-4b-3000-{preset.lower()}"
        # Write run_config yaml so report_parameters.summary works cleanly in local_dashboard.py
        cfg_src = ROOT / f"configs/hyperparameters.qwen35_4b_3000.{preset}.yaml"
        run_cfg_dest = run_configs_dir / f"{run_id}.yaml"
        if cfg_src.exists():
            import yaml
            raw_cfg = yaml.safe_load(cfg_src.read_text(encoding="utf-8"))
            wrapped_cfg = {
                "model": raw_cfg.get("model", {"base_model_id": "Qwen/Qwen3.5-4B", "revision": "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a"}),
                "quantization": raw_cfg.get("quantization", {"load_in_4bit": False, "dtype": "bfloat16"}),
                "experiments": [
                    {
                        "name": f"Qwen3.5-4B {preset}",
                        "preset": preset,
                        "training": raw_cfg.get("training", {}),
                        "lora": raw_cfg.get("lora", {}),
                    }
                ],
            }
            run_cfg_dest.write_text(yaml.safe_dump(wrapped_cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
            exported_paths.append(run_cfg_dest)

        for epoch_num in (2, 5):
            epoch_str = f"epoch{epoch_num}"
            wid = str(uuid.uuid5(uuid.NAMESPACE_DNS, f"qwen35-4b-{preset}-{epoch_str}"))
            comp_files = sorted(p_root.glob(f"**/full3000/{epoch_str}/comparison/case*.json"))
            for c_file in comp_files:
                c_data = json.loads(c_file.read_text(encoding="utf-8"))
                c_idx = c_data.get("case_index", int(c_file.stem.replace("case", "")))
                messages = new_prompts[c_idx]["messages"][:-1]
                reference = new_prompts[c_idx]["messages"][-1]["content"]

                folder_name = f"smoke_compare_4B_{preset}_ep{epoch_num}_c{c_idx:02d}"
                out_folder = reports_dir / folder_name
                out_folder.mkdir(parents=True, exist_ok=True)

                manifest = {
                    "run_id": run_id,
                    "weight_id": wid,
                    "trained_epoch": epoch_num,
                    "config_hash": c_data.get("contract", {}).get("config_sha256", ""),
                    "is_sample": False,
                    "model": {
                        "base_model_id": "Qwen/Qwen3.5-4B",
                        "revision": "851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a",
                    },
                    "dataset": {
                        "format": "messages",
                        "train": {
                            "sha256": c_data.get("contract", {}).get("data_sha256", ""),
                            "rows": 3000,
                        },
                        "validation": None,
                        "training_scope": "expanded_3000_fixed10",
                    },
                }

                base_obj = dict(c_data.get("base", {}))
                base_obj.setdefault("ended_with_eos", not base_obj.get("hit_token_limit", False))
                tuned_obj = dict(c_data.get("tuned", {}))
                tuned_obj.setdefault("ended_with_eos", not tuned_obj.get("hit_token_limit", False))

                comp_payload = {
                    "purpose": "fixed-input BF16 comparison; human evaluation scored separately",
                    "created_at": datetime.now(timezone.utc).isoformat(),
                    "model": manifest["model"],
                    "quantization": {"load_in_4bit": False, "dtype": "bfloat16"},
                    "training_quantization": {"load_in_4bit": False, "dtype": "bfloat16"},
                    "adapter_path": f"outputs/qwen35_4b_3000_{preset}/full3000/{epoch_str}/adapter",
                    "factory_manifest": manifest,
                    "adapter_sha256": c_data.get("adapter_sha256", ""),
                    "test_sha256": eval_sha,
                    "case_index": c_idx,
                    "evaluation_total": 10,
                    "evaluation_cohort": "report",
                    "messages": messages,
                    "reference_unreviewed": reference,
                    "reference_sha256": hashlib.sha256(reference.encode("utf-8")).hexdigest(),
                    "training_config_hash": manifest["config_hash"],
                    "reference_status": "fixed_dataset_answer_not_expert_validated",
                    "generation": {"max_new_tokens": 4096, "do_sample": False},
                    "packages": {"torch": "2.8.0+cu128", "transformers": "5.20.0", "peft": "0.21.2", "triton": "3.6.0"},
                    "inference_runtime": {"linear_attention_backend": "installed"},
                    "base": base_obj,
                    "tuned": tuned_obj,
                    "texts_identical": base_obj.get("text") == tuned_obj.get("text"),
                }

                comp_json_path = out_folder / "comparison.json"
                comp_json_path.write_text(json.dumps(comp_payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
                (out_folder / "practical_report.md").write_text(practical_reports.render(comp_payload), encoding="utf-8")
                exported_paths.append(comp_json_path)

    print(f"[+] Exported {len(exported_paths)} 4B comparison/config files to qwen_factory/reports/")

    # 3. Rebuild catalog & candidate_versions.json
    groups = human_reports.catalog(ROOT, cohort="report")
    print(f"[+] human_reports.catalog now has {len(groups)} weight groups ready for Streamlit!")

    # 4. Persist all exported comparison.json, run_configs, candidate_versions.json, prompts.app_v2.jsonl to Neon DB
    to_persist = [
        ROOT / "data/eval/prompts.app_v2.jsonl",
        ROOT / "reports/candidate_versions.json",
        ROOT / "reports/control_history.json",
    ] + exported_paths
    dashboard_store.persist_many(ROOT, to_persist)
    print(f"[+] Persisted {len(to_persist)} documents to Neon PostgreSQL (qf_dashboard.documents)!")

    # 5. Re-run canonical AI evaluation sync so all signatures match 100%
    subprocess.run([sys.executable, "-X", "utf8", str(ROOT / "scripts/sync_all_weights_to_streamlit_canonical.py")], check=True)


if __name__ == "__main__":
    main()

