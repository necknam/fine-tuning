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
import importlib
import experiment_presets
# Cloud keeps imported helpers between reruns, including across deployments.
importlib.reload(experiment_presets)
from experiment_presets import PRESETS, PRESET_GUIDE_MARKDOWN
from db_registry import sample_mode, validate_dataset_pair, report_input_info
import prepare_data
importlib.reload(prepare_data)
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



def load_view(section, force=False):
    flag="_loaded_"+section
    if force or not st.session_state.get(flag):
        dashboard_store.hydrate(ROOT,force=True,section=section)
        st.session_state[flag]=True


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
    safe=json.loads(redact(json.dumps(overview["jobs"],ensure_ascii=False)))
    data=dashboard_store.merge_history(ROOT,safe,overview.get("observed_at"))
    path=ROOT/"reports/control_history.json"
    path.parent.mkdir(parents=True,exist_ok=True)
    temporary=path.with_name(path.name+"."+uuid.uuid4().hex+".tmp")
    temporary.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding="utf-8")
    temporary.replace(path)
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
    with st.expander("현재 학습 설정의 예상 시간 · 실측 속도 기준",expanded=True):
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
        target_steps=steps
        seconds=target_steps*speed
        st.metric(f"학습 {count:,}개 · {int(training['num_train_epochs'])}에포크 예상 학습 시간",duration_text(seconds))
        if started:
            end=datetime.fromtimestamp(started,kst)+timedelta(seconds=seconds)
            st.caption("작업 시작 시각을 기준으로 순수 학습 시간만 더한 참고 시각: "+end.strftime("%m/%d %H:%M"))
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
        st.caption("학습: BF16 LoRA 또는 NF4 QLoRA 선택 · 평가: 원본 BF16 + 어댑터")
    auto_ai=st.toggle("새 답변 전체 자동 AI 평가",value=False,key="auto_ai_evaluation")
    st.caption("입력·답변을 OpenAI API로 전송하며 호출 비용이 발생합니다. 이미 평가한 답변은 건너뜁니다.")
    st.header("RunPod 연결")
    settings_path = ROOT / "configs/local_connection.json"
    saved = json.loads(settings_path.read_text(encoding="utf-8")) if settings_path.exists() else {}
    url = st.text_input("Jupyter 주소", app_settings.get(ROOT,"RUNPOD_JUPYTER_URL",saved.get("url", "")))
    token = st.text_input("Jupyter 토큰 또는 비밀번호", type="password", value=app_settings.get(ROOT,"RUNPOD_JUPYTER_TOKEN", ""))
    st.caption("RunPod의 JUPYTER_PASSWORD 또는 Jupyter 로그인에 쓴 값입니다. HF 토큰·RunPod API 키와 다릅니다.")
    remote = st.text_input("Jupyter 내 프로젝트 경로", app_settings.get(ROOT,"RUNPOD_REMOTE_PATH",saved.get("remote_path", "workspace/qwen_factory")))
    if st.button("연결", type="primary"):
        try:
            client = RunPodClient(url, token, remote)
            client.connect()
            for name in ("runpod_bridge.py", "control_pipeline.py", "compare_factory_sample.py", "db_registry.py", "runpod_factory_sample.py", "prepare_data.py", "factory_state.py","cloud_evidence.py","cloud_evaluation.py","cloud_employee_context.py","practical_reports.py"):
                client.contents("scripts/"+name, (ROOT / "scripts" / name).read_text(encoding="utf-8"))
            st.session_state.client = client
            st.session_state["_poll_requested"]=True
            st.session_state.pop("recovery_service_ready",None)
            settings_path.write_text(json.dumps({"url": client.url, "remote_path": remote}, indent=2), encoding="utf-8")
            st.success("연결 완료 · 토큰은 파일에 저장하지 않습니다.")
        except Exception as error:
            st.error(redact(str(error)))
    if st.session_state.get("client"):
        st.success("RunPod 제어 연결됨")
    with st.expander("HF·실험 DB·실전 근거 DB 인증정보"):
        st.caption("아래 적용 버튼을 누르면 입력값을 HTTPS로 현재 RunPod 제어 커널에 전달합니다. 원격 파일에는 저장하지 않습니다.")
        hf = st.text_input("HF_TOKEN", type="password", value=app_settings.get(ROOT,"HF_TOKEN", ""))
        repo = st.text_input("HF_REPO_ID", value=app_settings.get(ROOT,"HF_REPO_ID", "Ssum-mer/qwen-factory-adapters"))
        database = st.text_input("DATABASE_URL", type="password", value=app_settings.get(ROOT,"DATABASE_URL", ""))
        evidence_db = st.text_input("실전 근거 DB · GROWPATH_DB_URL", type="password", value=app_settings.get(ROOT,"GROWPATH_DB_URL", ""))
        if st.button("이 접속정보를 RunPod 세션에 적용"):
            try:
                if not all((hf, repo, database)):
                    raise ValueError("세 값을 모두 입력하세요.")
                values = {"HF_TOKEN": hf, "HF_REPO_ID": repo, "DATABASE_URL": database}
                if evidence_db: values["GROWPATH_DB_URL"] = evidence_db
                connection().execute("import os\nos.environ.update(" + repr(values) + ")\n"
                    "os.environ['HF_HOME']='/workspace/.cache/huggingface'\n"
                    "os.environ['PIP_CACHE_DIR']='/workspace/qwen_factory/.cache/pip'\n")
                st.session_state.remote_secrets = values
                st.session_state.pop("recovery_service_ready",None)
                st.success("적용 완료")
            except Exception as error:
                st.error(redact(str(error)))



