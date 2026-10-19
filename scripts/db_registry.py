"""Preview/register immutable experiment plans; never starts training or uploads."""
import argparse
import copy
import hashlib
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv
from sqlalchemy import (JSON, Boolean, Column, DateTime, ForeignKey, Integer,
                        MetaData, String, Table, UniqueConstraint, create_engine,
                        insert, select)
from sqlalchemy.exc import IntegrityError


metadata = MetaData()
runs = Table("qf_runs", metadata,
    Column("run_id", String(36), primary_key=True),
    Column("config_hash", String(64), nullable=False, unique=True),
    Column("recipe_name", String(128), nullable=False),
    Column("is_sample", Boolean, nullable=False),
    Column("status", String(32), nullable=False),
    Column("config", JSON, nullable=False),
    Column("created_at", DateTime(timezone=True), nullable=False))
artifacts = Table("qf_artifacts", metadata,
    Column("weight_id", String(36), primary_key=True),
    Column("run_id", String(36), ForeignKey("qf_runs.run_id"), nullable=False),
    Column("trained_epoch", Integer, nullable=False),
    Column("status", String(32), nullable=False),
    Column("hf_repo_id", String(256)),
    Column("hf_revision", String(64)),
    Column("hf_subfolder", String(256)),
    UniqueConstraint("run_id", "trained_epoch", name="uq_qf_run_epoch"))


def digest(path):
    hasher = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            hasher.update(block)
    return hasher.hexdigest()


def sample_mode(config):
    mode=config.get('dataset_mode','sample')
    if mode not in ('sample','production'):
        raise ValueError('dataset_mode must be sample or production')
    return mode=='sample'

def factory_output(root,run_id,is_sample):
    uuid.UUID(str(run_id))
    return Path(root)/'outputs'/('factory_sample' if is_sample else 'factory_production')/run_id

def training_text(text):
    from prepare_data import validate
    rows=[];prompts=set()
    for number,line in enumerate(text.splitlines(),1):
        if not line.strip():continue
        try:
            row=json.loads(line)
            prompt=validate(row)
        except (ValueError,KeyError,TypeError,StopIteration):
            raise ValueError(f'Invalid training conversation at line {number}') from None
        rows.append(row);prompts.add(prompt)
    if not rows:raise ValueError('Training/validation dataset is empty')
    return rows,prompts

def validate_dataset_pair(train_text,validation_text):
    train,train_prompts=training_text(train_text)
    validation,validation_prompts=training_text(validation_text)
    if train_prompts & validation_prompts:
        raise ValueError('Training and validation share first-user prompts; split the data again without leakage')
    return len(train),len(validation)

def dataset_info(root, relative, is_sample):
    path = (root / relative).resolve()
    path.relative_to(root)  # Disallow accidental reads outside the project.
    in_sample = path.is_relative_to(root / "data" / "sample")
    if in_sample != is_sample:
        raise ValueError("--sample must match data/sample paths for BOTH datasets")
    if not path.is_file():
        raise ValueError(f"Missing dataset: {relative}")
    count = 0
    with path.open(encoding="utf-8-sig") as stream:
        for number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            row = json.loads(line)
            messages = row.get("messages") if isinstance(row, dict) else None
            if not isinstance(messages, list) or not messages:
                raise ValueError(f"Invalid messages: {relative}, line {number}")
            count += 1
    if count == 0:
        raise ValueError(f"Empty dataset: {relative}")
    return {"sha256": digest(path), "rows": count}


