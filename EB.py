import streamlit as st
import pandas as pd
from datetime import date, datetime
from st_supabase_connection import SupabaseConnection
import uuid
import time

# --- 1. CONFIGURATION & STYLING ---
st.set_page_config(page_title="PropEase Admin", page_icon="🏢", layout="wide")
conn = st.connection("supabase", type=SupabaseConnection)

def set_background():
    st.markdown("""
        <style>
        .stApp {
            background-image: linear-gradient(rgba(15,15,15,0.9), rgba(15,15,15,0.9)), 
            url("https://images.unsplash.com/photo-1558441331-574b454e5827?auto=format&fit=crop&w=1920&q=80");
            background-attachment: fixed; background-size: cover;
        }
        .block-container {
            background-color: rgba(28, 28, 28, 0.95); backdrop-filter: blur(10px);
            border-radius: 15px; padding: 2rem; border: 1px solid rgba(255,255,255,0.1);
        }
        h1, h2, h3, p, label { color: #fdfdfd !important; }
        .stTabs [data-baseweb="tab-list"] { gap: 10px; }
        .stTabs [data-baseweb="tab"] {
            background-color: rgba(255,255,255,0.05); border-radius: 5px; padding: 10px 20px;
        }
        </style>
    """, unsafe_allow_html=True)

set_background()

# --- 2. AUTHENTICATION GATE ---
def auth_gate():
    if 'user' not in st.session_state:
        st.markdown("<h1 style='text-align: center;'>🏢 PropEase Admin</h1>", unsafe_allow_html=True)
        tabs = st.tabs(["🔐 Login", "📝 Register Owner", "🔄 Reset Password"])
        
        with tabs[0]:
            email = st.text_input("Email", key="l_email")
            pw = st.text_input("Password", type="password", key="l_pw")
            if st.button("Sign In", type="primary", use_container_width=True):
                try:
                    res = conn.auth.sign_in_with_password({"email": email, "password": pw})
                    st.session_state.user = res.user
                    st.rerun()
                except: st.error("Authentication failed.")

        with tabs[1]:
            st.info("Register as an owner to manage multiple properties.")
            r_email = st.text_input("Email", key="r_email")
            r_pw = st.text_input("Password", type="password", key="r_pw")
            if st.button("Create Account", type="primary", use_container_width=True):
                try:
                    conn.auth.sign_up({"email": r_email, "password": r_pw})
                    st.success("Verification email sent!")
                except Exception as e: st.error(str(e))

        with tabs[2]:
            reset_e = st.text_input("Email", key="res_email")
            if st.button("Send Reset Link", use_container_width=True):
                conn.auth.reset_password_for_email(reset_e)
                st.success("Check your inbox.")
        return False
    return True

# --- 3. ADMIN DASHBOARD ---
def admin_dashboard(user_id):
    # Sidebar: Global Actions
    st.sidebar.title("🏢 My Properties")
    p_res = conn.table("properties").select("*").eq("owner_id", user_id).execute()
    properties = p_res.data if p_res.data else []
    
    active_prop_id = None
    if properties:
        p_map = {p['property_name']: p['id'] for p in properties}
        sel_p = st.sidebar.selectbox("Select Active Property", list(p_map.keys()))
        active_prop_id = p_map[sel_p]
        current_p_data = next(p for p in properties if p['id'] == active_prop_id)
    
    with st.sidebar:
        st.divider()
        if st.button("🚪 Logout", use_container_width=True):
            conn.auth.sign_out()
            st.session_state.clear()
            st.rerun()

    # TABS (Settings is now always available at the end)
    t1, t2, t3, t4, t5, t6 = st.tabs(["👥 Tenants", "🏢 Meters", "⚡ Generate", "💰 Collections", "📖 Help", "⚙️ Settings"])

    # --- TAB 1: TENANTS ---
    with t1:
        if active_prop_id:
            st.subheader("Resident Registry & Dues")
            tenants = conn.table("profiles").select("*").eq("property_id", active_prop_id).execute().data
            
            t_display = []
            for t in tenants:
                # WHOLE DATA: SUM ALL HISTORY
                rents = conn.table("rent_records").select("amount, amount_paid").eq("flat_number", t['flat_number']).execute().data
                bills = conn.table("bills").select("total_amount, amount_paid").eq("flat_number", t['flat_number']).execute().data
                
                outstanding = (sum(r['amount'] for r in rents) - sum(r.get('amount_paid', 0) or 0 for r in rents)) + \
                              (sum(b['total_amount'] for b in bills) - sum(b.get('amount_paid', 0) or 0 for b in bills))
                
                t_display.append({
                    "Flat": t['flat_number'], "Name": t['full_name'], 
                    "Meter": t.get('assigned_meter', 'Unlinked'),
                    "Logic": "Remainder" if t.get('is_remainder_tenant') else "Standard",
                    "Total Outstanding (₹)": round(outstanding, 2)
                })
            
            if t_display:
                st.dataframe(pd.DataFrame(t_display), use_container_width=True, hide_index=True)
        else:
            st.warning("No property selected. Go to 'Settings' to add one.")

    # --- TAB 2: METERS ---
    with t2:
        if active_prop_id:
            st.subheader("Data Entry: Readings")
            # Logic to fetch named meters from property settings
            m_name = st.text_input("Meter Name (e.g. Ground Floor)")
            r_date = st.date_input("Read Date", value=date.today())
            
            with st.form("reading_entry"):
                col_a, col_b = st.columns(2)
                # CHAIN CONTINUITY: Fetching last month's current as this month's previous
                last_m = conn.table("main_meters").select("current_reading").eq("meter_name", m_name).order("bill_month", desc=True).limit(1).execute().data
                prev_val = last_m[0]['current_reading'] if last_m else 0.0
                
                prev = col_a.number_input("Previous Reading", value=float(prev_val))
                curr = col_b.number_input("Current Reading", min_value=prev)
                bill = st.number_input("Main Bill Amount (₹)", min_value=0.0)
                
                if st.form_submit_button("Save Reading"):
                    conn.table("main_meters").upsert({
                        "property_id": active_prop_id, "meter_name": m_name, "bill_month": str(r_date),
                        "previous_reading": prev, "current_reading": curr, "total_bill_amount": bill
                    }).execute()
                    st.success("Reading recorded.")

    # --- TAB 6: SETTINGS (Registration & Migration) ---
    with t6:
        st.subheader("⚙️ Building Setup Wizard")
        action = st.radio("Mode", ["Add New Property", "Edit Current Settings"], horizontal=True)
        
        with st.form("prop_config"):
            p_name = st.text_input("Property Name")
            e_mode = st.selectbox("Electricity Logic", ["Dynamic", "Fixed Rate"])
            w_mode = st.selectbox("Water Logic", ["Shared", "Fixed", "None"])
            
            if st.form_submit_button("🚀 Finalize Configuration"):
                payload = {
                    "owner_id": user_id, "property_name": p_name,
                    "electricity_billing_mode": e_mode, "water_billing_mode": w_mode
                }
                if action == "Add New Property":
                    conn.table("properties").insert(payload).execute()
                else:
                    conn.table("properties").update(payload).eq("id", active_prop_id).execute()
                st.success("Configuration Saved!")
                time.sleep(1)
                st.rerun()

# --- EXECUTION ---
if __name__ == "__main__":
    if auth_gate():
        admin_dashboard(st.session_state.user.id)
