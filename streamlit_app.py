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

# Khởi tạo session state cho Ticket ID và System Log để không bị mất khi reload
if 'tid' not in st.session_state:
    st.session_state['tid'] = f"CSVN-{dt.date.today().strftime('%d%m%y')}-{uuid.uuid4().hex[:6].upper()}"
if 'sys_log' not in st.session_state:
    st.session_state['sys_log'] = []

# ==========================================
# 1. LOAD CONFIG TỪ GOOGLE SHEETS (DÙNG CACHE)
# ==========================================
@st.cache_data(ttl=600) # Cache 10 phút để tránh bị limit API
def load_data_models():
    # Sử dụng Service Account JSON lưu trong st.secrets
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
    act_list = ["INBOUND", "OUTBOUND"]
    channels = []
    if not df_act.empty:
        act_list = sorted([str(x).strip() for x in df_act["ACTIVITY"].unique() if str(x).strip()])
        channels = sorted(df_act["CHANNEL"].unique())
        
    return {
        "p_to_c": p_to_c, "pc_to_s": pc_to_s, "s_to_b": s_to_b, 
        "d_to_r": d_to_r, "d_to_e": d_to_e, "agents": agent_list, 
        "all_parents": all_parents, "activities": act_list, "channels": channels
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

def get_escalation_by_oid(oid):
    engine = get_pg_engine()
    try:
        df = pd.read_sql(f"SELECT * FROM escalations WHERE oid = '{oid}'", engine)
        if not df.empty: return df.iloc[-1].to_dict() # Lấy record mới nhất
    except: pass
    return None


# ==========================================
# GIAO DIỆN CHÍNH (UI)
# ==========================================
st.title("ADAHUB Unified v24.28 (Web)")

tab1, tab2 = st.tabs(["Standard Master (1)", "Escalation Hub (2)"])

# ------------------------------------------
# TAB 1: STANDARD MASTER
# ------------------------------------------
with tab1:
    st.subheader("Master Log Entry")
    
    # Block 1: Thông tin chung
    c1, c2, c3, c4 = st.columns(4)
    with c1:
        tid = st.text_input("Ticket #", value=st.session_state['tid'], disabled=True)
        channel_index = m["channels"].index("Chat") if "Chat" in m["channels"] else 0
        channel = st.selectbox("Channel *", options=m["channels"], index=channel_index)
    with c2:
        agent = st.selectbox("Agent *", options=m["agents"])
        rating = st.radio("Rating (Reviews)", options=["1","2","3","4","5","No"], index=5, horizontal=True)
    with c3:
        activity = st.multiselect("Activity Type", options=m["activities"], default=["INBOUND"])
        inq_date = st.date_input("Inquiry Date", value=dt.date.today(), format="DD/MM/YYYY")
    with c4:
        inq_time = st.time_input("Inquiry Time", value=dt.datetime.now().time())
        st.markdown("<br>", unsafe_allow_html=True) # Spacer
        is_complaint = st.checkbox("THIS IS A CUSTOMER COMPLAINT ?", value=False)
        if is_complaint: st.error("🚨 Đã đánh dấu là Khiếu nại!")

    st.markdown("---")
    
    # Block 2: Logic Sync (Platform -> Client -> Store -> Brand)
    c_pl, c_cl, c_st, c_br = st.columns(4)
    
    pl = c_pl.selectbox("Platform *", options=list(m["p_to_c"].keys()))
    
    cl_options = sorted(list(m["p_to_c"].get(pl, [])))
    cl = c_cl.selectbox("Client *", options=cl_options)
    
    st_options = sorted(list(m["pc_to_s"].get((pl, cl), set())))
    store = c_st.selectbox("Store *", options=st_options)
    
    is_enable = store in BRAND_ENABLED_STORES
    br_options = sorted(m["s_to_b"].get(store, [])) if is_enable else []
    brand = c_br.selectbox("Brand", options=br_options, disabled=not is_enable)
    
    # Block 3: Details & OID
    c_sk, c_oid, c_uid, c_rs = st.columns(4)
    sku = c_sk.text_input("Related SKU", disabled=not is_enable)
    oid = c_oid.text_input("OID")
    uid = c_uid.text_input("User ID *")
    
    # Logic Sync: Reason Details -> Reason Parent
    dt_options = sorted(list(m["d_to_r"].keys()))
    rs_detail = c_rs.selectbox("Reason Details *", options=dt_options)
    rs_parent = m["d_to_r"].get(rs_detail, "")
    
    # Hiển thị Guideline
    st.info(f"**Contact Reason:** {rs_parent} &nbsp;|&nbsp; **Guide:** {m['d_to_e'].get(rs_detail, 'Waiting Selection.')}")
    
    cmt = st.text_area("Comment / Description", height=68)

    # Nút Bấm Submit & Xử lý Database
    if st.button("Submit Data", type="primary", use_container_width=True):
        if not uid.strip() or not rs_detail.strip():
            st.warning("Reason Details & User ID là bắt buộc.")
        else:
            vui_ve = [
                "Em tuyệt dzời lắm 💞", "Ờ mây dzing! Gút chóp em! 😍",
                "Một chíu nữa thôi là clear xong cái shop rồi 😛",
                "Cứu Thuận Phát/ Reckitt/ Nutifood/ Ensure/ Curel đi mấy níííííííí 😥",
                "Tất cả là do Daniel 🤩", "Chị Uyên đẹp gái ha mấy đứa!😙",
                "Mừi đỉm, khum lói nhèo ⭐⭐⭐", "Đừng có lịm ngang nha ní 😱"
            ]
            cau_random = random.choice(vui_ve)
            
            # Map dữ liệu để đưa vào Postgres
            row_data = {
                "ticket_id": tid, "agent": agent, "activity": ", ".join(activity),
                "channel": channel, "platform": pl, "client": cl, "store": store,
                "rating": rating, "reason_parent": rs_parent, "reason_detail": rs_detail,
                "is_complaint": "Yes" if is_complaint else "No", "brand": brand if is_enable else "",
                "sku": sku if is_enable else "", "oid": oid, "user_id": uid, "comment": cmt,
                "inquiry_date": inq_date.strftime("%d/%m/%Y"), "inquiry_time": inq_time.strftime("%H:%M"),
                "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            }
            
            try:
                save_to_postgres(row_data, "master_logs")
                
                # Cập nhật System Log nội bộ UI
                log_html = f"✅ Logged: {tid} | User ID: **{uid}** <br> <span style='color:blue'><i>- {cau_random}</i></span>"
                st.session_state['sys_log'].insert(0, log_html)
                
                # Cấp mã Ticket mới và refresh
                st.session_state['tid'] = f"CSVN-{dt.date.today().strftime('%d%m%y')}-{uuid.uuid4().hex[:6].upper()}"
                st.rerun() 
            except Exception as e:
                st.error(f"Lỗi hệ thống khi lưu Database: {e}")
    
    # Vùng hiển thị System Log
    st.markdown("### System Log")
    for log in st.session_state['sys_log'][:3]:
        st.markdown(log, unsafe_allow_html=True)
        st.divider()


# ------------------------------------------
# TAB 2: ESCALATION HUB
# ------------------------------------------
with tab2:
    st.subheader("Escalation Management")
    
    col_s1, col_s2 = st.columns([3, 1])
    search_oid = col_s1.text_input("Nhập OID Reference để kiểm tra Duplicate", key="esc_oid")
    
    is_update = False
    old_data = {}
    
    if search_oid:
        old_data = get_escalation_by_oid(search_oid)
        if old_data:
            is_update = True
            st.warning("⚠️ OID ĐÃ TỒN TẠI! Chuyển sang chế độ CẬP NHẬT RECORD (Update).")
        else:
            st.success("✅ OID mới. Đang ở chế độ TẠO ESCALATION MỚI (New).")

    with st.form("escalation_form"):
        e_c1, e_c2, e_c3 = st.columns(3)
        
        with e_c1:
            e_agt = st.selectbox("Agent", options=m["agents"])
            e_pl = st.selectbox("Platform", options=list(m["p_to_c"].keys()), disabled=is_update)
            e_st = st.text_input("Store Name", value=old_data.get("store", "") if is_update else "", disabled=is_update)
            e_uid = st.text_input("User ID", value=old_data.get("user_id", "") if is_update else "", disabled=is_update)
            e_ph = st.text_input("Phone #", value=old_data.get("phone", "") if is_update else "", disabled=is_update)
            
        with e_c2:
            e_cl = st.text_input("Client Entity", value=old_data.get("client", "") if is_update else "", disabled=is_update)
            e_ch = st.text_input("Channel Cont", value=old_data.get("channel", "") if is_update else "", disabled=is_update)
            e_name = st.text_input("Customer Name", value=old_data.get("name", "") if is_update else "", disabled=is_update)
            e_addr = st.text_input("Address", value=old_data.get("address", "") if is_update else "", disabled=is_update)
        
        with e_c3:
            cb_dept = st.text_input("Dept Escalate", value=old_data.get("dept", ""))
            cb_issue = st.text_input("Issue Type", value=old_data.get("issue_type", ""))
            cb_neg = st.text_input("Neg SKU/Cat", value=old_data.get("neg_sku", ""))
            cb_status = st.selectbox("Status", ["Open", "Pending", "Resolved", "Closed"])

        if is_update:
            st.text_area("Lịch sử CS Note", value=old_data.get("cs_note", ""), disabled=True, height=100)
        
        txt_update = st.text_area("Nội dung Cập nhật mới (CS Update)", height=100)
        
        sub_label = "CẬP NHẬT LỊCH SỬ" if is_update else "TẠO ESCALATION MỚI"
        submit_esc = st.form_submit_button(sub_label, type="primary")
        
        if submit_esc:
            if not search_oid.strip():
                st.error("Vui lòng nhập OID trước khi Submit.")
            else:
                date_tag = dt.date.today().strftime('%d/%m/%Y')
                formatted_entry = f"{date_tag}: {txt_update} - {e_agt}"
                
                engine = get_pg_engine()
                try:
                    if is_update:
                        new_note = str(old_data.get("cs_note", "")) + "\n" + formatted_entry
                        # Dùng Parameterized Query để chống SQL Injection
                        stmt = text("UPDATE escalations SET cs_note=:note, status=:st WHERE oid=:oid")
                        with engine.begin() as conn:
                            conn.execute(stmt, {"note": new_note, "st": cb_status, "oid": search_oid})
                        st.success("Đã nối Note vào Lịch sử thành công!")
                    else:
                        esc_data = {
                            "ticket_id": f"ECS-{int(time.time())}", "timestamp": dt.datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                            "agent": e_agt, "status": cb_status, "platform": e_pl, "client": e_cl, "store": e_st,
                            "issue_type": cb_issue, "channel": e_ch, "dept": cb_dept, "neg_sku": cb_neg,
                            "oid": search_oid, "user_id": e_uid, "name": e_name, "phone": e_ph, "address": e_addr,
                            "cs_note": formatted_entry
                        }
                        save_to_postgres(esc_data, "escalations")
                        st.success("Đã tạo mới Ticket Escalation vào DB thành công!")
                except Exception as e:
                    st.error(f"Lỗi Database: {e}")
