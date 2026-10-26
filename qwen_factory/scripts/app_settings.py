"""Shared dashboard/worker settings: Cloud Secrets > environment > local .env."""
import os
import sys
from pathlib import Path
from dotenv import dotenv_values

KEYS = ('GROWPATH_DB_URL', 'DASHBOARD_PASSWORD', 'DATABASE_URL', 'DASHBOARD_STORAGE', 'HF_TOKEN', 'HF_REPO_ID',
        'OPENAI_API_KEY', 'OPENAI_EVAL_MODEL', 'RUNPOD_JUPYTER_URL',
        'RUNPOD_JUPYTER_TOKEN', 'RUNPOD_REMOTE_PATH')
SENSITIVE = ('GROWPATH_DB_URL', 'DASHBOARD_PASSWORD', 'DATABASE_URL', 'HF_TOKEN', 'OPENAI_API_KEY', 'RUNPOD_JUPYTER_TOKEN')

def cloud_values(root):
    # A running Streamlit app knows the deployment's configured secret locations.
    if 'streamlit' in sys.modules:
        import streamlit as st
        from streamlit.runtime.scriptrunner import get_script_run_ctx
        if get_script_run_ctx(suppress_warning=True) is not None:
            try:
                secrets = st.secrets.to_dict()
            except FileNotFoundError:
                return {}
            except Exception:
                raise RuntimeError('Cloud Secrets 형식을 확인하세요. 설정값은 로그에 표시하지 않습니다.') from None
            return {k: secrets[k] for k in KEYS if k in secrets}
    # Standalone workers can use a local Secrets file without importing Streamlit.
    path = Path(root)/'.streamlit/secrets.toml'
    if not path.exists(): return {}
    try:
        import tomllib
        with path.open('rb') as stream: secrets = tomllib.load(stream)
    except Exception:
        raise RuntimeError('secrets.toml 형식을 확인하세요. 설정값은 로그에 표시하지 않습니다.') from None
    return {k: secrets[k] for k in KEYS if k in secrets}

def read(root):
    values = {**dotenv_values(Path(root)/'.env'), **os.environ, **cloud_values(root)}
    for key in KEYS:
        value = values.get(key)
        if value is not None and not isinstance(value, str):
            raise RuntimeError(f'{key} 설정은 문자열이어야 합니다.')
    return values

def get(root, key, default=''):
    value = read(root).get(key)
    return default if value is None else value.strip()

def worker_environment(root):
    env = os.environ.copy()
    values = read(root)
    # Workers only require database access and OpenAI credentials, not HF/RunPod keys.
    for key in ('DATABASE_URL','DASHBOARD_STORAGE','OPENAI_API_KEY','OPENAI_EVAL_MODEL'):
        if key in values and values[key] is not None: env[key] = values[key]
    return env

def redact(root, text):
    # Hide effective values and shadowed local/env values as well.
    sources = (dotenv_values(Path(root)/'.env'), os.environ, cloud_values(root))
    for source in sources:
        for key in SENSITIVE:
            value = source.get(key)
            if isinstance(value,str) and value: text = text.replace(value,'[비밀값 숨김]')
    return text
