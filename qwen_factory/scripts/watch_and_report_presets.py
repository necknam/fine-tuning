"""Watchdog & Automated Reporter for Qwen3.5-4B Presets P01~P06 on RunPod.

Monitors training loss, epoch progression, benchmark evaluations, pulls artifacts,
sends hourly progress emails to gom2553@naver.com while running, sends preset completion
emails, and automatically stops the RunPod instance upon completion (discontinuing hourly reports).
"""
import argparse
import base64
import json
import os
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import app_settings
from runpod_client import RunPodClient
from send_notification_email import send_email


def get_remote_state(client: RunPodClient):
    code = '''
import json, glob, os, subprocess

# 1. GPU metrics
gpu_out = "N/A"
try:
    gpu_out = subprocess.check_output(
        ['nvidia-smi', '--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,power.draw', '--format=csv,noheader,nounits'],
        text=True
    ).strip()
except Exception:
    pass

# 2. Check active processes
ps_lines = subprocess.check_output(['ps', '-ef'], text=True).splitlines()
active_batch = None
active_runner = None
for l in ps_lines:
    if 'run_all_qwen35_presets.py' in l:
        active_batch = l
    elif 'qwen35_b200_runner.py' in l:
        active_runner = l

current_running_preset = None
if active_runner:
    for p in ['P01', 'P02', 'P03', 'P04', 'P05', 'P06']:
        if f'{p}.yaml' in active_runner:
            current_running_preset = p
            break

# 3. Batch progress file
batch_prog = {}
if os.path.exists('/workspace/qwen_factory/outputs/all_presets_progress.json'):
    try:
        with open('/workspace/qwen_factory/outputs/all_presets_progress.json', 'r', encoding='utf-8') as f:
            batch_prog = json.load(f)
    except Exception:
        pass

# 4. Latest training status
current_status = {}
statuses = glob.glob('/workspace/qwen_factory/outputs/**/full3000/status.json', recursive=True)
if statuses:
    statuses.sort(key=os.path.getmtime, reverse=True)
    try:
        with open(statuses[0], 'r', encoding='utf-8') as f:
            current_status = json.load(f)
            current_status['status_file'] = statuses[0]
    except Exception:
        pass

# 5. Tail of log for recent losses
recent_losses = []
if os.path.exists('/workspace/qwen_factory/outputs/run_all_presets.log'):
    try:
        with open('/workspace/qwen_factory/outputs/run_all_presets.log', 'r', encoding='utf-8') as f:
            for line in reversed(f.readlines()):
                if 'learning_rate' in line:
                    recent_losses.append(line.strip())
                    if len(recent_losses) >= 5:
                        break
    except Exception:
        pass

# 6. Check completed presets and reports
completed_presets = {}
for p in ['P01', 'P02', 'P03', 'P04', 'P05', 'P06']:
    res_files = glob.glob(f'/workspace/qwen_factory/outputs/qwen35_4b_3000_{p}/**/full3000/result.json', recursive=True)
    if res_files:
        try:
            with open(res_files[0], 'r', encoding='utf-8') as f:
                completed_presets[p] = json.load(f)
        except Exception:
            pass

print(json.dumps({
    "gpu": gpu_out,
    "is_batch_running": bool(active_batch),
    "current_running_preset": current_running_preset,
    "current_status": current_status,
    "recent_losses": list(reversed(recent_losses)),
    "completed_presets": completed_presets,
    "batch_progress": batch_prog
}))
'''
    res = client.execute(code, timeout=30)
    return json.loads(res.strip())


def stop_remote_pod(client: RunPodClient, pod_id: str = "kq65qxmwibvy27"):
    code = f'''
import os, json, urllib.request
query = 'mutation {{ podStop(input: {{podId: "{pod_id}"}}) {{ id desiredStatus }} }}'
req = urllib.request.Request(
    'https://api.runpod.io/graphql',
    data=json.dumps({{'query': query}}).encode(),
    headers={{
        'Content-Type': 'application/json',
        'Authorization': 'Bearer ' + os.environ.get('RUNPOD_API_KEY', '')
    }}
)
with urllib.request.urlopen(req, timeout=30) as resp:
    res = json.load(resp)
print(json.dumps(res))
'''
    res = client.execute(code, timeout=35)
    return json.loads(res.strip())


