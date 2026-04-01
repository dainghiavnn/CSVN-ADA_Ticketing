import streamlit as st
import pandas as pd
import datetime as dt
import uuid
import random
from sqlalchemy import create_engine

# --- BẢO HIỂM SESSION STATE (Chống lỗi KeyError khi F5) ---
if 'sys_log' not in st.session_state:
    st.session_state['sys_log'] = []
if 'tid' not in st.session_state:
    st.session_state['tid'] = f"MP-{dt.date.today().strftime('%d%m%y')}-{uuid.uuid4().hex[:4].upper()}"
if 'logged_in' not in st.session_state or not st.session_state['logged_in']:
    st.warning("Vui lòng đăng nhập lại tại trang chủ.")
    st.stop()

# CSS FIX LAYOUT & STYLE COMPLAINT
st.markdown("""
    <style>
        .block-container { padding-top: 1rem !important; max-width: 98% !important; }
        div[data-testid="stVerticalBlock"] > div { margin-bottom: -10px !important; }
        .stSelectbox, .stTextInput, .stMultiSelect, .stDateInput { margin-bottom: 8px !important; }
        label { font-size: 13px !important; font-weight: 600 !important; color: #444; }
        
        /* Style cho dòng chữ đỏ Customer Complaint */
        .complaint-text {
            color: red !important;
            font-size: 18px !important;
            font-weight: 900 !important;
            text-transform: uppercase !important;
            margin-left: -20px;
            margin-top: 5px;
        }
    </style>
""", unsafe_allow_html=True)

BRAND_ENABLED_STORES = {"Bách Hóa Unilever Official Store", "Unilever Premium Beauty", "KAO Official Store"}