def pull_reports(client, overview):
    count=0
    changed=[]
    folder=ROOT/"reports/run_configs"
    folder.mkdir(parents=True,exist_ok=True)
    for run_id,text in overview.get("configurations",{}).items():
        uuid.UUID(run_id)
        path=folder/(run_id+".yaml")
        if not path.exists():
            path.write_text(text,encoding="utf-8")
            changed.append(path)
    # Keep the exact registered evaluation input locally for reproducible new-Pod restores.
    for text in overview.get("configurations",{}).values():
        cfg=yaml.safe_load(text)
        relative=cfg.get("data",{}).get("test_file")
        if relative:
            path=(ROOT/relative).resolve()
            path.relative_to((ROOT/"data").resolve())
            if not dashboard_store.allowed(relative):
                raise ValueError("등록 평가 입력 경로가 올바르지 않습니다.")
            if not path.exists():
                snapshot=client.contents(relative)["content"]
                for line in snapshot.splitlines():
                    if line.strip():
                        json.loads(line)
                path.parent.mkdir(parents=True,exist_ok=True)
                path.write_text(snapshot,encoding="utf-8")
                changed.append(path)
    for relative in overview["reports"]:
        path=(ROOT/relative).resolve()
        path.relative_to((ROOT/"reports").resolve())
        if path.exists():
            continue
        text=client.contents(relative)["content"]
        json.loads(text)
        path.parent.mkdir(parents=True,exist_ok=True)
        path.write_text(text,encoding="utf-8")
        changed.append(path)
        count+=1
    dashboard_store.persist_many(ROOT,changed)
    return count


def publish(cfg):
    c=connection()
    for name in ("control_pipeline.py","compare_factory_sample.py","runpod_bridge.py","db_registry.py","runpod_factory_sample.py","prepare_data.py","factory_state.py","cloud_evidence.py","cloud_evaluation.py","cloud_employee_context.py","practical_reports.py"):
        c.contents("scripts/"+name,(ROOT/"scripts"/name).read_text(encoding="utf-8"))
    is_sample=sample_mode(cfg)
    prefix="data/sample" if is_sample else "data/production"
    for field in ("train_file","validation_file"):
        path=(ROOT/cfg["data"][field]).resolve()
        path.relative_to((ROOT/prefix).resolve())
        text=path.read_text(encoding="utf-8-sig")
        digest=hashlib.sha256(text.encode()).hexdigest()
        destination=prefix+"/processed/"+field.removesuffix("_file")+"_"+digest+".jsonl"
        cfg["data"][field.removesuffix("_file")+"_sha256"]=digest
        local_data=ROOT/destination
        local_data.parent.mkdir(parents=True,exist_ok=True)
        local_data.write_text(text,encoding="utf-8",newline="")
        dashboard_store.persist(ROOT,local_data)
        c.ensure_file(destination,text)
        cfg["data"][field]=destination
    test=cfg["data"].get("test_file","data/sample/eval/test.jsonl")
    test_path=(ROOT/test).resolve()
    test_path.relative_to((ROOT/"data").resolve())
    # Preserve frozen evaluation bytes (including CRLF) across Windows -> Linux.
    test_text=test_path.read_bytes().decode('utf-8')
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
    fixed_report=report_input_info(ROOT,cfg)
    test_snapshot=fixed_report['file'] if fixed_report else prefix+"/eval/control_"+hashlib.sha256(test_text.encode()).hexdigest()[:20]+".jsonl"
    local_snapshot=ROOT/test_snapshot
    local_snapshot.parent.mkdir(parents=True,exist_ok=True)
    local_snapshot.write_text(test_text,encoding="utf-8",newline='')
    dashboard_store.persist(ROOT,local_snapshot)
    c.ensure_file(test_snapshot,test_text)
    cfg["data"]["test_file"]=test_snapshot
    if cfg['data'].get('heldout_test_file'):
        heldout=(ROOT/cfg['data']['heldout_test_file']).resolve()
        heldout.relative_to((ROOT/'data/production').resolve())
        heldout_text=heldout.read_bytes().decode('utf-8')
        heldout_hash=hashlib.sha256(heldout_text.encode()).hexdigest()
        if heldout_hash!=cfg['data'].get('heldout_sha256'):
            raise ValueError('최종 평가 데이터 해시가 변경됐습니다.')
        heldout_snapshot=prefix+'/eval/heldout_'+heldout_hash+'.jsonl'
        local_heldout=ROOT/heldout_snapshot;local_heldout.parent.mkdir(parents=True,exist_ok=True)
        local_heldout.write_text(heldout_text,encoding='utf-8',newline='')
        dashboard_store.persist(ROOT,local_heldout);c.ensure_file(heldout_snapshot,heldout_text)
        cfg['data']['heldout_test_file']=heldout_snapshot
    payload=yaml.safe_dump(cfg,allow_unicode=True,sort_keys=False)
    name="configs/control_"+hashlib.sha256(payload.encode()).hexdigest()[:20]+".yaml"
    (ROOT/name).write_text(payload,encoding="utf-8")
    c.ensure_file(name,payload)
    return name


