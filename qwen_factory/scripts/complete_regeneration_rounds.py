"""Resume authorized failed-record repairs; preserve every API artifact and production."""
import concurrent.futures,json,time
from pathlib import Path
import app_settings
from rewrite_diverse_corpus import ROOT,call_one
from review_generated_corpus import inspect

def main():
    folder=ROOT/'data/revision_1500'
    expected=len((folder/'regeneration_requests.jsonl').read_text(encoding='utf-8').splitlines())
    while True:
        files=list((folder/'generated_retry_01').glob('*.json'))
        active=sum(json.loads(p.read_text(encoding='utf-8')).get('status')=='REQUEST_RESERVED' for p in files)
        if len(files)>=expected and not active:break
        print('WAITING_EXISTING_ROUND',len(files),expected,active,flush=True);time.sleep(30)
    key=app_settings.read(ROOT).get('OPENAI_API_KEY')
    if not key:raise ValueError('OPENAI_API_KEY missing')
    for number in range(2,7):
        retry=inspect(folder,latest=True)
        if not retry:
            print('ALL_1003_STRUCTURALLY_REVIEWED; semantic review and final assembly still required',flush=True);return
        target=folder/('generated_retry_%02d'%number);target.mkdir(exist_ok=True)
        print('REPAIR_ROUND',number,'COUNT',len(retry),flush=True)
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            for result in pool.map(lambda r:call_one(r,key,target),retry):pass
    remaining=inspect(folder,latest=True)
    print('REPEATED_FAILURE_DIAGNOSIS_REQUIRED',len(remaining),flush=True)
if __name__=='__main__':main()
