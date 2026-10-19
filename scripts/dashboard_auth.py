"""One shared entrance password; every authenticated visitor has equal access."""
import hashlib
import hmac
import secrets
import app_settings

def password(root):
    value=app_settings.get(root,'DASHBOARD_PASSWORD')
    return '' if value.startswith('REPLACE_WITH_') else value

def stamp(expected,nonce):
    return hmac.new(expected.encode('utf-8'),nonce.encode('utf-8'),hashlib.sha256).hexdigest()

def authenticated(root,state):
    expected=password(root)
    nonce=state.get('_entry_nonce','')
    saved=state.get('_entry_stamp','')
    return bool(expected and nonce and saved and hmac.compare_digest(saved,stamp(expected,nonce)))

def logout():
    import streamlit as st
    # Also discard in-memory Pod credentials and remote clients for this browser session.
    for key in list(st.session_state):del st.session_state[key]

def require_login(root):
    import streamlit as st
    if authenticated(root,st.session_state):
        with st.sidebar:
            st.caption('입장 완료 · 모든 사용자가 동일한 권한을 사용합니다.')
            st.button('나가기',key='entry_logout',on_click=logout)
        return
    st.title('GrowPath · 실험실 입장')
    expected=password(root)
    if not expected:
        st.info('Cloud Secrets 또는 로컬 .env에 DASHBOARD_PASSWORD를 설정하세요.')
        st.stop()
    def login():
        entered=st.session_state.get('_entry_password','')
        if hmac.compare_digest(entered.encode('utf-8'),password(root).encode('utf-8')):
            nonce=secrets.token_urlsafe(32)
            st.session_state['_entry_nonce']=nonce
            st.session_state['_entry_stamp']=stamp(password(root),nonce)
            st.session_state['_entry_error']=False
        else:
            st.session_state['_entry_error']=True
        st.session_state.pop('_entry_password',None)
    with st.form('entry_form',clear_on_submit=True):
        st.text_input('입장 비밀번호',type='password',key='_entry_password')
        st.form_submit_button('입장',type='primary',on_click=login)
    if st.session_state.get('_entry_error'):st.error('비밀번호가 맞지 않습니다.')
    st.stop()

def checkpoint(root):
    """Fragments can rerun without executing the page's initial password gate."""
    import streamlit as st
    if not authenticated(root,st.session_state):st.rerun(scope='app')
