"""Package only reviewed 4B training inputs and code, never .env or weights."""
import argparse,json,zipfile
from pathlib import Path
import yaml
from qwen35_b200_runner import ROOT,validate_release,inside,digest

def main():
 p=argparse.ArgumentParser();p.add_argument('--config',default='configs/hyperparameters.qwen35_4b_3000.P01.yaml');p.add_argument('--output',type=Path,required=True);args=p.parse_args()
 config=inside(ROOT,args.config);cfg=yaml.safe_load(config.read_text(encoding='utf-8'))
 _,contract=validate_release(ROOT,cfg)
 release_path=inside(ROOT,cfg['data']['release_manifest']);release=json.loads(release_path.read_text(encoding='utf-8'))
 relative={args.config,cfg['data']['train_file'],cfg['data']['original_file'],cfg['data']['release_manifest'],cfg['evaluation']['file'],'requirements-runpod.txt','requirements-kernel-b200.txt','scripts/qwen35_b200_runner.py','scripts/run_all_qwen35_presets.py','scripts/pack_comparison_results.py','scripts/qwen35_comparison_dashboard.py','scripts/model_runtime.py','scripts/compare_factory_sample.py'}
 for pid in ('P01','P02','P03','P04','P05','P06'):
  c_path=f'configs/hyperparameters.qwen35_4b_3000.{pid}.yaml'
  if (ROOT/c_path).is_file():relative.add(c_path)
 artifacts=[release['automatic_checks'],release['provenance']]+[cycle[role] for cycle in release['rounds'] for role in ('maker','reviewer','inspector')]
 for item in artifacts:
  path=inside(ROOT,item['path'])
  if not path.is_relative_to(ROOT/'data/production/expanded_3000'):raise ValueError('Copy review evidence into expanded_3000 before packaging')
  relative.add(item['path'])
 files={rel:inside(ROOT,rel) for rel in sorted(relative)}
 if any(not path.is_file() or path.name.startswith('.env') for path in files.values()):raise ValueError('Missing or forbidden bundle file')
 output=args.output.resolve()
 if output.exists():raise ValueError('Output exists; nothing overwritten')
 output.parent.mkdir(parents=True,exist_ok=True)
 hashes={rel:digest(path) for rel,path in files.items()}
 with zipfile.ZipFile(output,'x',zipfile.ZIP_DEFLATED) as z:
  for rel,path in files.items():z.write(path,'qwen_factory/'+rel)
  z.writestr('qwen_factory/bundle_manifest.json',json.dumps({'contract':contract,'files':hashes,'training_started':False},ensure_ascii=False,indent=2))
 with zipfile.ZipFile(output) as z:
  if z.testzip() is not None:raise ValueError('Bundle integrity failed')
 print(json.dumps({'path':str(output),'sha256':digest(output),'files':len(files),'archive_root':'qwen_factory','secrets_included':False}))

if __name__=='__main__':main()
