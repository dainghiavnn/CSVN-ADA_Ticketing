import streamlit as st
import pandas as pd
import datetime as dt
import uuid
import random
from sqlalchemy import create_engine

# --- BẢO HIỂM SESSION STATE (Chống lỗi KeyError) ---
if 'sys_log' not in st.session_state:
    st.session_state['sys_log'] = []
if 'tid' not in st.session_state:
    st.session_state['tid'] = f"MP-{dt.date.today().strftime('%d%m%y')}-{uuid.uuid4().hex[:4].upper()}"
if 'logged_in' not in st.session_state or not st.session_state['logged_in']:
    st.warning("Vui lòng đăng nhập lại tại trang chủ.")
    st.stop()

# CSS FIX LAYOUT (Đảm bảo không bị sập và fit màn hình)
st.markdown("""
    <style>
        .block-container { padding-top: 1rem !important; max-width: 98% !important; }
        /* Giảm khoảng cách giữa các dòng widget để fit 1 màn hình */
        div[data-testid="stVerticalBlock"] > div { margin-bottom: -10px !important; }
        /* Fix khoảng cách cho các ô nhập liệu */
        .stSelectbox, .stTextInput, .stMultiSelect { margin-bottom: 8px !important; }
        /* Font size label */
        label { font-size: 13px !important; font-weight: 600 !important; color: #555; }
    </style>
""", unsafe_allow_html=True)

# 1. LOAD CONFIG (Cached)
@st.cache_data(ttl=600)
def load_config():
    import gspread
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    sh = gc.open_by_url(st.secrets["DATA_SHEET_URL"])
    def to_df(n):
        return pd.DataFrame(sh.worksheet(n).get_all_records()).astype(str).apply(lambda x: x.str.strip())
    
    df_cs = to_df("client_store")
    p_to_c, pc_to_s = {}, {}
    for _, r in df_cs.iterrows():
        p, c, s = r["PLATFORM"], r["CLIENT"], r["STORE"]
        p_to_c.setdefault(p, set()).add(c)
        pc_to_s.setdefault((p, c), set()).add(s)
        
    df_tf = to_df("ticket_field")
    df_act = to_df("activity")
    return {
        "p_to_c": p_to_c, "pc_to_s": pc_to_s, 
        "d_to_r": {r["REASON_DETAIL"]: r["REASON"] for _, r in df_tf.iterrows()},
        "d_to_e": {r["REASON_DETAIL"]: r["REASON_EXP"] for _, r in df_tf.iterrows()},
        "acts": sorted(df_act["ACTIVITY"].unique()) if not df_act.empty else ["INBOUND"],
        "chans": sorted(df_act["CHANNEL"].unique()) if not df_act.empty else ["Chat", "Call"]
    }

m = load_config()

# 2. DÀN TRANG (7:3)
col_form, col_spacer, col_log = st.columns([6.8, 0.2, 3])

with col_form:
    st.markdown("##### MP Ticketing Form")
    
    # --- DÒNG 1: CHANNEL & AGENT ---
    r1c1, r1c2 = st.columns(2)
    # Tìm index của "Chat" để làm mặc định
    chan_opts = m["chans"]
    chat_idx = chan_opts.index("Chat") if "Chat" in chan_opts else 0
    channel = r1c1.selectbox("Channel *", options=chan_opts, index=chat_idx)
    agent = r1c2.text_input("Agent", value=st.session_state.get('agent_name', 'Unknown'), disabled=True)
    
    # --- DÒNG 2: ACTIVITY & RATING ---
    r2c1, r2c2 = st.columns(2)
    activity = r2c1.multiselect("Activity *", options=m["acts"], default=["INBOUND"])
    rating = r2c2.radio("Rating", ["1","2","3","4","5","No"], index=5, horizontal=True)
    
    # --- DÒNG 3: PLATFORM & CLIENT ---
    r3c1, r3c2 = st.columns(2)
    pl = r3c1.selectbox("Platform *", options=list(m["p_to_c"].keys()))
    cl = r3c2.selectbox("Client *", options=sorted(list(m["p_to_c"].get(pl, []))))
    
    # --- DÒNG 4: STORE & COMPLAINT ---
    r4c1, r4c2 = st.columns(2)
    st_opts = sorted(list(m["pc_to_s"].get((pl, cl), set())))
    store = r4c1.selectbox("Store *", options=st_opts)
    with r4c2:
        st.markdown("<div style='margin-top:25px;'></div>", unsafe_allow_html=True)
        is_cp = st.checkbox("CUSTOMER COMPLAINT?", help="Tích vào nếu đây là khiếu nại")
    
    # --- DÒNG 5: OID REFERENCE & USER ID (GOM CHUNG) ---
    r5c1, r5c2 = st.columns(2)
    oid = r5c1.text_input("OID Reference")
    uid = r5c2.text_input("User ID *")
    
    # --- DÒNG 6: REASON DETAIL & REASON PARENT (GOM CHUNG) ---
    r6c1, r6c2 = st.columns(2)
    rs_detail = r6c1.selectbox("Reason Detail *", options=sorted(m["d_to_r"].keys()), index=None, placeholder="🔍 Tìm lý do...")
    rs_parent = m["d_to_r"].get(rs_detail, "") if rs_detail else ""
    r6c2.text_input("Reason Parent", value=rs_parent, disabled=True)

    # Hiển thị Guide nếu có
    if rs_detail: st.info(f"**Guide:** {m['d_to_e'].get(rs_detail, 'N/A')}")
    
    # --- DÒNG 7: COMMENT ---
    cmt = st.text_area("Comment / Description", height=60)

    # NÚT SUBMIT
    if st.button("Submit Ticket", type="primary", use_container_width=True):
        if not uid or not rs_detail:
            st.warning("⚠️ Vui lòng điền User ID và Lý do.")
        else:
            row = {
                "ticket_id": st.session_state['tid'], "agent": st.session_state['agent_name'],
                "activity": ", ".join(activity), "channel": channel, "platform": pl, "client": cl, 
                "store": store, "oid": oid, "user_id": uid, "reason_detail": rs_detail, 
                "reason_parent": rs_parent, "is_complaint": "Yes" if is_cp else "No",
                "comment": cmt, "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            try:
                pg_cfg = st.secrets["postgres"]
                engine = create_engine(f"postgresql://{pg_cfg['user']}:{pg_cfg['password']}@{pg_cfg['host']}:{pg_cfg['port']}/{pg_cfg['database']}")
                pd.DataFrame([row]).to_sql("master_logs", engine, if_exists='append', index=False)
                
                # Cập nhật log và reset ID
                st.session_state['sys_log'].insert(0, f"✅ {st.session_state['tid']} | {uid}")
                st.session_state['tid'] = f"MP-{dt.date.today().strftime('%d%m%y')}-{uuid.uuid4().hex[:4].upper()}"
                st.rerun()
            except Exception as e: st.error(f"Lỗi DB: {e}")

with col_log:
    st.markdown("##### System Log")
    log_box = st.container(height=620, border=True)
    with log_box:
        if not st.session_state['sys_log']:
            st.caption("Chưa có ca làm việc mới.")
        else:
            for item in st.session_state['sys_log']:
                st.write(item)
                st.markdown("<hr style='margin:0.2em 0; opacity:0.3;'>", unsafe_allow_html=True)
