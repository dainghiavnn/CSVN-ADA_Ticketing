import streamlit as st
import pandas as pd
import datetime as dt
import uuid
import random
from sqlalchemy import create_engine

# CSS ép giao diện không scroll
st.markdown("""
    <style>
        .block-container { padding-top: 1rem !important; padding-bottom: 0rem !important; max-width: 98% !important; }
        div[data-testid="stVerticalBlock"] > div { margin-bottom: -12px !important; }
    </style>
""", unsafe_allow_html=True)

# Lấy thông tin từ session_state (đã login ở app.py)
current_agent = st.session_state.get('agent_name', 'Unknown')

# 1. Load Data Config (GSheets)
@st.cache_data(ttl=600)
def load_mp_config():
    import gspread
    gc = gspread.service_account_from_dict(st.secrets["gcp_service_account"])
    sh = gc.open_by_url(st.secrets["DATA_SHEET_URL"])
    
    def to_df(n):
        ws = sh.worksheet(n)
        return pd.DataFrame(ws.get_all_records()).astype(str).apply(lambda x: x.str.strip())

    df_cs = to_df("client_store")
    p_to_c, pc_to_s = {}, {}
    for _, r in df_cs.iterrows():
        p, c, s = r["PLATFORM"], r["CLIENT"], r["STORE"]
        p_to_c.setdefault(p, set()).add(c)
        pc_to_s.setdefault((p, c), set()).add(s)
        
    df_tf = to_df("ticket_field")
    d_to_r = {r["REASON_DETAIL"]: r["REASON"] for _, r in df_tf.iterrows()}
    d_to_e = {r["REASON_DETAIL"]: r["REASON_EXP"] for _, r in df_tf.iterrows()}
    
    df_act = to_df("activity")
    return {
        "p_to_c": p_to_c, "pc_to_s": pc_to_s, "d_to_r": d_to_r, "d_to_e": d_to_e,
        "activities": sorted(df_act["ACTIVITY"].unique()) if not df_act.empty else ["INBOUND"],
        "channels": sorted(df_act["CHANNEL"].unique()) if not df_act.empty else ["Chat"]
    }

m = load_mp_config()
BRAND_STORES = ["Bách Hóa Unilever Official Store", "Unilever Premium Beauty", "KAO Official Store"]

# 2. Database Engine
def save_mp_data(data):
    pg = st.secrets["postgres"]
    engine = create_engine(f"postgresql://{pg['user']}:{pg['password']}@{pg['host']}:{pg['port']}/{pg['database']}")
    pd.DataFrame([data]).to_sql("master_logs", engine, if_exists='append', index=False)

# 3. UI Layout 7:3
col_form, _, col_log = st.columns([7, 0.2, 3])

with col_form:
    st.markdown("##### MP Ticketing Form")
    
    # Row 1: Channel & Agent (Agent tự điền & Khóa)
    r1c1, r1c2 = st.columns(2)
    channel = r1c1.selectbox("Channel *", options=m["channels"])
    agent = r1c2.text_input("Agent", value=current_agent, disabled=True)
    
    # Row 2: Activity & Rating
    r2c1, r2c2 = st.columns(2)
    activity = r2c1.multiselect("Activity *", options=m["activities"], default=["INBOUND"])
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
    cmt = st.text_area("Comment", height=60)

    if st.button("Submit Ticket", type="primary", use_container_width=True):
        if not uid or not rs_detail:
            st.warning("Thiếu User ID hoặc Lý do.")
        else:
            row = {
                "ticket_id": st.session_state['tid'], "agent": current_agent, "activity": ", ".join(activity),
                "channel": channel, "platform": pl, "client": cl, "store": store, "oid": oid, "user_id": uid,
                "reason_detail": rs_detail, "reason_parent": rs_parent, "is_complaint": "Yes" if is_cp else "No",
                "comment": cmt, "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            try:
                save_mp_data(row)
                st.session_state['sys_log'].insert(0, f"✅ {st.session_state['tid']} - {uid}")
                st.session_state['tid'] = f"MP-{dt.date.today().strftime('%d%m%y')}-{uuid.uuid4().hex[:4].upper()}"
                st.rerun()
            except Exception as e: st.error(f"Lỗi DB: {e}")

with col_log:
    st.markdown("##### System Log")
    log_box = st.container(height=550, border=True)
    with log_box:
        for l in st.session_state['sys_log']:
            st.write(l)
            st.divider()
