"""Local Streamlit control and human evaluation for the sample factory."""
import hashlib
import json
import os
from pathlib import Path
import sys
from datetime import datetime, timezone, timedelta
import uuid

import streamlit as st
import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent))
import app_settings
import dashboard_auth
import recovery
from runpod_client import RunPodClient
from experiment_presets import PRESETS
import dashboard_store
import human_reports
import ai_evaluation
import importlib
# Streamlit reruns must use the matching helper code after a deployment.
importlib.reload(human_reports)
importlib.reload(ai_evaluation)

ROOT = Path(__file__).resolve().parents[1]
st.set_page_config(page_title="GrowPath · 실험실", layout="wide")
dashboard_auth.require_login(ROOT)
dashboard_store.hydrate(ROOT)

st.markdown("""
<style>
/* Use theme variables so labels stay readable in light and dark mode. */
[data-testid="stTextInput"] input,
[data-testid="stNumberInput"] input,
[data-testid="stTextArea"] textarea {
    border: 1px solid #718198 !important;
    border-radius: 8px !important;
}
[data-baseweb="select"] > div {
    border: 1px solid #718198 !important;
    border-radius: 8px !important;
    min-height: 46px;
}
[data-testid="stWidgetLabel"] p {font-weight: 650; margin-bottom: .35rem;}
[data-testid="stExpander"] {border: 1px solid #8793a5; border-radius: 10px;}
[data-testid="stForm"] {border: 2px solid #64748b; border-radius: 12px; padding: 1.3rem;}
[data-testid="stRadio"] [role="radiogroup"] {gap: .65rem; flex-wrap: wrap;}
[data-testid="stRadio"] [role="radiogroup"] label {
    border: 1px solid #718198; border-radius: 8px; padding: .55rem .9rem;
}
[data-testid="stRadio"] label:has(input:checked) {border: 2px solid #258459; background: rgba(37,132,89,.12);}
[data-testid="stMetric"] {border: 1px solid #8793a5; border-radius: 10px; padding: .85rem 1rem;}
.st-key-report_picker, .st-key-case_picker {border-left: 5px solid #5276c4 !important;}
.st-key-input_card {border: 1px solid #6689ca !important; border-top: 5px solid #5276c4 !important; background: rgba(82,118,196,.05);}
.st-key-answer_card {border: 1px solid #539682 !important; border-top: 5px solid #258459 !important; background: rgba(37,132,89,.05);}
.st-key-input_card h3, .st-key-answer_card h3 {padding-top: .2rem;}
[data-testid="stButton"] button, [data-testid="stDownloadButton"] button {border: 1px solid #718198;}
[data-testid="stTabs"] button[role="tab"] {padding: .6rem 1.1rem; font-weight: 650;}
[data-testid="stTabs"] button[aria-selected="true"] {border-radius: 8px 8px 0 0; background: rgba(82,118,196,.10);}
.block-container {max-width: 1440px; padding-top: 2rem;}
/* Keep the last rendered monitor readable during a remote refresh. */
.st-key-live_monitor [data-stale="true"] {opacity: 1 !important; transition: none !important; animation: none !important;}
[data-testid="stCaptionContainer"] {color: var(--text-color) !important; opacity: .85;}
[data-testid="stWidgetLabel"] p {font-size: 1rem !important; line-height: 1.6;}
[data-testid="stDataFrame"] {border: 1px solid #718198; border-radius: 10px; overflow: hidden;}
.st-key-report_library, .st-key-report_summary, .st-key-review_controls {
    border: 1px solid #718198 !important; border-radius: 14px; padding: 1.2rem !important;
    margin-bottom: 1.3rem;
}
.st-key-report_library {border-top: 5px solid #5276c4 !important;}
.st-key-report_summary {border-top: 5px solid #7d68ac !important;}
.st-key-review_controls {border-top: 5px solid #5276c4 !important;}
.st-key-report_library h3, .st-key-report_summary h2, .st-key-review_controls h3 {padding-top: 0;}
.st-key-review_controls [data-testid="stCheckbox"] {border: 1px solid #718198; border-radius: 8px; padding: .5rem .8rem;}
.st-key-input_card, .st-key-answer_card {padding: 1.2rem !important;}
[data-testid="stSelectbox"] {margin-bottom: .6rem;}
[data-testid="stForm"] {margin-top: 1.2rem; border-top: 5px solid #258459;}

</style>
""",unsafe_allow_html=True)

st.title("GrowPath · 실험실")
st.caption("설정·실행 요청·결과·평가는 이 대시보드에서, GPU 학습과 답변 생성은 RunPod에서 처리합니다.")



def refresh_view():
    from streamlit.errors import StreamlitInvalidLayoutContextError
    try:
        st.rerun(scope="fragment")
    except StreamlitInvalidLayoutContextError:
        # Widget events can also be replayed during a whole-app run.
        st.rerun()


def redact(text):
    text = app_settings.redact(ROOT,text)
    for key in ("HF_TOKEN", "DATABASE_URL", "RUNPOD_JUPYTER_TOKEN", "OPENAI_API_KEY"):
        value = os.getenv(key)
        if value:
            text = text.replace(value, "[비밀값 숨김]")
    for value in st.session_state.get("remote_secrets", {}).values():
        if value:
            text = text.replace(value, "[비밀값 숨김]")
    return text


def connection():
    client = st.session_state.get("client")
    if client is None:
        raise ValueError("왼쪽에서 RunPod에 연결하세요.")
    return client


def last_history():
    path=ROOT/"reports/control_history.json"
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {"jobs":[]}


def persist_history(overview):
    old=last_history()
    jobs={j["job_id"]:dict(j,stale=True) for j in old.get("jobs",[])}
    for item in overview["jobs"]:
        safe=json.loads(redact(json.dumps(item,ensure_ascii=False)))
        safe["stale"]=False
        jobs[item["job_id"]]=safe
    data={"last_sync":datetime.now(timezone.utc).isoformat(),"jobs":sorted(jobs.values(),key=lambda j:j["created_at"])}
    path=ROOT/"reports/control_history.json"
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_suffix(".tmp")
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    temporary.replace(path)
    dashboard_store.persist(ROOT,path)
    return data


def show_job_times(job):
    def fmt(value):
        return datetime.fromtimestamp(value,timezone(timedelta(hours=9))).strftime("%m-%d %H:%M:%S") if value else "—"
    st.caption(f"등록 {fmt(job.get('created_at'))} · 시작 {fmt(job.get('started_at'))} · 종료 {fmt(job.get('finished_at'))} (한국 시간)")




