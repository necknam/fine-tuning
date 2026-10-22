"""Continue epoch2 weights for three further epochs; optimizer restarts explicitly."""
import os,json,hashlib,time,math,sys,contextlib,random,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'outputs/B200_P01_continue3to5';RUN.mkdir(parents=True,exist_ok=True)
CFG=json.loads((RUN/'execution.json').read_text())
SOURCE=ROOT/'outputs/B200_P01_epoch2'
MODEL='Qwen/Qwen3.8-27B';REV='1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0'
STAGED=os.environ['STAGED_MODEL_PATH']
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def status(stage,**kwargs):
 d={'stage':stage,'run_id':CFG['run_id'],'updated_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),**kwargs};p=RUN/'status.json';tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(d,indent=2));tmp.replace(p);print('STATUS',json.dumps(d),flush=True)
def compare_loaded(torch,tok,model):
 from peft import PeftModel
 from compare_factory_sample import load_case,save_report
 p=ROOT/'data/eval/prompts.app_v2.jsonl';assert digest(p)==CFG['eval_sha256'];assert len(p.read_text().splitlines())==10
 adapter=RUN/'adapter';assert adapter.is_dir();model.eval()
 layers=model.get_layer_status();assert layers and all(x.enabled and 'default' in x.active_adapters for x in layers)
 generation={'max_new_tokens':3072,'do_sample':False,'num_beams':1,'use_cache':True,'pad_token_id':tok.pad_token_id,'eos_token_id':tok.eos_token_id}
 report_dirs=[]
 for i in range(10):
  messages,reference=load_case(p,i);inputs=tok.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,enable_thinking=False,return_tensors='pt',return_dict=True).to('cuda:0')
  assert inputs['input_ids'].shape[1]<=7168
  outputs={}
  for label in ['base','tuned']:
   status('comparing',comparison_completed=i,case_index=i,model=label)
   ctx=model.disable_adapter() if label=='base' else contextlib.nullcontext()
   with ctx,torch.inference_mode():
    torch.cuda.synchronize();start=time.perf_counter();ids=model.generate(**inputs,**generation);torch.cuda.synchronize();elapsed=time.perf_counter()-start
   tokens=ids[0,inputs['input_ids'].shape[1]:].tolist();outputs[label]={'text':tok.decode(tokens,skip_special_tokens=True),'tokens':len(tokens),'seconds':elapsed,'hit_token_limit':len(tokens)>=3072,'ended_with_eos':bool(tokens and tokens[-1]==tok.eos_token_id)}
  manifest={'run_id':CFG['run_id'],'weight_id':CFG['weight_id'],'trained_epoch':CFG['epochs'],'file_sha256':json.loads((RUN/'training_result.json').read_text())['adapter_hashes'],'config_hash':CFG['config_sha256']}
  result={'model':{'base_model_id':MODEL,'revision':REV},'quantization':{'load_in_4bit':False,'dtype':'bfloat16'},'adapter_path':str(adapter),'factory_manifest':manifest,'adapter_sha256':digest(adapter/'adapter_model.safetensors'),'test_sha256':digest(p),'case_index':i,'evaluation_total':10,'evaluation_cohort':'report','messages':messages,'reference_unreviewed':reference,'reference_status':'fixed_input_output_comparison_only','generation':generation,'training_config_hash':CFG['config_sha256'],'base':outputs['base'],'tuned':outputs['tuned'],'texts_identical':outputs['base']['text']==outputs['tuned']['text']}
  directory=ROOT/'reports'/('smoke_compare_B200_epoch'+str(CFG['epochs'])+'_'+CFG['run_id'][:8]+'_'+str(i));save_report(directory,result);report_dirs.append(str(directory));status('comparing',comparison_completed=i+1,total_comparisons=10)
 (RUN/'comparison_index.json').write_text(json.dumps({'run_id':CFG['run_id'],'data_sha256':CFG['data_sha256'],'eval_sha256':CFG['eval_sha256'],'reports':report_dirs},indent=2));status('comparison_complete',comparison_completed=10,quality_verdict='PENDING_CONTENT_REVIEW')

