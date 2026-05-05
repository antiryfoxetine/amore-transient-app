import streamlit as st
import mysql.connector
import pandas as pd
from datetime import datetime, timedelta
import urllib.parse
import os

# --- Page Config ---
st.set_page_config(page_title="Amore Transient Apartment", layout="wide", page_icon="🏠")

# --- DATABASE & AUTH CONFIGURATION ---
try:
    DB_CONFIG = {
        'host': st.secrets["mysql"]["host"],
        'port': int(st.secrets["mysql"]["port"]),
        'user': st.secrets["mysql"]["user"],
        'password': st.secrets["mysql"]["password"],
        'database': st.secrets["mysql"]["database"]
    }
    APP_PASSWORD = st.secrets["auth"]["password"]
except KeyError:
    st.error("Secrets not configured! Please add [mysql] and [auth] settings in Streamlit Cloud.")
    st.stop()

def get_connection():
    return mysql.connector.connect(**DB_CONFIG)

# --- Google Calendar Link Generator ---
def get_google_cal_link(guest, phone, unit, start_dt, end_dt, guests, is_long_term=False):
    base_url = "https://www.google.com/calendar/render?action=TEMPLATE"
    fmt = "%Y%m%dT%H%M%S"
    
    event_name = f"LONG-TERM: {guest} ({unit})" if is_long_term else f"AMORE: {guest} ({unit})"
    details = f"Guest: {guest}\nPhone: {phone}\nUnit: {unit}\nHeadcount: {guests} person(s)"
    if is_long_term: details += "\nStatus: Long-term Rental"
    details += "\n\nSynced via Amore Business Cloud"
    
    params = {
        "text": event_name,
        "dates": f"{start_dt.strftime(fmt)}/{end_dt.strftime(fmt)}",
        "details": details,
        "add": "none"
    }
    return f"{base_url}&{urllib.parse.urlencode(params)}"

# --- Login Logic ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    col_l1, col_l2, col_l3 = st.columns([1, 1, 1])
    with col_l2:
        if os.path.exists("logo.png"):
            st.image("logo.png", use_container_width=True)
        else:
            st.markdown("<h1 style='text-align: center;'>🏠</h1>", unsafe_allow_html=True)

    st.markdown("""
        <div style="text-align: center; padding-bottom: 20px;">
            <h1 style="color: #507d00; font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; margin-top: 0;">AMORE TRANSIENT APARTMENT</h1>
            <p style="color: #666;">Secure Management Portal</p>
        </div>
    """, unsafe_allow_html=True)
    
    col1, col2, col3 = st.columns([1, 1, 1])
    with col2:
        with st.form("login_form"):
            pwd = st.text_input("Enter Staff Password", type="password")
            if st.form_submit_button("Access Dashboard", use_container_width=True):
                if pwd == APP_PASSWORD:
                    st.session_state.logged_in = True
                    st.rerun()
                else:
                    st.error("Incorrect password.")
    st.stop()

# --- Custom Styling ---
st.markdown("""
    <style>
    .main-header {
        background-color: #507d00;
        padding: 25px;
        border-radius: 15px;
        color: white;
        text-align: center;
        margin-bottom: 25px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }
    .stMetric {
        background-color: white;
        padding: 15px;
        border-radius: 12px;
        border: 1px solid #f0f2f6;
    }
    div[data-testid="stForm"] {
        border-radius: 15px;
        background-color: white;
        border: 1px solid #eee;
    }
    </style>
    <div class="main-header">
        <h1 style="margin:0;">AMORE TRANSIENT APARTMENT</h1>
        <p style="margin:0; opacity: 0.8;">Business Management & Calendar Sync</p>
    </div>
    """, unsafe_allow_html=True)

# --- Overlap Logic ---
def check_overlap(unit, in_dt, out_dt, exclude_id=None, is_long_term=False):
    buffer = timedelta(hours=2)
    try:
        conn = get_connection(); cursor = conn.cursor(dictionary=True)
        query = "SELECT * FROM bookings WHERE unit_room = %s AND status != 'Checked-out'"
        if exclude_id: query += f" AND id != {exclude_id}"
        cursor.execute(query, (unit,))
        rows = cursor.fetchall(); conn.close()

        for row in rows:
            exist_in = datetime.strptime(f"{row['checkin_date']} {row['checkin_time']}", "%m-%d-%Y %I:%M %p")
            if row['checkout_date'] == "Long-term":
                if out_dt > exist_in - buffer:
                    return f"CONFLICT: Unit {unit} has a Long-term resident ({row['guest_name']})."
                continue
            exist_out = datetime.strptime(f"{row['checkout_date']} {row['checkout_time']}", "%m-%d-%Y %I:%M %p")
            if (in_dt < exist_out + buffer) and (out_dt > exist_in - buffer):
                return f"CONFLICT: Unit {unit} is busy with {row['guest_name']}."
        return None
    except: return None