def concise_log(text):
    import re
    text=re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", text)
    lines=[line.strip() for line in text.replace("\r","\n").splitlines() if line.strip()]
    messages=[]
    latest_progress=None
    stages={"register":"실험 정보를 등록하고 있습니다.","train or resume":"모델 준비·학습을 진행하고 있습니다."}
    for line in lines:
        if "Loading weights:" in line:
            percent=re.search(r"(\d+)%",line)
            if percent:
                latest_progress="모델 불러오는 중 · "+percent.group(1)+"%"
            continue
        if line.startswith("진행 안내:"):
            messages.append(line.removeprefix("진행 안내:").strip())
            latest_progress=None
        elif line.startswith("PIPELINE: "):
            stage=line.removeprefix("PIPELINE: ")
            if stage in stages:
                messages.append(stages[stage])
            elif stage.startswith("compare"):
                match=re.search(r"epoch=(\d+) case=(\d+)",stage)
                if match:
                    messages.append(f"{match[1]}에포크 · 입력 {int(match[2])+1} 답변 생성 중")
            latest_progress=None
        elif line.startswith("PIPELINE COMPLETE"):
            messages.append("모든 작업 완료 · 보고서에서 답변을 평가할 수 있습니다.")
            latest_progress=None
        elif line.startswith("UPLOADED"):
            epoch=re.search(r"epoch=(\d+)",line)
            messages.append((epoch[1]+"에포크 " if epoch else "")+"가중치 업로드 완료")
        elif line.startswith("FINAL"):
            continue
        elif "eval_loss" in line or "train_loss" in line:
            messages.append("학습 지표 · "+line)
        elif re.search(r"(?:Error|Exception):|PIPELINE FAILED|CUDA out of memory",line):
            messages.append("오류 · "+line)
            latest_progress=None
        elif re.match(r"\d+%\|",line):
            percent=re.match(r"(\d+)%",line)
            latest_progress="현재 연산 진행률 · "+percent[1]+"%"
    unique=[]
    for line in messages:
        if not unique or unique[-1]!=line:
            unique.append(line)
    if latest_progress:
        unique.append(latest_progress)
    return unique[-5:]



def job_stage(job):
    text=job.get("log_tail","")
    current,next_step="작업 준비","실험 등록"
    # Stage comes from observed markers; the separate duration estimate is a user-facing reference.
    for line in text.replace("\r","\n").splitlines():
        if "PIPELINE: register" in line:
            current,next_step="실험 등록","모델 준비·학습"
        elif "PIPELINE: train or resume" in line:
            current,next_step="모델 준비·학습","가중치 저장·업로드"
        elif "Loading weights:" in line and "답변 생성" not in current:
            current,next_step="모델 불러오기","학습 진행"
        elif "BF16 MODEL READY" in line:
            current,next_step="BF16 모델 준비 완료","평가 입력 답변 생성"
        elif "UPLOADED epoch=4" in line:
            current,next_step="4에포크 저장·업로드 완료","5에포크 학습·저장"
        elif "UPLOADED epoch=5" in line:
            current,next_step="5에포크 저장·업로드 완료","평가 입력 답변 생성"
        elif "BF16 MODEL READY" in line or "BF16 BATCH COMPLETE" in line or "PIPELINE: compare" in line or ("진행 안내:" in line and "답변" in line):
            current,next_step="평가 입력 답변 생성","보고서 수신·사람 평가"
        elif "PIPELINE COMPLETE" in line:
            current,next_step="원격 작업 완료","보고서 수신·사람 평가"
    state=job.get("state")
    if state=="QUEUED":
        return "대기 중","앞선 작업 종료 후 실행"
    if state=="SUCCEEDED":
        return "완료","보고서에서 답변 평가" if job.get("kind") in ("experiment","continue_experiment") else "작업 결과 확인"
    if state in ("FAILED","INTERRUPTED"):
        return "실패" if state=="FAILED" else "중단","오류 확인 후 이어하기"
    if job.get("kind")=="evaluate_existing" and current in ("작업 준비","모델 준비·학습"):
        return "기존 가중치 BF16 평가 준비","답변 생성 · 재학습 없음"
    return current,next_step


def duration_text(seconds):
    seconds=max(0,int(seconds))
    hours,rest=divmod(seconds,3600)
    minutes,seconds=divmod(rest,60)
    return (f"{hours}시간 " if hours else "")+f"{minutes}분 {seconds:02d}초"



def measured_training_speed(text, expected_steps):
    import re,statistics
    samples=[]
    for line in text.replace("\r","\n").splitlines():
        if "Loading weights" in line:
            continue
        match=re.search(r"(\d+)%.*?\|\s*(\d+)/(\d+)\s*\[.*?,\s*([0-9.]+)s/it",line)
        if match and int(match[3])==expected_steps and int(match[2])>=2 and int(match[1])<100:
            samples.append(float(match[4]))
    return statistics.median(samples[-5:]) if samples else None


def show_measured_estimate(job,started,kst):
    import math
    with st.expander("3,000개 · 5에포크 학습 예상 · 실측 속도 기준",expanded=True):
        config=job.get("config")
        path=ROOT/config if config else None
        if not path or not path.is_file():
            st.caption("실행 설정을 확인할 수 없어 예상 시간을 계산하지 않았습니다.")
            return
        cfg=yaml.safe_load(path.read_text(encoding="utf-8-sig"))
        training=cfg["experiments"][0]["training"]
        effective=int(training["per_device_train_batch_size"])*int(training["gradient_accumulation_steps"])
        count=cfg["data"].get("expected_train_samples")
        if not count:
            train_path=ROOT/cfg["data"]["train_file"]
            count=sum(bool(x.strip()) for x in train_path.read_text(encoding="utf-8-sig").splitlines())
        steps=math.ceil(count/effective)*int(training["num_train_epochs"])
        speed=measured_training_speed(job.get("log_tail",""),steps)
        key="measured_speed_"+job["job_id"]
        if speed is not None:
            st.session_state[key]=speed
        speed=st.session_state.get(key)
        if speed is None:
            st.info("학습 속도 측정 중 · 학습 진행 로그가 쌓이면 예상 시간이 표시됩니다.")
            return
        target_steps=math.ceil(3000/effective)*5
        seconds=target_steps*speed
        st.metric("3,000개 · 5에포크 예상 학습 시간",duration_text(seconds))
        if started:
            end=datetime.fromtimestamp(started,kst)+timedelta(seconds=seconds)
            st.write("**같은 시작 시각에 3,000개로 학습했다면: "+end.strftime("%m/%d %H:%M")+" 학습 종료 예상**")
        st.caption(f"측정 {speed:.1f}초/스텝 × {target_steps:,}스텝 · GPU 1장 / 유효 배치 {effective}. 최근 최대 5개 학습 속도의 중앙값을 사용합니다.")
        st.caption("현재 샘플의 처리 속도를 실제 데이터에 적용한 참고값입니다. 실제 데이터 길이가 달라지면 달라집니다. 모델 로딩·검증·저장·답변 생성 시간은 제외하며, 전체 보고서 완료 시각으로 표시하지 않습니다.")



def completion_message(mine,all_cases,expected=0):
    if not all_cases or any(case not in mine for case in all_cases):
        return None
    average=sum(mine[case]["score"] for case in all_cases)/len(all_cases)
    if expected and len(all_cases)<expected:
        return f"현재 수신된 {len(all_cases)}개 답변 평가 완료 · 전체 {expected}개 중 나머지 답변 생성·수신 대기 · 내 평균 {average:.2f} / 5"
    return f"평가 완료 · {len(all_cases)}/{len(all_cases)}개 저장 완료 · 내 평균 {average:.2f} / 5"


