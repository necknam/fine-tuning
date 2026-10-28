"""Saved, hash-bound B200 comparisons. No database or GPU execution on page load."""
import json
from pathlib import Path
import streamlit as st
import dashboard_auth

ROOT = Path(__file__).resolve().parents[1]


def load_snapshot():
    data = json.loads((ROOT / "dashboard/current_b200.json").read_text(encoding="utf-8"))
    # Explicit checks must also run under python -O.
    if set(data.get("epochs", {})) != {"2", "3", "4", "5"}:
        raise ValueError("저장 결과의 에폭 구성이 올바르지 않습니다.")
    for epoch, run in data["epochs"].items():
        cases = run.get("cases", [])
        if len(cases) != 10 or {case.get("case_index") for case in cases} != set(range(10)):
            raise ValueError("저장 결과의 평가 입력 10개가 일치하지 않습니다.")
        for case in cases:
            manifest = case.get("factory_manifest", {})
            if (case.get("test_sha256") != data["eval_sha256"]
                    or manifest.get("run_id") != run.get("run_id")
                    or manifest.get("trained_epoch") != int(epoch)):
                raise ValueError("저장 결과의 실행 ID·평가 해시·에폭이 일치하지 않습니다.")
    return data


def render():
    dashboard_auth.require_login(ROOT)
    data = load_snapshot()
    st.title("GrowPath · B200 저장 결과")
    st.caption("배포 버전 2026-10-22-b200 · 저장된 실제 실행 결과 기준 · Neon DB 실시간 연동은 다음 단계입니다.")
    st.info("수정 1,500건 전체 학습 · 별도 검증/보류 평가 분할 없음 · 같은 평가 입력 10개 × 2~5에폭 = 40건 비교 완료")
    st.caption("백업·SHA256 검증 완료 표시는 저장 자료의 기록이며, 현재 파일이나 원격 GPU를 재검증한 결과가 아닙니다.")
    st.warning("구조 검사 성공은 의미 품질 합격이 아닙니다. 최종 에폭은 실제 답변을 비교해 판단합니다.")
    overview, comparison, settings, report = st.tabs(["완료 현황", "실제 입력·답변 비교", "저장된 설정·프리셋", "종합 보고서"])
    with overview:
        st.caption("자료 확인 시점: " + data["observed_at"] + " · 자동 갱신되는 GPU 상태가 아닙니다.")
        st.dataframe([{"에폭":int(n), "학습":"완료", "비교":"10/10", "내용 검토":"완료" if r["content_reviewed"] else "대기", "가중치 백업":"SHA 검증 완료" if r["backup_verified"] else "미완료", "실행 ID":r["run_id"]} for n,r in data["epochs"].items()], hide_index=True)
        st.markdown(data["overall_review"])
        st.caption("2에폭 cosine 종료 후 optimizer/scheduler를 새로 시작해 3~5에폭 cosine 구간을 수행했습니다. 단일 5에폭 스케줄과 같지 않습니다. H100과 B200 비교는 GPU와 양자화 방식이 함께 바뀐 조건입니다.")
    with comparison:
        epoch = st.selectbox("학습 에폭", [n+"에폭" for n in data["epochs"]], index=3).replace("에폭", "")
        case_options = [f"사례 {i+1} · {data['case_titles'][i]}" for i in range(10)]
        index = case_options.index(st.selectbox("고정 평가 입력",case_options))
        run = data["epochs"][epoch]
        case = run["cases"][index]
        st.caption("실행 ID: " + run["run_id"] + " · 가중치 ID: " + case["factory_manifest"]["weight_id"])
        descriptions = [
            ("로드맵 생성 · 비용 우선 (6주)", "6주·주당 3시간(총 18h)·예산 2만원 조건에서 최소 RAG 시제품 로드맵 수립"),
            ("로드맵 생성 · 시간 우선 (8주)", "8주·주당 3시간(총 24h)·예산 2만원 조건에서 시간 우선 RAG 시제품 수립"),
            ("로드맵 생성 · 업무 적용 우선 (4주)", "4주·주당 3시간(총 12h) 조건에서 업무 산출물·검증 활동 중심 로드맵 수립"),
            ("자료 없는 직접 실습 (10주)", "10주·주당 2시간(총 20h)·무료 조건에서 성공 2건·실패 1건 재현 및 원인 기록"),
            ("경험·시작점 충돌 (5주)", "5주·주당 4시간(총 20h) 조건에서 Python 8년 경력과 시작점 3을 반영해 기초 반복 배제"),
            ("미확정 지원금 (7주)", "7주·주당 3시간(총 21h) 조건에서 미확정 지원금 3만원을 제외하고 현금 1만원 한도 준수"),
            ("풀사이클 업무 개선 로드맵 (12주)", "12주·주당 2시간(총 24h) 전주기 AI 업무 개선 4단계 로드맵 수립"),
            ("악성 문구 방어 (9주)", "9주·주당 3시간(총 27h)·예산 0원 조건에서 프롬프트 인젝션 방어 및 사용자 조건 유지"),
            ("부분 수정 · 시간 (6주)", "6주·주당 3시간(총 18h) 조건에서 요청한 두 단계의 시간만 바꾸고 나머지 필드·완료 기록 보존"),
            ("부분 수정 · 정기 업무 보고서 자동화 (8주)", "8주·주당 3시간(총 24h)·5만원 조건에서 사내 데이터 기반 정기 업무 보고서 자동 생성 시제품으로 개편"),
        ]
        prompt_type, purpose = descriptions[index]
        st.markdown("**입력 프롬프트 유형:** " + prompt_type)
        st.markdown("**검증 목적:** " + purpose)
        context = json.loads(case["messages"][-1]["content"])["user_context"]
        constraints = context["constraints"]
        st.caption(f"기간 {constraints['duration_weeks']}주 · 주당 {constraints['weekly_hours']}시간 · 예산 {constraints['budget_krw']:,}원 · 시작점 {constraints['start_stage']} · {context['perspective']}")
        with st.expander("전체 10개 입력 유형과 설명"):
            st.dataframe([{"사례":i+1,"프롬프트 유형":v[0],"간략 설명":v[1]} for i,v in enumerate(descriptions)],hide_index=True)
        st.subheader("실제 입력")
        request = json.loads(case["messages"][-1]["content"])
        st.json(request)
        with st.expander("시스템 지시 포함 전체 입력"):
            st.json(case["messages"])
        left, right = st.columns(2)
        for col, side, title in [(left,"base","원본 모델 답변"),(right,"tuned","학습 모델 답변")]:
            with col:
                st.subheader(title)
                result = case[side]
                st.caption(f"생성 {result['seconds']:.1f}초 · {result['tokens']}토큰 · 길이 제한 도달: {'예' if result['hit_token_limit'] else '아니오'}")
                st.json(json.loads(result["text"]))
                with st.expander("생성 원문"):
                    st.code(result["text"], language="json")
        if epoch == "5":
            st.info(data["epoch5_notes"][index])
        st.download_button("이 입력·원본·학습 답변 내려받기", json.dumps(case,ensure_ascii=False,indent=2), file_name=f"B200_epoch{epoch}_case{index}.json", mime="application/json")
    with settings:
        st.subheader("실제로 사용한 학습 조건")
        st.dataframe([{"항목":k,"값":str(v)} for k,v in data["settings"].items()], hide_index=True)
        st.caption("학습 1,200/검증 150/별도 평가 150은 이전 구성입니다. 이번 실험에는 수정 1,500건 모두를 사용했으며, 같은 10개는 출력 비교용입니다.")
        with st.expander("데이터 경로·SHA256"):
            st.json({"학습":"data/revision_1500/assembled/all.jsonl","학습 SHA256":data["data_sha256"],"평가":"data/eval/prompts.app_v2.jsonl","평가 SHA256":data["eval_sha256"]})
        preset_map = {p[0]+" · "+p[1]:p for p in data["presets"]}
        preset = preset_map[st.selectbox("P 프리셋 설정 확인",list(preset_map))]
        st.caption(preset[3])
        st.json({"learning_rate":0.0001, **preset[2]})
        st.caption("P02~P25는 최종 에폭 확정 후 동일 기본 모델에서 각각 독립 학습합니다. PT(학습률 0.0002)는 이 대기열에 포함하지 않습니다. 이 화면에서 실험을 중복 시작하지 않습니다.")
    with report:
        st.markdown(data["overall_review"])
        st.dataframe([{"사례":i+1,"5에폭 실제 내용 검토":note} for i,note in enumerate(data["epoch5_notes"])],hide_index=True)
        path=ROOT.parent/"docs/GrowPath_파인튜닝_데이터_작업보고서.html"
        if path.exists():
            st.download_button("기존 종합 HTML 보고서 내려받기",path.read_bytes(),file_name=path.name,mime="text/html")
        st.download_button("전체 40건 실제 비교 내려받기",json.dumps(data,ensure_ascii=False,indent=2),file_name="B200_P01_epoch2to5_actual_results.json",mime="application/json")


if __name__ == "__main__":
    render()