# --- Sidebar ---
with st.sidebar:
    if os.path.exists("logo.png"): st.image("logo.png", use_container_width=True)
    else: st.image("https://cdn-icons-png.flaticon.com/512/619/619034.png", width=100)
    
    st.write("Logged in: **Business Admin**")
    if st.button("Logout", use_container_width=True):
        st.session_state.logged_in = False
        st.rerun()
    
    st.divider()
    st.markdown("[🗓️ View Google Calendar](https://calendar.google.com/calendar/u/0/r/month)", unsafe_allow_html=True)
    st.divider()
    
    if "edit_id" not in st.session_state: st.session_state.edit_id = None
    if "edit_val" not in st.session_state: st.session_state.edit_val = {}
    
    title = "✏️ Edit Booking" if st.session_state.edit_id else "➕ New Booking"
    with st.form("main_form", clear_on_submit=False):
        st.subheader(title)
        guest = st.text_input("Guest Name", value=st.session_state.edit_val.get('guest_name', ""))
        phone = st.text_input("Phone Number", value=st.session_state.edit_val.get('phone_number', ""))
        guests_head = st.number_input("Number of Guests (Per head)", min_value=1, step=1, value=int(st.session_state.edit_val.get('num_guests', 1)))
        unit = st.text_input("Unit/Room", value=st.session_state.edit_val.get('unit_room', ""))
        
        c1, c2 = st.columns(2)
        in_date = c1.date_input("Check-in", format="MM/DD/YYYY")
        in_time = c2.time_input("Time", value=datetime.strptime("14:00", "%H:%M").time())
        
        is_lt = (st.session_state.edit_val.get('checkout_date') == "Long-term")
        long_term = st.checkbox("Long-term Rental (No fixed check-out)", value=is_lt)
        
        c3, c4 = st.columns(2)
        out_date = c3.date_input("Check-out", format="MM/DD/YYYY", disabled=long_term)
        out_time = c4.time_input("Time", value=datetime.strptime("12:00", "%H:%M").time(), disabled=long_term)
        
        status_opts = ["Reserved", "Booked", "Checked-in", "Checked-out", "Long-term"]
        def_status = "Long-term" if long_term else st.session_state.edit_val.get('status', "Reserved")
        status = st.selectbox("Status", status_opts, index=status_opts.index(def_status) if def_status in status_opts else 0, disabled=long_term)
        
        if st.form_submit_button("SAVE TO CLOUD", use_container_width=True):
            if guest and unit:
                start_dt = datetime.combine(in_date, in_time)
                if long_term:
                    end_dt = start_dt + timedelta(days=3650)
                    cout_d, cout_t, f_status = "Long-term", "N/A", "Long-term"
                else:
                    end_dt = datetime.combine(out_date, out_time)
                    cout_d, cout_t, f_status = end_dt.strftime("%m-%d-%Y"), end_dt.strftime("%I:%M %p"), status
                
                conflict = check_overlap(unit, start_dt, end_dt, exclude_id=st.session_state.edit_id, is_long_term=long_term)
                if conflict: st.error(conflict)
                else:
                    try:
                        conn = get_connection(); cursor = conn.cursor()
                        if st.session_state.edit_id:
                            sql = "UPDATE bookings SET guest_name=%s, phone_number=%s, num_guests=%s, unit_room=%s, checkin_date=%s, checkin_time=%s, checkout_date=%s, checkout_time=%s, status=%s WHERE id=%s"
                            cursor.execute(sql, (guest, phone, guests_head, unit, start_dt.strftime("%m-%d-%Y"), start_dt.strftime("%I:%M %p"), cout_d, cout_t, f_status, st.session_state.edit_id))
                        else:
                            sql = "INSERT INTO bookings (guest_name, phone_number, num_guests, unit_room, checkin_date, checkin_time, checkout_date, checkout_time, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)"
                            cursor.execute(sql, (guest, phone, guests_head, unit, start_dt.strftime("%m-%d-%Y"), start_dt.strftime("%I:%M %p"), cout_d, cout_t, f_status))
                        conn.commit(); conn.close()
                        st.session_state.edit_id = None; st.session_state.edit_val = {}; st.rerun()
                    except Exception as e: st.error(f"Error: {e}")

    if st.button("❌ Clear Form", use_container_width=True):
        st.session_state.edit_id = None; st.session_state.edit_val = {}; st.rerun()
    st.caption("v3.8 | MM-DD-YYYY & Headcount Ready")