def show_job_log(job):
    text=redact(job.get("log_tail",""))
    lines=concise_log(text)
    current,next_step=job_stage(job)
    started=job.get("started_at")
    finished=job.get("finished_at")
    observed=datetime.now(timezone.utc).timestamp()
    history_only=job.get("stale") or st.session_state.get("client") is None
    if history_only and not finished:
        synced=last_history().get("last_sync")
        observed=datetime.fromisoformat(synced).timestamp() if synced else started
    elapsed=duration_text((finished or observed)-started) if started and (finished or observed) else "시작 전"
    with st.container(border=True):
        cards=st.columns([1.2,1.5,1])
        cards[0].metric("현재 단계",current)
        cards[1].metric("다음 단계",next_step)
        cards[2].metric("총 소요 시간" if finished else "시작 후 경과",elapsed)
        if history_only and not finished:
            st.caption("마지막 동기화 시점 기준입니다. 연결하면 최신 진행 상황을 확인합니다.")
        timing=st.columns(2)
        kst=timezone(timedelta(hours=9))
        timing[0].metric("실제 시작 시각 · 한국 시간",datetime.fromtimestamp(started,kst).strftime("%m/%d %H:%M") if started else "시작 전")
        timing[1].metric("실제 종료 시각 · 한국 시간",datetime.fromtimestamp(finished,kst).strftime("%m/%d %H:%M") if finished else "진행 중" if started else "—")
        if job.get("kind") in ("experiment","continue_experiment"):
            show_measured_estimate(job,started,kst)

    with st.container(border=True):
        st.markdown("**실행 요약**")
        if lines:
            for line in lines:
                st.write("• "+line)
        else:
            st.caption("작업을 준비하고 있습니다. 새 로그가 들어오면 표시합니다.")
    with st.expander("원본 로그 · 문제 확인용",expanded=False):
        st.code(text or "아직 기록된 로그가 없습니다.",language="text",wrap_lines=True)


with st.sidebar:
    model_settings=yaml.safe_load((ROOT/"configs/hyperparameters.sample.pinned.yaml").read_text(encoding="utf-8-sig"))
    with st.container(border=True):
        st.caption("현재 모델 · 실행 설정 기준")
        st.markdown("**"+model_settings["model"]["base_model_id"]+"**")
        st.caption("학습: 4비트 QLoRA · 평가: 원본 BF16 + 어댑터")
    auto_ai=st.toggle("새 답변 전체 자동 AI 평가",value=True,key="auto_ai_evaluation")
    st.caption("입력·답변을 OpenAI API로 전송하며 호출 비용이 발생합니다. 이미 평가한 답변은 건너뜁니다.")
    st.header("RunPod 연결")
    settings_path = ROOT / "configs/local_connection.json"
    saved = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
    url = st.text_input("Jupyter 주소", app_settings.get(ROOT,"RUNPOD_JUPYTER_URL",saved.get("url", "https://wsmwv2tt9t8txp-8888.proxy.runpod.net")))
    token = st.text_input("Jupyter 토큰 또는 비밀번호", type="password", value=app_settings.get(ROOT,"RUNPOD_JUPYTER_TOKEN", ""))
    st.caption("RunPod의 JUPYTER_PASSWORD 또는 Jupyter 로그인에 쓴 값입니다. HF 토큰·RunPod API 키와 다릅니다.")
    remote = st.text_input("Jupyter 내 프로젝트 경로", app_settings.get(ROOT,"RUNPOD_REMOTE_PATH",saved.get("remote_path", "workspace/qwen_factory")))
    if st.button("연결", type="primary"):
        try:
            client = RunPodClient(url, token, remote)
            client.connect()
            for name in ("runpod_bridge.py", "control_pipeline.py", "compare_factory_sample.py"):
                client.contents("scripts/"+name, (ROOT / "scripts" / name).read_text(encoding="utf-8"))
            st.session_state.client = client
            st.session_state.pop("recovery_service_ready",None)
            settings_path.write_text(json.dumps({"url": client.url, "remote_path": remote}, indent=2), encoding="utf-8")
            st.success("연결 완료 · 토큰은 파일에 저장하지 않습니다.")
        except Exception as error:
            st.error(redact(str(error)))
    if st.session_state.get("client"):
        st.success("RunPod 제어 연결됨")
    with st.expander("HF·Neon 인증정보"):
        st.caption("아래 적용 버튼을 누르면 입력값을 HTTPS로 현재 RunPod 제어 커널에 전달합니다. 원격 파일에는 저장하지 않습니다.")
        hf = st.text_input("HF_TOKEN", type="password", value=app_settings.get(ROOT,"HF_TOKEN", ""))
        repo = st.text_input("HF_REPO_ID", value=app_settings.get(ROOT,"HF_REPO_ID", "Ssum-mer/qwen-factory-adapters"))
        database = st.text_input("DATABASE_URL", type="password", value=app_settings.get(ROOT,"DATABASE_URL", ""))
        if st.button("이 접속정보를 RunPod 세션에 적용"):
            try:
                if not all((hf, repo, database)):
                    raise ValueError("세 값을 모두 입력하세요.")
                values = {"HF_TOKEN": hf, "HF_REPO_ID": repo, "DATABASE_URL": database}
                connection().execute("import os\nos.environ.update(" + repr(values) + ")\n"
                    "os.environ['HF_HOME']='/workspace/qwen_factory/.cache/huggingface'\n"
                    "os.environ['PIP_CACHE_DIR']='/workspace/qwen_factory/.cache/pip'\n")
                st.session_state.remote_secrets = values
                st.session_state.pop("recovery_service_ready",None)
                st.success("적용 완료")
            except Exception as error:
                st.error(redact(str(error)))



def pull_reports(client, overview):
    count=0
    folder=ROOT/"reports/run_configs"
    folder.mkdir(parents=True,exist_ok=True)
    for run_id,text in overview.get("configurations",{}).items():
        uuid.UUID(run_id)
        path=folder/(run_id+".yaml")
        if not path.exists():
            path.write_text(text,encoding="utf-8")
        dashboard_store.persist(ROOT,path)
    # Keep the exact registered evaluation input locally for reproducible new-Pod restores.
    for text in overview.get("configurations",{}).values():
        cfg=yaml.safe_load(text)
        relative=cfg.get("data",{}).get("test_file")
        if relative:
            path=(ROOT/relative).resolve()
            path.relative_to((ROOT/"data/sample/eval").resolve())
            if not path.exists():
                snapshot=client.contents(relative)["content"]
                for line in snapshot.splitlines():
                    if line.strip():
                        json.loads(line)
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(snapshot,encoding="utf-8")
            dashboard_store.persist(ROOT,path)
    for relative in overview["reports"]:
        path=(ROOT/relative).resolve()
        path.relative_to((ROOT/"reports").resolve())
        if path.exists():
            continue
        text=client.contents(relative)["content"]
        json.loads(text)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text,encoding="utf-8")
        dashboard_store.persist(ROOT,path)
        count+=1
    return count


