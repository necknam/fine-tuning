"""Current B200 results by default, with the historical control screen retained."""
from pathlib import Path
import runpy
import sys
import streamlit as st
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/"scripts"))
st.set_page_config(page_title="GrowPath · 실험실",layout="wide")
view=st.sidebar.selectbox("화면",["Qwen3.5-4B P01~P06 비교","학습·실전 보고서","B200 저장 결과 (27B)"])
if view=="Qwen3.5-4B P01~P06 비교":
    from qwen35_comparison_dashboard import render
    render()
elif view=="B200 저장 결과 (27B)":
    from current_experiment_dashboard import render
    render()
else:
    st.info("Cloud 파라미터 선택 → 학습 → 최신 DB 근거 조회 → 고정10개 입력 → RunPod 답변 → 보고서 저장·평가")
    runpy.run_path(str(root/"scripts/local_dashboard.py"),run_name="__main__")