def main():
 global RUN,CFG
 import torch,shutil,numpy as np
 from transformers import AutoTokenizer,AutoModelForImageTextToText,Trainer,TrainingArguments,TrainerCallback,set_seed
 from peft import PeftModel
 assert torch.cuda.is_available() and 'B200' in torch.cuda.get_device_name(0)
 initial=json.loads((SOURCE/'training_result.json').read_text());assert initial['epochs']==2 and initial['steps']==188
 assert digest(SOURCE/'adapter/adapter_model.safetensors')==initial['adapter_hashes']['adapter_model.safetensors']
 assert CFG['learning_rate']==.0001 and CFG['additional_epochs']==3 and CFG['data_sha256']==initial['data_sha256']
 set_seed(42);common={'local_files_only':True,'trust_remote_code':False}
 tok=AutoTokenizer.from_pretrained(STAGED,**common)
 if tok.pad_token_id is None:tok.pad_token=tok.eos_token
 p=ROOT/CFG['data_file'];assert digest(p)==CFG['data_sha256'];rows=[json.loads(l) for l in p.read_text().splitlines() if l.strip()];assert len(rows)==1500
 train=[];status('encoding',samples=1500)
 for row in rows:
  m=row['messages'];ids=tok.apply_chat_template(m,tokenize=True,enable_thinking=False,add_generation_prompt=False,return_dict=False);prefix=tok.apply_chat_template(m[:-1],tokenize=True,enable_thinking=False,add_generation_prompt=True,return_dict=False)
  assert ids[:len(prefix)]==prefix and len(prefix)<len(ids)<=7168
  train.append({'input_ids':ids,'attention_mask':[1]*len(ids),'labels':[-100]*len(prefix)+ids[len(prefix):]})
 status('loading_bf16_epoch2_adapter')
 base=AutoModelForImageTextToText.from_pretrained(STAGED,dtype=torch.bfloat16,device_map={'':0},attn_implementation='sdpa',**common)
 base.requires_grad_(False);base.config.use_cache=False;base.config.text_config.use_cache=False;base.enable_input_require_grads();base.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
 model=PeftModel.from_pretrained(base,str(SOURCE/'adapter'),is_trainable=True)
 assert not getattr(model,'is_loaded_in_4bit',False)
 assert all('lora_' in n and 'language_model' in n.split('.') for n,p in model.named_parameters() if p.requires_grad)
 def collate(batch):
  n=max(len(x['input_ids']) for x in batch)
  return {k:torch.tensor([x[k]+[(-100 if k=='labels' else tok.pad_token_id if k=='input_ids' else 0)]*(n-len(x[k])) for x in batch],dtype=torch.long) for k in ['input_ids','attention_mask','labels']}
 main_run=RUN;main_cfg=dict(CFG);step_times=[];comparison_seconds=0.;epoch_step_start=0
 args=TrainingArguments(output_dir=str(RUN/'trainer'),num_train_epochs=3,per_device_train_batch_size=1,gradient_accumulation_steps=16,learning_rate=.0001,lr_scheduler_type='cosine',warmup_steps=15,weight_decay=.01,bf16=True,gradient_checkpointing=True,gradient_checkpointing_kwargs={'use_reentrant':False},optim='paged_adamw_8bit',logging_steps=1,eval_strategy='no',save_strategy='no',report_to='none',seed=42,data_seed=42,remove_unused_columns=False,dataloader_num_workers=0,disable_tqdm=True)
 class Monitor(TrainerCallback):
  def on_step_begin(self,args,state,control,**kwargs):torch.cuda.synchronize();self.begin=time.perf_counter()
  def on_step_end(self,args,state,control,**kwargs):
   torch.cuda.synchronize();step_times.append(time.perf_counter()-self.begin);mean=sum(step_times)/len(step_times)
   status('training',step=state.global_step,total_steps=state.max_steps,cumulative_epoch=2+state.epoch,last_step_seconds=step_times[-1],mean_step_seconds=mean,remaining_training_estimate_seconds=(state.max_steps-state.global_step)*mean,comparison_seconds_excluded=True)
  def on_epoch_end(self,args,state,control,**kwargs):
   global RUN,CFG
   nonlocal comparison_seconds,epoch_step_start
   epoch=2+round(state.epoch);assert epoch in [3,4,5]
   RUN=ROOT/'outputs'/f'B200_P01_epoch{epoch}';RUN.mkdir(exist_ok=True)
   CFG={**main_cfg,'run_id':main_cfg['run_id']+'-epoch'+str(epoch),'weight_id':str(uuid.uuid4()),'epochs':epoch,'optimizer_restart_after_epoch':2,'continuous_five_epoch_schedule':False}
   CFG['config_sha256']=hashlib.sha256(json.dumps(CFG,sort_keys=True).encode()).hexdigest();(RUN/'execution.json').write_text(json.dumps(CFG,indent=2))
   status('saving_adapter_and_optimizer',cumulative_epoch=epoch)
   local=Path('/tmp')/f'B200_epoch{epoch}_adapter';local.mkdir(exist_ok=True)
   model.peft_config['default'].base_model_name_or_path=MODEL;model.peft_config['default'].revision=REV
   trainer.save_model(str(local));tok.save_pretrained(local)
   from safetensors import safe_open
   with safe_open(str(local/'adapter_model.safetensors'),framework='pt',device='cpu') as f:
    assert list(f.keys())
    for k in f.keys():assert torch.isfinite(f.get_tensor(k)).all().item()
   adapter=RUN/'adapter';adapter.mkdir(exist_ok=True);hashes={p.name:digest(p) for p in local.iterdir() if p.is_file()}
   for p in local.iterdir():
    if p.is_file():shutil.copy2(p,adapter/p.name);assert digest(adapter/p.name)==hashes[p.name]
   ckpt=RUN/'continuation_state';ckpt.mkdir(exist_ok=True)
   torch.save({'optimizer':kwargs['optimizer'].state_dict(),'scheduler':kwargs['lr_scheduler'].state_dict(),'python_rng':random.getstate(),'numpy_rng':np.random.get_state(),'torch_rng':torch.get_rng_state(),'cuda_rng':torch.cuda.get_rng_state_all(),'step':state.global_step,'segment_epoch':state.epoch,'segment_total_epochs':3},ckpt/'optimizer_scheduler_rng.pt');state.save_to_json(str(ckpt/'trainer_state.json'))
   losses=[x['loss'] for x in state.log_history if 'loss' in x and x.get('step',0)>epoch_step_start];epoch_step_start=state.global_step
   result={'run_id':CFG['run_id'],'model':MODEL,'revision':REV,'data_sha256':CFG['data_sha256'],'epochs':epoch,'train_samples':1500,'segment_steps':state.global_step,'epoch_mean_logged_loss':sum(losses)/len(losses) if losses else None,'training_step_seconds':sum(step_times),'adapter_hashes':hashes,'config':CFG,'quality_verdict':'PENDING_CONTENT_REVIEW','peak_allocated_gib':torch.cuda.max_memory_allocated()/2**30,'optimizer_restart_after_epoch':2}
   (RUN/'training_result.json').write_text(json.dumps(result,indent=2))
   rng=(random.getstate(),np.random.get_state(),torch.get_rng_state(),torch.cuda.get_rng_state_all());t=time.perf_counter()
   try:compare_loaded(torch,tok,model)
   finally:
    comparison_seconds+=time.perf_counter()-t;model.train();model.config.use_cache=False;model.config.text_config.use_cache=False;random.setstate(rng[0]);np.random.set_state(rng[1]);torch.set_rng_state(rng[2]);torch.cuda.set_rng_state_all(rng[3]);torch.cuda.empty_cache();RUN=main_run;CFG=main_cfg
   status('epoch_comparison_saved',cumulative_epoch=epoch,comparison_completed=10)
 trainer=Trainer(model=model,args=args,train_dataset=train,processing_class=tok,data_collator=collate,callbacks=[Monitor()])
 status('training',step=0,total_steps=282,cumulative_epoch=2,optimizer_restarted=True)
 trainer.train();assert trainer.state.global_step==282 and math.isclose(trainer.state.epoch,3,abs_tol=1e-5)
 status('completed',cumulative_epoch=5,step=282,total_steps=282,comparison_completed=30,comparison_seconds=comparison_seconds)

if __name__=='__main__':
 try:main()
 except Exception as e:status('failed',error_type=type(e).__name__);raise