def publish(cfg):
    c=connection()
    for name in ("control_pipeline.py","compare_factory_sample.py","runpod_bridge.py"):
        c.contents("scripts/"+name,(ROOT/"scripts"/name).read_text(encoding="utf-8"))
    for field in ("train_file","validation_file"):
        path=(ROOT/cfg["data"][field]).resolve()
        path.relative_to((ROOT/"data/sample").resolve())
        text=path.read_text(encoding="utf-8-sig")
        destination="data/sample/processed/control_"+hashlib.sha256(text.encode()).hexdigest()[:20]+".jsonl"
        c.ensure_file(destination,text)
        cfg["data"][field]=destination
    test=cfg["data"].get("test_file","data/sample/eval/test.jsonl")
    test_path=(ROOT/test).resolve()
    test_path.relative_to((ROOT/"data").resolve())
    test_text=test_path.read_text(encoding="utf-8-sig")
    evaluation_rows=[json.loads(line) for line in test_text.splitlines() if line.strip()]
    if not evaluation_rows:
        raise ValueError("평가 입력 파일이 비어 있습니다.")
    for number,entry in enumerate(evaluation_rows,1):
        messages=entry.get("messages") if isinstance(entry,dict) else None
        if not isinstance(messages,list) or not messages:
            raise ValueError(f"평가 입력 {number}행에 messages 배열이 필요합니다.")
        if any(not isinstance(m,dict) or m.get("role") not in ("system","user","assistant") or not isinstance(m.get("content"),str) or not m["content"].strip() for m in messages):
            raise ValueError(f"평가 입력 {number}행의 role/content를 확인하세요.")
        prompt=messages[:-1] if messages[-1]["role"]=="assistant" else messages
        if not prompt or prompt[-1]["role"]!="user":
            raise ValueError(f"평가 입력 {number}행은 user 요청으로 끝나야 합니다.")
    test_snapshot="data/sample/eval/control_"+hashlib.sha256(test_text.encode()).hexdigest()[:20]+".jsonl"
    local_snapshot=ROOT/test_snapshot
    local_snapshot.parent.mkdir(parents=True,exist_ok=True)
    local_snapshot.write_text(test_text,encoding="utf-8")
    c.ensure_file(test_snapshot,test_text)
    cfg["data"]["test_file"]=test_snapshot
    payload=yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False)
    name="configs/control_"+hashlib.sha256(payload.encode()).hexdigest()[:20]+".yaml"
    (ROOT/name).write_text(payload,encoding="utf-8")
    c.ensure_file(name,payload)
    return name


