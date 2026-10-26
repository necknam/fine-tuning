"""Verify uploaded adapters and export existing frozen inputs for local inference.

This module never queries the employee database and never loads a model.
"""
import copy
import hashlib
import json
import os
from contextlib import closing
from pathlib import Path


def sha(path):
    h = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b''):
            h.update(chunk)
    return h.hexdigest()


def frozen_inputs(cfg, receipt):
    from cloud_evidence import canonical
    policy = cfg['live_evaluation']
    if receipt.get('cohort_id') != policy['cohort_id']:
        raise ValueError('Frozen cohort identity mismatch')
    if receipt.get('template_sha256') != cfg['evaluation']['sha256']:
        raise ValueError('Frozen input template mismatch')
    if receipt.get('case_employee_ids') != policy.get('case_employee_ids'):
        raise ValueError('Frozen employee assignment mismatch')
    if len(receipt.get('rows', [])) != 10:
        raise ValueError('Exactly ten frozen inputs are required')
    body = ''.join(canonical(row) + '\n' for row in receipt['rows'])
    if hashlib.sha256(body.encode()).hexdigest() != receipt['sha256']:
        raise ValueError('Frozen input hash mismatch')
    return body


def export_bundle(root, cfg, plan, run_id, snapshots, output):
    import dashboard_store
    from cloud_evaluation import validate_batch
    from huggingface_hub import HfApi, hf_hub_download
    from runpod_factory_sample import verify_snapshot
    root = Path(root)
    cohort = validate_batch(cfg['live_evaluation']['cohort_id'])
    key = 'reports/live_cohorts/' + cohort + '.json'
    with closing(dashboard_store.pg(root)) as db:
        saved = db.execute('SELECT content FROM documents WHERE path=%s', (key,)).fetchone()
    if not saved:
        raise ValueError('P01 frozen inputs missing; refusing to create a new DB snapshot')
    receipt = json.loads(saved[0])
    body = frozen_inputs(cfg, receipt)
    expected = set(cfg['experiments'][0]['artifacts']['save_epochs'])
    if len(snapshots) != len(expected) or {x['trained_epoch'] for x in snapshots} != expected:
        raise ValueError('Saved epoch plan mismatch')
    token = os.environ['HF_TOKEN']
    api = HfApi(token=token)
    entries = []
    for snapshot in snapshots:
        if snapshot['status'] not in ('TRAINED', 'EVALUATED') or not all(snapshot.get(k) for k in ('hf_repo_id', 'hf_revision', 'hf_subfolder')):
            raise ValueError('Weight upload is incomplete')
        path = Path(output) / 'artifacts' / snapshot['weight_id']
        manifest = verify_snapshot(path, snapshot, plan, run_id)
        files = dict(manifest['file_sha256'])
        files['factory_manifest.json'] = sha(path / 'factory_manifest.json')
        for name, digest in files.items():
            if Path(name).name != name:
                raise ValueError('Unsafe artifact filename')
            downloaded = hf_hub_download(snapshot['hf_repo_id'], filename=snapshot['hf_subfolder'] + '/' + name,
                                         revision=snapshot['hf_revision'], token=token)
            if sha(downloaded) != digest:
                raise ValueError('Remote adapter hash mismatch')
        entries.append(dict(snapshot, file_sha256=files))
    folder = Path(output) / 'local_evaluation_bundle'
    folder.mkdir(parents=True, exist_ok=True)
    (folder / 'fixed10.jsonl').write_bytes(body.encode())
    local_cfg = copy.deepcopy(cfg)
    local_cfg['data']['test_file'] = 'fixed10.jsonl'
    local_cfg['evaluation'].update(file='fixed10.jsonl', sha256=receipt['sha256'])
    bundle = dict(version='growpath-local-evaluation/v1', run_id=run_id, config_hash=plan['config_hash'],
                  model=cfg['model'], config=local_cfg, cohort_id=cohort,
                  inputs_sha256=receipt['sha256'], artifacts=entries,
                  generation=dict(max_new_tokens=cfg.get('inference', {}).get('max_new_tokens', 4096),
                                  do_sample=False, num_beams=1, use_cache=True),
                  generation_location='LOCAL_STREAMLIT', generated_answers=0)
    (folder / 'bundle.json').write_text(json.dumps(bundle, ensure_ascii=False, indent=2), encoding='utf-8')
    repo_id = os.environ['HF_REPO_ID']
    subfolder = 'local_evaluation/' + run_id
    commit = api.upload_folder(repo_id=repo_id, repo_type='model', folder_path=str(folder), path_in_repo=subfolder,
                               commit_message='Frozen local evaluation bundle ' + run_id)
    for name in ('bundle.json', 'fixed10.jsonl'):
        downloaded = hf_hub_download(repo_id, filename=subfolder + '/' + name, revision=commit.oid, token=token)
        if sha(downloaded) != sha(folder / name):
            raise ValueError('Remote local-evaluation bundle hash mismatch')
    result = dict(run_id=run_id, hf_repo_id=repo_id, hf_revision=commit.oid, hf_subfolder=subfolder,
                  inputs_sha256=receipt['sha256'], epochs=sorted(expected), generated_answers=0)
    (folder / 'upload_receipt.json').write_text(json.dumps(result, indent=2), encoding='utf-8')
    return result