def pack_and_download_results(client: RunPodClient):
    print("[+] Packaging comparison results on RunPod...")
    code = '''
import subprocess
res = subprocess.check_output(
    ['python', 'scripts/pack_comparison_results.py', '--zip', 'outputs/qwen35_4b_reports.zip'],
    cwd='/workspace/qwen_factory', text=True
)
print(res)
'''
    client.execute(code, timeout=60)
    
    print("[+] Downloading zip artifact to local outputs/...")
    code_b64 = '''
import base64
with open('/workspace/qwen_factory/outputs/qwen35_4b_reports.zip', 'rb') as f:
    print(base64.b64encode(f.read()).decode('ascii'))
'''
    b64_str = client.execute(code_b64, timeout=60).strip()
    zip_bytes = base64.b64decode(b64_str)
    local_zip = ROOT / "outputs" / "qwen35_4b_reports.zip"
    local_zip.parent.mkdir(parents=True, exist_ok=True)
    local_zip.write_bytes(zip_bytes)
    print(f"[+] Downloaded {len(zip_bytes)} bytes to {local_zip}")

    import zipfile
    with zipfile.ZipFile(local_zip, "r") as z:
        z.extractall(ROOT)
    print("[+] Extracted comparison reports to local project workspace.")


def handle_hourly_email(state):
    """Check if 1 hour has elapsed since last hourly report and training is active."""
    all_done_file = ROOT / "outputs" / "all_done.json"
    if all_done_file.exists():
        # Completed: do not send any more hourly updates
        return

    tracker_file = ROOT / "outputs" / "hourly_email_tracker.json"
    tracker = {}
    if tracker_file.exists():
        try:
            tracker = json.loads(tracker_file.read_text(encoding="utf-8"))
        except Exception:
            pass

    now = time.time()
    last_sent = tracker.get("last_sent_at", 0)

    # If first run or >= 3600 seconds (1 hour) elapsed
    if (now - last_sent) >= 3600:
        curr_p = state.get("current_running_preset", "Unknown")
        curr = state.get("current_status", {})
        step = curr.get("step", 0)
        total = curr.get("total_steps", 940)
        epoch = curr.get("epoch", 0.0)
        mean_s = curr.get("steady_step_mean_seconds", 0.0)
        rem_s = curr.get("remaining_training_estimate_seconds", 0.0)
        losses = state.get("recent_losses", [])
        latest_loss = losses[-1] if losses else "N/A"
        gpu = state.get("gpu", "N/A")
        completed = list(state.get("completed_presets", {}).keys())

        subject = f"[GrowPath 1시간 요약] Qwen3.5-4B 학습 현황 (진행중: {curr_p}, {epoch:.2f}에폭)"
        body = f"""안녕하세요!
GrowPath Qwen3.5-4B RunPod B200 파인튜닝 1시간 정기 현황 요약입니다.

■ 현재 진행 상태:
- 활성 프리셋: {curr_p}
- 진행률: {step}/{total} 스텝 ({(step/total*100):.1f}%) | Epoch: {epoch:.2f} / 5.0
- 최근 Loss: {latest_loss}
- 스텝당 실측 속도: {mean_s:.2f}초/스텝
- 현재 프리셋 잔여 시간: 약 {rem_s/60:.1f} 분
- 완료된 프리셋 목록: {', '.join(completed) if completed else '없음 (P01 진행 중)'}

■ GPU 리소스 상태:
- GPU: {gpu}

※ 본 1시간 정기 요약 보고는 전체 학습(P01~P06) 완료 및 RunPod 자동 중단과 동시에 발송이 자동 중단됩니다.
감사합니다."""

        print(f"[+] Sending 1-hour progress summary email to gom2553@naver.com...")
        send_email(subject, body)
        tracker["last_sent_at"] = now
        tracker["last_preset"] = curr_p
        tracker["last_epoch"] = epoch
        tracker_file.write_text(json.dumps(tracker, indent=2), encoding="utf-8")


def check_and_update(client: RunPodClient):
    state = get_remote_state(client)
    local_state_file = ROOT / "outputs" / "live_monitoring_status.json"
    local_state_file.parent.mkdir(parents=True, exist_ok=True)
    
    # 1. Preset completion notification emails
    sent_file = ROOT / "outputs" / "emailed_presets.json"
    emailed = json.loads(sent_file.read_text(encoding="utf-8")) if sent_file.exists() else []

    completed = state.get("completed_presets", {})
    for pid, pdata in completed.items():
        if pid not in emailed:
            subject = f"[GrowPath 프리셋 완료] Qwen3.5-4B {pid} 학습 및 10개 평가 완료"
            body = f"""안녕하세요!
GrowPath Qwen3.5-4B {pid} 프리셋의 5에폭 학습 및 10개 고정 벤치마크 평가가 성공적으로 완료되었습니다.

■ 프리셋 완료 정보:
- 프리셋: {pid}
- 최종 에폭: {pdata.get('epochs', 5)}
- 최종 Train Loss: {pdata.get('train_loss', 'N/A')}
- 총 소요 시간: {pdata.get('runtime_seconds', 0)/60:.1f} 분

다음 프리셋 학습이 순차적으로 진행되고 있습니다.
전체 완료 시 Streamlit 시각화 대시보드 저장 및 인스턴스 자동 정지 처리가 진행됩니다."""
            send_email(subject, body)
            emailed.append(pid)
            sent_file.write_text(json.dumps(emailed, indent=2), encoding="utf-8")

    # 2. 1-hour summary report check
    handle_hourly_email(state)

    local_state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")
    return state