experiment_tab, guide_tab, review_tab, setup_tab=st.tabs(["파라미터·실험 대기열","파라미터 설명","보고서 평가","최초 연결·새 Pod 안내"])
with experiment_tab:
    st.subheader("파라미터를 바꾸고 실험을 등록하세요")
    st.caption("등록 → 5에포크 학습 또는 재개 → 4·5에포크 저장·업로드 → 같은 평가 입력으로 답변 생성 → 보고서 저장까지 자동 진행합니다.")
    st.info("현재 학습/검증 데이터는 가상 샘플 54/3개입니다. 평가 입력은 아래 파일에서 선택합니다. 본 데이터 학습은 별도 준비가 필요합니다.")
    options=[("P00","커스텀",{},"기준 권장값에서 시작해 아래 파라미터를 직접 수정하세요.")]+PRESETS
    preset=st.selectbox("파라미터 프리셋",range(len(options)),index=1,format_func=lambda i:options[i][0]+" "+options[i][1])
    pid,pname,changes,reason=options[preset]
    st.caption(reason)
    base=yaml.safe_load((ROOT/"configs/hyperparameters.sample.pinned.yaml").read_text(encoding="utf-8-sig"))
    recipe=base["experiments"][0]
    with st.expander("현재 데이터 위치"):
        st.caption("현재 실행은 아래 샘플 파일을 사용합니다. 본 데이터 원본은 data/raw/dataset.jsonl이며 아직 이 시험 학습기에 연결되지 않았습니다.")
        st.dataframe([
            {"구분":"학습", "로컬 파일":str(ROOT/base["data"]["train_file"])},
            {"구분":"검증", "로컬 파일":str(ROOT/base["data"]["validation_file"])},
            {"구분":"평가 입력", "로컬 파일":"아래 평가 입력 파일 선택 항목 참조"},
        ],hide_index=True)
    defaults={**recipe["training"],**recipe["lora"],**changes}
    evaluation_files=["data/sample/eval/test.jsonl"]+[p.relative_to(ROOT).as_posix() for p in sorted((ROOT/"data/eval").glob("*.jsonl"))]
    default_eval="data/eval/prompts.jsonl"
    evaluation_file=st.selectbox("평가 입력 파일",evaluation_files,index=evaluation_files.index(default_eval) if default_eval in evaluation_files else 0)
    try:
        evaluation_count=sum(bool(line.strip()) for line in (ROOT/evaluation_file).read_text(encoding="utf-8-sig").splitlines())
        st.caption(f"{evaluation_count}개 입력 · 각 입력에 대한 답변을 생성하고 종합 1~5점으로 평가합니다.")
    except OSError:
        st.error("평가 입력 파일을 읽을 수 없습니다.")
    with st.form("parameters_"+pid):
        label=st.text_input("실험 이름",value=pid+" "+pname)
        a,b,c=st.columns(3)
        with a:
            lr_options=[1e-4,7.5e-5,5e-5,2.5e-5,1.5e-4,2e-4,None]
            lr_choice=st.selectbox("학습률",lr_options,index=lr_options.index(float(defaults["learning_rate"])),
                format_func=lambda v:"직접 입력값 사용" if v is None else f"{v:.6f} ({v:.1e})")
            with st.expander("학습률 직접 입력"):
                custom_lr=st.number_input("직접 입력할 학습률",min_value=0.000001,max_value=0.01,
                    value=float(defaults["learning_rate"]),step=0.000025,format="%.6f")
            lr=custom_lr if lr_choice is None else lr_choice
            rank=st.selectbox("LoRA r",[8,16,32,64,128],index=[8,16,32,64,128].index(defaults["r"]))
            alpha=st.number_input("LoRA alpha",min_value=1,value=int(defaults["lora_alpha"]),step=8)
            dropout=st.number_input("LoRA dropout",min_value=0.0,max_value=0.5,value=float(defaults["lora_dropout"]),step=0.05)
        with b:
            batch=st.number_input("GPU 배치 크기",min_value=1,max_value=16,value=int(defaults["per_device_train_batch_size"]))
            accumulation=st.number_input("그래디언트 누적",min_value=1,max_value=256,value=int(defaults["gradient_accumulation_steps"]))
            length=st.selectbox("최대 토큰 길이",[1024,2048,4096,8192],index=[1024,2048,4096,8192].index(defaults["max_length"]))
            decay=st.number_input("가중치 감쇠",min_value=0.0,max_value=1.0,value=float(defaults["weight_decay"]),step=0.01)
        with c:
            warmup=st.number_input("워밍업 비율",min_value=0.0,max_value=0.9,value=float(defaults["warmup_ratio"]),step=0.05)
            scheduler=st.selectbox("학습률 스케줄",["cosine","linear","constant"],index=["cosine","linear","constant"].index(defaults["lr_scheduler_type"]))
            seed=st.number_input("시드",min_value=0,value=int(defaults["seed"]))
            priority=st.selectbox("대기열 우선순위",[10,0,20],format_func=lambda v:{0:"높음",10:"보통",20:"낮음"}[v])
        st.caption("총 5에포크 · 4/5에포크 저장 · NF4/BF16 · 언어 모델 Linear 계층. 높은 우선순위도 현재 실행 중인 작업을 중단하지 않습니다.")
        start=st.form_submit_button("실험 등록 · 실행 중이면 다음 순서로",type="primary")
    if start:
        try:
            base["data"]["test_file"]=evaluation_file
            recipe["recipe_name"]=label
            recipe["lora"].update(r=int(rank),lora_alpha=int(alpha),lora_dropout=float(dropout))
            recipe["training"].update(learning_rate=float(lr),per_device_train_batch_size=int(batch),
                gradient_accumulation_steps=int(accumulation),max_length=int(length),weight_decay=float(decay),
                warmup_ratio=float(warmup),lr_scheduler_type=scheduler,seed=int(seed),data_seed=int(seed))
            name=publish(base)
            job=connection().call("runpod_bridge.submit('experiment', config="+repr(name)+", priority="+str(priority)+", label="+repr(label)+")")
            st.success("대기열에 등록했습니다: "+job["job_id"])
        except Exception as error:
            st.error(redact(str(error)))

    refresh_controls=st.columns([2,3])
    with refresh_controls[0]:
        auto_refresh=st.toggle("실행 현황 자동 갱신",value=True,key="monitor_auto_refresh")
    with refresh_controls[1]:
        st.caption("30초 간격 · 끄면 화면이 고정됩니다. 원격 작업은 계속 실행됩니다.")

    @st.fragment(run_every="30s" if auto_refresh else None)
    def monitor():
        dashboard_auth.checkpoint(ROOT)
        st.subheader("실행·대기 순서")
        st.button("지금 갱신",key="monitor_refresh_now")
        history=last_history()
        online=False
        try:
            if not st.session_state.get("client"):
                recovery.reconnect(ROOT,st.session_state)
            if st.session_state.get("recovery_notice"):
                st.caption(st.session_state.recovery_notice)
            if st.session_state.get("client"):
                try:
                    try:
                        recovery.ensure_service(ROOT,st.session_state,auto_ai)
                        st.caption("RunPod 자동 수집·AI 평가 복구 서비스 연결됨")
                    except Exception as service_error:
                        st.warning("독립 복구 서비스를 시작하지 못했습니다. "+redact(str(service_error)))
                    data=connection().call("runpod_bridge.overview()")
                    history=persist_history(data)
                    online=True
                    pull_reports(connection(),data)
                    if auto_ai:
                        ai_evaluation.ensure_worker(ROOT)
                except Exception as error:
                    st.session_state.pop("recovery_service_ready",None)
                    recovery.reconnect(ROOT,st.session_state)
                    st.warning("현재 상태를 확인하지 못했습니다. "+redact(str(error)))
            if not online:
                st.info("마지막으로 저장한 기록입니다. 연결하면 실제 최신 진행 상태를 확인합니다.")
            if history.get("last_sync"):
                st.caption("마지막 동기화: "+datetime.fromisoformat(history["last_sync"]).astimezone(timezone(timedelta(hours=9))).strftime("%Y-%m-%d %H:%M:%S KST"))
            jobs=history["jobs"]
            running=[j for j in jobs if j["state"]=="RUNNING" and not j.get("stale")]
            queued=sorted([j for j in jobs if j["state"]=="QUEUED" and not j.get("stale")],key=lambda j:(j.get("priority",10),j["created_at"],j["job_id"]))
            for job in running:
                st.success(("실행 중 · " if online else "마지막 확인: 실행 중 · ")+job.get("label",job["job_id"]))
                show_job_times(job)
                show_job_log(job)
            if not running:
                st.caption("실행 중인 작업 없음" if online else "현재 실행 여부는 재연결 후 확인됩니다.")
            for index,job in enumerate(queued,1):
                row=st.columns([5,2,2])
                row[0].write(f"{index}. {job.get('label') or job['job_id']} · 우선순위 {job.get('priority',10)}")
                if row[1].button("다음 실행으로",key="next_"+job["job_id"],disabled=not online):
                    connection().call("runpod_bridge.promote("+repr(job["job_id"])+")")
                    refresh_view()
                new_priority=row[2].number_input("우선순위",value=int(job.get("priority",10)),key="priority_"+job["job_id"]+"_"+str(job.get("priority",10)),disabled=not online)
                if new_priority!=job.get("priority",10):
                    connection().call("runpod_bridge.promote("+repr(job["job_id"])+", priority="+str(int(new_priority))+")")
                    refresh_view()
            finished=[j for j in jobs if j["state"] not in ("RUNNING","QUEUED") or j.get("stale")]
            show_all=st.checkbox("지난 실험 전체 보기",value=False)
            for job in reversed(finished if show_all else finished[-10:]):
                state=("이전 연결의 마지막 확인: " if job.get("stale") else "")+{"SUCCEEDED":"완료","FAILED":"실패","INTERRUPTED":"중단"}.get(job["state"],job["state"])
                with st.expander(state+" · "+(job.get("label") or job["job_id"])):
                    show_job_times(job)
                    show_job_log(job)
                    if job["state"] in ("FAILED","INTERRUPTED") and job["kind"] in ("experiment","continue_experiment","evaluate_existing"):
                        st.caption("같은 설정과 원격 실험 파일로 재개합니다. 원래 실행 폴더가 없으면 새로 학습하지 않고 중단합니다.")
                        if st.button("BF16 평가 이어하기" if job["kind"]=="evaluate_existing" else "이 실험 이어하기",key="resume_"+job["job_id"],disabled=not online or job.get("stale",False)):
                            config=job.get("config")
                            if not config:
                                config=job["argv"][job["argv"].index("--config")+1]
                            resume_kind="evaluate_existing" if job["kind"]=="evaluate_existing" else "continue_experiment"
                            connection().call("runpod_bridge.submit("+repr(resume_kind)+", config="+repr(config)
                                +", priority="+str(job.get("priority",10))+", label="+repr((job.get("label") or job["job_id"])+" · 이어하기")+")")
                            st.success("재개 요청을 대기열에 등록했습니다.")
                            refresh_view()
        except Exception as error:
            st.warning(redact(str(error)))
    with st.container(key="live_monitor"):
        monitor()


def parse_payload(text):
    text=text.strip()
    if text.startswith("```") and "\n" in text:
        text=text.split("\n",1)[1].rsplit("```",1)[0].strip()
    try:
        return json.loads(text)
    except (ValueError,TypeError):
        return None


def case_request(report):
    users=[m["content"] for m in report["messages"] if m["role"]=="user"]
    text=users[-1] if users else ""
    parsed=parse_payload(text)
    return parsed if isinstance(parsed,dict) else {},text