def build_plans(root, config_path, is_sample):
    config = yaml.safe_load(config_path.read_text(encoding="utf-8-sig"))
    if config.get("schema_version") != 1:
        raise ValueError("Unsupported schema_version")
    if sample_mode(config) != is_sample:
        raise ValueError("Dataset mode does not match registration mode")
    data = config["data"]
    train = dataset_info(root, data["train_file"], is_sample)
    validation = dataset_info(root, data["validation_file"], is_sample)
    for field,info in (("train",train),("validation",validation)):
        expected_hash=data.get(field+"_sha256")
        if expected_hash and info["sha256"]!=expected_hash:
            raise ValueError(field+" dataset changed after submission")
    if config.get('dataset_mode')=='production':
        validate_dataset_pair((root/data['train_file']).read_text(encoding='utf-8-sig'),
                              (root/data['validation_file']).read_text(encoding='utf-8-sig'))
    if train["sha256"] == validation["sha256"]:
        raise ValueError("Training and validation files are identical")
    expected = data.get("expected_train_samples")
    if expected is not None and expected != train["rows"]:
        raise ValueError(f"Expected {expected} training rows; found {train['rows']}")
    experiments = config.get("experiments")
    if not isinstance(experiments, list) or not experiments:
        raise ValueError("No experiments")
    plans = []
    for experiment in experiments:
        training = experiment["training"]
        total = training["num_train_epochs"]
        epochs = experiment["artifacts"]["save_epochs"]
        if not isinstance(epochs, list) or not epochs or any(type(e) is not int or e < 1 or e > total for e in epochs):
            raise ValueError("save_epochs must contain integers between 1 and num_train_epochs")
        if len(epochs) != len(set(epochs)):
            raise ValueError("Duplicate save_epochs")
        for field in ("per_device_train_batch_size", "gradient_accumulation_steps", "max_length"):
            if type(training[field]) is not int or training[field] < 1:
                raise ValueError(f"Invalid {field}")
        if not 0 < float(training["learning_rate"]) < 1:
            raise ValueError("Invalid learning_rate")
        canonical = {
            "identity_version": 1, "is_sample": is_sample,
            "model": config["model"], "quantization": config["quantization"],
            "data": {"format": data["format"], "train": train, "validation": validation},
            "lora": experiment["lora"], "training": training,
            # Save plan is immutable for this initial implementation.
            "save_epochs": sorted(epochs),
            "checkpoints": experiment["checkpoints"],
            "pipeline_version": "growpath-registry-v1",
        }
        if config.get('experiment_id'):
            uuid.UUID(config['experiment_id'])
            canonical.update(identity_version=2,experiment_id=config['experiment_id'])
        blob = json.dumps(canonical, sort_keys=True, ensure_ascii=False, allow_nan=False, separators=(",", ":"))
        plans.append({"recipe_name": experiment["recipe_name"],
                      "config_hash": hashlib.sha256(blob.encode()).hexdigest(),
                      "config": copy.deepcopy(canonical)})
    return plans


def register(engine, plan):
    try:
        with engine.begin() as connection:
            existing = connection.execute(select(runs).where(runs.c.config_hash == plan["config_hash"])).mappings().first()
            if existing:
                return False, dict(existing)
            run_id = str(uuid.uuid4())
            record = dict(run_id=run_id, config_hash=plan["config_hash"],
                          recipe_name=plan["recipe_name"], is_sample=plan["config"]["is_sample"],
                          status="PLANNED", config=plan["config"], created_at=datetime.now(timezone.utc))
            connection.execute(insert(runs).values(**record))
            for epoch in plan["config"]["save_epochs"]:
                connection.execute(insert(artifacts).values(weight_id=str(uuid.uuid4()),
                    run_id=run_id, trained_epoch=epoch, status="PENDING"))
            return True, record
    except IntegrityError:
        # Another process can register the same hash at the same time.
        with engine.connect() as connection:
            existing = connection.execute(select(runs).where(runs.c.config_hash == plan["config_hash"])).mappings().first()
            if existing:
                return False, dict(existing)
        raise


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--sample", action="store_true")
    parser.add_argument("--register", action="store_true", help="Create registry tables and insert plans")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    plans = build_plans(root, (root / args.config).resolve(), args.sample)
    for plan in plans:
        print(f"Recipe: {plan['recipe_name']}; hash: {plan['config_hash']}")
        print(f"Sample: {args.sample}; epochs: {plan['config']['save_epochs']}")
        if plan["config"]["model"].get("revision") in (None, "main"):
            print("NOTE: model revision must be pinned before real training; preview registration is not training approval.")
    if not args.register:
        print("PREVIEW ONLY: no database connection or writes.")
        return
    load_dotenv(root / ".env")
    url = os.getenv("DATABASE_URL")
    if not url:
        raise ValueError("DATABASE_URL missing")
    engine = create_engine(url, pool_pre_ping=True)
    try:
        metadata.create_all(engine)
        for plan in plans:
            created, record = register(engine, plan)
            print(f"{'REGISTERED' if created else 'EXISTS'} run_id={record['run_id']} status={record['status']}")
            with engine.connect() as connection:
                records = connection.execute(select(artifacts).where(artifacts.c.run_id == record["run_id"]).order_by(artifacts.c.trained_epoch)).mappings()
                for row in records:
                    print(f"  epoch={row['trained_epoch']} weight_id={row['weight_id']} status={row['status']}")
    finally:
        engine.dispose()
    print("No training, HF upload, evaluation or status transition was performed.")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        # Never print connection URLs or database exception details containing secrets.
        print(f"FAILED ({type(error).__name__}). Check config, dataset paths, packages and .env connection settings.")
        if isinstance(error, (ValueError, FileNotFoundError, KeyError)):
            print(str(error) if "postgres" not in str(error).lower() else "Check DATABASE_URL.")
        raise SystemExit(1)
