import streamlit as st
import pandas as pd
import gspread

# Cấu hình trang trung tâm
st.set_page_config(layout="centered", page_title="ADAHUB Unified Login")

# 1. Khởi tạo Session State
if 'logged_in' not in st.session_state:
    st.session_state['logged_in'] = False
if 'user_project' not in st.session_state:
    st.session_state['user_project'] = ""
if 'agent_name' not in st.session_state:
    st.session_state['agent_name'] = ""

# 2. Hàm kiểm tra đăng nhập từ Google Sheets
def check_login(email, password):
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    sh = gc.open_by_url(st.secrets["DATA_SHEET_URL"])
    df_ag = pd.DataFrame(sh.worksheet("agent_id").get_all_records())
    
    if not df_ag.empty:
        # Lọc dữ liệu theo MAIL và PASS
        match = df_ag[(df_ag["MAIL"] == email) & (df_ag["PASS"] == str(password))]
        if not match.empty:
            st.session_state['logged_in'] = True
            st.session_state['user_email'] = email
            st.session_state['agent_name'] = match.iloc[0]["NAME"]
            st.session_state['user_project'] = str(match.iloc[0].get("PROJECT", "")).strip().upper()
            return True
    return False

# 3. MÀN HÌNH LOGIN (Bị chặn ở đây nếu chưa đăng nhập)
if not st.session_state['logged_in']:
    st.markdown("<div style='height: 50px;'></div>", unsafe_allow_html=True)
    with st.container(border=True):
        st.markdown("### 🔐 ADAHUB UNIFIED LOGIN")
        email_input = st.text_input("Email")
        pass_input = st.text_input("Password", type="password")
        if st.button("Login", type="primary", use_container_width=True):
            if check_login(email_input, pass_input):
                st.rerun()
            else:
                st.error("Sai tài khoản hoặc mật khẩu.")
    st.stop() # Dừng toàn bộ code bên dưới

# 4. KHAI BÁO CÁC TRANG DỰ ÁN CÓ SẴN (Trong thư mục 'pages/')
page_csvn = st.Page("pages/csvn_ticket.py", title="Dự án CSVN", icon="📝")
page_loreal = st.Page("pages/loreal_ticket.py", title="Dự án L'OREAL", icon="💄")
page_mp = st.Page("pages/mp_app.py", title="Dự án MP", icon="💊") # Thêm trang MP ở đây

# 5. LOGIC PHÂN QUYỀN VÀ ĐIỀU HƯỚNG (DYNAMIC NAVIGATION)
pages_dict = {}
role = st.session_state['user_project']

if role == "ADMIN":
    # Admin thấy toàn bộ các project
    pages_dict["Quản lý Toàn phần (ADMIN)"] = [page_csvn, page_loreal, page_mp]
elif role == "CSVN":
    pages_dict["Workspace"] = [page_csvn]
elif role == "LOREAL":
    pages_dict["Workspace"] = [page_loreal]
elif role == "MP":
    # Phân quyền cho team MP
    pages_dict["Workspace"] = [page_mp]
else:
    st.error("Tài khoản của bạn chưa được phân bổ vào dự án nào hợp lệ.")
    st.stop()

# 6. Hiển thị thông tin User và nút Logout ở Sidebar
st.sidebar.markdown(f"**👤 {st.session_state['agent_name']}**")
st.sidebar.caption(f"Role: {role}")
if st.sidebar.button("Logout", use_container_width=True):
    st.session_state.clear()
    st.rerun()

# Kích hoạt bộ điều hướng của Streamlit
pg = st.navigation(pages_dict)
pg.run()
