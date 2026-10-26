"""Validate text-only messages JSONL and split by normalized first user prompt."""
import argparse
import hashlib
import json
import random
import re
import unicodedata
import shutil
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


def import_curated_release(source, root):
    """Import an already grouped 1200/150/150 release without re-splitting it."""
    source=Path(source).resolve();root=Path(root).resolve()
    manifest=json.loads((source/'manifest.json').read_text(encoding='utf-8'))
    counts={'train':1200,'validation':150,'test':150}
    if manifest.get('selected')!=1500 or manifest.get('split_counts')!=counts:
        raise ValueError('Expected the curated 1500-record release with 1200/150/150 splits')
    expected=manifest['files_sha256']
    names=[f'sft_{s}.jsonl' for s in counts]+['provenance.jsonl','sample_review.json']
    for name in names:
        if hashlib.sha256((source/name).read_bytes()).hexdigest()!=expected[name]:
            raise ValueError('Release file hash mismatch: '+name)
    provenance=[json.loads(l) for l in (source/'provenance.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
    if len(provenance)!=1500:raise ValueError('Expected 1500 provenance records')
    families={};seen_prompts=set();seen_ids=set()
    for split,count in counts.items():
        rows=[json.loads(l) for l in (source/f'sft_{split}.jsonl').read_text(encoding='utf-8').splitlines() if l.strip()]
        metadata=[r for r in provenance if r['split']==split]
        if len(rows)!=count or len(metadata)!=count:raise ValueError('Release split count mismatch')
        prompts=set()
        for row,info in zip(rows,metadata):
            prompt=validate(row);prompts.add(prompt)
            sha=hashlib.sha256(json.dumps(row,ensure_ascii=False,sort_keys=True,default=str).encode('utf-8')).hexdigest()
            if sha!=info['sha256'] or info['id'] in seen_ids:raise ValueError('Provenance binding or duplicate ID error')
            seen_ids.add(info['id'])
            family=info['family_id']
            if family in families and families[family]!=split:raise ValueError('Cross-split project family')
            families[family]=split
        if seen_prompts & prompts:raise ValueError('Cross-split user prompt overlap')
        seen_prompts.update(prompts)
    target=root/'data/production/curation_1500'
    if target.exists():raise ValueError('Curated import exists; refusing overwrite')
    target.mkdir(parents=True)
    for split in counts:shutil.copyfile(source/f'sft_{split}.jsonl',target/f'{split}.jsonl')
    for name in ('provenance.jsonl','manifest.json','sample_review.json'):shutil.copyfile(source/name,target/name)
    return {'status':'IMPORTED_WITH_ORIGINAL_FAMILY_SPLITS','counts':counts,'target':str(target),
            'training_started':False,'reshuffled':False,'external_upload':False}


def install_curated_uploads(root, uploads, config):
    """Install exactly the frozen files required by the selected training policy."""
    import tempfile
    from db_registry import build_plans
    root=Path(root).resolve()
    specs={
        'train':(config['data']['train_file'],config['data']['train_sha256']),
        'report':(config['evaluation']['file'],config['evaluation']['sha256']),
    }
    for key,field in (('validation','validation_file'),('heldout','heldout_test_file')):
        if config['data'].get(field):specs[key]=(config['data'][field],config['data'][key+'_sha256'])
    if set(uploads)!=set(specs):raise ValueError('Upload all required files together: '+', '.join(specs))
    for key,(relative,expected) in specs.items():
        target=(root/relative).resolve()
        if not target.is_relative_to(root/'data'):raise ValueError('Unsafe dataset path')
        raw=uploads[key]
        if not isinstance(raw,bytes) or hashlib.sha256(raw).hexdigest()!=expected:
            raise ValueError('Frozen file hash mismatch: '+key)
        if target.exists() and target.read_bytes()!=raw:raise ValueError('Refusing to overwrite different data: '+key)
    # Validate counts, hashes, heldout isolation and the report cohort before any installation.
    import yaml
    with tempfile.TemporaryDirectory() as folder:
        stage=Path(folder).resolve()
        for key,(relative,_) in specs.items():
            target=stage/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(uploads[key])
        recipe=stage/'recipe.yaml';recipe.write_text(yaml.safe_dump(config),encoding='utf-8')
        build_plans(stage,recipe,False)
    for key,(relative,_) in specs.items():
        target=root/relative;target.parent.mkdir(parents=True,exist_ok=True);target.write_bytes(uploads[key])
    return ({'train':1500,'report':10} if config['data'].get('training_scope')=='all_1500_fixed10'
            else {'train':1200,'validation':150,'heldout':150,'report':10})


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--input", type=Path)
    mode.add_argument("--release", type=Path, help="Import an existing 1200/150/150 release without random re-splitting")
    parser.add_argument("--seed", default=42, type=int)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    if args.release:
        print(json.dumps(import_curated_release(args.release,root),ensure_ascii=False,indent=2))
        return
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
