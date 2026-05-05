import streamlit as st
import mysql.connector
import pandas as pd
from datetime import datetime, timedelta

# --- HOW TO RUN ---
# Open your VS Code terminal and type:
# python -m streamlit run Amore_Web_App.py

# --- Page Config ---
st.set_page_config(page_title="Amore Transient Apartment", layout="wide", page_icon="🏠")

# --- DATABASE & AUTH CONFIGURATION (SECURE VERSION) ---
# We pull credentials from Streamlit's Secret vault to keep your password off GitHub.
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

def init_db():
    """Creates the bookings table on Aiven if it doesn't exist yet."""
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id INT AUTO_INCREMENT PRIMARY KEY,
                guest_name VARCHAR(255) NOT NULL,
                phone_number VARCHAR(50),
                unit_room VARCHAR(100),
                checkin_date VARCHAR(20),
                checkin_time VARCHAR(20),
                checkout_date VARCHAR(20),
                checkout_time VARCHAR(20),
                status VARCHAR(50)
            )
        """)
        conn.commit()
        conn.close()
    except Exception as e:
        st.error(f"Cloud Connection Error: {e}")

# --- Custom Styling (#507d00 Green) ---
st.markdown(f"""
    <style>
    .main-header {{
        background-color: #507d00;
        padding: 30px;
        border-radius: 15px;
        color: white;
        text-align: center;
        margin-bottom: 25px;
        box-shadow: 0 4px 6px rgba(0,0,0,0.1);
    }}
    .stMetric {{
        background-color: #ffffff;
        padding: 15px;
        border-radius: 10px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        border: 1px solid #eee;
    }}
    div[data-testid="stForm"] {{
        border: 1px solid #e0e0e0;
        border-radius: 15px;
        padding: 20px;
        background-color: white;
    }}
    </style>
    <div class="main-header">
        <h1 style="margin:0; font-size: 2.5rem;">AMORE TRANSIENT APARTMENT</h1>
        <p style="margin:5px 0 0 0; opacity: 0.9;">Secure Cloud Management System</p>
    </div>
    """, unsafe_allow_html=True)

# --- Login Logic ---
if "logged_in" not in st.session_state:
    st.session_state.logged_in = False

if not st.session_state.logged_in:
    with st.sidebar:
        st.subheader("🔐 Staff Login")
        pwd = st.text_input("Enter Admin Password", type="password")
        if st.button("Login"):
            if pwd == APP_PASSWORD:
                st.session_state.logged_in = True
                st.rerun()
            else:
                st.error("Incorrect password.")
    st.info("Please login from the sidebar to access the booking system.")
    st.stop()

# --- Overlap Logic ---
def check_overlap(unit, in_dt, out_dt, exclude_id=None):
    buffer = timedelta(hours=2)
    try:
        conn = get_connection()
        cursor = conn.cursor(dictionary=True)
        query = "SELECT * FROM bookings WHERE unit_room = %s AND status != 'Checked-out'"
        if exclude_id:
            query += f" AND id != {exclude_id}"
        cursor.execute(query, (unit,))
        rows = cursor.fetchall()
        conn.close()

        for row in rows:
            exist_in = datetime.strptime(f"{row['checkin_date']} {row['checkin_time']}", "%m-%d-%Y %I:%M %p")
            exist_out = datetime.strptime(f"{row['checkout_date']} {row['checkout_time']}", "%m-%d-%Y %I:%M %p")
            if (in_dt < exist_out + buffer) and (out_dt > exist_in - buffer):
                return f"CONFLICT: Unit {unit} is occupied by {row['guest_name']}. 2-hour cleaning gap is required!"
        return None
    except: return None

# Initialize Cloud Table
init_db()

# --- App State ---
if "edit_id" not in st.session_state: st.session_state.edit_id = None
if "edit_val" not in st.session_state: st.session_state.edit_val = {}

# --- Sidebar ---
with st.sidebar:
    st.image("https://cdn-icons-png.flaticon.com/512/619/619034.png", width=80)
    st.write(f"Logged in as: **Admin**")
    if st.button("Logout"):
        st.session_state.logged_in = False
        st.rerun()
    
    st.divider()
    
    title = "✏️ Edit Record" if st.session_state.edit_id else "📝 New Booking"
    
    with st.form("main_form", clear_on_submit=False):
        st.subheader(title)
        g_val = st.session_state.edit_val.get('guest_name', "")
        p_val = st.session_state.edit_val.get('phone_number', "")
        u_val = st.session_state.edit_val.get('unit_room', "")
        
        guest = st.text_input("Guest Name", value=g_val)
        phone = st.text_input("Phone Number", value=p_val)
        unit = st.text_input("Unit/Room", value=u_val)
        
        c1, c2 = st.columns(2)
        in_date = c1.date_input("Check-in")
        in_time = c2.time_input("Time", value=datetime.strptime("14:00", "%H:%M").time())
        
        c3, c4 = st.columns(2)
        out_date = c3.date_input("Check-out")
        out_time = c4.time_input("Time", value=datetime.strptime("12:00", "%H:%M").time())
        
        status_options = ["Reserved", "Booked", "Checked-in", "Checked-out"]
        current_status = st.session_state.edit_val.get('status', "Reserved")
        def_status_idx = status_options.index(current_status) if current_status in status_options else 0
        
        status = st.selectbox("Status", status_options, index=def_status_idx)
        
        btn_label = "UPDATE CLOUD" if st.session_state.edit_id else "SAVE TO CLOUD"
        if st.form_submit_button(btn_label):
            if guest and unit:
                start_dt = datetime.combine(in_date, in_time)
                end_dt = datetime.combine(out_date, out_time)
                conflict = check_overlap(unit, start_dt, end_dt, exclude_id=st.session_state.edit_id)
                
                if conflict:
                    st.error(conflict)
                else:
                    try:
                        conn = get_connection(); cursor = conn.cursor()
                        if st.session_state.edit_id:
                            sql = "UPDATE bookings SET guest_name=%s, phone_number=%s, unit_room=%s, checkin_date=%s, checkin_time=%s, checkout_date=%s, checkout_time=%s, status=%s WHERE id=%s"
                            cursor.execute(sql, (guest, phone, unit, start_dt.strftime("%m-%d-%Y"), start_dt.strftime("%I:%M %p"), end_dt.strftime("%m-%d-%Y"), end_dt.strftime("%I:%M %p"), status, st.session_state.edit_id))
                        else:
                            sql = "INSERT INTO bookings (guest_name, phone_number, unit_room, checkin_date, checkin_time, checkout_date, checkout_time, status) VALUES (%s, %s, %s, %s, %s, %s, %s, %s)"
                            cursor.execute(sql, (guest, phone, unit, start_dt.strftime("%m-%d-%Y"), start_dt.strftime("%I:%M %p"), end_dt.strftime("%m-%d-%Y"), end_dt.strftime("%I:%M %p"), status))
                        conn.commit(); conn.close()
                        st.success("Synced with Aiven Cloud!")
                        st.session_state.edit_id = None; st.session_state.edit_val = {}
                        st.rerun()
                    except Exception as e: st.error(e)
            else: st.warning("Name and Unit are required.")

    if st.session_state.edit_id or any(st.session_state.edit_val.values()):
        if st.button("❌ Clear Form / Cancel Edit", use_container_width=True):
            st.session_state.edit_id = None; st.session_state.edit_val = {}; st.rerun()

# --- Main Board ---
try:
    conn = get_connection()
    df = pd.read_sql("SELECT * FROM bookings", conn)
    conn.close()

    if not df.empty:
        st.subheader("📊 Live Summary")
        m1, m2, m3 = st.columns(3)
        m1.metric("Reserved", len(df[df['status'] == 'Reserved']))
        m2.metric("Checked-in", len(df[df['status'] == 'Checked-in']))
        m3.metric("Total Active", len(df[df['status'] != 'Checked-out']))

        st.divider()
        
        # --- Sorting and Search Controls ---
        ctrl_col1, ctrl_col2, ctrl_col3 = st.columns([2, 1, 1])
        search = ctrl_col1.text_input("🔍 Search Table (Guest or Unit Number)")
        
        sort_map = {
            "ID Number": "id",
            "Guest Name": "guest_name",
            "Unit Number": "unit_room",
            "Check-in Date": "checkin_dt_obj",
            "Check-out Date": "checkout_dt_obj"
        }
        
        sort_by_label = ctrl_col2.selectbox("Sort By", list(sort_map.keys()))
        sort_order = ctrl_col3.selectbox("Order", ["Descending", "Ascending"])

        df['checkin_dt_obj'] = pd.to_datetime(df['checkin_date'], format='%m-%d-%Y')
        df['checkout_dt_obj'] = pd.to_datetime(df['checkout_date'], format='%m-%d-%Y')

        if search:
            df = df[df['guest_name'].str.contains(search, case=False) | df['unit_room'].str.contains(search, case=False)]
        
        df = df.sort_values(by=sort_map[sort_by_label], ascending=(sort_order == "Ascending"))
        display_df = df.drop(columns=['checkin_dt_obj', 'checkout_dt_obj'])
        
        st.dataframe(display_df, use_container_width=True, hide_index=True)

        st.divider()
        st.subheader("🛠️ Quick Actions")
        a1, a2, a3 = st.columns([2, 1, 1])
        
        booking_options = {f"{row['guest_name']} - {row['unit_room']} (ID: {row['id']})": row['id'] for idx, row in df.iterrows()}
        selected_label = a1.selectbox("Select a Booking to Edit or Delete", ["-- Select a Guest --"] + list(booking_options.keys()))
        
        if a2.button("✏️ LOAD FOR EDIT", use_container_width=True):
            if selected_label != "-- Select a Guest --":
                tid = booking_options[selected_label]
                row = df[df['id'] == tid]
                if not row.empty:
                    st.session_state.edit_id = tid
                    st.session_state.edit_val = row.iloc[0].to_dict()
                    st.rerun()
        
        if a3.button("🗑️ DELETE FOREVER", use_container_width=True):
            if selected_label != "-- Select a Guest --":
                tid = booking_options[selected_label]
                try:
                    conn = get_connection(); cursor = conn.cursor()
                    cursor.execute("DELETE FROM bookings WHERE id=%s", (tid,))
                    conn.commit(); conn.close()
                    st.warning(f"Booking removed from Cloud.")
                    st.rerun()
                except Exception as e:
                    st.error(e)
    else:
        st.info("The cloud database is currently empty.")
except Exception as e:
    st.error(f"Cloud Connection Failed: {e}")

st.caption("Amore Transient Apartment v2.6 | Secured Cloud Version")
