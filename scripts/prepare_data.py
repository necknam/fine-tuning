"""Validate text-only messages JSONL and split by normalized first user prompt."""
import argparse
import hashlib
import json
import random
import re
import unicodedata
from pathlib import Path


def normalize(value):
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", value)).strip()


def validate(row):
    if not isinstance(row, dict) or set(row) != {"messages"}:
        raise ValueError('each row must contain only "messages"')
    messages = row["messages"]
    if not isinstance(messages, list) or len(messages) < 2:
        raise ValueError("messages must contain at least user and assistant")
    expected = "user"
    for i, message in enumerate(messages):
        if not isinstance(message, dict) or set(message) != {"role", "content"}:
            raise ValueError("each message must contain role and content only")
        role, content = message["role"], message["content"]
        if not isinstance(content, str) or not normalize(content):
            raise ValueError("content must be non-empty text")
        if i == 0 and role == "system":
            continue
        if role != expected:
            raise ValueError("after optional system, alternate user/assistant")
        expected = "assistant" if role == "user" else "user"
    if messages[-1]["role"] != "assistant":
        raise ValueError("conversation must end with assistant")
    return next(normalize(m["content"]) for m in messages if m["role"] == "user")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--seed", default=42, type=int)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    source = args.input.resolve()
    if not source.is_file():
        raise SystemExit(f"Input file missing: {source}")
    targets = [root / "data/processed/train.jsonl",
               root / "data/processed/validation.jsonl",
               root / "data/eval/test.jsonl",
               root / "data/processed/data_manifest.json"]
    if any(p.exists() for p in targets):
        raise SystemExit("Output already exists. Back it up and remove it deliberately before re-splitting.")
    groups, seen, errors = {}, set(), []
    duplicates = blanks = records = 0
    with source.open(encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                blanks += 1
                continue
            try:
                row = json.loads(line)
                group_key = validate(row)
                canonical = json.dumps(row, ensure_ascii=False, sort_keys=True)
                if canonical in seen:
                    duplicates += 1
                    continue
                seen.add(canonical)
                groups.setdefault(group_key, []).append(row)
                records += 1
            except (ValueError, TypeError, KeyError, StopIteration) as error:
                errors.append(f"line {line_number}: {error}")
    if errors:
        print("Validation failed; no output written.")
        print("\n".join(errors[:20]))
        raise SystemExit(f"Total invalid rows: {len(errors)}")
    if len(groups) < 20:
        raise SystemExit("Need at least 20 distinct first-user prompts for the 90/5/5 split.")
    keys = sorted(groups)
    random.Random(args.seed).shuffle(keys)
    held_out = max(1, int(len(keys) * 0.05))
    subsets = [keys[held_out * 2:], keys[:held_out], keys[held_out:held_out * 2]]
    counts = {}
    for name, path, subset in zip(("train", "validation", "test"), targets, subsets):
        rows = [row for key in subset for row in groups[key]]
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8", newline="\n") as stream:
            for row in rows:
                stream.write(json.dumps(row, ensure_ascii=False) + "\n")
        counts[name] = len(rows)
        print(f"{name}: {len(rows)} rows -> {path}")
    manifest = {
        "source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(),
        "seed": args.seed,
        "split_policy": "90/5/5 by normalized first user prompt group; rounded held-out counts",
        "unique_records": records,
        "prompt_groups": len(groups),
        "duplicates_removed": duplicates,
        "blank_lines_ignored": blanks,
        "counts": counts,
        "output_sha256": {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in targets[:3]},
    }
    targets[3].write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"Duplicates removed: {duplicates}; blank lines ignored: {blanks}")
    print("Done. Semantic similarity, factual quality and token lengths still need review.")


if __name__ == "__main__":
    main()
