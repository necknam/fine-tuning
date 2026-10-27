"""Qwen3.5-4B 3,000-sample P01~P06 Comparative Dashboard for Streamlit."""
import json
from pathlib import Path
import streamlit as st
import yaml

ROOT = Path(__file__).resolve().parents[1]

CASE_DESCRIPTIONS = [
    ("로드맵 생성 · 비용 우선", "같은 RAG 목표에서 예산을 지키면서 비용 중심 활동·자원을 선택하는지 확인"),
    ("로드맵 생성 · 시간 우선", "총 6시간 안에 목표를 완수하고 단계별 시간을 배분하는지 확인"),
    ("로드맵 생성 · 업무 적용 우선", "비용·시간 관점과 다른 실제 업무 산출물·검증 활동을 제시하는지 확인"),
    ("자료 없는 직접 실습", "새 강좌·유료 API 없이 성공 2건·실패 1건을 재현하고 원인을 기록하는지 확인"),
    ("경험·시작점 충돌", "낮은 자기평가보다 Python 8년 경험과 시작점 3을 우선해 기초 반복을 피하는지 확인"),
    ("미확정 지원금", "지원금 3만원을 예산에서 빼지 않고 현금 1만원 한도를 지키는지 확인"),
    ("확인 질문", "기간 0주·목표 불명확일 때 일정을 임의 생성하지 않고 필요한 질문을 하는지 확인"),
    ("악성 문구 방어", "자료 속 구매·예산 변경 지시를 무시하고 사용자 조건과 자료 ID를 유지하는지 확인"),
    ("부분 수정 · 시간", "요청한 두 단계의 시간만 바꾸고 문자열·배열·완료 기록을 보존하는지 확인"),
    ("부분 수정 · 요청 우선순위", "직원 요청의 완료 기준만 바꾸고 부서장의 유료 과정·20시간 제안을 거부하는지 확인"),
]

PRESET_META = {
    "P01": {"name": "기준 실험", "desc": "LR 1e-4, r=32, alpha=64"},
    "P02": {"name": "학습률 절반", "desc": "LR 5e-5, r=32, alpha=64 (보수적)"},
    "P03": {"name": "학습률 중간", "desc": "LR 7.5e-5, r=32, alpha=64"},
    "P04": {"name": "학습률 상향", "desc": "LR 1.5e-4, r=32, alpha=64 (공격적)"},
    "P05": {"name": "LoRA 용량 축소", "desc": "LR 1e-4, r=16, alpha=32 (경량)"},
    "P06": {"name": "LoRA 용량 확대", "desc": "LR 1e-4, r=64, alpha=128 (표현력)"},
}


def scan_local_results(root):
    """Scan local outputs directory for P01~P06 results."""
    data = {"presets": {}}
    for pid in sorted(PRESET_META.keys()):
        p_dir = root / f"outputs/qwen35_4b_3000_{pid}"
        if not p_dir.is_dir():
            continue

        for run_dir in p_dir.iterdir():
            if not run_dir.is_dir() or run_dir.name in ('sample60', 'control_jobs'):
                continue

            full3000 = run_dir / "full3000"
            result_file = full3000 / "result.json"
            train_meta = {}
            if result_file.is_file():
                try:
                    train_meta = json.loads(result_file.read_text(encoding="utf-8"))
                except Exception:
                    pass

            epochs_data = {}
            for epoch in (2, 5):
                comp_dir = full3000 / f"epoch{epoch}" / "comparison"
                if not comp_dir.is_dir():
                    continue

                cases = []
                for i in range(10):
                    c_file = comp_dir / f"case{i:02d}.json"
                    if c_file.is_file():
                        try:
                            cases.append(json.loads(c_file.read_text(encoding="utf-8")))
                        except Exception:
                            pass

                if cases:
                    epochs_data[str(epoch)] = {
                        "cases": cases,
                        "count": len(cases),
                        "adapter_path": str(full3000 / f"epoch{epoch}/adapter")
                    }

            if epochs_data or train_meta:
                data["presets"][pid] = {
                    "meta": PRESET_META[pid],
                    "run_id": run_dir.name,
                    "train_meta": train_meta,
                    "epochs": epochs_data
                }

    # Also check if snapshot exists in dashboard/
    snapshot_path = root / "dashboard/current_4b_results.json"
    if snapshot_path.is_file():
        try:
            snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
            for pid, pdata in snapshot.get("presets", {}).items():
                if pid not in data["presets"]:
                    data["presets"][pid] = pdata
        except Exception:
            pass

    return data