def print_summary(state):
    print("=" * 60)
    print("  Qwen3.5-4B B200 Realtime Presets Monitor")
    print("=" * 60)
    print(f"GPU Status (Util, VRAM, Total, Temp, Power): {state.get('gpu')}")
    print(f"Batch Controller: {'RUNNING' if state.get('is_batch_running') else 'STOPPED'}")
    curr_p = state.get("current_running_preset")
    print(f"Active Preset: {curr_p if curr_p else 'None'}")
    
    curr = state.get("current_status", {})
    if curr:
        step = curr.get("step", 0)
        total = curr.get("total_steps", 940)
        epoch = curr.get("epoch", 0.0)
        pct = (step / total) * 100 if total else 0
        mean_s = curr.get("steady_step_mean_seconds", 0.0)
        rem_s = curr.get("remaining_training_estimate_seconds", 0.0)
        print(f"Progress: Step {step}/{total} ({pct:.1f}%) | Epoch: {epoch:.3f} / 5.0")
        print(f"Measured Speed: {mean_s:.2f}s/step | Preset ETA: {rem_s/60:.1f} min")

    losses = state.get("recent_losses", [])
    if losses:
        print("\nRecent Steps:")
        for l in losses[-3:]:
            print(f"  {l}")

    completed = state.get("completed_presets", {})
    if completed:
        print("\nCompleted Presets:")
        for p, d in completed.items():
            print(f"  [+] {p}: Status={d.get('status')}, Epochs={d.get('epochs')}, Loss={d.get('train_loss')}")
    else:
        print("\nCompleted Presets: None yet (P01 in progress)")
    print("=" * 60)


def finalize_run(client: RunPodClient):
    print("[!] Finalizing run: packaging, stopping pod, sending final completion email...")
    pack_and_download_results(client)
    stop_resp = stop_remote_pod(client, "kq65qxmwibvy27")
    print("[+] RunPod stopped successfully:", stop_resp)

    # Mark all done so hourly emails permanently stop
    all_done_file = ROOT / "outputs" / "all_done.json"
    all_done_file.write_text(json.dumps({
        "completed_at": time.time(),
        "pod_stopped": True,
        "stop_response": stop_resp
    }, indent=2), encoding="utf-8")

    # Send final completion and pod stop email
    subject = "[GrowPath 최종완료] Qwen3.5-4B 전 프리셋 학습 완료 및 RunPod GPU 정지 완료"
    body = """안녕하세요!
Qwen3.5-4B 프리셋 P01부터 P06까지 모든 5에폭 학습과 10개 벤치마크 평가가 최종 완료되었습니다.

■ 최종 처리 내역:
1. P01~P06 가중치 및 평가 결과 패킹 및 로컬 회수 완료
2. 추가 과금 방지를 위한 RunPod B200 인스턴스 자동 정지 완료 (desiredStatus: EXITED)
3. 1시간 정기 요약 메일 발송 종료
4. 로컬 Streamlit 비교 대시보드(P01~P06 비교) 시각화 데이터 준비 완료

그동안 진행 상황을 확인해 주셔서 감사합니다.
로컬 환경에서 Streamlit 대시보드를 열어 최적의 가중치 결과를 확인하실 수 있습니다."""
    send_email(subject, body)
    print("[+] Final completion email sent to gom2553@naver.com.")


def main():
    parser = argparse.ArgumentParser(description="Watch & report RunPod presets")
    parser.add_argument("--check", action="store_true", help="One-shot check and print summary")
    parser.add_argument("--finalize", action="store_true", help="Pack, download, and stop pod")
    args = parser.parse_args()

    s = app_settings.read(ROOT)
    client = RunPodClient(s.get("RUNPOD_JUPYTER_URL"), s.get("RUNPOD_JUPYTER_TOKEN"))
    client.connect()

    try:
        if args.finalize:
            finalize_run(client)
            return

        state = check_and_update(client)
        print_summary(state)

        # Check if all 6 presets are completed
        completed = state.get("completed_presets", {})
        if len(completed) == 6 and not state.get("is_batch_running"):
            finalize_run(client)

    finally:
        if client.kernel_id:
            try:
                client.api("/api/kernels/" + client.kernel_id, method="DELETE")
            except Exception:
                pass


if __name__ == "__main__":
    main()