def show_input(report):
    request,text=case_request(report)
    st.subheader("입력")
    if not request:
        st.text(text)
        return
    st.caption("목표")
    st.write(request.get("goal",request.get("change_request",request.get("request","입력 내용 확인"))))
    if request.get("current_level"):
        st.caption("현재 수준")
        st.write(request["current_level"])
    metrics=st.columns(3)
    metrics[0].metric("기간",str(request.get("duration_weeks","—"))+"주")
    metrics[1].metric("주당 시간",str(request.get("weekly_hours","—"))+"시간")
    budget=request.get("budget_krw")
    metrics[2].metric("예산",f"{budget:,}원" if isinstance(budget,(int,float)) else "—")
    if request.get("perspective"):
        st.info("관점 · "+str(request["perspective"]))
    for field in ("change_request","modification_request","revision_request","changes"):
        if request.get(field):
            st.caption("수정 요청")
            st.write(request[field])
    for field,label in (("profile","직무·경험"),("self_check","사전 자기점검 · 품질 점수와 별개"),("start_stage","선택한 시작 단계"),("preserve_constraints","유지 조건"),("manager_comment","부서장 코멘트"),("employee_requested_changes","직원이 반영 요청한 항목"),("completed_stages","완료 단계"),("existing_roadmap","수정 전 로드맵")):
        if field in request:
            with st.expander(label,expanded=field in ("preserve_constraints","employee_requested_changes")):
                st.write(request[field])
    resources=request.get("resources",[])
    if resources:
        st.caption("제공된 자료")
        for resource in resources:
            if isinstance(resource,dict):
                st.write(str(resource.get("resource_id",""))+" · "+str(resource.get("title","")))
    with st.expander("전체 입력 · 이전 대화"):
        st.json(report["messages"])


def show_answer(item):
    if item["hit_token_limit"]:
        st.warning("생성 길이 제한에 도달했습니다. 답변이 잘렸는지 확인하세요.")
    answer=parse_payload(item["text"])
    if isinstance(answer,dict):
        roadmap=answer.get("roadmap",answer)
    else:
        roadmap=None
    if not isinstance(roadmap,dict) or not isinstance(roadmap.get("stages"),list):
        st.text(item["text"])
        return
    for index,stage in enumerate(roadmap["stages"],1):
        if not isinstance(stage,dict):
            st.write(stage)
            continue
        with st.container(border=True):
            st.markdown("#### "+str(index)+" · "+str(stage.get("name",stage.get("title","단계"))))
            st.caption(" · ".join(str(v) for v in [
                str(stage.get("hours","—"))+"시간",
                str(stage.get("cost_krw",0))+"원",
            ]))
            activity=stage.get("activity",stage.get("description",stage.get("goal","")))
            if activity:
                st.write(activity)
            if stage.get("deliverable"):
                st.caption("결과물")
                st.write(stage["deliverable"])
            criterion=stage.get("completion_criterion",stage.get("check"))
            if criterion:
                st.caption("완료 기준")
                st.write(criterion)
            resources=stage.get("resource_ids",stage.get("resources",[]))
            if resources:
                st.caption("자료 · "+", ".join(map(str,resources)))
    totals=st.columns(2)
    totals[0].metric("총시간",str(roadmap.get("total_hours","—"))+"시간")
    totals[1].metric("총비용",str(roadmap.get("total_cost_krw","—"))+"원")
    with st.expander("원문 보기"):
        st.code(item["text"],language="json",wrap_lines=True)


