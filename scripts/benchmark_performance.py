"""GPU throughput probe with queue lock; never registers, exports or evaluates via APIs."""
import argparse,ast,json,math,os,sys,time
from pathlib import Path
from types import SimpleNamespace

def _train(a):
    root=Path(__file__).resolve().parents[1]
    import yaml,torch,bitsandbytes as bnb
    from dotenv import load_dotenv
    from peft import LoraConfig,get_peft_model,prepare_model_for_kbit_training
    from transformers import AutoTokenizer,AutoModelForImageTextToText,BitsAndBytesConfig,Trainer,TrainerCallback,TrainingArguments,set_seed
    from torch.utils.data import DataLoader
    from runpod_factory_sample import encode_all
    load_dotenv(root/'.env');set_seed(42)
    cfg=yaml.safe_load((root/'configs/hyperparameters.sample.pinned.yaml').read_text());hp=cfg['experiments'][0];t=hp['training']
    common=dict(revision=cfg['model']['revision'],token=os.getenv('HF_TOKEN'),trust_remote_code=False)
    tokenizer=AutoTokenizer.from_pretrained(cfg['model']['base_model_id'],**common);tokenizer.padding_side='right'
    if tokenizer.pad_token_id is None:tokenizer.pad_token=tokenizer.eos_token
    rows=encode_all(root/cfg['data']['train_file'],tokenizer,t['max_length'])[:48]
    assert len(rows)==48
    model=AutoModelForImageTextToText.from_pretrained(cfg['model']['base_model_id'],quantization_config=BitsAndBytesConfig(load_in_4bit=True,bnb_4bit_quant_type='nf4',bnb_4bit_compute_dtype=torch.bfloat16,bnb_4bit_use_double_quant=True),device_map={'':0},dtype=torch.bfloat16,attn_implementation='sdpa',**common)
    model.config.use_cache=False;model.config.text_config.use_cache=False
    model=prepare_model_for_kbit_training(model,use_gradient_checkpointing=True,gradient_checkpointing_kwargs={'use_reentrant':False})
    targets=[name for name,module in model.named_modules() if 'language_model' in name.split('.') and isinstance(module,(torch.nn.Linear,bnb.nn.Linear4bit)) and not name.endswith('lm_head')]
    l=hp['lora'];model=get_peft_model(model,LoraConfig(r=l['r'],lora_alpha=l['lora_alpha'],lora_dropout=l['lora_dropout'],bias='none',target_modules=targets,task_type='CAUSAL_LM'))
    def collate(batch):
     length=max(len(row['input_ids']) for row in batch)
     return {key:torch.tensor([row[key]+[pad]*(length-len(row[key])) for row in batch]) for key,pad in (('input_ids',tokenizer.pad_token_id),('attention_mask',0),('labels',-100))}
    class SequentialTrainer(Trainer):
     def get_train_dataloader(self):return self.accelerator.prepare(DataLoader(rows,batch_size=a.batch,shuffle=False,collate_fn=collate))
    class Timing(TrainerCallback):
     def __init__(self):self.seconds=[]
     def on_step_begin(self,args,state,control,**kw):torch.cuda.synchronize();self.start=time.perf_counter()
     def on_step_end(self,args,state,control,**kw):
      torch.cuda.synchronize();self.seconds.append(time.perf_counter()-self.start);print('BENCH_STEP',state.global_step,self.seconds[-1],flush=True)
    timer=Timing();torch.cuda.reset_peak_memory_stats()
    args=TrainingArguments(output_dir=str(Path(a.output).parent/'scratch'),per_device_train_batch_size=a.batch,gradient_accumulation_steps=16//a.batch,max_steps=3,learning_rate=1e-4,warmup_steps=0,lr_scheduler_type='constant',bf16=True,gradient_checkpointing=True,gradient_checkpointing_kwargs={'use_reentrant':False},optim='paged_adamw_8bit',logging_steps=1,save_strategy='no',eval_strategy='no',report_to='none',remove_unused_columns=False,dataloader_num_workers=0,seed=42)
    trainer=SequentialTrainer(model=model,args=args,train_dataset=rows,processing_class=tokenizer,data_collator=collate,callbacks=[timer]);result=trainer.train()
    assert math.isfinite(result.training_loss)
    result={'batch':a.batch,'accumulation':16//a.batch,'effective_batch':16,'step_seconds':timer.seconds,'steady_step_seconds':sum(timer.seconds[1:])/2,'samples_per_second':32/sum(timer.seconds[1:]),'peak_allocated_gib':torch.cuda.max_memory_allocated()/2**30,'peak_reserved_gib':torch.cuda.max_memory_reserved()/2**30,'loss':result.training_loss,'trainable_parameters':sum(p.numel() for p in model.parameters() if p.requires_grad),'sample_token_lengths':[len(r['input_ids']) for r in rows],'optimized_modules_loaded':[n for n in ('causal_conv1d','fla.ops.gated_delta_rule') if n in sys.modules]}
    Path(a.output).write_text(json.dumps(result,indent=2));print('BENCH_RESULT',json.dumps(result),flush=True)


def _generate(a):
    ROOT=Path(__file__).resolve().parents[1];F=a.folder
    import torch,yaml
    from transformers import AutoTokenizer,AutoModelForImageTextToText
    from peft import PeftModel
    sys.path.insert(0,str(ROOT/'scripts'))
    from compare_factory_sample import load_case
    cfg=yaml.safe_load((ROOT/'configs/hyperparameters.sample.pinned.yaml').read_text())
    adapter=(ROOT/a.adapter).resolve()
    tokenizer=AutoTokenizer.from_pretrained(str(adapter),trust_remote_code=False);tokenizer.padding_side='left'
    if tokenizer.pad_token_id is None:tokenizer.pad_token=tokenizer.eos_token
    total=sum(bool(line.strip()) for line in (ROOT/a.eval_file).read_text(encoding='utf-8-sig').splitlines())
    cases=[(i,*load_case((ROOT/a.eval_file),i)) for i in range(min(10,total))]
    lengths=[len(tokenizer.apply_chat_template(messages,tokenize=True,add_generation_prompt=True,enable_thinking=False,return_dict=False)) for _,messages,_ in cases]
    (F/'prompt_lengths.json').write_text(json.dumps(lengths));assert max(lengths)<=2048, lengths
    base=AutoModelForImageTextToText.from_pretrained(cfg['model']['base_model_id'],revision=cfg['model']['revision'],dtype=torch.bfloat16,device_map={'':0},attn_implementation='sdpa',trust_remote_code=False)
    model=PeftModel.from_pretrained(base,str(adapter),is_trainable=False);model.eval()
    generation={'max_new_tokens':a.max_new_tokens,'do_sample':False,'num_beams':1,'use_cache':True,'pad_token_id':tokenizer.pad_token_id,'eos_token_id':tokenizer.eos_token_id}
    args=SimpleNamespace(max_new_tokens=a.max_new_tokens)
    source=ast.parse((ROOT/'scripts/compare_factory_sample.py').read_text());functions=[next(n for n in ast.walk(source) if isinstance(n,ast.FunctionDef) and n.name==name) for name in ('trim_generated','generate_batch')]
    scope=locals().copy()
    exec(compile(ast.Module(body=functions,type_ignores=[]),'compare_factory_sample.py','exec'),scope)
    generate_batch=scope['generate_batch']
    generate_batch(cases[:1]);results=[];baseline_texts=None
    for batch in (1,2,4):
     torch.cuda.empty_cache();torch.cuda.reset_peak_memory_stats();torch.cuda.synchronize();start=time.perf_counter();all_res=[]
     try:
      for offset in range(0,len(cases),batch):
       responses,actual_lengths=generate_batch(cases[offset:offset+batch]);assert actual_lengths==lengths[offset:offset+batch]
       assert len(responses)==len(cases[offset:offset+batch]);all_res+=responses
      torch.cuda.synchronize();seconds=time.perf_counter()-start
      if baseline_texts is None:baseline_texts=[r['text'] for r in all_res]
      matches=sum(r['text']==text for r,text in zip(all_res,baseline_texts))
      result={'exact_text_matches_to_batch1':matches,'batch':batch,'inputs':len(cases),'seconds':seconds,'output_tokens':sum(r['tokens'] for r in all_res),'output_tokens_per_second':sum(r['tokens'] for r in all_res)/seconds,'peak_allocated_gib':torch.cuda.max_memory_allocated()/2**30,'peak_reserved_gib':torch.cuda.max_memory_reserved()/2**30,'token_cap':a.max_new_tokens,'purpose':'throughput only; truncated probes are never evaluation reports'}
      results.append(result);print('GENERATION_BENCH',json.dumps(result),flush=True)
     except torch.cuda.OutOfMemoryError:
      results.append({'batch':batch,'status':'OOM'});torch.cuda.empty_cache()
     (F/'generation_results.json').write_text(json.dumps(results,indent=2))

def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--mode',choices=('train','generation'),required=True)
    parser.add_argument('--batch',type=int,choices=(1,2,4),default=4)
    parser.add_argument('--adapter',help='Existing local factory adapter for generation mode')
    parser.add_argument('--eval-file',default='data/eval/prompts.jsonl')
    parser.add_argument('--max-new-tokens',type=int,default=128)
    a=parser.parse_args()
    if a.mode=='generation' and not a.adapter:parser.error('--adapter is required in generation mode')
    if not 1<=a.max_new_tokens<=2048:parser.error('--max-new-tokens must be 1..2048')
    if os.name!='posix':parser.error('Run on the Linux RunPod GPU environment')
    import fcntl
    import runpod_bridge as bridge
    root=Path(__file__).resolve().parents[1]
    a.folder=root/'outputs'/('performance_probe_'+time.strftime('%Y%m%d_%H%M%S'))
    a.folder.mkdir(parents=True,exist_ok=False)
    a.output=str(a.folder/('train_b'+str(a.batch)+'.json'))
    bridge.JOBS.mkdir(parents=True,exist_ok=True)
    with (bridge.JOBS/'submit.lock').open('a') as submission:
        fcntl.flock(submission,fcntl.LOCK_EX)
        if any(job['state'] in ('RUNNING','QUEUED') for job in bridge.status()):
            raise RuntimeError('GPU queue is active; run the probe after queued work finishes')
        guard=bridge.gpu_lock()
        if guard is None:raise RuntimeError('GPU is already owned by another task')
    try:
        if a.mode=='train':_train(a)
        else:_generate(a)
    finally:guard.close()
    print('Probe results:',a.folder,flush=True)

if __name__=='__main__':main()
