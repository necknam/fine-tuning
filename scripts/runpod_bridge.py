"""Detached RunPod jobs; called through the existing authenticated Jupyter kernel."""
import fcntl
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
import uuid

ROOT = Path(__file__).resolve().parents[1]
JOBS = ROOT / "outputs/control_jobs"
PYTHON = ROOT / ".venv-runpod/bin/python"


def inside(relative, prefix):
    path = (ROOT / relative).resolve()
    path.relative_to((ROOT / prefix).resolve())
    return path


def atomic(path, data):
    temporary = path.with_name(path.name + "." + uuid.uuid4().hex + ".tmp")
    temporary.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def process_stamp(pid):
    try:
        return Path(f"/proc/{pid}/stat").read_text().rpartition(")")[2].split()[19]
    except (FileNotFoundError, IndexError, PermissionError):
        return None


def alive(pid, stamp=None):
    try:
        os.kill(pid, 0)
        fields = Path(f"/proc/{pid}/stat").read_text().rpartition(")")[2].split()
        return fields[0] not in ("Z", "X") and (stamp is None or fields[19] == stamp)
    except (ProcessLookupError, FileNotFoundError, IndexError):
        return False
    except PermissionError:
        # Unknown is busy, not permission to launch another GPU job.
        return True


def status():
    result = []
    for f in sorted(JOBS.glob("*/job.json")):
        item = json.loads(f.read_text())
        if item["state"] == "RUNNING" and not alive(item["pid"], item.get("pid_stamp")):
            item = dict(item, state="INTERRUPTED")
        if item["state"] == "QUEUED" and item.get("worker_pid") and not alive(item["worker_pid"],item.get("worker_stamp")):
            item = dict(item, state="INTERRUPTED")
        log = f.parent / "job.log"
        if log.exists():
            with log.open("rb") as stream:
                stream.seek(max(0, log.stat().st_size - 16000))
                item["log_tail"] = stream.read().decode("utf-8", errors="replace")
        result.append(item)
    return result


def command(kind, config, adapter=None, case=0):
    config_path = inside(config, "configs")
    if not config_path.is_file():
        raise ValueError("Config not found")
    factory = [str(PYTHON), "-u", "scripts/runpod_factory_sample.py", "--config", config]
    if kind == "check":
        return factory + ["--check-connections"]
    if kind == "register":
        import yaml
        from db_registry import sample_mode
        cfg=yaml.safe_load(config_path.read_text(encoding='utf-8-sig'))
        return [str(PYTHON), "-u", "scripts/db_registry.py", "--config", config, *(["--sample"] if sample_mode(cfg) else []), "--register"]
    if kind in ("train", "resume", "sync"):
        return factory + (["--sync-only"] if kind == "sync" else ["--execute"]) + (["--resume"] if kind == "resume" else [])
    if kind == "compare":
        path = inside(adapter, "outputs")
        if not (path / "factory_manifest.json").is_file() or not 0 <= int(case) <= 100000:
            raise ValueError("Invalid adapter or case")
        return [str(PYTHON), "-u", "scripts/compare_factory_sample.py", "--config", config,
                "--adapter", str(path), "--case-index", str(int(case)), "--max-new-tokens", "2048"]
    if kind == "probe":
        return [str(PYTHON), "-c", "print('LOCAL_RUNPOD_BRIDGE_OK', flush=True)"]
    if kind == "experiment":
        return [str(PYTHON), "-u", "scripts/control_pipeline.py", "--config", config]
    if kind == "evaluate_existing":
        return [str(PYTHON), "-u", "scripts/control_pipeline.py", "--config", config, "--evaluate-only"]
    if kind == "continue_experiment":
        return [str(PYTHON), "-u", "scripts/control_pipeline.py", "--config", config, "--resume-existing"]
    raise ValueError("Unsupported job kind")


