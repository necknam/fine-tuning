"""Isolated BF16 full-length checkpointing test; never updates saved weights.

Run only after the active P01 training and comparisons finish. Writes a small
diagnostic receipt, not a factory run, trained adapter, or evaluation report.
"""
import argparse
import hashlib
import json
import math
import os
from pathlib import Path
import statistics
import subprocess
import sys
import time

ROOT = Path(__file__).resolve().parents[1]


def measure(args, cfg, folder):
    import torch
    from dotenv import load_dotenv
    from peft import LoraConfig, get_peft_model
    from transformers import AutoModelForImageTextToText, AutoTokenizer, set_seed
    from model_runtime import configure
    from runpod_factory_sample import encode_all
    load_dotenv(ROOT / '.env')
    configure(cfg)
    set_seed(42)
    common = dict(revision=cfg['model']['revision'], token=os.environ['HF_TOKEN'], trust_remote_code=False,
                  local_files_only=True)
    tokenizer = AutoTokenizer.from_pretrained(cfg['model']['base_model_id'], **common)
    if tokenizer.pad_token_id is None:
        tokenizer.pad_token = tokenizer.eos_token
    rows = encode_all(ROOT / cfg['data']['train_file'], tokenizer, 10240, loss_policy='final_assistant_only')
    if len(rows) != 1500:
        raise ValueError('Probe requires the complete production dataset')
    order = sorted(range(len(rows)), key=lambda i: len(rows[i]['input_ids']))
    indices = [order[len(order)//2], order[-1]]
    model = AutoModelForImageTextToText.from_pretrained(cfg['model']['base_model_id'],
              dtype=torch.bfloat16, device_map={'':0}, attn_implementation='sdpa', **common)
    model.config.use_cache = False
    model.config.text_config.use_cache = False
    if args.checkpointing == 'on':
        model.enable_input_require_grads()
    hp = cfg['experiments'][0]['lora']
    targets = [name for name, module in model.named_modules() if 'language_model' in name.split('.')
               and isinstance(module, torch.nn.Linear) and not name.endswith('lm_head')]
    model = get_peft_model(model, LoraConfig(r=hp['r'], lora_alpha=hp['lora_alpha'],
              lora_dropout=hp['lora_dropout'], bias='none', target_modules=targets, task_type='CAUSAL_LM'))
    if args.checkpointing == 'on':
        model.gradient_checkpointing_enable(gradient_checkpointing_kwargs={'use_reentrant':False})
    else:
        model.gradient_checkpointing_disable()
    model.train()
    import bitsandbytes as bnb
    optimizer = bnb.optim.PagedAdamW8bit([p for p in model.parameters() if p.requires_grad], lr=1e-4)
    optimizer_steps = 0
    results = []
    for index in indices:
        batch = {key: torch.tensor([rows[index][key]], device='cuda')
                 for key in ('input_ids','attention_mask','labels')}
        seconds = []
        losses = []
        torch.cuda.reset_peak_memory_stats()
        for attempt in range(3):
            model.zero_grad(set_to_none=True)
            set_seed(42)
            torch.cuda.synchronize()
            started = time.perf_counter()
            with torch.autocast('cuda', dtype=torch.bfloat16):
                loss = model(**batch).loss
            loss.backward()
            if not all(torch.isfinite(p.grad).all().item() for p in model.parameters() if p.grad is not None):
                raise ValueError("Non-finite gradient")
            optimizer.step()
            optimizer_steps += 1
            torch.cuda.synchronize()
            elapsed = time.perf_counter() - started
            value = float(loss.detach().float().cpu())
            if not math.isfinite(value) or not all(torch.isfinite(p.grad).all().item() for p in model.parameters() if p.grad is not None):
                raise ValueError('Non-finite loss or gradient')
            if attempt:
                seconds.append(elapsed)
                losses.append(value)
            del loss
        results.append(dict(case_index=index, tokens=len(rows[index]['input_ids']),
                            forward_backward_seconds=statistics.median(seconds),losses=losses,
                            peak_allocated_gib=torch.cuda.max_memory_allocated()/2**30,
                            peak_reserved_gib=torch.cuda.max_memory_reserved()/2**30,
                            gpu_total_gib=torch.cuda.get_device_properties(0).total_memory/2**30))
        del batch
    return dict(status='PASSED', checkpointing=args.checkpointing, rows=results,
                optimizer_steps=optimizer_steps, saved_weights_modified=False, limitations='Single-microbatch optimizer-step fit/timing in scratch memory; not production accumulation16 throughput or quality evidence')


def main():
    import yaml
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--config', required=True)
    parser.add_argument('--child', action='store_true')
    parser.add_argument('--checkpointing', choices=['on','off'], default='on')
    parser.add_argument('--folder')
    args = parser.parse_args()
    config = (ROOT / args.config).resolve()
    config.relative_to(ROOT / 'configs')
    cfg = yaml.safe_load(config.read_text(encoding='utf-8-sig'))
    path = (ROOT / cfg['data']['train_file']).resolve()
    path.relative_to(ROOT / 'data')
    if cfg['quantization']['load_in_4bit'] or hashlib.sha256(path.read_bytes()).hexdigest() != cfg['data']['train_sha256']:
        raise ValueError('Pinned BF16 production data required')
    if args.child:
        import fcntl
        descriptor = int(os.environ['QF_PROBE_GPU_LOCK_FD'])
        if Path('/proc/self/fd/' + str(descriptor)).resolve() != (ROOT/'outputs/control_jobs/gpu.lock').resolve():
            raise ValueError('Expected inherited GPU lock')
        os.fstat(descriptor)
        fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
        folder = Path(args.folder).resolve()
        folder.relative_to(ROOT / 'outputs')
        try:
            result = measure(args, cfg, folder)
        except Exception as error:
            # Do not print token-bearing exception text.
            result = dict(status='FAILED', error_type=type(error).__name__, optimizer_steps=0,
                          saved_weights_modified=False)
        (folder / (args.checkpointing + '.json')).write_text(json.dumps(result, indent=2), encoding='utf-8')
        print(json.dumps(result), flush=True)
        return
    import fcntl
    import runpod_bridge as bridge
    plan = json.loads((ROOT/'outputs/conditional_p02_p05/plan.json').read_text())
    if plan.get('gate_status') != 'PASSED':
        raise RuntimeError('P01 quality gate has not passed; no GPU probe started')
    for job_id in ('20261023_052813_d5546aee','20261023_035554_c70bab74'):
        job = json.loads((bridge.JOBS/job_id/'job.json').read_text())
        if job['state'] != 'SUCCEEDED':
            raise RuntimeError('P01 jobs are not complete; no GPU probe started')
    bridge.JOBS.mkdir(parents=True, exist_ok=True)
    # Standalone only; never runs while training, comparisons, or queued work exists.
    with (bridge.JOBS/'submit.lock').open('a') as submission:
        fcntl.flock(submission, fcntl.LOCK_EX)
        if any(job['state'] in ('RUNNING','QUEUED') for job in bridge.status()):
            raise RuntimeError('Queue is active; wait until P01 comparisons finish')
        guard = bridge.gpu_lock()
        if guard is None:
            raise RuntimeError('GPU is owned by another process')
    folder = ROOT/'outputs'/('checkpointing_fit_'+time.strftime('%Y%m%d_%H%M%S'))
    folder.mkdir(exist_ok=False)
    try:
        for mode in ('on','off'):
            subprocess.run([sys.executable,'-u',str(Path(__file__)), '--config',args.config,
                            '--child','--checkpointing',mode,'--folder',str(folder)],
                           cwd=ROOT,check=True,timeout=480,pass_fds=(guard.fileno(),),
                           env={**os.environ,'QF_PROBE_GPU_LOCK_FD':str(guard.fileno())})
        baseline = json.loads((folder/'on.json').read_text())
        candidate = json.loads((folder/'off.json').read_text())
        result = dict(baseline=baseline,candidate=candidate, config=args.config,
                      config_sha256=hashlib.sha256(config.read_bytes()).hexdigest(),
                      production_config_modified=False, saved_weights_modified=False)
        if baseline['status']=='PASSED' and candidate['status']=='PASSED':
            result['microbatch_comparison'] = [dict(tokens=a['tokens'],
                faster_ratio=a['forward_backward_seconds']/b['forward_backward_seconds'],
                absolute_loss_delta=abs(a['losses'][0]-b['losses'][0]),
                candidate_reserved_headroom_gib=b['gpu_total_gib']-b['peak_reserved_gib'])
                for a,b in zip(baseline['rows'],candidate['rows'])]
        (folder/'result.json').write_text(json.dumps(result,indent=2),encoding='utf-8')
        print('PROBE_RECEIPT', folder/'result.json', flush=True)
    finally:
        guard.close()


if __name__ == '__main__':
    main()
