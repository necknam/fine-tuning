"""Check HF access and pin model metadata, without downloading model weights."""
import argparse
import io
import os
import uuid
from pathlib import Path

import yaml
from dotenv import load_dotenv
from huggingface_hub import HfApi


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--check-upload", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = (root / args.config).resolve()
    config = yaml.safe_load(source.read_text(encoding="utf-8-sig"))
    output = (root / args.output).resolve() if args.output else None
    if output:
        output.relative_to(root)
        if output.exists():
            raise ValueError("Output exists; choose another filename. Nothing overwritten.")
        if output == source:
            raise ValueError("Output must differ from input")
    load_dotenv(root / ".env")
    token = os.getenv("HF_TOKEN")
    repo_id = os.getenv("HF_REPO_ID")
    if not token or not repo_id:
        raise ValueError("HF_TOKEN or HF_REPO_ID missing in .env")
    api = HfApi(token=token)
    api.whoami()
    print("[OK] HF authentication")
    info = api.model_info(config["model"]["base_model_id"], revision=config["model"].get("revision", "main"))
    if not info.sha or len(info.sha) != 40:
        raise ValueError("Model commit could not be resolved")
    config["model"]["revision"] = info.sha
    print(f"[OK] Base model commit: {info.sha}")
    repository = api.repo_info(repo_id=repo_id, repo_type="model")
    if not repository.private:
        raise ValueError("Expected a private adapter repository. Check HF_REPO_ID and repository settings.")
    print("[OK] Private adapter repository is readable")
    if args.check_upload:
        probe = f"_preflight/{uuid.uuid4().hex}.txt"
        uploaded = False
        try:
            api.upload_file(path_or_fileobj=io.BytesIO(b"GrowPath temporary write-access probe. No personal data.\n"),
                path_in_repo=probe, repo_id=repo_id, repo_type="model",
                commit_message="Check GrowPath upload permission")
            uploaded = True
            print("[OK] Temporary file upload")
        finally:
            if uploaded:
                try:
                    api.delete_file(path_in_repo=probe, repo_id=repo_id, repo_type="model",
                                    commit_message="Remove GrowPath temporary access probe")
                    print("[OK] Temporary file removed from repository tree")
                except Exception:
                    print(f"[ACTION REQUIRED] Remove this temporary file manually: {probe}")
                    raise
    else:
        print("[NOT TESTED] Write permission; use --check-upload to verify")
    if output:
        output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive create prevents overwriting an existing configuration.
        with output.open("x", encoding="utf-8") as stream:
            stream.write("# Model revision pinned by preflight. No model weights downloaded.\n")
            yaml.safe_dump(config, stream, allow_unicode=True, sort_keys=False)
        print(f"[OK] Pinned YAML: {output}")
    print("DONE: HF checks only. No GPU, training or DB registration.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print(f"[FAIL] {type(error).__name__}")
        if isinstance(error, (ValueError, FileNotFoundError, KeyError)):
            print(str(error))
        else:
            print("Check network access, HF_TOKEN permissions, model ID and HF_REPO_ID. Secret-bearing exception details were omitted.")
        raise SystemExit(1)
