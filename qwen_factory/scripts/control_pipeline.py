"""Run a registered sample recipe and generate all held-out comparisons serially."""
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys

import yaml
from dotenv import load_dotenv
from sqlalchemy import create_engine, select
from db_registry import build_plans, runs, artifacts, sample_mode, factory_output, report_input_info


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--resume-existing", action="store_true")
    parser.add_argument("--evaluate-only", action="store_true", help="Use uploaded adapters without invoking training")
    parser.add_argument("--case-limit", type=int, help="Limit cases per epoch for a GPU verification run")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    load_dotenv(root/".env")
    config = (root/args.config).resolve()
    config.relative_to(root/"configs")
    cfg = yaml.safe_load(config.read_text(encoding="utf-8-sig"))
    is_sample=sample_mode(cfg)
    plan = build_plans(root, config, is_sample)[0]
    def execute(script, *flags):
        options = {}
        if os.environ.get("QF_GPU_LOCK_FD"):
            descriptor = int(os.environ["QF_GPU_LOCK_FD"])
            os.fstat(descriptor)
            options["pass_fds"] = (descriptor,)
        subprocess.run([sys.executable, "-u", "scripts/"+script, "--config", args.config, *flags], cwd=root, check=True, **options)
    if not args.resume_existing and not args.evaluate_only:
        print("PIPELINE: register", flush=True)
        print("진행 안내: 1/3 · 실험 설정을 등록합니다. 아직 학습은 시작되지 않았습니다.", flush=True)
        execute("db_registry.py", *(["--sample"] if is_sample else []), "--register")
    engine = create_engine(os.environ["DATABASE_URL"], pool_pre_ping=True)
    try:
        with engine.connect() as c:
            record = c.execute(select(runs).where(runs.c.config_hash==plan["config_hash"])).mappings().one()
            run_id = record["run_id"]
        if not args.evaluate_only:
            print("PIPELINE: train or resume", flush=True)
            print("진행 안내: 2/3 · 모델을 불러온 뒤 학습합니다. 설정한 에포크의 가중치를 각각 저장하고 업로드합니다.", flush=True)
        else:
            print("PIPELINE: evaluate existing adapters",flush=True)
        output = factory_output(root,run_id,is_sample)
        if not args.resume_existing and not args.evaluate_only and (output.exists() or record["status"] in ("TRAINED","EVALUATED")):
            raise ValueError("Existing experiment detected; start a new experiment or use explicit resume/evaluation")
        if (args.resume_existing or args.evaluate_only) and not output.is_dir():
            raise ValueError("Existing run files are missing; restore the original run directory before resuming")
        if not args.evaluate_only:
            execute("runpod_factory_sample.py", "--execute", *(["--resume"] if args.resume_existing else []))
        else:
            print("진행 안내: 재학습 없이 저장된 가중치의 BF16 평가만 수행합니다.",flush=True)
        with engine.connect() as c:
            snapshots = [dict(r) for r in c.execute(select(artifacts).where(artifacts.c.run_id==run_id)
                         .order_by(artifacts.c.trained_epoch)).mappings()]
    finally:
        engine.dispose()
    expected_epochs=set(cfg['experiments'][0]['artifacts']['save_epochs'])
    if len(snapshots)!=len(expected_epochs) or {snapshot['trained_epoch'] for snapshot in snapshots}!=expected_epochs:
        raise ValueError("Saved artifacts differ from the registered epoch plan")
    if os.environ.get('QF_LINEAR_ATTENTION_BACKEND'):
        from model_runtime import configure
        configure(cfg)
    if cfg.get('live_evaluation',{}).get('enabled'):
        print('진행 안내: 학습 완료. 최신 Cloud DB 근거를 조회해 고정10개 입력을 확정합니다.',flush=True)
        from cloud_evaluation import freeze
        cfg,receipt=freeze(root,cfg)
        inferred=config.with_name(config.stem+'_live_eval.yaml')
        inferred.write_text(yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False),encoding='utf-8')
        args.config=inferred.relative_to(root).as_posix()
        print('LIVE COHORT: '+json.dumps(receipt,ensure_ascii=False),flush=True)
    report_input_info(root,cfg)
    max_new_tokens=cfg.get('inference',{}).get('max_new_tokens',2048)
    cohorts=[('report',cfg['data'].get('test_file','data/sample/eval/test.jsonl'))]
    if cfg['data'].get('heldout_test_file'):
        cohorts.append(('heldout',cfg['data']['heldout_test_file']))
    for cohort,cohort_file in cohorts:
        report_prefix='heldout_compare_' if cohort=='heldout' else 'smoke_compare_'
        print('평가 묶음: '+cohort+'; 별도 지정한 case-limit이 없으면 전체 입력을 평가합니다.',flush=True)
        test_path=(root/cohort_file).resolve()
        test_path.relative_to((root/"data").resolve())
        cases = [json.loads(s) for s in test_path.read_text(encoding="utf-8-sig").splitlines() if s.strip()]
        if not cases:
            raise ValueError("Evaluation dataset is empty")
        print(f"진행 안내: 학습·업로드 완료. 3/3 · {len(cases)}개 입력의 답변을 에포크별로 생성합니다.", flush=True)
        if args.case_limit is not None and args.case_limit<1:
            raise ValueError("case-limit must be positive")
        indices=range(min(len(cases),args.case_limit)) if args.case_limit else range(len(cases))
        for snapshot in snapshots:
            if snapshot["status"] not in ("TRAINED", "EVALUATED"):
                raise RuntimeError("Snapshot upload not complete")
            adapter = output/"artifacts"/snapshot["weight_id"]
            pending=[]
            for index in indices:
                # Avoid re-generating a completed comparison for the same artifact and conditions.
                matching = False
                for f in (root/"reports").glob(report_prefix+"*/comparison.json"):
                    d = json.loads(f.read_text(encoding="utf-8"))
                    if (d.get("factory_manifest",{}).get("weight_id")==snapshot["weight_id"]
                        and d.get("case_index")==index and d.get("generation",{}).get("max_new_tokens")==max_new_tokens
                        and d.get("generation",{}).get("do_sample") is False
                        and d.get("generation",{}).get("num_beams")==1
                        and d.get("generation",{}).get("use_cache") is True
                        and d.get("model")==cfg["model"]
                        and d.get("quantization")=={"load_in_4bit":False,"dtype":"bfloat16"}
                        and d.get("test_sha256")==__import__("hashlib").sha256(test_path.read_bytes()).hexdigest()
                        and not d["tuned"]["hit_token_limit"]):
                        matching=True
                        break
                if matching:
                    print(f"진행 안내: {snapshot['trained_epoch']}에포크 · 입력 {index+1}/{len(cases)} · 기존 답변을 사용합니다.", flush=True)
                    continue
                pending.append(index)
            if pending:
                print(f"PIPELINE: compare epoch={snapshot['trained_epoch']} cases={len(pending)}",flush=True)
                print(f"진행 안내: {snapshot['trained_epoch']}에포크 · BF16 모델을 한 번 로딩해 미완료 {len(pending)}개를 순서대로 생성합니다.",flush=True)
                execute("compare_factory_sample.py", "--adapter", str(adapter), "--case-indices", *map(str,pending), "--max-new-tokens", str(max_new_tokens), "--cohort", cohort)
    print("진행 안내: 답변 생성 완료. 로컬 보고서를 동기화한 뒤 입력별로 1~5점 평가하세요.", flush=True)
    print("PIPELINE COMPLETE: ready for human evaluation", flush=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("PIPELINE FAILED: " + type(error).__name__ + "; inspect the preceding stage log", flush=True)
        sys.exit(1)
