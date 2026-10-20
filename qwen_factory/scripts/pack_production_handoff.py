"""Build a local portable production bundle; no secrets, weights, DB, network or training."""
import hashlib,json,zipfile
from pathlib import Path
import yaml
from db_registry import build_plans,report_input_info

def pack(root):
    root=Path(root).resolve()
    config=root/'configs/hyperparameters.production.pinned.yaml'
    cfg=yaml.safe_load(config.read_text(encoding='utf-8-sig'))
    plan=build_plans(root,config,False)[0]
    report_input_info(root,cfg)
    files=list((root/'scripts').glob('*.py'))+list((root/'tests').glob('test_*.py'))
    files+=list((root/'configs').glob('hyperparameters*.yaml'))
    files+=[root/n for n in ('requirements-runpod.txt','requirements.txt','README.md','.env.example')]
    files+=[root/cfg['data'][k] for k in ('train_file','validation_file','heldout_test_file','test_file')]
    companion=(root/cfg['data']['test_file']).with_suffix('.manifest.json')
    if companion.is_file():files.append(companion)
    docs=[root.parent/'docs'/n for n in ('CODEX_HANDOFF.md','FINETUNING_GUIDE.md')]
    target=root/'outputs/gpu_production_handoff.zip';target.parent.mkdir(exist_ok=True)
    manifest={'format_version':1,'training_config_hash':plan['config_hash'],'files':{},'contains_credentials':False,'contains_model_weights':False}
    with zipfile.ZipFile(target,'w',zipfile.ZIP_DEFLATED) as archive:
        for path in sorted(set(files+docs)):
            if not path.is_file():raise ValueError('Missing bundle input: '+path.name)
            name=('qwen_factory/'+path.relative_to(root).as_posix()) if path.is_relative_to(root) else 'docs/'+path.name
            raw=path.read_bytes();manifest['files'][name]=hashlib.sha256(raw).hexdigest();archive.writestr(name,raw)
        archive.writestr('handoff_manifest.json',json.dumps(manifest,ensure_ascii=False,indent=2))
    return {'file':str(target),'files':len(manifest['files']),'config_hash':plan['config_hash'],'sha256':hashlib.sha256(target.read_bytes()).hexdigest()}

if __name__=='__main__':print(json.dumps(pack(Path(__file__).resolve().parents[1]),ensure_ascii=False))
