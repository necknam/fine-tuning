import json,hashlib,statistics
from pathlib import Path
from transformers import AutoTokenizer
root=Path(__file__).resolve().parents[1]/'data/revision_1500/assembled'
revision='1d4bf0f2ff6012fd82039f2fa52739d0dd7c60c0'
tok=AutoTokenizer.from_pretrained('Qwen/Qwen3.8-27B',revision=revision,trust_remote_code=False,local_files_only=True)
lengths=[];issues=[];records=[]
for n,line in enumerate((root/'all.jsonl').read_text(encoding='utf-8').splitlines(),1):
 row=json.loads(line);m=row['messages'];ids=tok.apply_chat_template(m,tokenize=True,add_generation_prompt=False,enable_thinking=False,return_dict=False);prefix=tok.apply_chat_template(m[:-1],tokenize=True,add_generation_prompt=True,enable_thinking=False,return_dict=False)
 if ids[:len(prefix)]!=prefix or len(prefix)>=len(ids):issues.append(n)
 lengths.append(len(ids));records.append({'line':n,'total_tokens':len(ids),'prompt_tokens':len(prefix),'assistant_tokens':len(ids)-len(prefix)})
 if n%250==0:print('Measured',n,flush=True)
s=sorted(lengths);report={'model':'Qwen/Qwen3.8-27B','revision':revision,'total':len(s),'min':min(s),'max':max(s),'median':statistics.median(s),'p95':s[int(.95*(len(s)-1))],'over_7168':sum(x>7168 for x in s),'prefix_mask_issues':issues,'truncation_used':False,'all_sha256':hashlib.sha256((root/'all.jsonl').read_bytes()).hexdigest()}
(root/'token_measurement.json').write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8');(root/'token_lengths.jsonl').write_text(''.join(json.dumps(r)+'\n' for r in records),encoding='utf-8')
m=json.loads((root/'manifest.json').read_text(encoding='utf-8'));m['token_summary']=report;m['token_measurement_completed']=True;m['files']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in root.glob('*.jsonl')};(root/'manifest.json').write_text(json.dumps(m,ensure_ascii=False,indent=2),encoding='utf-8');print(json.dumps(report,ensure_ascii=False))
