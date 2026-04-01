import streamlit as st
import pandas as pd
import gspread

st.set_page_config(layout="centered", page_title="Unified Login Hub")

# Khởi tạo session state
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'user_project' not in st.session_state:
    st.session_state['user_project'] = ""

# --- HÀM KIỂM TRA ĐĂNG NHẬP ---
def check_login(email, password):
    # Lấy data từ sheet agent_id
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    sh = gc.open_by_url(st.secrets["DATA_SHEET_URL"])
    df_ag = pd.DataFrame(sh.worksheet("agent_id").get_all_records())
    
    if not df_ag.empty:
        match = df_ag[(df_ag["MAIL"] == email) & (df_ag["PASS"] == str(password))]
        if not match.empty:
            st.session_state['logged_in'] = True
            st.session_state['user_email'] = email
            st.session_state['agent_name'] = match.iloc[0]["NAME"]
            # Lưu lại tên Project của user này (Lấy từ cột PROJECT trong sheet)
            st.session_state['user_project'] = match.iloc[0].get("PROJECT", "ADA") 
            return True
    return False

# --- MÀN HÌNH LOGIN ---
if not st.session_state['logged_in']:
    st.markdown("<div style='height: 50px;'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("### 🔐 UNIFIED HUB LOGIN")
        email_input = st.text_input("Email")
        pass_input = st.text_input("Password", type="password")
        if st.button("Login", type="primary", use_container_width=True):
            if check_login(email_input, pass_input):
                st.rerun()
            else:
                st.error("Sai tài khoản hoặc mật khẩu.")
    st.stop() # Dừng code tại đây nếu chưa login

# --- ĐIỀU HƯỚNG ĐỘNG (DYNAMIC ROUTING) ---
# Dựa vào tên project của user, Streamlit sẽ chỉ nạp đúng trang tương ứng
pages = {}

if st.session_state['user_project'] == "ADA":
    pages["Dự án ADA"] = [
        st.Page("pages/ada_ticket.py", title="ADA Master Log", icon="📝"),
        # st.Page("pages/ada_dashboard.py", title="Báo cáo ADA", icon="📊") # Mốt có thể thêm
    ]
elif st.session_state['user_project'] == "PROJECT_B":
    pages["Dự án B"] = [
        st.Page("pages/project_b_ticket.py", title="Project B Log", icon="📦")
    ]

# Gắn nút Logout vào sidebar
st.sidebar.markdown(f"**👤 {st.session_state['agent_name']}**")
if st.sidebar.button("Logout", use_container_width=True):
    st.session_state.clear()
    st.rerun()

# Khởi chạy hệ thống điều hướng
pg = st.navigation(pages)
pg.run()