# 1. LOAD CONFIG
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
        
    df_bs = to_df("brand_store")
    s_to_b = {}
    for _, r in df_bs.iterrows():
        s_to_b.setdefault(r["STORE"], []).append(r["BRAND_NAME"])

    df_tf = to_df("ticket_field")
    df_act = to_df("activity")
    
    return {
        "p_to_c": p_to_c, "pc_to_s": pc_to_s, "s_to_b": s_to_b,
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
    
    # ROW 1: CHANNEL & AGENT
    r1c1, r1c2 = st.columns(2)
    chan_opts = m["chans"]
    chat_idx = chan_opts.index("Chat") if "Chat" in chan_opts else 0
    channel = r1c1.selectbox("Channel *", options=chan_opts, index=chat_idx)
    agent = r1c2.text_input("Agent", value=st.session_state.get('agent_name', 'Unknown'), disabled=True)

    # ROW 3: ACTIVITY & RATING
    r3c1, r3c2 = st.columns(2)
    activity = r3c1.multiselect("Activity *", options=m["acts"], default=["INBOUND"])
    rating = r3c2.radio("Rating", ["1","2","3","4","5","No"], index=5, horizontal=True)
    
    # ROW 4: PLATFORM & CLIENT
    r4c1, r4c2 = st.columns(2)
    pl = r4c1.selectbox("Platform *", options=list(m["p_to_c"].keys()))
    cl = r4c2.selectbox("Client *", options=sorted(list(m["p_to_c"].get(pl, []))))
    
    # ROW 5: STORE & BRAND
    r5c1, r5c2 = st.columns(2)
    st_opts = sorted(list(m["pc_to_s"].get((pl, cl), set())))
    store = r5c1.selectbox("Store *", options=st_opts)
    is_brand_enable = store in BRAND_ENABLED_STORES
    br_opts = sorted(m["s_to_b"].get(store, [])) if is_brand_enable else []
    brand = r5c2.selectbox("Brand", options=br_opts, disabled=not is_brand_enable)
    
    # ROW 6: RELATED SKU (Nằm dưới dòng Store/Brand)
    sku = st.text_input("Related SKU", disabled=not is_brand_enable, placeholder="Nhập SKU nếu có...")
    
    # ROW 8: REASON PARENT (TRÁI) & DETAIL (PHẢI)
    r8c1, r8c2 = st.columns(2)
    rs_detail = r8c2.selectbox("Reason Detail *", options=sorted(m["d_to_r"].keys()), index=None, placeholder="🔍 Tìm lý do...")
    rs_parent = m["d_to_r"].get(rs_detail, "") if rs_detail else ""
    r8c1.text_input("Reason Parent", value=rs_parent, disabled=True)
    
    # ROW 9: CUSTOMER COMPLAINT (CHECKBOX VÀ CHỮ TRÊN 1 DÒNG)
    comp_col1, comp_col2 = st.columns([0.05, 0.95])
    with comp_col1:
        st.markdown("<div style='margin-top:10px;'></div>", unsafe_allow_html=True)
        is_cp = st.checkbox("", label_visibility="collapsed")
    with comp_col2:
        st.markdown('<p class="complaint-text">THIS IS A CUSTOMER COMPLAINT ?</p>', unsafe_allow_html=True)
    
    # ROW 7: OID & USER ID
    r7c1, r7c2 = st.columns(2)
    oid = r7c1.text_input("OID Reference")
    uid = r7c2.text_input("User ID *")
    
    # ROW 2: INQUIRY DATE & TIME (GOM CHUNG 1 DÒNG)
    r2c1, r2c2 = st.columns(2)
    inq_date = r2c1.date_input("Inquiry Date", value=dt.date.today(), format="DD/MM/YYYY")
    inq_time = r2c2.time_input("Inquiry Time", value=dt.datetime.now().time())

    if rs_detail: st.info(f"**Guide:** {m['d_to_e'].get(rs_detail, 'N/A')}")
    cmt = st.text_area("Comment / Description", height=60)

    # NÚT SUBMIT
    if st.button("Submit Ticket", type="primary", use_container_width=True):
        if not uid or not rs_detail:
            st.warning("⚠️ Vui lòng điền User ID và Lý do.")
        else:
            row = {
                "ticket_id": st.session_state['tid'], 
                "agent": st.session_state['agent_name'],
                "activity": ", ".join(activity), 
                "channel": channel, 
                "platform": pl, 
                "client": cl, 
                "store": store, 
                "oid": oid, 
                "user_id": uid, 
                "reason_detail": rs_detail, 
                "reason_parent": rs_parent, 
                "is_complaint": "Yes" if is_cp else "No",
                "comment": cmt, 
                "brand": brand if is_brand_enable else "", 
                "sku": sku if is_brand_enable else "",
                "inquiry_date": inq_date.strftime("%d/%m/%Y"),
                "inquiry_time": inq_time.strftime("%H:%M"),
                "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            try:
                pg_cfg = st.secrets["postgres"]
                engine = create_engine(f"postgresql://{pg_cfg['user']}:{pg_cfg['password']}@{pg_cfg['host']}:{pg_cfg['port']}/{pg_cfg['database']}")
                pd.DataFrame([row]).to_sql("master_logs", engine, if_exists='append', index=False)
                
                # QUOTES VUI VẺ
                vui_ve = [
                     "Em tuyệt dzời lắm 💞",
                "Ờ mây dzing! Gút chóp em! 😍",
                "Một chíu nữa thôi là clear xong cái shop rồi 😛",
                "Ê, làm đúng shop chưa đó ba?",
                "Nãy giờ đi đâu đó? 🤬🤬🤬",
                "Chat tiếp đi 🤨",
                "Tất cả là do Daniel 🤩",
                "Chị Uyên đẹp gái ha mấy đứa!😙",
                "Thẳng cái lưng lên 💢",
                "Ún mín nước đi rồi log tiếp! ☕",
                "Ai lớp Daniel 😘😘😘",
                "Đi *è đi 💦",
                "Tà tữa gì chưa người đẹp 🥛",
                "Coi chừng miss tin nhắn 😥 ",
                "Miss shop kìa má 🙃",
                "Shop nhỏ đừng quên 😫",
                "Cứu Thuận Phát/ Reckitt/ Nutifood/ Ensure/ Curel đi mấy níííííííí 😥",
                "Bảo vệ thận đi mậy!🚽🚽🚽",
                "Clear lẹ lẹ còn đi date mầy ôi 🙄!",
                "Nhiều tin quá, cíu bóe 🔥🔥🔥🚒🚒🚒",
                "Quên cái gì không đó mại 😗",
                "Mắt mở chưa đó 😳",
                "Mới vô ca mà mệt rồi hả mại 😪",
                "Còn sống không đó 😬",
                "Làm đúng quy trình chưa đó bé ơi 😑",
                "Nhìn lại lần nữa cho chắc 🧐",
                "Coi lại shop nhỏ dùm chị tui 😫",
                "Hơi lag đó, tỉnh lên 😤",
                "Nhìn kỹ tên shop hộ cái 😬",
                "Gần hết ca rồi, ráng 😭",
                "Senior đang theo dõi log đó 👀",
                "Đừng để Senior nhắc lần 3 😈",
                "Làm lẹ nhưng mà đừng ẩu nha mại 😑",
                "Lướt ít thôi má ơi 😑",
                "Cái này quen mà, làm đi 😌 Sai oánh đòn!",
                "Đừng có biến mất nha 😶‍🌫️",
                "Gì mà giỏi dữ vậy trời 😘😘😘",
                "Mượt như sunsilk 🧴",
                "Tự nhiên thấy tự hào dùm luôn á 😭",
                "Cái này mà không ổn thì cái gì ổn 😤",
                "Đừng có lịm ngang nha ní 😱",
                "Còn sống không, log cái nữa coi 😬",
                "Còn thở là còn Log 😎",
                "Log gì mà pro max dữ vị ⭐",
                "Mừi đỉm, khum lói nhèo ⭐⭐⭐"
                ]
                cau_random = random.choice(vui_ve)
                
                log_html = f"✅ **{st.session_state['tid']}** | {uid} <br> <span style='color:blue;'><i>- {cau_random}</i></span>"
                st.session_state['sys_log'].insert(0, log_html)
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
                st.markdown(item, unsafe_allow_html=True)
                st.markdown("<hr style='margin:0.2em 0; opacity:0.3;'>", unsafe_allow_html=True)
