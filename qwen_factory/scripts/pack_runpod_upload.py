"""Build a source/sample bundle, excluding credentials, caches and weights."""
from pathlib import Path
import zipfile
import yaml
from db_registry import report_input_info

root = Path(__file__).resolve().parents[1]
target = root / "outputs/runpod_control_bundle.zip"
files = list((root/"scripts").glob("*.py")) + list((root/"configs").glob("hyperparameters*.yaml"))
files += list((root/"tests").glob("test_*.py"))
files += list((root/"data/sample").rglob("*.jsonl"))
files += [root/name for name in ("requirements-runpod.txt", "README.md", "data/eval/prompts.jsonl")]
guide=root.parent/'docs/FINETUNING_GUIDE.md'
files.append(guide if guide.is_file() else root/'docs/FINETUNING_GUIDE.md')
config=yaml.safe_load((root/'configs/hyperparameters.sample.pinned.yaml').read_text(encoding='utf-8-sig'))
cohort=report_input_info(root,config)
if cohort:
    evaluation_path=root/cohort['file']
    files.append(evaluation_path)
    manifest=evaluation_path.with_suffix('.manifest.json')
    if manifest.is_file():files.append(manifest)
for path in files:
    if not path.is_file():
        raise SystemExit(f"Missing bundle input: {path.name}")
target.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(set(files)):
        archive.write(path, path.relative_to(root) if path.is_relative_to(root) else Path('docs')/path.name)
print(target)
