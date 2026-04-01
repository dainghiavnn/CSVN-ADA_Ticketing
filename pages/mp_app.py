import streamlit as st
import pandas as pd
import datetime as dt
import uuid
import time
import random
from sqlalchemy import create_engine, text
import gspread

# ===== CONFIGURATION & HYBRID SETUP =====
st.set_page_config(layout="wide", page_title="ADAHUB Unified v24.28 (Web)")

BRAND_ENABLED_STORES = {"Bách Hóa Unilever Official Store", "Unilever Premium Beauty", "KAO Official Store"}

# Lấy tên Agent hiện tại và trích xuất chữ cái đầu tiên (Viết hoa)
current_agent_name = st.session_state.get('agent_name', 'Unknown')
agent_char = current_agent_name[0].upper() if current_agent_name and current_agent_name != 'Unknown' else 'U'

# Khởi tạo session state cho Ticket ID và System Log để không bị mất khi reload
if 'sys_log' not in st.session_state:
    st.session_state['sys_log'] = []
# Tự động sinh mã Ticket ID (CSVN - Ngày tháng - Ký tự Agent - 6 mã Hex)
if 'tid' not in st.session_state:
    st.session_state['tid'] = f"CSVN-{dt.date.today().strftime('%d%m%y')}-{agent_char}-{uuid.uuid4().hex[:6].upper()}"

# CSS FIX LAYOUT & STYLE COMPLAINT
st.markdown("""
    <style>
        .block-container { padding-top: 1rem !important; max-width: 98% !important; }
        div[data-testid="stVerticalBlock"] > div { margin-bottom: -8px !important; }
        .stSelectbox, .stTextInput, .stMultiSelect, .stDateInput, .stRadio { margin-bottom: 5px !important; }
        
        /* IN ĐẬM VÀ LÀM RÕ TITLE CỦA CÁC TRƯỜNG NHẬP LIỆU */
        label, div[data-testid="stWidgetLabel"] p { 
            font-size: 14px !important; 
            font-weight: 800 !important; 
            color: #000 !important;      
        }
        
        /* Ép màu đỏ và in đậm trực tiếp cho chữ của ô tick Customer Complaint */
        div[data-testid="stCheckbox"] p {
            color: red !important;
            font-size: 16px !important;
            font-weight: 900 !important;
            text-transform: uppercase !important;
        }
        
        /* Đổi viền ô vuông thành đỏ */
        div[data-testid="stCheckbox"] div[role="checkbox"] {
            border-color: red !important;
        }
    </style>
""", unsafe_allow_html=True)

# ==========================================
# 1. LOAD CONFIG TỪ GOOGLE SHEETS (DÙNG CACHE)
# ==========================================
@st.cache_data(ttl=600) # Cache 10 phút để tránh bị limit API
def load_data_models():
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    sh = gc.open_by_url(st.secrets["DATA_SHEET_URL"])
    
    def to_df(n):
        try:
            ws = sh.worksheet(n)
            data = ws.get_all_records()
            return pd.DataFrame(data).astype(str).apply(lambda x: x.str.strip()) if data else pd.DataFrame()
        except: return pd.DataFrame()

    p_to_c, pc_to_s, s_to_b = {}, {}, {}
    
    df_cs = to_df("client_store")
    for _, r in df_cs.iterrows():
        p, c, s = r["PLATFORM"], r["CLIENT"], r["STORE"]
        p_to_c.setdefault(p, set()).add(c)
        pc_to_s.setdefault((p, c), set()).add(s)
        
    df_bs = to_df("brand_store")
    for _, r in df_bs.iterrows(): 
        s_to_b.setdefault(r["STORE"], []).append(r["BRAND_NAME"])
    
    df_tf = to_df("ticket_field")
    all_parents = sorted(set(df_tf["REASON"].tolist()))
    d_to_r = {r["REASON_DETAIL"]: r["REASON"] for _, r in df_tf.iterrows()}
    d_to_e = {r["REASON_DETAIL"]: r["REASON_EXP"] for _, r in df_tf.iterrows()}
    
    df_ag = to_df("agent_id")
    agent_list = df_ag["NAME"].unique().tolist() if not df_ag.empty else ["Agent_01"]
    
    df_act = to_df("activity")
    
    # BỘ LỌC THÉP LOẠI BỎ GIÁ TRỊ RỖNG
    valid_acts = [x for x in df_act["ACTIVITY"].unique() if str(x).strip() not in ["", "nan", "None"]] if not df_act.empty else ["INBOUND", "OUTBOUND"]
    valid_chans = [x for x in df_act["CHANNEL"].unique() if str(x).strip() not in ["", "nan", "None"]] if not df_act.empty else ["Chat", "Call"]
        
    return {
        "p_to_c": p_to_c, "pc_to_s": pc_to_s, "s_to_b": s_to_b, 
        "d_to_r": d_to_r, "d_to_e": d_to_e, "agents": agent_list, 
        "all_parents": all_parents, "activities": sorted(valid_acts), "channels": sorted(valid_chans)
    }

