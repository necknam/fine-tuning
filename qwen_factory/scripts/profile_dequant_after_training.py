"""Sequential CUDA-event benchmark after training exits, before BF16 comparison."""
import json,statistics,subprocess,os
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
RUN=ROOT/'outputs/P01_validity_20261022'
if __name__=='__main__':
 result=json.loads((RUN/'training_result.json').read_text())
 assert result['steps']==94 and result['epochs']==1
 stage=json.loads((RUN/'status.json').read_text())['stage']
 assert stage=='comparison_process_started','Only run after the training process exits'
 query=subprocess.run(['nvidia-smi','--query-compute-apps=pid,used_memory','--format=csv,noheader,nounits'],capture_output=True,text=True,check=True)
 for line in query.stdout.splitlines():
  if ',' not in line:continue
  pid,used=[x.strip() for x in line.split(',',1)]
  assert int(pid)==os.getpid() or not used.isdigit() or int(used)<1024,'Another GPU workload is active; skip the benchmark'
 import torch,bitsandbytes as bnb
 torch.cuda.set_device(0)
 w=torch.randn((17408,5120),device='cuda',dtype=torch.bfloat16)
 q,state=bnb.functional.quantize_4bit(w,quant_type='nf4',compress_statistics=True)
 a=torch.randn((3500,5120),device='cuda',dtype=torch.bfloat16)
 results={}
 for label in ['dequantize_only','bf16_forward_backward','nf4_forward_backward']:
  times=[]
  for repeat in range(5):
   aa=a.detach().requires_grad_(True);start=torch.cuda.Event(enable_timing=True);end=torch.cuda.Event(enable_timing=True)
   start.record()
   if label=='dequantize_only':out=bnb.functional.dequantize_4bit(q,state)
   elif label=='bf16_forward_backward':out=torch.nn.functional.linear(aa,w);out.sum().backward()
   else:out=bnb.matmul_4bit(aa,q.t(),quant_state=state);out.sum().backward()
   end.record();end.synchronize()
   if repeat>=2:times.append(start.elapsed_time(end))
   del out,aa
  results[label]={'milliseconds':times,'median_ms':statistics.median(times)}
 report={'scope':'representative 3500x5120 input and 17408x5120 weight; sequential after training','not_full_step_profile':True,'measurements':results,'peak_allocated_gib':torch.cuda.max_memory_allocated()/2**30,'limitations':'Representative layer only; not the fraction of the actual full training step; no claim about B200.'}
 (RUN/'dequant_layer_profile.json').write_text(json.dumps(report,indent=2));print(json.dumps(report),flush=True)