# --- Dashboard ---
try:
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM bookings", conn)
    conn.close()

    if not df.empty:
        # Metrics Row
        m1, m2, m3, m4, m5 = st.columns(5)
        m1.metric("Occupied", len(df[df['status'] == 'Checked-in']))
        m2.metric("Upcoming", len(df[df['status'] == 'Reserved']))
        m3.metric("Monthly Tenants", len(df[df['status'] == 'Long-term']))
        m4.metric("Active Units", df[df['status'] != 'Checked-out']['unit_room'].nunique())
        m5.metric("Total Records", len(df))

        st.divider()
        c_left, c_right = st.columns([2, 1])
        with c_left:
            st.subheader("📈 Occupancy Insights")
            st.bar_chart(df['unit_room'].value_counts(), color="#507d00")
        with c_right:
            st.subheader("📊 Business Data")
            csv = df.to_csv(index=False).encode('utf-8')
            st.download_button("📥 Export to Excel/CSV", data=csv, file_name="amore_records.csv", use_container_width=True)

        st.divider()
        st.subheader("📋 Booking Ledger")
        
        ctrl1, ctrl2, ctrl3 = st.columns([2, 1, 1])
        search = ctrl1.text_input("🔍 Search")
        sort_map = {"UNIT": "unit_room", "GUEST": "guest_name", "GUESTS (HEAD)": "num_guests", "CHECK IN": "checkin_dt_obj", "STATUS": "status"}
        sort_by = ctrl2.selectbox("Sort By", list(sort_map.keys()))
        sort_order = ctrl3.selectbox("Order", ["Ascending", "Descending"])

        df['checkin_dt_obj'] = pd.to_datetime(df['checkin_date'], format='%m-%d-%Y')
        if search: df = df[df['guest_name'].str.contains(search, case=False) | df['unit_room'].str.contains(search, case=False)]
        df = df.sort_values(by=sort_map.get(sort_by, 'checkin_dt_obj'), ascending=(sort_order == "Ascending"))

        # Final table layout
        display_df = df[[
            'unit_room', 'guest_name', 'phone_number', 'num_guests',
            'checkin_date', 'checkin_time', 'checkout_date', 'checkout_time', 'status'
        ]].rename(columns={
            'unit_room': 'UNIT', 'guest_name': 'GUEST', 'phone_number': 'PHONE NUMBER',
            'num_guests': 'GUESTS (HEAD)', 'checkin_date': 'CHECK IN DATE', 'checkin_time': 'CHECK IN TIME',
            'checkout_date': 'CHECK OUT DATE', 'checkout_time': 'CHECK OUT TIME', 'status': 'STATUS'
        })
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        # Tools
        st.divider()
        st.subheader("🛠️ Management Tools")
        q1, q2, q3 = st.columns([2, 1, 1])
        booking_options = {f"{r['guest_name']} - {r['unit_room']} (ID: {r['id']})": r['id'] for _, r in df.iterrows()}
        selected_label = q1.selectbox("Select Record", ["-- Select Guest --"] + list(booking_options.keys()))
        
        if selected_label != "-- Select Guest --":
            tid = booking_options[selected_label]; row = df[df['id'] == tid].iloc[0]
            s_dt = datetime.strptime(f"{row['checkin_date']} {row['checkin_time']}", "%m-%d-%Y %I:%M %p")
            is_lt = (row['checkout_date'] == "Long-term")
            e_dt = s_dt + timedelta(days=30) if is_lt else datetime.strptime(f"{row['checkout_date']} {row['checkout_time']}", "%m-%d-%Y %I:%M %p")
            
            cal_url = get_google_cal_link(row['guest_name'], row['phone_number'], row['unit_room'], s_dt, e_dt, row.get('num_guests', 1), is_lt)
            q2.markdown(f'<a href="{cal_url}" target="_blank" style="text-decoration:none;"><button style="width:100%; height:45px; border-radius:10px; background-color:#4285F4; color:white; border:none; cursor:pointer; font-weight:bold;">📅 SYNC CALENDAR</button></a>', unsafe_allow_html=True)
            
            if q3.button("🗑️ DELETE", use_container_width=True):
                conn = get_connection(); cursor = conn.cursor()
                cursor.execute("DELETE FROM bookings WHERE id=%s", (tid,))
                conn.commit(); conn.close(); st.rerun()
            if st.button("✏️ LOAD FOR EDIT", use_container_width=True):
                st.session_state.edit_id = tid; st.session_state.edit_val = row.to_dict(); st.rerun()
    else: st.info("Cloud is empty.")
except Exception as e: st.error(f"Error: {e}")
st.caption("Amore Transient Apartment v3.8 | Ry Edition")