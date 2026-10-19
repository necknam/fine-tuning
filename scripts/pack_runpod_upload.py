"""Build a source/sample bundle, excluding credentials, caches and weights."""
from pathlib import Path
import zipfile

root = Path(__file__).resolve().parents[1]
target = root / "outputs/runpod_control_bundle.zip"
files = list((root/"scripts").glob("*.py")) + list((root/"configs").glob("hyperparameters*.yaml"))
files += list((root/"data/sample").rglob("*.jsonl"))
files += [root/name for name in ("requirements-runpod.txt", "README.md", "docs/hyperparameters.html", "data/eval/prompts.jsonl")]
for path in files:
    if not path.is_file():
        raise SystemExit(f"Missing bundle input: {path.name}")
target.parent.mkdir(exist_ok=True)
with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as archive:
    for path in sorted(set(files)):
        archive.write(path, path.relative_to(root))
print(target)
