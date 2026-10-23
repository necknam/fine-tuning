"""Evaluate verified historical B200 adapters after the current improved run; never train."""
import argparse
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import uuid

import yaml
from db_registry import build_plans, digest
import runpod_bridge as bridge

ROOT=Path(__file__).resolve().parents[1]


def immutable(path,raw):
    path.parent.mkdir(parents=True,exist_ok=True)
    if path.exists():
        if path.read_bytes()!=raw:raise ValueError('Existing imported artifact differs: '+path.name)
    else:path.write_bytes(raw)


def prepare(root,config):
    """Create a separate inference view; preserve all historical source files."""
    root=Path(root).resolve();config=Path(config)
    source_cfg=yaml.safe_load(config.read_text(encoding='utf-8'))
    live_path=config.with_name(config.stem+'_live_eval.yaml')
    live=yaml.safe_load(live_path.read_text(encoding='utf-8'))
    # The completed improved pipeline already froze these exact DB inputs.
    if live['live_evaluation']['cohort_id']!=source_cfg['live_evaluation']['cohort_id']:
        raise ValueError('Historical evaluation must use the completed improved cohort')
    sources=[]
    for epoch in (2,5):
        folder=root/'outputs'/f'B200_P01_epoch{epoch}'
        execution=json.loads((folder/'execution.json').read_text(encoding='utf-8'))
        result=json.loads((folder/'training_result.json').read_text(encoding='utf-8'))
        if (execution.get('epochs')!=epoch or execution.get('train_samples')!=1500
                or result.get('epochs')!=epoch or result.get('train_samples')!=1500
                or result.get('model')!=source_cfg['model']['base_model_id']
                or result.get('revision')!=source_cfg['model']['revision']):
            raise ValueError('Historical training identity does not match')
        original_data=(root/execution['data_file']).resolve();original_data.relative_to(root/'data')
        if digest(original_data)!=execution['data_sha256'] or result['data_sha256']!=execution['data_sha256']:
            raise ValueError('Historical training data hash mismatch')
        hashes=result['adapter_hashes']
        if not {'adapter_model.safetensors','adapter_config.json'}<=set(hashes):
            raise ValueError('Historical adapter hash receipt is incomplete')
        for name,expected in hashes.items():
            if Path(name).name!=name:raise ValueError('Unsafe historical adapter filename')
            if digest(folder/'adapter'/name)!=expected:raise ValueError('Historical adapter hash mismatch: '+name)
        sources.append((folder,execution,result))
    if sources[0][1]['data_sha256']!=sources[1][1]['data_sha256']:
        raise ValueError('Historical epochs use different training data')
    binding=json.dumps([x[1] for x in sources],sort_keys=True,separators=(',',':'))
    cfg=copy.deepcopy(source_cfg)
    cfg['experiment_id']=str(uuid.uuid5(uuid.NAMESPACE_URL,'saved-b200-eval:'+binding))
    cfg['execution_policy']='evaluate_only'
    cfg['data'].update(train_file=sources[0][1]['data_file'],train_sha256=sources[0][1]['data_sha256'],minimum_max_length=7168)
    cfg['data']['test_file']=live['data']['test_file'];cfg['evaluation']=live['evaluation']
    cfg['live_evaluation']['enabled']=False
    cfg['experiments'][0]['recipe_name']='saved_B200_P01_epoch2_5_inference_only'
    cfg['experiments'][0]['training']['max_length']=7168
    cfg['historical_training']=[x[1] for x in sources]
    relative='configs/saved_b200_fixed10_'+cfg['experiment_id']+'.yaml'
    imported_config=root/relative
    immutable(imported_config,yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False).encode())
    plan=build_plans(root,imported_config,False)[0]
    run_id=str(uuid.uuid5(uuid.NAMESPACE_URL,'saved-b200-run:'+plan['config_hash']))
    output=root/'outputs/factory_production'/run_id
    runtime={'pipeline':'historical_B200_inference_import_v1','model':cfg['model'],'config_hash':plan['config_hash'],
             'provenance':'Historical weights reused; no training or optimizer changes performed',
             'inference_backend':cfg.get('runtime',{}),'historical_training':cfg['historical_training']}
    immutable(output/'runtime_manifest.json',json.dumps(runtime,ensure_ascii=False,indent=2).encode())
    immutable(output/'config.yaml',imported_config.read_bytes())
    adapters=[]
    for folder,execution,result in sources:
        weight=execution['weight_id'];uuid.UUID(weight)
        adapter=output/'artifacts'/weight;adapter.mkdir(parents=True,exist_ok=True)
        hashes={}
        for name,expected in result['adapter_hashes'].items():
            # Trainer pickle state is preserved at source and never loaded for inference.
            if name=='training_args.bin':continue
            target=adapter/name
            if not target.exists():shutil.copyfile(folder/'adapter'/name,target)
            if digest(target)!=expected:raise ValueError('Imported adapter hash mismatch')
            hashes[name]=expected
        manifest={'run_id':run_id,'weight_id':weight,'trained_epoch':execution['epochs'],
                  'config_hash':plan['config_hash'],'is_sample':False,'model':cfg['model'],
                  'dataset':plan['config']['data'],'file_sha256':hashes,'runtime':runtime,
                  'imported_without_training':True,'original_run_id':execution['run_id'],
                  'original_source':str(folder),'historical_training':execution}
        immutable(adapter/'factory_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2).encode())
        adapters.append(adapter)
    return relative,cfg,adapters


def evaluate(root,config,execute=subprocess.run):
    relative,cfg,adapters=prepare(root,config)
    expected_hash=cfg['evaluation']['sha256'];max_tokens=cfg['inference']['max_new_tokens']
    for adapter in adapters:
        manifest=json.loads((adapter/'factory_manifest.json').read_text(encoding='utf-8'))
        completed=set()
        for p in (root/'reports').glob('smoke_compare_*/comparison.json'):
            report=json.loads(p.read_text(encoding='utf-8'))
            if (report.get('factory_manifest',{}).get('weight_id')==adapter.name
                and report.get('test_sha256')==expected_hash
                and report.get('inference_runtime',{})==cfg.get('runtime',{})
                and report.get('generation',{}).get('max_new_tokens')==max_tokens
                and report.get('generation',{}).get('do_sample') is False
                and not report.get('tuned',{}).get('hit_token_limit',True)):
                completed.add(report['case_index'])
        pending=[i for i in range(10) if i not in completed]
        if not pending:continue
        print('SAVED B200 EVALUATION: epoch='+str(manifest['trained_epoch'])+'; pending='+str(pending)+'; no training',flush=True)
        options={}
        if os.environ.get('QF_GPU_LOCK_FD'):options['pass_fds']=(int(os.environ['QF_GPU_LOCK_FD']),)
        execute([sys.executable,'-u','scripts/compare_factory_sample.py','--config',relative,
                 '--adapter',str(adapter),'--case-indices',*map(str,pending),'--max-new-tokens',str(max_tokens),'--cohort','report'],
                cwd=root,check=True,**options)
    print('SAVED B200 FIXED10 EVALUATION COMPLETE: epoch2 and epoch5; training calls=0',flush=True)


def submit(after_job,config):
    if not re.fullmatch(r'[0-9_]+[a-f0-9]{8}',after_job):raise ValueError('Invalid dependency job ID')
    config_path=bridge.inside(config,'configs')
    if not config_path.is_file():raise ValueError('Missing improved config')
    bridge.JOBS.mkdir(parents=True,exist_ok=True)
    with (bridge.JOBS/'submit.lock').open('a') as lock:
        fcntl.flock(lock,fcntl.LOCK_EX)
        previous=next((j for j in bridge.status() if j.get('kind')=='evaluate_saved_b200' and j.get('after_job')==after_job
                       and j['state'] in ('RUNNING','QUEUED','SUCCEEDED')),None)
        if previous:return previous
        job_id=time.strftime('%Y%m%d_%H%M%S')+'_'+uuid.uuid4().hex[:8]
        folder=bridge.JOBS/job_id;folder.mkdir()
        argv=[str(bridge.PYTHON),'-u',str(Path(__file__)), '--run-job',job_id]
        job={'job_id':job_id,'kind':'evaluate_saved_b200','state':'QUEUED','created_at':time.time(),
             'priority':20,'label':'Saved B200 epoch2/5; same fixed10; NO RETRAINING','config':config,
             'after_job':after_job,'argv':argv,'training_allowed':False}
        bridge.atomic(folder/'job.json',job)
        with (folder/'job.log').open('ab') as log:
            worker=subprocess.Popen(argv,cwd=ROOT,stdout=log,stderr=subprocess.STDOUT,stdin=subprocess.DEVNULL,start_new_session=True)
        job.update(worker_pid=worker.pid,worker_stamp=bridge.process_stamp(worker.pid))
        bridge.atomic(folder/'job.json',job)
        return job


def run(job_id):
    path=bridge.JOBS/job_id/'job.json';guard=None
    try:
        print('WAITING: improved training and its fixed10 generation must finish first. No old-data retraining.',flush=True)
        while True:
            with (bridge.JOBS/'submit.lock').open('a') as lock:
                fcntl.flock(lock,fcntl.LOCK_EX)
                job=json.loads(path.read_text(encoding='utf-8'))
                dependency=json.loads((bridge.JOBS/job['after_job']/'job.json').read_text(encoding='utf-8'))
                if dependency['state'] not in ('QUEUED','RUNNING','SUCCEEDED'):
                    raise RuntimeError('Improved job did not complete; saved evaluation was not started')
                jobs=bridge.status()
                queued=sorted((j for j in jobs if j['state']=='QUEUED'),key=lambda j:(j.get('priority',10),j['created_at'],j['job_id']))
                if (dependency['state']=='SUCCEEDED' and queued and queued[0]['job_id']==job_id
                    and not any(j['state']=='RUNNING' for j in jobs) and (guard:=bridge.gpu_lock()) is not None):
                    job.update(state='RUNNING',pid=os.getpid(),pid_stamp=bridge.process_stamp(os.getpid()),started_at=time.time())
                    bridge.atomic(path,job);break
            time.sleep(10)
        os.environ['QF_GPU_LOCK_FD']=str(guard.fileno())
        evaluate(ROOT,ROOT/job['config'])
        bridge.atomic(path,dict(job,state='SUCCEEDED',finished_at=time.time(),exit_code=0))
    except BaseException as error:
        import traceback
        traceback.print_exc()
        record=json.loads(path.read_text(encoding='utf-8'));bridge.atomic(path,dict(record,state='FAILED',finished_at=time.time(),error=type(error).__name__))
        raise
    finally:
        if guard:guard.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    mode=parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--submit-after');mode.add_argument('--run-job')
    parser.add_argument('--config',default='configs/hyperparameters.compare.reviewed_v4_full1500.yaml')
    args=parser.parse_args()
    if args.submit_after:print(json.dumps(submit(args.submit_after,args.config)))
    else:
        if not re.fullmatch(r'[0-9_]+[a-f0-9]{8}',args.run_job):raise ValueError('Invalid job ID')
        run(args.run_job)


if __name__=='__main__':main()
