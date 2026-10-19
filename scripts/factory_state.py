"""Short-transaction database lease and artifact status helpers."""
import threading
import uuid
from datetime import datetime, timedelta, timezone

from sqlalchemy import Column, DateTime, ForeignKey, String, Table, delete, insert, select, update
from sqlalchemy.exc import IntegrityError

from db_registry import artifacts, metadata, runs


leases = Table("qf_run_leases", metadata,
    Column("run_id", String(36), ForeignKey("qf_runs.run_id"), primary_key=True),
    Column("owner_token", String(36), nullable=False),
    Column("expires_at", DateTime(timezone=True), nullable=False))


class RunLease:
    def __init__(self, engine, run_id, ttl=180, interval=30):
        self.engine, self.run_id = engine, run_id
        self.token = str(uuid.uuid4())
        self.ttl, self.interval = ttl, interval
        self.stop = threading.Event()
        self.lost = threading.Event()
        self.thread = None

    def acquire(self, heartbeat=True):
        now = datetime.now(timezone.utc)
        values = dict(owner_token=self.token, expires_at=now + timedelta(seconds=self.ttl))
        try:
            with self.engine.begin() as c:
                c.execute(insert(leases).values(run_id=self.run_id, **values))
        except IntegrityError:
            with self.engine.begin() as c:
                result = c.execute(update(leases).where(leases.c.run_id == self.run_id,
                    leases.c.expires_at < now).values(**values))
                if result.rowcount != 1:
                    raise RuntimeError("This run is owned by another worker. Wait for it to finish or its lease to expire.")
        if heartbeat:
            self.thread = threading.Thread(target=self._heartbeat, daemon=True)
            self.thread.start()
        return self

    def _heartbeat(self):
        while not self.stop.wait(self.interval):
            try:
                with self.engine.begin() as c:
                    self.assert_owned(c)
                    result = c.execute(update(leases).where(leases.c.run_id == self.run_id,
                        leases.c.owner_token == self.token).values(
                            expires_at=datetime.now(timezone.utc) + timedelta(seconds=self.ttl)))
                    if result.rowcount != 1:
                        raise RuntimeError("Lease ownership changed")
            except Exception:
                self.lost.set()
                return

    def assert_owned(self, connection=None):
        if self.lost.is_set():
            raise RuntimeError("Database lease heartbeat failed; stopping this worker")
        if connection is None:
            with self.engine.connect() as c:
                return self.assert_owned(c)
        row = connection.execute(select(leases.c.owner_token, leases.c.expires_at).where(
            leases.c.run_id == self.run_id)).first()
        expiry = row.expires_at if row else None
        if expiry is not None and expiry.tzinfo is None:
            expiry = expiry.replace(tzinfo=timezone.utc)
        if not row or row.owner_token != self.token or expiry <= datetime.now(timezone.utc):
            self.lost.set()
            raise RuntimeError("Run lease expired or was lost")

    def release(self):
        self.stop.set()
        if self.thread:
            self.thread.join(timeout=20)
        with self.engine.begin() as c:
            c.execute(delete(leases).where(leases.c.run_id == self.run_id,
                                           leases.c.owner_token == self.token))


def artifact_rows(engine, run_id):
    with engine.connect() as c:
        return [dict(row) for row in c.execute(select(artifacts).where(
            artifacts.c.run_id == run_id).order_by(artifacts.c.trained_epoch)).mappings()]


def set_run_status(engine, lease, status):
    with engine.begin() as c:
        lease.assert_owned(c)
        c.execute(update(runs).where(runs.c.run_id == lease.run_id).values(status=status))


def set_local_saved(engine, lease, weight_id):
    with engine.begin() as c:
        lease.assert_owned(c)
        c.execute(update(artifacts).where(artifacts.c.run_id == lease.run_id,
            artifacts.c.weight_id == weight_id,
            artifacts.c.status.not_in(["TRAINED", "EVALUATED"])).values(status="LOCAL_SAVED"))


def set_uploaded(engine, lease, weight_id, repo_id, revision, subfolder):
    if not revision or not repo_id or not subfolder:
        raise ValueError("A successful upload commit and path are required")
    with engine.begin() as c:
        lease.assert_owned(c)
        result = c.execute(update(artifacts).where(artifacts.c.run_id == lease.run_id,
            artifacts.c.weight_id == weight_id,
            artifacts.c.status.not_in(["TRAINED", "EVALUATED"])).values(
                status="TRAINED", hf_repo_id=repo_id,
                hf_revision=revision, hf_subfolder=subfolder))
        if result.rowcount == 0:
            existing = c.execute(select(artifacts).where(artifacts.c.run_id == lease.run_id,
                artifacts.c.weight_id == weight_id)).mappings().first()
            if not existing or existing["status"] not in ("TRAINED", "EVALUATED"):
                raise RuntimeError("Artifact record missing")
