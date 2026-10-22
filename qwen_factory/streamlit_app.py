"""Current B200 results by default, with the historical control screen retained."""
from pathlib import Path
import runpy
import sys
import streamlit as st
root=Path(__file__).resolve().parent
sys.path.insert(0,str(root/"scripts"))
st.set_page_config(page_title="GrowPath · 실험실",layout="wide")
view=st.sidebar.selectbox("화면",["현재 B200 실제 결과","이전 실험 대기열·이력"])
if view=="현재 B200 실제 결과":
    from current_experiment_dashboard import render
    render()
else:
    st.warning("이전 1,200/150/150 데이터 구성의 제어 화면입니다. 현재 B200 실험 설정·결과는 현재 B200 실제 결과에서 확인하세요.")
    runpy.run_path(str(root/"scripts/local_dashboard.py"),run_name="__main__")