m = load_data_models()

# ==========================================
# 2. HÀM KẾT NỐI POSTGRESQL (STORAGE ENGINE)
# ==========================================
def get_pg_engine():
    pg = st.secrets["postgres"]
    conn_str = f"postgresql://{pg['user']}:{pg['password']}@{pg['host']}:{pg['port']}/{pg['database']}"
    return create_engine(conn_str)

def save_to_postgres(data_dict, table_name):
    engine = get_pg_engine()
    df = pd.DataFrame([data_dict])
    df.to_sql(table_name, engine, if_exists='append', index=False)

# ==========================================
# GIAO DIỆN CHÍNH (UI)
# ==========================================
st.title("ADAHUB Unified v24.28 (Web)")

# 3. DÀN TRANG (7:3) - Khôi phục lại dàn ô chuẩn
col_form, col_spacer, col_log = st.columns([6.8, 0.2, 3])

# ================= CỘT TRÁI (FORM NHẬP LIỆU) =================
with col_form:
    st.markdown("##### Master Log Entry")
    
    # ROW 1: INQUIRY DATE & TIME
    r1c1, r1c2 = st.columns(2)
    inq_date = r1c1.date_input("Inquiry Date", value=dt.date.today(), format="DD/MM/YYYY")
    inq_time = r1c2.text_input("Inquiry Time (VD: 1830 hoặc 18:30)", value=dt.datetime.now().strftime("%H:%M"))

    # ROW 2: CHANNEL & PLATFORM
    r2c1, r2c2 = st.columns(2)
    chan_opts = m["chans"]
    chat_idx = chan_opts.index("Chat") if "Chat" in chan_opts else 0
    channel = r2c1.selectbox("Channel *", options=chan_opts, index=chat_idx)
    pl = r2c2.selectbox("Platform *", options=list(m["p_to_c"].keys()))

    # ROW 3: ACTIVITY & RATING (2 Ô RADIO TRÊN CÙNG 1 DÒNG)
    r3c1, r3c2 = st.columns(2)
    acts_opts = m["activities"]
    inb_idx = acts_opts.index("INBOUND") if "INBOUND" in acts_opts else 0
    activity = r3c1.radio("Activity *", options=acts_opts, index=inb_idx, horizontal=True)
    rating = r3c2.radio("Rating", ["1","2","3","4","5","No"], index=5, horizontal=True)
    
    # ROW 4: CLIENT & STORE
    r4c1, r4c2 = st.columns(2)
    cl = r4c1.selectbox("Client *", options=sorted(list(m["p_to_c"].get(pl, []))))
    st_opts = sorted(list(m["pc_to_s"].get((pl, cl), set())))
    store = r4c2.selectbox("Store *", options=st_opts)
    
    # ROW 5: BRAND & RELATED SKU
    r5c1, r5c2 = st.columns(2)
    is_brand_enable = store in BRAND_ENABLED_STORES
    br_opts = sorted(m["s_to_b"].get(store, [])) if is_brand_enable else []
    brand = r5c1.selectbox("Brand", options=br_opts, disabled=not is_brand_enable)
    sku = r5c2.text_input("Related SKU", disabled=not is_brand_enable, placeholder="Nhập SKU nếu có...")

    # ROW 6: OID & USER ID
    r6c1, r6c2 = st.columns(2)
    oid = r6c1.text_input("OID Reference")
    uid = r6c2.text_input("User ID *")
    
    # ROW 7: REASON PARENT (TRÁI) & DETAIL (PHẢI)
    r7c1, r7c2 = st.columns(2)
    rs_detail = r7c2.selectbox("Reason Detail *", options=sorted(m["d_to_r"].keys()), index=None, placeholder="🔍 Tìm lý do...")
    rs_parent = m["d_to_r"].get(rs_detail, "") if rs_detail else ""
    r7c1.text_input("Reason Parent", value=rs_parent, disabled=True)
    
    # ROW 8: CUSTOMER COMPLAINT (CĂN GIỮA TUYỆT ĐỐI)
    st.markdown("<div style='margin-top: 15px;'></div>", unsafe_allow_html=True)
    space_left, center_col, space_right = st.columns([1, 2, 1])
    with center_col:
        is_cp = st.checkbox("THIS IS A CUSTOMER COMPLAINT ?")

    if rs_detail: st.info(f"**Guide:** {m['d_to_e'].get(rs_detail, 'N/A')}")
    cmt = st.text_area("Comment / Description", height=60)

    # NÚT SUBMIT
    if st.button("Submit Data", type="primary", use_container_width=True):
        if not uid or not rs_detail:
            st.warning("⚠️ Vui lòng điền User ID và Lý do.")
        else:
            # === LOGIC XỬ LÝ AUTO FORMAT GIỜ ===
            clean_time = inq_time.strip().replace(":", "").replace(" ", "")
            if len(clean_time) == 4 and clean_time.isdigit():
                final_time = f"{clean_time[:2]}:{clean_time[2:]}" # 1830 -> 18:30
            elif len(clean_time) == 3 and clean_time.isdigit():
                final_time = f"0{clean_time[0]}:{clean_time[1:]}" # 930 -> 09:30
            else:
                final_time = inq_time.strip()
            # ===================================
            
            row_data = {
                "ticket_id": st.session_state['tid'], 
                "agent": current_agent_name,
                "activity": activity, 
                "channel": channel, 
                "platform": pl, 
                "client": cl, 
                "store": store, 
                "rating": rating,
                "oid": oid, 
                "user_id": uid, 
                "reason_detail": rs_detail, 
                "reason_parent": rs_parent, 
                "is_complaint": "Yes" if is_cp else "No",
                "comment": cmt, 
                "brand": brand if is_brand_enable else "", 
                "sku": sku if is_brand_enable else "",
                "inquiry_date": inq_date.strftime("%d/%m/%Y"),
                "inquiry_time": final_time,
                "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            try:
                # Sử dụng hàm save_to_postgres từ logic mới
                save_to_postgres(row_data, "master_logs")
                
                vui_ve = [
                    "Em tuyệt dzời lắm 💞", "Ờ mây dzing! Gút chóp em! 😍",
                    "Một chíu nữa thôi là clear xong cái shop rồi 😛",
                    "Cứu Thuận Phát/ Reckitt/ Nutifood/ Ensure/ Curel đi mấy níííííííí 😥",
                    "Tất cả là do Daniel 🤩", "Chị Uyên đẹp gái ha mấy đứa!😙",
                    "Mừi đỉm, khum lói nhèo ⭐⭐⭐", "Đừng có lịm ngang nha ní 😱"
                ]
                cau_random = random.choice(vui_ve)
                
                log_html = f"✅ Logged: {st.session_state['tid']} | User ID: **{uid}** <br> <span style='color:blue;'><i>- {cau_random}</i></span>"
                st.session_state['sys_log'].insert(0, log_html)
                
                # Sinh mã Ticket mới kèm Ký tự Agent
                st.session_state['tid'] = f"CSVN-{dt.date.today().strftime('%d%m%y')}-{agent_char}-{uuid.uuid4().hex[:6].upper()}"
                st.rerun()
            except Exception as e: st.error(f"Lỗi DB: {e}")

# ================= CỘT PHẢI (HÀNH CHÍNH & LOG) =================
with col_log:
    st.markdown("##### System Info")
    st.text_input("Ticket ID", value=st.session_state['tid'], disabled=True)
    
    # Cho phép chọn Agent nếu chưa có (Lấy mảng Agent từ config)
    agent_idx = m["agents"].index(current_agent_name) if current_agent_name in m["agents"] else 0
    selected_agent = st.selectbox("Agent", options=m["agents"], index=agent_idx)
    
    # Lưu lại Agent nếu đổi
    if selected_agent != current_agent_name:
        st.session_state['agent_name'] = selected_agent
        st.rerun()
    
    st.markdown("<hr style='margin:0.5em 0;'>", unsafe_allow_html=True)
    st.markdown("##### System Log")
    log_box = st.container(height=450, border=True)
    with log_box:
        if not st.session_state['sys_log']:
            st.caption("Chưa có ca làm việc mới.")
        else:
            for item in st.session_state['sys_log']:
                st.markdown(item, unsafe_allow_html=True)
                st.markdown("<hr style='margin:0.2em 0; opacity:0.3;'>", unsafe_allow_html=True)
