"""Streamlit Community Cloud entry point; also usable locally."""
from pathlib import Path
import runpy

runpy.run_path(str(Path(__file__).resolve().parent/'scripts/local_dashboard.py'),run_name='__main__')
