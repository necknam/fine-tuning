"""Advance the explicitly authorized original-data P02-P06 save-only jobs."""
import fcntl,json,os,sys,time
from pathlib import Path
ROOT=Path('/workspace/qwen_factory')
sys.path.insert(0,str(ROOT/'scripts'))
import runpod_bridge as bridge
from db_registry import build_plans,factory_output,runs
from sqlalchemy import create_engine,select
PLAN=ROOT/'outputs/restored_baseline_p02_p06/plan.json'

def write(plan):
    plan['controller_observed_at']=time.time();bridge.atomic(PLAN,plan)

def run():
    guard=PLAN.with_name('controller.lock').open('a')
    try:fcntl.flock(guard,fcntl.LOCK_EX|fcntl.LOCK_NB)
    except BlockingIOError:return
    plan=json.loads(PLAN.read_text());plan['controller_pid']=os.getpid();write(plan)
    while True:
        plan=json.loads(PLAN.read_text())
        if plan.get('controller_stop_requested'):return
        jobs={j['job_id']:j for j in bridge.status()}
        for preset in plan['preset_order']:
            row=next(x for x in plan['configs'] if x['preset']==preset)
            if row.get('status')=='SUCCEEDED':
                if not row.get('upload_receipt'):raise ValueError('Successful preset has no verified upload receipt')
                continue
            job=jobs.get(row.get('job_id'))
            if job:
                row['status']=job['state'] if job['state']!='SUCCEEDED' else 'VERIFYING_SAVED_ARTIFACTS';plan['current_preset']=preset;write(plan)
                if job['state'] in ('RUNNING','QUEUED'):break
                if job['state']!='SUCCEEDED':
                    plan['state']='STOPPED_ON_JOB_ERROR';write(plan);return
                log=(ROOT/'outputs/control_jobs'/job['job_id']/'job.log').read_text()
                if 'TRAIN_SAVE_ONLY COMPLETE:' not in log:raise ValueError('Save-only completion receipt missing')
                engine=create_engine(os.environ['DATABASE_URL'],pool_pre_ping=True)
                try:
                    with engine.connect() as db:record=db.execute(select(runs).where(runs.c.config_hash==row['config_hash'])).mappings().one()
                finally:engine.dispose()
                row['run_id']=record['run_id'];folder=factory_output(ROOT,row['run_id'],False)/'local_evaluation_bundle';receipt=json.loads((folder/'upload_receipt.json').read_text())
                if receipt['generated_answers']!=0 or receipt['epochs']!=[2,5] or receipt['inputs_sha256']!='e21bb336f56085edbd6f4a904eda9a3ea94b245d0d3e5eec252405c80ddb30d7':raise ValueError('Uploaded bundle does not match frozen-input save-only plan')
                row.update(status='SUCCEEDED',upload_receipt=receipt);write(plan);continue
            active=[j for j in jobs.values() if j['state'] in ('RUNNING','QUEUED')]
            if active:break
            matches=[j for j in jobs.values() if j.get('config')==row['config']]
            if matches:raise ValueError('Unrecorded job exists; inspect before any resubmission')
            checked=build_plans(ROOT,ROOT/row['config'],False)[0]
            if checked['config_hash']!=row['config_hash']:raise ValueError('Config changed')
            j=bridge.submit('train_save_only',row['config'],label='원본 복구 '+preset+' · 가중치 저장 전용')
            row.update(job_id=j['job_id'],status=j['state']);plan.update(state=preset+'_SUBMITTED',current_preset=preset);write(plan);break
        else:
            plan.update(state='ALL_PRESETS_SUCCEEDED',required_gpu_jobs_complete=True);write(plan);return
        time.sleep(15)

if __name__=='__main__':
    try:run()
    except Exception as error:
        plan=json.loads(PLAN.read_text());plan.update(state='CONTROLLER_ERROR',controller_error=type(error).__name__+': '+str(error));write(plan);raise
