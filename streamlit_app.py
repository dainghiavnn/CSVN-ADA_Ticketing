import streamlit as st
import pandas as pd
import gspread

# Cấu hình tab trình duyệt
st.set_page_config(layout="centered", page_title="ADAHUB Login")

if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False

# --- HÀM CHECK LOGIN ---
def check_login(email, password):
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    sh = gc.open_by_url(st.secrets["DATA_SHEET_URL"])
    df_ag = pd.DataFrame(sh.worksheet("agent_id").get_all_records())
    
    match = df_ag[(df_ag["MAIL"] == email) & (df_ag["PASS"] == str(password))]
    if not match.empty:
        st.session_state['logged_in'] = True
        st.session_state['agent_name'] = match.iloc[0]["NAME"]
        st.session_state['user_project'] = str(match.iloc[0].get("PROJECT", "")).strip().upper()
        return True
    return False

# --- GIAO DIỆN LOGIN ---
if not st.session_state['logged_in']:
    st.markdown("### 🔐 ADAHUB LOGIN")
    email = st.text_input("Email")
    pw = st.text_input("Password", type="password")
    if st.button("Login", type="primary", use_container_width=True):
        if check_login(email, pw): st.rerun()
        else: st.error("Sai tài khoản hoặc mật khẩu")
    st.stop()

# --- ĐIỀU HƯỚNG SAU KHI LOGIN ---
# Khai báo file mp_app.py nằm trong thư mục pages
page_mp = st.Page("pages/mp_app.py", title="Ticketing MP", icon="📝")

# Nếu User thuộc project MP hoặc là ADMIN thì cho thấy trang MP
pages_to_show = []
role = st.session_state['user_project']

if role in ["MP", "ADMIN"]:
    pages_to_show.append(page_mp)

if pages_to_show:
    st.sidebar.write(f"👤 {st.session_state['agent_name']}")
    if st.sidebar.button("Logout"):
        st.session_state.clear()
        st.rerun()
    pg = st.navigation(pages_to_show)
    pg.run()
else:
    st.error("Bạn không có quyền truy cập vào dự án này.")