with review_tab:
    @st.fragment
    def review():
        dashboard_auth.checkpoint(ROOT)
        precision_view=st.selectbox("평가 결과 유형",["최신 결과","BF16 결과","4비트 시험 결과"],key="precision_view")
        groups=human_reports.catalog(ROOT,{"BF16 결과":"bf16","4비트 시험 결과":"4bit"}.get(precision_view))
        st.subheader("실험 보고서 · 입력별 휴먼 평가")
        st.caption("입력 하나당 종합 1~5점. 평가한 입력들의 평균이 보고서 제목에 반영됩니다. 평가 중 자동 새로고침은 하지 않습니다.")
        if st.button("새 보고서 확인"):
            refresh_view()
        if not groups:
            st.info("답변 생성이 끝나면 이 목록에서 평가합니다.")
            return
        records=[]
        names={}
        for weight,group in groups.items():
            m=group["manifest"]
            config=ROOT/"reports/run_configs"/(m["run_id"]+".yaml")
            cfg=yaml.safe_load(config.read_text(encoding="utf-8")) if config.exists() else {}
            recipe=cfg.get("experiments",[{}])[0]
            names[weight]=recipe.get("recipe_name",m["run_id"][:8])
            summary=human_reports.case_summary(ROOT,weight,group)
            ai_summary=ai_evaluation.group_summary(ROOT,weight,group)
            records.append({"보고서":human_reports.title(ROOT,weight,group),"실험":names[weight],
                "모델":m["model"]["base_model_id"],"에포크":m["trained_epoch"],
                "학습률":recipe.get("training",{}).get("learning_rate"),"LoRA r":recipe.get("lora",{}).get("r"),
                "생성된 답변":summary["total"],"사람 평가":f"{summary['rated']}/{summary['total']}","사람 평균":round(summary["average"],2) if summary["average"] is not None else None,"AI 평가":f"{ai_summary['rated']}/{ai_summary['total']}","AI 평균":round(ai_summary["average"],2) if ai_summary["average"] is not None else None,"가중치 ID":weight})
        with st.container(border=True,key="report_library"):
            st.subheader("① 보고서 목록")
            query=st.text_input("실험 검색",placeholder="실험명, 모델, 버전, 가중치 ID")
            filtered=[row for row in records if query.lower() in " ".join(map(str,row.values())).lower()]
            st.dataframe([{k:v for k,v in row.items() if k!="가중치 ID"} for row in filtered],hide_index=True,width="stretch")
            if not filtered:
                st.info("검색 결과가 없습니다.")
                return
            weights=sorted([row["가중치 ID"] for row in filtered],
                key=lambda w:max(r[1]["created_at"] for r in groups[w]["cases"].values()),reverse=True)
            with st.container(border=True,key="report_picker"):
                weight=st.selectbox("열어볼 보고서",weights,format_func=lambda w:
                    human_reports.title(ROOT,w,groups[w])+" · "+names[w]+f" · {groups[w]['manifest']['trained_epoch']}에포크 · 답변 {len(groups[w]['cases'])}개", key="report_picker_newest_v2")
        group=groups[weight]
        manifest=group["manifest"]
        summary=human_reports.case_summary(ROOT,weight,group)
        heading=human_reports.title(ROOT,weight,group)
        notice=st.session_state.pop("rating_notice_"+weight,None)
        if notice:
            st.success(notice)
        with st.expander("기존 가중치로 BF16 평가 실행 · 재학습 없음"):
            st.caption("저장된 4·5에포크 가중치로 원본 BF16 답변을 생성합니다. 에포크마다 모델을 한 번만 불러옵니다. GPU 비용이 발생합니다.")
            if st.button("기존 가중치 BF16 답변 생성",key="bf16_existing_"+manifest["run_id"]):
                try:
                    c=connection()
                    for name in ("control_pipeline.py","compare_factory_sample.py","runpod_bridge.py"):
                        c.contents("scripts/"+name,(ROOT/"scripts"/name).read_text(encoding="utf-8"))
                    cfg_path=ROOT/"reports/run_configs"/(manifest["run_id"]+".yaml")
                    config_name="configs/control_bf16_"+manifest["run_id"]+".yaml"
                    c.ensure_file(config_name,cfg_path.read_text(encoding="utf-8"))
                    job=c.call("runpod_bridge.submit('evaluate_existing', config="+repr(config_name)+", label='BF16 기존 가중치 평가 · 재학습 없음')")
                    st.success("BF16 평가 등록 완료 · "+job["job_id"])
                except Exception as error:
                    st.error(redact(str(error)))
        latest_report=max(row[1]["created_at"] for row in group["cases"].values())
        st.caption("실행 ID: "+manifest["run_id"][:8]+" · 마지막 답변 생성: "+datetime.fromisoformat(latest_report).astimezone(timezone(timedelta(hours=9))).strftime("%m/%d %H:%M 한국 시간"))
        expected=max((row[1].get("evaluation_total",0) for row in group["cases"].values()),default=0)
        if expected and summary["total"]<expected:
            st.info(f"답변 생성·수신 중: {summary['total']}/{expected}개. 아직 모든 입력의 답변이 들어오지 않았습니다.")
        elif summary["total"]==1:
            st.info("이 보고서에는 생성된 답변이 1개만 있습니다. 위 보고서 목록에서 새 실행의 보고서를 선택하세요. ‘새 보고서 확인’은 로컬로 수신된 최신 결과를 다시 읽습니다.")

        precision=next(iter(group["cases"].values()))[1].get("quantization",{})
        st.info("이 보고서 평가 모델: "+("4비트 기본 모델 + 어댑터 · 이전 평가" if precision.get("load_in_4bit") else "원본 BF16 기본 모델 + 어댑터" if precision.get("dtype")=="bfloat16" else "정밀도 정보 확인 필요"))
        with st.container(border=True,key="report_summary"):
            st.caption("선택한 보고서")
            st.markdown("## "+heading)
            st.caption(manifest["model"]["base_model_id"]+f" · {manifest['trained_epoch']}에포크 · "+names[weight])
            ai_summary=ai_evaluation.group_summary(ROOT,weight,group)
            metrics=st.columns(4)
            metrics[0].metric("수신된 입력·답변",f"{summary['total']} / {expected}" if expected else summary["total"])
            metrics[1].metric("사람 평가 완료",f"{summary['rated']} / {summary['total']}")
            metrics[2].metric("사람 평균",f"{summary['average']:.2f} / 5" if summary["average"] is not None else "평가 대기")
            metrics[3].metric("AI 평균",f"{ai_summary['average']:.2f} / 5" if ai_summary["average"] is not None else "평가 대기")
            st.progress(summary["rated"]/summary["total"] if summary["total"] else 0)
            if summary["rated"]<summary["total"] and summary["rated"]:
                st.caption("현재는 평가한 입력만 반영한 임시 평균입니다.")
            with st.expander("모델·학습 파라미터"):
                config=ROOT/"reports/run_configs"/(manifest["run_id"]+".yaml")
                if config.exists():
                    cfg=yaml.safe_load(config.read_text(encoding="utf-8"))
                    recipe=cfg["experiments"][0]
                    st.dataframe([{"항목":k,"값":str(v)} for k,v in {**recipe["lora"],**recipe["training"]}.items()],hide_index=True)
                st.caption("weight_id: "+weight)
        @st.fragment(run_every="15s")
        def show_ai_summary():
            dashboard_auth.checkpoint(ROOT)
            with st.container(border=True,key="ai_report_summary"):
                st.subheader("AI 보조 평가 결과 · OpenAI")
                _,judge_model=ai_evaluation.settings(ROOT)
                ai_entries=[]
                for case_number,(_,case_report) in sorted(group["cases"].items()):
                    entry=ai_evaluation.latest(ROOT,weight,case_report,judge_model)
                    if entry:
                        ai_entries.append(entry)
                values=[entry["average"] for entry in ai_entries if entry["average"] is not None]
                human_live=human_reports.case_summary(ROOT,weight,group)
                ai_metrics=st.columns(3)
                ai_metrics[0].metric("AI 평가 완료",f"{len(ai_entries)} / {len(group['cases'])}")
                ai_metrics[1].metric("사람 평균",f"{human_live['average']:.2f} / 5" if human_live["average"] is not None else "평가 전")
                ai_metrics[2].metric("AI 평균 · 사람 점수와 별개",f"{sum(values)/len(values):.2f} / 5" if values else "평가 전")
                st.caption("평가 모델: "+judge_model+" · 새 답변 전체를 자동 평가합니다. 기존 결과는 재사용하며 사람 점수와 별도로 저장합니다.")
                states=ai_evaluation.queue_states(ROOT,weight,group)
                failed=[(case,state[1]) for case,state in states.items() if state[0]=="FAILED"]
                processing=sum(state[0]=="RUNNING" for state in states.values())
                waiting=sum(state[0]=="PENDING" for state in states.values())
                st.progress(len(ai_entries)/len(group["cases"]) if group["cases"] else 0)
                st.caption(f"평가 중 {processing}개 · 대기 {waiting}개 · 실패 {len(failed)}개")
                if failed:
                    st.warning("실패한 입력: "+", ".join(str(case+1) for case,_ in failed))
                    if st.button("실패한 AI 평가만 재시도",key="retry_ai_"+weight):
                        ai_evaluation.retry_failed(ROOT,weight,group)
                        ai_evaluation.ensure_worker(ROOT)
                if st.button("AI 평가 결과 갱신",key="refresh_ai_"+weight):
                    refresh_view()
                if ai_entries:
                    st.dataframe([{"입력":e["case_index"]+1,"AI 평균":round(e["average"],2) if e["average"] is not None else None,"요약":e["review"]["summary"]} for e in ai_entries],hide_index=True,width="stretch")
                else:
                    st.info("현재 보고서의 입력·답변·평가 모델에 맞는 AI 평가 결과가 아직 없습니다.")
        show_ai_summary()
        st.divider()
        with st.container(border=True,key="review_controls"):
            st.subheader("② 평가할 입력 고르기")
            controls=st.columns([2,1],gap="large",vertical_alignment="bottom")
            with controls[0]:
                evaluator=st.text_input("평가자",value="나",key="case_evaluator").strip()
            with controls[1]:
                only_unrated=st.checkbox("미평가 입력만 보기",key="unrated_"+weight)
        entries=human_reports.case_ratings(ROOT,weight,group,evaluator)
        mine={entry["case_index"]:entry for entry in entries}
        all_cases=sorted(group["cases"])
        cases=[case for case in all_cases if not only_unrated or case not in mine]
        if not cases:
            st.success("이 평가자의 모든 입력 평가가 끝났습니다. AI 보조 평가·재검토가 가능하도록 기존 입력을 표시합니다.")
            cases=all_cases
        selection="case_selection_"+weight
        pending=st.session_state.pop("next_case_"+weight,None)
        if pending in cases:
            st.session_state[selection]=pending
        if st.session_state.get(selection) not in cases:
            st.session_state[selection]=cases[0]
        def case_label(case):
            request,_=case_request(group["cases"][case][1])
            goal=str(request.get("goal",request.get("task","입력")))
            score=f"{mine[case]['score']}점" if case in mine else "미평가"
            return f"{all_cases.index(case)+1:02d} · {score} · {goal[:65]}"
        with st.container(border=True,key="case_picker"):
            case=st.selectbox("평가할 입력",cases,format_func=case_label,key=selection)
            row=st.columns([1,4,1])
            position=cases.index(case)
            if row[0].button("← 이전",disabled=position==0,key="previous_"+weight):
                st.session_state["next_case_"+weight]=cases[position-1]
                refresh_view()
            row[1].caption(f"입력 {all_cases.index(case)+1} / {len(all_cases)}")
            if row[2].button("다음 →",disabled=position==len(cases)-1,key="next_"+weight):
                st.session_state["next_case_"+weight]=cases[position+1]
                refresh_view()
        path,report=group["cases"][case]
        st.markdown("### ③ 입력과 모델 답변 확인")
        left,right=st.columns([.9,1.3],gap="large")
        with left:
            with st.container(border=True,key="input_card"):
                show_input(report)
        with right:
            with st.container(border=True,key="answer_card"):
                st.subheader("모델 답변")
                show_answer(report["tuned"])
        with st.expander("기본 모델 답변과 비교"):
            if report.get("base_reused"):
                st.caption("같은 BF16 모델·입력·생성 조건·토크나이저로 이미 생성한 기본 답변입니다. 생성 시간은 최초 생성 때의 기록입니다.")
            show_answer(report["base"])
        human_tab,ai_tab=st.tabs(["사람 평가","AI 보조 평가 · OpenAI"])
        with human_tab:
            previous=mine.get(case,{})
            sig=human_reports.case_signature(report)
            with st.form("case_rating_"+weight+"_"+str(case)+"_"+sig[:8]+"_"+hashlib.sha256(evaluator.encode()).hexdigest()[:8]):
                st.markdown("### ④ 이 답변 평가")
                st.caption(f"입력 {all_cases.index(case)+1} / {len(all_cases)} · 선택한 모델 답변에 대한 종합 점수를 저장합니다.")
                choices=[None,1,2,3,4,5]
                score=st.radio("종합 점수",choices,index=choices.index(previous.get("score")),horizontal=True,
                    format_func=lambda v:"미평가" if v is None else str(v)+"점")
                note=st.text_area("의견 · 선택 사항",value=previous.get("note",""))
                a,b=st.columns(2)
                save=a.form_submit_button("점수 저장")
                other_unrated=[c for c in all_cases if c!=case and c not in mine]
                advance_label="저장하고 다음 미평가 입력" if other_unrated else ("저장하고 나머지 답변 대기" if expected>len(all_cases) else "저장하고 평가 완료")
                advance=b.form_submit_button(advance_label,type="primary")
            if save or advance:
                try:
                    human_reports.save_case_rating(ROOT,weight,group,case,evaluator,score,note)
                    if advance:
                        remaining=[c for c in all_cases if c!=case and c not in mine]
                        if remaining:
                            following=[c for c in remaining if c>case]
                            target=following[0] if following else remaining[0]
                            st.session_state["next_case_"+weight]=target
                            st.session_state["rating_notice_"+weight]=f"점수 저장 완료 · 다음 미평가 입력 {all_cases.index(target)+1}번으로 이동했습니다."
                        else:
                            st.session_state["rating_notice_"+weight]="점수 저장 완료 · 이 보고서에서 현재 수신된 답변의 평가가 모두 끝났습니다. 다음 입력이 없어 이동하지 않았습니다. 다른 보고서를 선택하거나 새 답변 수신 후 확인하세요."
                    else:
                        st.session_state["rating_notice_"+weight]="점수를 저장했습니다."
                    refresh_view()
                except ValueError as error:
                    st.error(str(error))
            completed=completion_message(mine,all_cases,expected)
            if completed:
                st.success("✓ "+completed)
                st.caption("점수는 저장되어 있습니다. 다른 보고서를 선택하거나 AI 보조 평가를 진행할 수 있습니다.")
                st.download_button("평가 완료 보고서 다운로드",human_reports.render(ROOT,weight,group),file_name=heading+".md",mime="text/markdown",key="completed_export_"+weight)
        with ai_tab:
            ai_evaluation.render_panel(ROOT,weight,group,case)
        with st.expander("입력별 평가 목록 · 내보내기"):
            st.dataframe([{"입력":c+1,"내 점수":mine.get(c,{}).get("score"),"의견":mine.get(c,{}).get("note","")} for c in all_cases],hide_index=True)
            st.download_button("이 보고서 Markdown",human_reports.render(ROOT,weight,group),file_name=heading+".md",mime="text/markdown",key="export_"+weight)
            import csv,io
            stream=io.StringIO()
            writer=csv.DictWriter(stream,fieldnames=list(records[0]))
            writer.writeheader()
            writer.writerows(records)
            st.download_button("전체 실험 목록 CSV",stream.getvalue().encode("utf-8-sig"),file_name="GrowPath_experiments.csv",mime="text/csv")
    review()


