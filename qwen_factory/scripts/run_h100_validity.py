"""Single approved 1500-record epoch, then immutable ten-case BF16 comparison."""
import os,json,hashlib,time,math,sys,uuid,contextlib
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'outputs/P01_validity_20261022';RUN.mkdir(parents=True,exist_ok=True)
CFG=json.loads((RUN/'execution.json').read_text())
MODEL='Qwen/Qwen3.8-27B';REV='1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0'
STAGED=os.environ['STAGED_MODEL_PATH']
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def status(stage,**kwargs):
 data={'stage':stage,'run_id':CFG['run_id'],'updated_at':time.strftime('%Y-%m-%dT%H:%M:%SZ',time.gmtime()),**kwargs}
 p=RUN/'status.json';tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(data,ensure_ascii=False,indent=2));tmp.replace(p);print('STATUS',json.dumps(data),flush=True)
def main():
 import torch
 from transformers import AutoTokenizer,AutoModelForImageTextToText
 assert torch.cuda.is_available() and torch.cuda.device_count()==1 and 'H100' in torch.cuda.get_device_name(0)
 common={'local_files_only':True,'trust_remote_code':False}
 tok=AutoTokenizer.from_pretrained(STAGED,**common)
 if tok.pad_token_id is None:tok.pad_token=tok.eos_token
 if '--compare' in sys.argv:
  import subprocess
  with (RUN/'dequant_layer_profile.log').open('w') as profile_log:
   profile_result=subprocess.run([sys.executable,'-u',str(ROOT/'scripts/profile_dequant_after_training.py')],stdout=profile_log,stderr=subprocess.STDOUT)
  print('SEQUENTIAL_LAYER_PROFILE_RETURN_CODE',profile_result.returncode,flush=True)
  compare(torch,tok,AutoModelForImageTextToText,common);return
 import bitsandbytes as bnb
 from transformers import BitsAndBytesConfig,Trainer,TrainingArguments,TrainerCallback,set_seed
 from peft import LoraConfig,get_peft_model,prepare_model_for_kbit_training
 set_seed(42)
 data=ROOT/CFG['data_file'];assert digest(data)==CFG['data_sha256']
 rows=[json.loads(l) for l in data.read_text().splitlines() if l.strip()];assert len(rows)==1500
 assert CFG['epochs']==1 and CFG['learning_rate']==.0001 and CFG['batch_size']==1 and CFG['accumulation']==16
 status('encoding',samples=len(rows));train=[]
 for row in rows:
  m=row['messages'];assert m[-1]['role']=='assistant'
  ids=tok.apply_chat_template(m,tokenize=True,enable_thinking=False,add_generation_prompt=False,return_dict=False)
  prefix=tok.apply_chat_template(m[:-1],tokenize=True,enable_thinking=False,add_generation_prompt=True,return_dict=False)
  assert ids[:len(prefix)]==prefix and len(prefix)<len(ids)<=7168
  train.append({'input_ids':ids,'attention_mask':[1]*len(ids),'labels':[-100]*len(prefix)+ids[len(prefix):]})
 status('loading_nf4',samples=1500,max_tokens=max(len(r['input_ids']) for r in train))
 loaded=time.perf_counter()
 model=AutoModelForImageTextToText.from_pretrained(STAGED,quantization_config=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_compute_dtype=torch.bfloat16,bnb_4bit_use_double_quant=True),dtype=torch.bfloat16,device_map={'':0},attn_implementation='sdpa',**common)
 load_seconds=time.perf_counter()-loaded;model.config.use_cache=False;model.config.text_config.use_cache=False
 model=prepare_model_for_kbit_training(model,use_gradient_checkpointing=True,gradient_checkpointing_kwargs={'use_reentrant':False})
 targets=[n for n,m in model.named_modules() if 'language_model' in n.split('.') and isinstance(m,(torch.nn.Linear,bnb.nn.Linear4bit)) and not n.endswith('lm_head')];assert targets
 model=get_peft_model(model,LoraConfig(r=32,lora_alpha=64,lora_dropout=.05,bias='none',target_modules=targets,task_type='CAUSAL_LM'))
 assert all('lora_' in n and 'language_model' in n.split('.') for n,p in model.named_parameters() if p.requires_grad)
 def collate(batch):
  length=max(len(x['input_ids']) for x in batch)
  return {k:torch.tensor([x[k]+[(-100 if k=='labels' else tok.pad_token_id if k=='input_ids' else 0)]*(length-len(x[k])) for x in batch],dtype=torch.long) for k in ['input_ids','attention_mask','labels']}
 total_steps=math.ceil(len(train)/16)
 args=TrainingArguments(output_dir=str(RUN/'checkpoints'),num_train_epochs=1,per_device_train_batch_size=1,gradient_accumulation_steps=16,per_device_eval_batch_size=1,learning_rate=.0001,lr_scheduler_type='cosine',warmup_steps=math.ceil(total_steps*.05),weight_decay=.01,bf16=True,gradient_checkpointing=True,gradient_checkpointing_kwargs={'use_reentrant':False},optim='paged_adamw_8bit',logging_steps=1,eval_strategy='no',save_strategy='no',report_to='none',seed=42,data_seed=42,remove_unused_columns=False,dataloader_num_workers=0,disable_tqdm=True)
 step_times=[];train_start=time.perf_counter()
 class Timer(TrainerCallback):
  def on_step_begin(self,args,state,control,**kwargs):torch.cuda.synchronize();self.started=time.perf_counter()
  def on_step_end(self,args,state,control,**kwargs):
   torch.cuda.synchronize();step_times.append(time.perf_counter()-self.started)
   mean=sum(step_times[1:])/len(step_times[1:]) if len(step_times)>1 else step_times[-1]
   status('training',step=state.global_step,total_steps=state.max_steps,epoch=state.epoch,elapsed_training_seconds=time.perf_counter()-train_start,last_step_seconds=step_times[-1],remaining_training_estimate_seconds=max(0,state.max_steps-state.global_step)*mean,estimate_excludes_comparison_and_save=True)
 trainer=Trainer(model=model,args=args,train_dataset=train,processing_class=tok,data_collator=collate,callbacks=[Timer()])
 status('training',step=0,total_steps=total_steps,samples=1500)
 started=time.perf_counter();metrics=trainer.train().metrics;train_runtime=time.perf_counter()-started
 assert math.isclose(trainer.state.epoch,1,abs_tol=1e-5) and trainer.state.global_step==total_steps and math.isfinite(metrics['train_loss'])
 status('saving_adapter',step=total_steps,total_steps=total_steps)
 local=Path('/tmp/P01_validity_adapter');local.mkdir(exist_ok=True)
 model.peft_config['default'].base_model_name_or_path=MODEL
 model.peft_config['default'].revision=REV
 trainer.save_model(str(local));tok.save_pretrained(local);trainer.save_state()
 from safetensors import safe_open
 with safe_open(str(local/'adapter_model.safetensors'),framework='pt',device='cpu') as f:
  keys=list(f.keys());assert keys
  for key in keys:assert torch.isfinite(f.get_tensor(key)).all().item()
 import shutil
 adapter=RUN/'adapter';adapter.mkdir(exist_ok=True)
 hashes={p.name:digest(p) for p in local.iterdir() if p.is_file()}
 for p in local.iterdir():
  if p.is_file():shutil.copy2(p,adapter/p.name);assert digest(adapter/p.name)==hashes[p.name]
 result={'status':'TRAINING_COMPLETE_COMPARISON_PENDING','run_id':CFG['run_id'],'model':MODEL,'revision':REV,'data_sha256':CFG['data_sha256'],'train_samples':1500,'epochs':trainer.state.epoch,'steps':total_steps,'train_loss':metrics['train_loss'],'independent_validation_loss':None,'training_runtime_seconds':train_runtime,'training_step_seconds':sum(step_times),'step_seconds':step_times,'first_step_seconds':step_times[0],'steady_step_mean_seconds':sum(step_times[1:])/len(step_times[1:]),'model_loading_seconds':load_seconds,'gpu':torch.cuda.get_device_name(0),'peak_allocated_gib':torch.cuda.max_memory_allocated()/2**30,'adapter_hashes':hashes,'config':CFG,'full_independent_semantic_review':False}
 (RUN/'training_result.json').write_text(json.dumps(result,ensure_ascii=False,indent=2));status('training_complete',step=total_steps,total_steps=total_steps,comparison_completed=0)

