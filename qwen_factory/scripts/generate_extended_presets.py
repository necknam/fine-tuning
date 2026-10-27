"""Generate systematic hyperparameters configs for extended presets P07 to P111.

Explores grid of:
- learning_rate: [3e-5, 5e-5, 7.5e-5, 1e-4, 1.25e-4, 1.5e-4, 2e-4]
- r & alpha: [(16,32), (32,64), (48,96), (64,128), (96,192), (128,256)]
- weight_decay: [0.01, 0.05, 0.0]
- warmup_ratio: [0.05, 0.03]
"""
import itertools
import json
from pathlib import Path
import yaml

ROOT = Path(__file__).resolve().parents[1]

LRS = [0.0001, 0.000075, 0.00005, 0.000125, 0.00015, 0.00003, 0.0002]
RANKS = [
    (32, 64),
    (64, 128),
    (128, 256),
    (16, 32),
    (48, 96),
    (96, 192),
]
WEIGHT_DECAYS = [0.01, 0.05, 0.0]
WARMUPS = [0.05, 0.03]

TEMPLATE = """# Extended preset {pid} (lr={lr}, r={r}, alpha={alpha}, wd={wd}, warmup={warmup})
profile: qwen35_4b_b200_3000_{pid_lower}_v1
preset: {pid}
hardware: B200
model:
  base_model_id: Qwen/Qwen3.5-4B
  revision: 851bf6e806efd8d0a36b00ddf55e13ccb7b8cd0a
quantization:
  load_in_4bit: false
  dtype: bfloat16
data:
  expected_records: 3000
  train_file: data/production/expanded_3000/all.jsonl
  release_manifest: data/production/expanded_3000/release_manifest.json
  original_file: data/revision_1500/assembled/all.jsonl
training:
  learning_rate: {lr_str}
  num_train_epochs: 5
  per_device_train_batch_size: 1
  gradient_accumulation_steps: 16
  max_length: 10240
  packing: false
  bf16: true
  gradient_checkpointing: true
  loss_policy: final_assistant_only
  seed: 42
  data_seed: 42
  warmup_ratio: {warmup}
  lr_scheduler_type: cosine
  weight_decay: {wd}
  optim: paged_adamw_8bit
lora:
  r: {r}
  lora_alpha: {alpha}
  lora_dropout: 0.05
  bias: none
  scope: language_model/all-linear
sample:
  records: 60
  epochs: 1
  maximum_memory_fraction: 0.95
save_epochs:
- 2
- 5
evaluation:
  file: data/eval/prompts.app_v2.jsonl
  sha256: d0e1b2d687063250aadeed1b7735dafaaa5d9fce25a82566b79dffbe30b050ac
inference:
  max_new_tokens: 4096
  do_sample: false
  enable_thinking: false
output_root: outputs/qwen35_4b_3000_{pid}
model_cache: /workspace/.cache/huggingface
runtime:
  packages:
    transformers: 4.57.3
    torch: 2.7.0
    peft: 0.17.1
    accelerate: 1.12.0
    datasets: 3.6.0
    triton: 3.6.0
"""

def generate_presets():
    combos = list(itertools.product(LRS, RANKS, WEIGHT_DECAYS, WARMUPS))
    configs_dir = ROOT / "configs"
    configs_dir.mkdir(parents=True, exist_ok=True)

    manifest = {}

    for idx in range(7, 112):
        pid = f"P{idx:02d}" if idx < 100 else f"P{idx}"
        combo_idx = (idx - 7) % len(combos)
        lr, (r, alpha), wd, warmup = combos[combo_idx]

        cfg_text = TEMPLATE.format(
            pid=pid,
            pid_lower=pid.lower(),
            lr=lr,
            lr_str=f"{lr:.6f}".rstrip('0'),
            r=r,
            alpha=alpha,
            wd=wd,
            warmup=warmup
        )
        file_path = configs_dir / f"hyperparameters.qwen35_4b_3000.{pid}.yaml"
        file_path.write_text(cfg_text, encoding="utf-8")
        manifest[pid] = {
            "learning_rate": lr,
            "r": r,
            "lora_alpha": alpha,
            "weight_decay": wd,
            "warmup_ratio": warmup
        }

    manifest_path = ROOT / "configs" / "extended_presets_manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(f"[+] Regenerated 105 extended preset YAMLs (P07 to P111)")

if __name__ == "__main__":
    generate_presets()