with guide_tab:
    st.subheader("파라미터 설명 · 설정할 때 참고하세요")
    st.caption("현재 실행 기준과 상세 설명을 함께 확인할 수 있습니다. 설명을 읽어도 실행 설정은 바뀌지 않습니다.")
    with st.container(border=True):
        st.markdown("#### 현재 샘플 실험 기준")
        st.write("학습률 0.0001 · LoRA r 32 / alpha 64 · dropout 0.05")
        st.write("배치 1 × 누적 16 = 유효 배치 16 (GPU 1장) · 최대 길이 2048")
        st.write("총 5에포크 / 4·5에포크 저장 · warmup 0.05 · cosine")
        st.caption("P00 커스텀이나 다른 프리셋을 고르면 설정이 달라집니다. 실제 등록값은 파라미터 화면과 해당 보고서에서 확인하세요.")
    st.info("아래는 제공한 설명 문서입니다. 문서의 5,184개 데이터·3에포크·배치 2·warmup 0.06은 현재 샘플 실행값과 다릅니다. 성공률·메모리·속도 수치와 특정 값에서의 실패 단정은 검증된 측정 결과로 취급하지 마세요.")
    guide_path=ROOT/"docs/hyperparameters.html"
    if guide_path.exists():
        guide_html=guide_path.read_text(encoding="utf-8")
        st.download_button("설명 문서 HTML 다운로드",guide_html,file_name="hyperparameters.html",mime="text/html")
        st.iframe(guide_path,height=1100,alt="파라미터 설명 문서")
    else:
        st.warning("docs/hyperparameters.html 설명 문서가 없습니다.")

with setup_tab:
    st.markdown((ROOT/"README.md").read_text(encoding="utf-8"))
    with st.expander("추천 파라미터 25개"):
        st.markdown((ROOT/"PARAMETER_PRESETS.md").read_text(encoding="utf-8"))
    if st.button("연결 시험 작업 (GPU 사용 없음)"):
        try:
            connection().call("runpod_bridge.submit('probe', label='연결 시험')")
            st.success("연결 시험을 대기열에 등록했습니다.")
        except Exception as error:
            st.error(redact(str(error)))

# Start/resume evaluation of already-downloaded reports without blocking the UI.
if auto_ai:
    ai_evaluation.ensure_worker(ROOT)
