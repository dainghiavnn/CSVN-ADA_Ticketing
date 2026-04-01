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
    st.warning("Vui lòng đăng nhập lại.")
    st.stop()

# CSS FIX LAYOUT (Giãn cách hợp lý để không bị sập giao diện)
st.markdown("""
    <style>
        .block-container { padding-top: 1rem !important; max-width: 98% !important; }
        /* Khoảng cách giữa các dòng widget */
        div[data-testid="stVerticalBlock"] > div { margin-bottom: -8px !important; }
        /* Fix lỗi hiển thị cho các ô nhập liệu */
        .stSelectbox, .stTextInput, .stMultiSelect { margin-bottom: 5px !important; }
        /* Tối ưu hóa font chữ nhỏ hơn một chút để fit màn hình */
        label { font-size: 14px !important; font-weight: 500 !important; }
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
        "chans": sorted(df_act["CHANNEL"].unique()) if not df_act.empty else ["Chat"]
    }

m = load_config()

# 2. DÀN TRANG 2 CỘT (7:3)
col_form, col_spacer, col_log = st.columns([6.8, 0.2, 3])

with col_form:
    st.markdown("##### MP Ticketing Form")
    
    # Row 1: Channel & Agent (Disabled)
    r1c1, r1c2 = st.columns(2)
    channel = r1c1.selectbox("Channel *", options=m["chans"])
    agent = r1c2.text_input("Agent", value=st.session_state.get('agent_name', 'Unknown'), disabled=True)
    
    # Row 2: Activity & Rating
    r2c1, r2c2 = st.columns(2)
    activity = r2c1.multiselect("Activity *", options=m["acts"], default=["INBOUND"])
    rating = r2c2.radio("Rating", ["1","2","3","4","5","No"], index=5, horizontal=True)
    
    # Row 3: Platform & Client
    r3c1, r3c2 = st.columns(2)
    pl = r3c1.selectbox("Platform *", options=list(m["p_to_c"].keys()))
    cl = r3c2.selectbox("Client *", options=sorted(list(m["p_to_c"].get(pl, []))))
    
    # Row 4: Store & OID
    r4c1, r4c2 = st.columns(2)
    st_opts = sorted(list(m["pc_to_s"].get((pl, cl), set())))
    store = r4c1.selectbox("Store *", options=st_opts)
    oid = r4c2.text_input("OID Reference")
    
    # Row 5: User ID & Reason Detail (Searchable)
    r5c1, r5c2 = st.columns(2)
    uid = r5c1.text_input("User ID *")
    rs_detail = r5c2.selectbox("Reason Detail *", options=sorted(m["d_to_r"].keys()), index=None, placeholder="🔍 Tìm lý do...")
    
    # Row 6: Parent & Checkbox
    r6c1, r6c2 = st.columns(2)
    rs_parent = m["d_to_r"].get(rs_detail, "") if rs_detail else ""
    r6c1.text_input("Reason Parent", value=rs_parent, disabled=True)
    with r6c2:
        st.markdown("<div style='margin-top:28px;'></div>", unsafe_allow_html=True)
        is_cp = st.checkbox("CUSTOMER COMPLAINT?")

    if rs_detail: st.info(f"**Guide:** {m['d_to_e'].get(rs_detail, 'N/A')}")
    cmt = st.text_area("Comment", height=65)

    if st.button("Submit Ticket", type="primary", use_container_width=True):
        if not uid or not rs_detail:
            st.warning("⚠️ Điền thiếu User ID hoặc Lý do.")
        else:
            row = {
                "ticket_id": st.session_state['tid'], "agent": st.session_state['agent_name'],
                "activity": ", ".join(activity), "channel": channel, "platform": pl, "client": cl, 
                "store": store, "oid": oid, "user_id": uid, "reason_detail": rs_detail, 
                "reason_parent": rs_parent, "is_complaint": "Yes" if is_cp else "No",
                "comment": cmt, "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            try:
                pg = st.secrets["postgres"]
                engine = create_engine(f"postgresql://{pg['user']}:{pg['password']}@{pg['host']}:{pg['port']}/{pg['database']}")
                pd.DataFrame([row]).to_sql("master_logs", engine, if_exists='append', index=False)
                
                st.session_state['sys_log'].insert(0, f"✅ {st.session_state['tid']} | {uid}")
                st.session_state['tid'] = f"MP-{dt.date.today().strftime('%d%m%y')}-{uuid.uuid4().hex[:4].upper()}"
                st.rerun()
            except Exception as e: st.error(f"Lỗi DB: {e}")

with col_log:
    st.markdown("##### System Log")
    # Container log có thanh cuộn, fix chiều cao để khớp với form
    log_box = st.container(height=600, border=True)
    with log_box:
        if not st.session_state['sys_log']:
            st.caption("Chưa có log mới.")
        else:
            for l in st.session_state['sys_log']:
                st.write(l)
                st.markdown("<hr style='margin:0.3em 0;'>", unsafe_allow_html=True)