experiment_tab, guide_tab, review_tab, setup_tab=st.tabs(["파라미터·실험 대기열","파라미터 설명","보고서 평가","최초 연결·새 Pod 안내"],key="main_navigation",on_change="rerun")
page_changed=st.session_state.get("_previous_page")!=st.session_state.get("main_navigation")
st.session_state["_previous_page"]=st.session_state.get("main_navigation")
with experiment_tab:
    if experiment_tab.open:
        load_view("history",force=page_changed)
        st.subheader("실험 설정")
        st.caption("등록 → 선택한 에포크까지 학습 → 지정한 에포크 가중치 저장 → 고정 입력으로 답변 생성 → 보고서 저장까지 진행합니다. 이전·개선 데이터 비교는 5에포크 학습 후 2·5에포크를 평가합니다.")
        dataset_mode=st.radio("학습 데이터 구분",["production","sample"],horizontal=True,
            format_func=lambda value:"샘플 시험" if value=="sample" else "실제 데이터 학습",key="dataset_mode_v2")
        st.caption("새 실험 등록은 항상 새 실행 ID를 만듭니다. 기존 가중치 사용과 중단 실험 이어하기는 해당 보고서·실행 이력에서만 선택합니다.")
        production_configs={
            '개선 데이터 v4 · 2·5에포크 비교':'hyperparameters.compare.reviewed_v4.yaml',
            '이전 데이터 v1 · 2·5에포크 비교':'hyperparameters.compare.baseline_v1.yaml',
            '기존 학습 설정':'hyperparameters.production.pinned.yaml'}
        if dataset_mode=='production':
            version=st.selectbox('학습 데이터·비교 설정',list(production_configs))
            production_config=ROOT/'configs'/production_configs[version]
        else:production_config=ROOT/'configs/hyperparameters.production.pinned.yaml'
        config_source=production_config if dataset_mode=='production' and production_config.is_file() else ROOT/'configs/hyperparameters.sample.pinned.yaml'
        base=yaml.safe_load(config_source.read_text(encoding="utf-8-sig"))
        minimum=base['data'].get('minimum_max_length',0)
        available_presets=[p for p in PRESETS if p[2].get('max_length',base['experiments'][0]['training']['max_length'])>=minimum]
        options=[("P00","커스텀",{},"확정 기준에서 시작해 아래 값을 수정하세요.")]+available_presets
        preset=st.selectbox("파라미터 프리셋",range(len(options)),index=1,format_func=lambda i:options[i][0]+" "+options[i][1])
        pid,pname,changes,reason=options[preset]
        st.caption(reason)
        base["dataset_mode"]=dataset_mode
        data_ready=True
        if dataset_mode=="sample":
            st.info("샘플 시험 · 가상 학습54개 / 검증3개. 실제 학습과 가중치·보고서를 구분합니다.")
        else:
            st.info("확정 데이터: 학습 1,200 · 검증 150 · 별도 평가 150 · 공통 비교 입력 10개. Cloud에는 파일을 직접 업로드하세요.")
            fields=('train_file','validation_file','heldout_test_file')
            data_ready=config_source==production_config and all((ROOT/base['data'][field]).is_file() for field in fields) and (ROOT/base['evaluation']['file']).is_file()
            with st.expander("학습·평가 데이터 준비" if not data_ready else "데이터 확인·교체",expanded=not data_ready):
                st.caption("학습 1200 · 검증 150 · 별도 평가 150 · 공통 입력 10개. 확정한 파일을 모두 올리세요.")
                left,right=st.columns(2)
                with left:
                    train_upload=st.file_uploader("학습 train.jsonl",type=["jsonl"],key="production_train")
                    heldout_upload=st.file_uploader("별도 평가 test.jsonl",type=["jsonl"],key="production_heldout")
                with right:
                    validation_upload=st.file_uploader("검증 validation.jsonl",type=["jsonl"],key="production_validation")
                    report_upload=st.file_uploader("공통 입력 JSONL",type=["jsonl"],key="production_report")
                uploads={'train':train_upload,'validation':validation_upload,'heldout':heldout_upload,'report':report_upload}
            if any(value is not None for value in uploads.values()):
                data_ready=False
                if all(value is not None for value in uploads.values()):
                    try:
                        prepare_data.install_curated_uploads(ROOT,{key:value.getvalue() for key,value in uploads.items()},base)
                        data_ready=True
                        st.success("4개 파일 해시·건수·평가 분리 확인 완료")
                    except (ValueError,UnicodeError,OSError) as error:
                        st.error("데이터를 확인하세요: "+str(error))
                else:
                    st.caption("평가 누락을 방지하기 위해 4개 파일을 모두 올려야 등록할 수 있습니다.")
            elif data_ready:
                st.caption("로컬에 준비된 확정 데이터 4개를 사용합니다. 등록 시 해시를 다시 확인합니다.")
            else:
                st.caption("데이터는 GitHub에 올리지 않습니다. 이 화면에서 확정 파일 4개를 직접 올리세요.")
        recipe=base["experiments"][0]
        with st.expander("현재 데이터 위치"):
            st.caption("선택한 학습/검증 파일을 내용 해시로 고정해 전송합니다. 학습 등록 후 파일 내용이 바뀌면 실행을 차단합니다.")
            st.dataframe([
                {"구분":"학습", "파일":base["data"]["train_file"]},
                {"구분":"검증", "파일":base["data"]["validation_file"]},
                {"구분":"평가 입력", "파일":base["data"]["test_file"]},
            ],hide_index=True)
        defaults={**recipe["training"],**recipe["lora"],**changes}
        evaluation_file=base['evaluation']['file']
        try:
            common_report=report_input_info(ROOT,base)
            st.caption(f"공통 평가 입력 {common_report['rows']}개 · 모든 새 실험에 같은 입력을 사용합니다.")
        except (OSError,ValueError) as error:
            data_ready=False
            st.caption("공통 비교 입력 파일이 준비되면 실험을 등록할 수 있습니다.")
        with st.form("parameters_"+dataset_mode+"_"+pid):
            label=st.text_input("실험 이름",value=pid+" "+pname)
            st.markdown("**기본 학습 설정**")
            a,b,c=st.columns(3)
            with a:
                lr=st.number_input("학습률",min_value=0.000001,max_value=0.01,
                    value=float(defaults["learning_rate"]),step=0.000025,format="%.6f")
                rank=st.selectbox("LoRA r",[8,16,32,64,128],index=[8,16,32,64,128].index(defaults["r"]))
            with b:
                batch=st.number_input("GPU 배치 크기",min_value=1,max_value=16,value=int(defaults["per_device_train_batch_size"]))
                accumulation=st.number_input("그래디언트 누적",min_value=1,max_value=256,value=int(defaults["gradient_accumulation_steps"]))
            with c:
                lengths=[n for n in (1024,2048,4096,7168,8192,10240,12288,16384) if n>=base['data'].get('minimum_max_length',0)]
                length=st.selectbox("최대 토큰 길이",lengths,index=lengths.index(defaults["max_length"]))
                alpha=st.number_input("LoRA alpha",min_value=1,value=int(defaults["lora_alpha"]),step=8)
            with st.expander("고급 설정 · 정규화·스케줄·평가"):
                a,b=st.columns(2)
                with a:
                    dropout=st.number_input("LoRA dropout",min_value=0.0,max_value=0.5,value=float(defaults["lora_dropout"]),step=0.05)
                    decay=st.number_input("가중치 감쇠",min_value=0.0,max_value=1.0,value=float(defaults["weight_decay"]),step=0.01)
                    warmup=st.number_input("워밍업 비율",min_value=0.0,max_value=0.9,value=float(defaults["warmup_ratio"]),step=0.05)
                    scheduler=st.selectbox("학습률 스케줄",["cosine","linear","constant"],index=["cosine","linear","constant"].index(defaults["lr_scheduler_type"]))
                with b:
                    seed=st.number_input("시드",min_value=0,value=int(defaults["seed"]))
                    checkpointing=st.checkbox("재계산으로 GPU 메모리 절약",value=bool(defaults.get("gradient_checkpointing",True)),help="긴 입력에서는 켜짐을 권장합니다. 끄기는 GPU 배치 1에서만 허용합니다.")
                    generation_batch=st.selectbox("답변 동시 생성 개수",[1,2,4,8],index=[1,2,4,8].index(base.get("inference",{}).get("batch_size",1)),help="학습 배치와 별개이며 메모리가 부족하면 1로 설정하세요.")
                    priority=st.selectbox("대기열 우선순위",[10,0,20],format_func=lambda v:{0:"높음",10:"보통",20:"낮음"}[v])
            st.caption("아래에서 에포크·저장 시점·학습 정밀도를 선택합니다. 기존 실험 설정은 변경하지 않습니다.")
            epochs=st.number_input("학습 에포크",min_value=1,max_value=50,value=int(defaults['num_train_epochs']))
            save_options=list(range(1,int(epochs)+1))
            save_epochs=st.multiselect("저장·평가할 에포크",save_options,default=[e for e in recipe['artifacts']['save_epochs'] if e<=epochs] or [int(epochs)])
            training_precision=st.selectbox("학습 정밀도",['BF16 LoRA','NF4 QLoRA'],index=1 if base['quantization']['load_in_4bit'] else 0)
            start=st.form_submit_button("새 실험 등록",type="primary",disabled=not data_ready)
        if not data_ready:
            st.caption("데이터 준비를 완료하면 등록 버튼이 활성화됩니다.")
        live_reports=st.checkbox("학습 후 실제 DB 근거로 실전 보고서 10건 생성",value=True)
        if live_reports:
            from cloud_employee_context import fixed_assignment
            case_employee_ids=fixed_assignment()
            st.caption('테스트 직원을 고정 10개 입력에 미리 무작위 배정했습니다. 모든 가중치·에포크는 동일한 직원 정보와 근거 스냅샷을 재사용합니다.')
            cohort_id=st.text_input("고정10개 평가 묶음 ID",value="live_test_manual_v1",key='cohort_fixed_test_manual',help="같은 ID는 가중치가 달라도 같은 입력·근거·직원 스냅샷을 재사용합니다.")
            template=ROOT/'data/eval/prompts.app_v2.jsonl'
            base['data']['test_file']=template.relative_to(ROOT).as_posix()
            base['evaluation']={'mode':'shared_fixed_10','file':base['data']['test_file'],'expected_count':10,'sha256':hashlib.sha256(template.read_bytes()).hexdigest()}
            base['live_evaluation']={'enabled':True,'cohort_id':cohort_id}
            if case_employee_ids is not None:base['live_evaluation']['case_employee_ids']=case_employee_ids
            st.caption("학습이 끝난 뒤 최신 로컬 DB를 복제한 Cloud 근거 DB를 조회합니다. 첫 생성 이후 이 묶음은 고정됩니다. 기존 실험의 평가 입력은 바뀌지 않습니다.")
        if start:
            try:
                if not checkpointing and int(batch)!=1:
                    raise ValueError("재계산을 끄려면 GPU 배치를 1로 설정하세요. 유효 배치 16을 유지하려면 누적은 16입니다.")
                if int(length)<base['data'].get('minimum_max_length',0):
                    raise ValueError('현재 준비된 데이터의 최대 길이보다 작습니다. 길이 제한을 늘려 주세요.')
                base["experiment_id"]=str(uuid.uuid4())
                if not live_reports: base["data"]["test_file"]=evaluation_file
                else:
                    from cloud_evaluation import validate_batch
                    validate_batch(cohort_id)
                    from cloud_employee_context import validate_assignment
                    validate_assignment(case_employee_ids)
                    if not app_settings.get(ROOT,'GROWPATH_DB_URL') and not st.session_state.get('remote_secrets',{}).get('GROWPATH_DB_URL'):
                        raise ValueError('실전 근거 DB 접속정보를 Cloud Secrets에 설정하거나 RunPod 세션에 적용하세요.')
                base.setdefault('inference',{}).update(batch_size=int(generation_batch))
                if not save_epochs:raise ValueError('저장·평가할 에포크를 한 개 이상 선택하세요.')
                recipe['training']['num_train_epochs']=int(epochs)
                recipe['artifacts']['save_epochs']=sorted(save_epochs)
                base['quantization']['load_in_4bit']=training_precision=='NF4 QLoRA'
                recipe["recipe_name"]=label
                recipe["lora"].update(r=int(rank),lora_alpha=int(alpha),lora_dropout=float(dropout))
                recipe["training"].update(learning_rate=float(lr),per_device_train_batch_size=int(batch),
                    gradient_checkpointing=bool(checkpointing),
                    gradient_accumulation_steps=int(accumulation),max_length=int(length),weight_decay=float(decay),
                    warmup_ratio=float(warmup),lr_scheduler_type=scheduler,seed=int(seed),data_seed=int(seed))
                name=publish(base)
                job=connection().call("runpod_bridge.submit('experiment', config="+repr(name)+", priority="+str(priority)+", label="+repr(("[샘플] " if dataset_mode=="sample" else "[실제] ")+label)+")")
                st.session_state["_poll_requested"]=True
                st.success("대기열에 등록했습니다: "+job["job_id"])
            except Exception as error:
                st.error(redact(str(error)))

        refresh_controls=st.columns([2,3])
        with refresh_controls[0]:
            auto_refresh=st.toggle("실행 현황 자동 갱신",value=False,key="monitor_auto_refresh_opt_in_v2")
        with refresh_controls[1]:
            st.caption("기본은 필요할 때 조회합니다. 켜면 30초 간격으로 갱신합니다. 원격 작업은 계속 실행됩니다.")

        @st.fragment(run_every="30s" if auto_refresh else None)
        def monitor():
            dashboard_auth.checkpoint(ROOT)
            st.subheader("실행·대기 순서")
            refresh_now=st.button("지금 갱신",key="monitor_refresh_now")
            should_poll=refresh_now or auto_refresh or st.session_state.pop("_poll_requested",False)
            history=last_history()
            online=False
            try:
                if should_poll and not st.session_state.get("client"):
                    recovery.reconnect(ROOT,st.session_state)
                if st.session_state.get("recovery_notice"):
                    st.caption(st.session_state.recovery_notice)
                if should_poll and st.session_state.get("client"):
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
    budget=request.get("budget_krw")
    budget_text=f"{budget:,}원" if isinstance(budget,(int,float)) else "미지정"
    st.write("기간: "+str(request.get("duration_weeks","—"))+"주 · 주당 시간: "+str(request.get("weekly_hours","—"))+"시간")
    st.write("예산: "+budget_text)
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
    st.markdown("#### 전체 계획 요약")
    st.write("총시간: "+str(roadmap.get("total_hours","—"))+"시간")
    total_cost=roadmap.get("total_cost_krw")
    st.write("총비용: "+(f"{total_cost:,}원" if isinstance(total_cost,(int,float)) else "미지정"))
    for field,label in (("confirmation_needed","추가 확인 사항"),("notice","안내"),("sample_notice","안내")):
        if roadmap.get(field):
            st.caption(label)
            if isinstance(roadmap[field],list):
                for notice_item in roadmap[field]:st.write("• "+str(notice_item))
            else:
                st.write(roadmap[field])
    with st.expander("원문 보기"):
        st.code(item["text"],language="json",wrap_lines=True)