def compare(torch,tok,AutoModel,common):
 from peft import PeftModel
 from compare_factory_sample import load_case,save_report
 p=ROOT/'data/eval/prompts.app_v2.jsonl';assert digest(p)==CFG['eval_sha256'];assert len(p.read_text().splitlines())==10
 adapter=RUN/'adapter';assert adapter.is_dir();status('loading_bf16_for_comparison',comparison_completed=0)
 base=AutoModel.from_pretrained(STAGED,dtype=torch.bfloat16,device_map={'':0},attn_implementation='sdpa',**common)
 model=PeftModel.from_pretrained(base,str(adapter),is_trainable=False);model.eval()
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
  manifest={'run_id':CFG['run_id'],'weight_id':CFG['weight_id'],'trained_epoch':1,'file_sha256':json.loads((RUN/'training_result.json').read_text())['adapter_hashes'],'config_hash':CFG['config_sha256']}
  result={'model':{'base_model_id':MODEL,'revision':REV},'quantization':{'load_in_4bit':False,'dtype':'bfloat16'},'adapter_path':str(adapter),'factory_manifest':manifest,'adapter_sha256':digest(adapter/'adapter_model.safetensors'),'test_sha256':digest(p),'case_index':i,'evaluation_total':10,'evaluation_cohort':'report','messages':messages,'reference_unreviewed':reference,'reference_status':'fixed_input_output_comparison_only','generation':generation,'training_config_hash':CFG['config_sha256'],'base':outputs['base'],'tuned':outputs['tuned'],'texts_identical':outputs['base']['text']==outputs['tuned']['text']}
  directory=ROOT/'reports'/('smoke_compare_P01_epoch1_'+CFG['run_id'][:8]+'_'+str(i));save_report(directory,result);report_dirs.append(str(directory));status('comparing',comparison_completed=i+1,total_comparisons=10)
 (RUN/'comparison_index.json').write_text(json.dumps({'run_id':CFG['run_id'],'data_sha256':CFG['data_sha256'],'eval_sha256':CFG['eval_sha256'],'reports':report_dirs},indent=2));status('comparison_complete',comparison_completed=10,quality_verdict='PENDING_CONTENT_REVIEW')
if __name__=='__main__':
 try:main()
 except Exception as e:
  status('failed',error_type=type(e).__name__);raise
