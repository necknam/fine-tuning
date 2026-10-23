"""Explicit checkpoint-preserving migration between verified GPU runtimes."""
import hashlib
import json
import os
from pathlib import Path


def digest(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as f:
        for block in iter(lambda: f.read(8 * 1024 * 1024), b''):
            h.update(block)
    return h.hexdigest()


def accept(output, previous, current):
    receipt_path = os.environ.get('QF_RUNTIME_MIGRATION_RECEIPT')
    if not receipt_path:
        raise ValueError('Runtime/config changed; an explicit verified migration receipt is required')
    receipt = json.loads(Path(receipt_path).read_text())
    if receipt.get('previous_runtime') != previous or receipt.get('next_runtime') != current:
        raise ValueError('Runtime migration does not match the exact previous/new runtime')
    for key in ('config_hash', 'model', 'loss', 'pipeline', 'cuda'):
        if previous.get(key) != current.get(key):
            raise ValueError('Runtime migration cannot change '+key)
    old_packages=dict(previous['packages']);new_packages=dict(current['packages'])
    old_packages.pop('triton', None);new_packages.pop('triton', None)
    if old_packages != new_packages or current['packages'].get('triton') != '3.6.0':
        raise ValueError('Only the explicitly tested Triton upgrade is allowed')
    probe=Path(receipt['probe_path'])
    if digest(probe) != receipt['probe_sha256']:
        raise ValueError('GPU probe receipt changed')
    evidence=json.loads(probe.read_text())
    if not evidence.get('passed') or evidence.get('triton') != '3.6.0' or len(evidence.get('tests', []))<2:
        raise ValueError('New GPU backend has not passed its forward/backward probe')
    checkpoint=(output/receipt['checkpoint']).resolve()
    checkpoint.relative_to(output.resolve()/'checkpoints')
    if receipt.get('restart_training') is not False:
        raise ValueError('Migration must preserve the existing training state')
    for name, expected in receipt['checkpoint_sha256'].items():
        if Path(name).name != name or digest(checkpoint/name) != expected:
            raise ValueError('Checkpoint changed: '+name)
    for name in ('adapter_model.safetensors','optimizer.pt','scheduler.pt','trainer_state.json','rng_state.pth'):
        if name not in receipt['checkpoint_sha256']:
            raise ValueError('Missing checkpoint state: '+name)
    history=output/'runtime_history';history.mkdir(exist_ok=True)
    serialized=json.dumps(previous,sort_keys=True).encode()
    target=history/(hashlib.sha256(serialized).hexdigest()+'.json')
    if not target.exists():target.write_text(json.dumps(previous,indent=2))
    (output/'runtime_migration.json').write_text(json.dumps(receipt,indent=2))
    (output/'runtime_manifest.json').write_text(json.dumps(current,indent=2))
    print('VERIFIED RUNTIME MIGRATION: optimizer/scheduler/RNG restored from '+str(checkpoint),flush=True)