with review_tab:
    if review_tab.open:
        load_view("reports",force=page_changed)
        if page_changed and auto_ai:
            ai_evaluation.ensure_worker(ROOT)
        @st.fragment
        def review():
            dashboard_auth.checkpoint(ROOT)
            precision_view=st.selectbox("평가 결과 유형",["최신 결과","BF16 결과","4비트 시험 결과"],key="precision_view")
            cohort_label=st.selectbox("평가 데이터",["공통 입력 10개 · 출력 비교","별도 평가 150건 · 기준 답변 비교"],key="evaluation_cohort_view")
            cohort="heldout" if cohort_label.startswith("별도") else "report"
            groups=human_reports.catalog(ROOT,{"BF16 결과":"bf16","4비트 시험 결과":"4bit"}.get(precision_view),cohort=cohort)
            st.caption("기준 답변은 확정 데이터의 답변이며 전수 전문가 검수를 거친 정답은 아닙니다." if cohort=="heldout" else "같은 10개 입력의 출력을 비교합니다. 이 묶음에는 기준 답변이 없습니다.")
            mode_view=st.selectbox("학습 구분",["전체","실제 데이터 학습","샘플 시험"],key="report_mode_view")
            if mode_view!="전체":
                groups={weight:group for weight,group in groups.items()
                        if bool(group["manifest"].get("is_sample",True)) == (mode_view=="샘플 시험")}
            st.subheader("실험 보고서 · 입력별 휴먼 평가")
            st.caption("입력 하나당 종합 1~5점. 평가한 입력들의 평균이 보고서 제목에 반영됩니다. 평가 중 자동 새로고침은 하지 않습니다.")
            if st.button("새 보고서 확인"):
                load_view("reports",force=True)
                human_reports._rating_cache.clear()
                ai_evaluation._latest_cache.clear()
                if auto_ai:ai_evaluation.ensure_worker(ROOT)
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
                records.append({"구분":"샘플 시험" if m.get("is_sample",True) else "실제 학습","보고서":human_reports.title(ROOT,weight,group),"실험":names[weight],
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
                st.caption("선택한 실험에 저장된 에포크 가중치로 원본 BF16 답변을 생성합니다. 에포크마다 모델을 한 번만 불러옵니다. GPU 비용이 발생합니다.")
                if st.button("기존 가중치 BF16 답변 생성",key="bf16_existing_"+manifest["run_id"]):
                    try:
                        c=connection()
                        for name in ("control_pipeline.py","compare_factory_sample.py","runpod_bridge.py","db_registry.py","runpod_factory_sample.py","prepare_data.py","factory_state.py","cloud_evidence.py","cloud_evaluation.py","cloud_employee_context.py","practical_reports.py"):
                            c.contents("scripts/"+name,(ROOT/"scripts"/name).read_text(encoding="utf-8"))
                        cfg_path=ROOT/"reports/run_configs"/(manifest["run_id"]+".yaml")
                        config_name="configs/control_bf16_"+manifest["run_id"]+".yaml"
                        c.ensure_file(config_name,cfg_path.read_text(encoding="utf-8"))
                        job=c.call("runpod_bridge.submit('evaluate_existing', config="+repr(config_name)+", label='BF16 기존 가중치 평가 · 재학습 없음')")
                        st.success("BF16 평가 등록 완료 · "+job["job_id"])
                    except Exception as error:
                        st.error(redact(str(error)))
            latest_report=max(row[1]["created_at"] for row in group["cases"].values())
            st.info("샘플 시험 결과 · 실제 데이터 학습 결과와 구분됩니다." if manifest.get("is_sample",True) else "실제 데이터 학습 결과")
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
            @st.fragment
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
                    st.caption("평가 모델: "+judge_model+" · 엄격 기준 v3 · 원문 근거·시작 단계 검증 · 같은 기준의 결과만 재사용하며 사람 점수와 별도로 저장합니다.")
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
                        for entry in ai_entries:
                            score_text=f"{entry['average']:.2f} / 5" if entry['average'] is not None else "판단 불가"
                            with st.expander(f"입력 {entry['case_index']+1} · AI {score_text}"):
                                st.write(entry["review"]["summary"])
                                for issue in entry["review"].get("issues",[]):st.write("• "+issue)
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
            with st.container(border=True,key="input_card"):
                show_input(report)
            with st.container(border=True,key="answer_card"):
                st.subheader("모델 답변 · 학습 로드맵 보고서")
                from practical_reports import render as render_practical_report
                st.markdown(render_practical_report(report,'tuned'))
                st.download_button("실전 보고서 Markdown 내려받기",render_practical_report(report,'tuned'),file_name=f"roadmap_case_{case+1}.md",mime="text/markdown",key="practical_"+weight+"_"+str(case))
                with st.expander("모델 구조화 응답 확인"):
                    show_answer(report["tuned"])
            if report.get("reference_unreviewed") is not None:
                with st.expander("고정 기준 답변 · 전문가 검수 미완료"):
                    st.code(report["reference_unreviewed"],language="json",wrap_lines=True)
                    st.caption("기준 답변 SHA-256: "+str(report.get("reference_sha256","이전 결과 · 데이터 해시 참조")))
            with st.expander("기본 모델 답변과 비교"):
                if report.get("base_reused"):
                    st.caption("같은 BF16 모델·입력·생성 조건·토크나이저로 이미 생성한 기본 답변입니다. 생성 시간은 최초 생성 때의 기록입니다.")
                show_answer(report["base"])
            human_tab,ai_tab=st.tabs(["사람 평가","AI 보조 평가 · OpenAI"],key="review_rating_tabs",on_change="rerun")
            with human_tab:
                if human_tab.open:
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
                if ai_tab.open:
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
    if guide_tab.open:
        st.subheader("파라미터 설명 · 설정할 때 참고하세요")
        st.caption("현재 실행 기준과 상세 설명을 함께 확인할 수 있습니다. 설명을 읽어도 실행 설정은 바뀌지 않습니다.")
        guide_config=yaml.safe_load((ROOT/'configs/hyperparameters.compare.reviewed_v4.yaml').read_text(encoding='utf-8-sig'))
        training=guide_config['experiments'][0]['training']
        lora=guide_config['experiments'][0]['lora']
        st.caption("확정 데이터의 기준 설정입니다. 선택한 실험에서 수정한 값은 파라미터 화면과 실행 보고서에서 확인하세요.")
        a,b,c=st.columns(3)
        a.metric("학습 횟수",f"{training['num_train_epochs']} epoch")
        b.metric("유효 배치",str(training['per_device_train_batch_size']*training['gradient_accumulation_steps']))
        c.metric("최대 입력·답변 길이",f"{training['max_length']:,} 토큰")
        st.info("이번 학습: 1,200건 학습 · 150건 검증 · 150건 별도 평가. 모든 비교에 같은 보고서 입력 10개를 사용합니다.")
        st.markdown("### 파라미터를 이해하는 순서")
        cards=[
            ("01 · 학습률",f"현재 **{training['learning_rate']:.5f}** · 한 번에 모델을 얼마나 조정할지 정합니다.",
             "너무 크게 바꾸면 학습이 불안정할 수 있고, 너무 작으면 변화가 충분하지 않을 수 있습니다. 다른 조건을 고정하고 비교합니다."),
            ("02 · LoRA 용량",f"현재 **r={lora['r']} / alpha={lora['lora_alpha']}** · 추가로 학습할 어댑터의 용량과 배율입니다.",
             "r을 높이면 어댑터의 용량과 메모리 요구가 커질 수 있습니다. alpha와 r의 비율도 함께 확인합니다."),
            ("03 · 배치와 누적",f"현재 **GPU 배치 {training['per_device_train_batch_size']} × 누적 {training['gradient_accumulation_steps']} = 유효 배치 {training['per_device_train_batch_size']*training['gradient_accumulation_steps']}** · GPU 1장 기준입니다.",
             "배치는 한 번에 처리하는 수, 누적은 가중치를 갱신하기 전 모으는 횟수입니다. 같은 곱이어도 속도·메모리·학습 결과가 완전히 같지는 않습니다."),
            ("04 · 최대 토큰 길이",f"현재 **{training['max_length']:,}토큰** · 질문·검색 근거·답변을 합한 길이입니다.",
             f"확정 데이터 최대 {guide_config['data']['minimum_max_length']:,}토큰을 수용합니다. 길이를 줄여 데이터를 잘라내지 않습니다. 실제 GPU 메모리 적합성은 사전 점검합니다."),
            ("05 · 정규화와 스케줄",f"현재 **dropout {lora['lora_dropout']} / weight decay {training['weight_decay']} / warmup {training['warmup_ratio']} / {training['lr_scheduler_type']}**",
             "dropout과 weight decay는 학습을 규제하고, warmup은 초기 학습률을 점진적으로 높입니다. 스케줄은 이후 학습률의 변화를 정합니다."),
            ("06 · 학습 횟수와 비교",f"현재 **{training['num_train_epochs']} epoch · 2/5 epoch 저장 · seed {training['seed']}**",
             "epoch는 학습 데이터를 반복해서 보는 횟수입니다. 검증 결과와 별도 평가를 함께 보고 어댑터를 고릅니다. 더 오래 학습했다고 반드시 좋아지는 것은 아닙니다."),
        ]
        for offset in range(0,len(cards),2):
            columns=st.columns(2)
            for column,(title,summary,explanation) in zip(columns,cards[offset:offset+2]):
                with column:
                    with st.container(border=True):
                        st.markdown("#### "+title)
                        st.markdown(summary)
                        st.caption(explanation)
        st.caption("재계산(gradient checkpointing)은 GPU 메모리를 줄이기 위한 설정입니다. 답변 동시 생성 수는 학습 배치와 별개입니다. 학습 속도·성능은 실제 측정 전입니다.")
        with st.expander("파라미터 탐색 후보 25개"):
            st.caption("샘플 기준에서 만든 탐색 후보입니다. 비교 실험의 학습 길이는 10240이며 25개를 자동으로 모두 실행하지 않습니다.")
            st.markdown(PRESET_GUIDE_MARKDOWN)
        with st.expander("개발자용 원본 설정 JSON",expanded=False):
            st.json({'model':guide_config['model'],'lora':lora,'training':training})

with setup_tab:
    if setup_tab.open:
        st.markdown((ROOT/"README.md").read_text(encoding="utf-8"))
        st.caption("파라미터 의미와 탐색 후보 25개는 파라미터 설명 탭에서 확인하세요.")
        if st.button("연결 시험 작업 (GPU 사용 없음)"):
            try:
                connection().call("runpod_bridge.submit('probe', label='연결 시험')")
                st.success("연결 시험을 대기열에 등록했습니다.")
            except Exception as error:
                st.error(redact(str(error)))

# Report/monitor refresh starts any needed UI-side fallback worker.
# The detached RunPod supervisor continues independently while this page is closed.