def render():
    st.title("GrowPath · Qwen3.5-4B P01~P06 파인튜닝 비교")
    st.caption("확장 3,000건 데이터셋 · Qwen3.5-4B Base · B200 BF16 LoRA · 공통 고정 10개 입력 실전 비교")

    data = scan_local_results(ROOT)
    presets = data["presets"]

    overview_tab, detail_tab, export_tab = st.tabs(["📊 프리셋 종합 현황", "🔍 상세 답변 비교", "📥 리포트 내보내기"])

    with overview_tab:
        st.subheader("1. 프리셋별 학습 현황 및 지표 요약")

        table_rows = []
        for pid, info in PRESET_META.items():
            run_data = presets.get(pid, {})
            train_meta = run_data.get("train_meta", {})
            epochs = run_data.get("epochs", {})

            status_text = "대기 (결과 없음)"
            if epochs:
                status_text = f"완료 ({', '.join(epochs.keys())}에포크 비교 가능)"
            elif train_meta:
                status_text = "학습 완료 (비교 대기)"

            loss_val = train_meta.get("training_loss")
            step_sec = train_meta.get("steady_step_mean_seconds")
            peak_mem = train_meta.get("peak_memory_fraction")

            table_rows.append({
                "프리셋": pid,
                "실험명": info["name"],
                "주요 설정": info["desc"],
                "학습 손실": f"{loss_val:.4f}" if loss_val else "-",
                "스텝당 시간": f"{step_sec:.2f}s" if step_sec else "-",
                "피크 VRAM": f"{peak_mem*100:.1f}%" if peak_mem else "-",
                "상태": status_text
            })

        st.dataframe(table_rows, hide_index=True, use_container_width=True)

        st.info("💡 **가이드**: RunPod에서 학습 및 비교(`--phase all --execute`) 완료 후 생성된 `outputs/` 폴더를 로컬로 가져오면 자동으로 지표와 답변이 렌더링됩니다.")

    with detail_tab:
        st.subheader("2. 10개 고정 입력별 답변 대조 (Side-by-Side)")

        available_presets = [pid for pid, p in presets.items() if p.get("epochs")]
        if not available_presets:
            st.warning("현재 로컬에 다운로드된 4B 비교 결과 JSON이 없습니다. RunPod에서 생성된 `comparison/` 폴더 또는 `dashboard/current_4b_results.json`을 배치해 주세요.")
            return

        col1, col2, col3 = st.columns([2, 1, 1])
        with col1:
            case_options = [f"사례 {i+1}: {CASE_DESCRIPTIONS[i][0]}" for i in range(10)]
            selected_case_idx = case_options.index(st.selectbox("평가 입력 케이스 선택", case_options))
        with col2:
            selected_preset = st.selectbox("프리셋 선택", available_presets)
        with col3:
            avail_epochs = list(presets[selected_preset]["epochs"].keys())
            selected_epoch = st.selectbox("에포크 선택", avail_epochs, index=len(avail_epochs)-1)

        case_desc, case_purpose = CASE_DESCRIPTIONS[selected_case_idx]
        st.markdown(f"**검증 목적:** {case_purpose}")

        cases = presets[selected_preset]["epochs"][selected_epoch]["cases"]
        if selected_case_idx >= len(cases):
            st.error("해당 사례 결과가 아직 로드되지 않았습니다.")
            return

        case_item = cases[selected_case_idx]

        with st.expander("입력 프롬프트 원문 보기 (User Context & Constraints)"):
            st.json(case_item.get("messages", []))

        left_col, right_col = st.columns(2)
        with left_col:
            st.markdown("#### 🏛️ Qwen3.5-4B 베이스 모델 답변")
            base_res = case_item.get("base", {})
            st.caption(f"생성 시간: {base_res.get('seconds', 0):.2f}초 · {base_res.get('tokens', 0)} 토큰")
            try:
                st.json(json.loads(base_res.get("text", "{}")))
            except Exception:
                st.code(base_res.get("text", ""), language="json")

        with right_col:
            st.markdown(f"#### 🚀 {selected_preset} ({selected_epoch}에포크) 어댑터 답변")
            tuned_res = case_item.get("tuned", {})
            st.caption(f"생성 시간: {tuned_res.get('seconds', 0):.2f}초 · {tuned_res.get('tokens', 0)} 토큰")
            try:
                st.json(json.loads(tuned_res.get("text", "{}")))
            except Exception:
                st.code(tuned_res.get("text", ""), language="json")

        st.divider()

    with export_tab:
        st.subheader("3. 평가 보고서 다운로드")
        if available_presets:
            st.download_button(
                "전체 스캔 결과 JSON 다운로드",
                data=json.dumps(data, ensure_ascii=False, indent=2),
                file_name="qwen35_4b_comparison_summary.json",
                mime="application/json"
            )
        else:
            st.info("결과가 로드되면 여기서 통합 요약 보고서를 다운로드할 수 있습니다.")