def submit(kind, config="configs/hyperparameters.sample.pinned.yaml", adapter=None, case=0, priority=10, label=""):
    JOBS.mkdir(parents=True, exist_ok=True)
    argv = command(kind, config, adapter, case)
    if not PYTHON.is_file():
        raise ValueError("RunPod venv is missing")
    if kind in ("check", "register", "train", "resume", "sync", "experiment", "continue_experiment", "evaluate_existing"):
        missing = [k for k in ("HF_TOKEN", "HF_REPO_ID", "DATABASE_URL") if not os.environ.get(k)]
        if missing:
            raise ValueError("Missing remote credentials: " + ", ".join(missing))
    # Serialize submissions and GPU work across controllers, even after a client disconnects.
    with (JOBS / "submit.lock").open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        existing = next((j for j in status() if j["state"] in ("RUNNING","QUEUED") and j["argv"] == argv),None)
        if existing:
            return existing
        job_id = time.strftime("%Y%m%d_%H%M%S") + "_" + uuid.uuid4().hex[:8]
        folder = JOBS / job_id
        folder.mkdir()
        record = dict(job_id=job_id, kind=kind, state="QUEUED", created_at=time.time(), argv=argv,
                      priority=int(priority), label=str(label)[:120],config=config,adapter=adapter,case=int(case))
        atomic(folder / "job.json", record)
        with (JOBS / "worker.log").open("ab") as log:
            worker = subprocess.Popen([str(PYTHON), str(Path(__file__)), job_id], cwd=ROOT,
                                      stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                      start_new_session=True, close_fds=True)
        record["worker_pid"] = worker.pid
        record["worker_stamp"] = process_stamp(worker.pid)
        atomic(folder/"job.json",record)
        return record


def promote(job_id, priority=None):
    if not re.fullmatch(r"[0-9_]+[a-f0-9]{8}", job_id):
        raise ValueError("Invalid job ID")
    with (JOBS / "submit.lock").open("a") as guard:
        fcntl.flock(guard, fcntl.LOCK_EX)
        path = JOBS / job_id / "job.json"
        record = json.loads(path.read_text())
        if record["state"] != "QUEUED":
            raise ValueError("Only queued work can be reordered")
        record["priority"] = int(priority) if priority is not None else min(
            [j.get("priority", 10) for j in status() if j["state"] == "QUEUED"] + [10]) - 1
        atomic(path, record)
        return record


def gpu_lock():
    guard = (JOBS/"gpu.lock").open("a")
    try:
        fcntl.flock(guard, fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:
        guard.close()
        return None
    return guard


def run(job_id):
    if not re.fullmatch(r"[0-9_]+[a-f0-9]{8}",job_id):
        raise ValueError("Invalid job ID")
    # Each waiting worker retains its submission credentials in memory, never on disk.
    gpu_guard = None
    while True:
        selected=None
        with (JOBS/"submit.lock").open("a") as guard:
            fcntl.flock(guard,fcntl.LOCK_EX)
            records=status()
            queued=sorted((j for j in records if j["state"]=="QUEUED"),
                          key=lambda j:(j.get("priority",10),j["created_at"],j["job_id"]))
            if (queued and queued[0]["job_id"]==job_id and not any(j["state"]=="RUNNING" for j in records)
                    and (gpu_guard := gpu_lock()) is not None):
                selected=queued[0]
                folder=JOBS/job_id
                try:
                    with (folder/"job.log").open("ab") as log:
                        env = dict(os.environ, QF_GPU_LOCK_FD=str(gpu_guard.fileno()))
                        child=subprocess.Popen(selected["argv"],cwd=ROOT,stdin=subprocess.DEVNULL,
                            stdout=log,stderr=subprocess.STDOUT,env=env,pass_fds=(gpu_guard.fileno(),))
                except BaseException:
                    gpu_guard.close()
                    raise
                selected.update(state="RUNNING",pid=child.pid,pid_stamp=process_stamp(child.pid),started_at=time.time())
                atomic(folder/"job.json",selected)
        if selected:
            break
        time.sleep(1)
    try:
        code=child.wait()
        atomic(folder/"job.json",dict(selected,state="SUCCEEDED" if code==0 else "FAILED",exit_code=code,finished_at=time.time()))
    except Exception as error:
        atomic(folder/"job.json",dict(selected,state="FAILED",error=type(error).__name__))
    finally:
        # Do not LOCK_UN: descendants retain the same lock after a parent dies.
        gpu_guard.close()


def overview():
    snapshots = []
    for f in (ROOT / "outputs").glob("factory_*/*/artifacts/*/factory_manifest.json"):
        m = json.loads(f.read_text())
        snapshots.append(dict(run_id=m["run_id"], weight_id=m["weight_id"], epoch=m["trained_epoch"],
                              adapter=str(f.parent.relative_to(ROOT))))
    configurations = {f.parent.name: f.read_text() for f in (ROOT/"outputs").glob("factory_*/*/config.yaml")}
    observed_at = time.time()
    return dict(jobs=status(), observed_at=observed_at, snapshots=snapshots, configurations=configurations,
                reports=[str(f.relative_to(ROOT)) for f in (ROOT / "reports").glob("smoke_compare_*/comparison.json")],
                scripts=[f.name for f in (ROOT / "scripts").glob("*.py")])


if __name__ == "__main__":
    run(sys.argv[1])
