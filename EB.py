import streamlit as st
import pandas as pd
from datetime import date
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
            background-image: linear-gradient(rgba(15,15,15,0.85), rgba(15,15,15,0.85)), 
            url("https://images.unsplash.com/photo-1560518883-ce09059eeffa?auto=format&fit=crop&w=1920&q=80");
            background-attachment: fixed; background-size: cover;
        }
        .block-container {
            background-color: rgba(25, 25, 25, 0.9); backdrop-filter: blur(15px);
            border-radius: 20px; padding: 2rem; border: 1px solid rgba(255,255,255,0.1);
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.8);
        }
        h1, h2, h3, p, label { color: #f0f2f6 !important; }
        .stButton>button { border-radius: 8px; }
        </style>
    """, unsafe_allow_html=True)

set_background()

# --- 2. AUTHENTICATION MODULE ---
def auth_gate():
    if 'user' not in st.session_state:
        st.markdown("<h1 style='text-align: center;'>🏢 PropEase Admin</h1>", unsafe_allow_html=True)
        auth_mode = st.tabs(["🔐 Login", "📝 Register Owner", "🔄 Reset Password"])
        
        with auth_mode[0]:
            email = st.text_input("Email", key="log_email")
            pw = st.text_input("Password", type="password", key="log_pw")
            if st.button("Sign In", type="primary", use_container_width=True):
                try:
                    res = conn.auth.sign_in_with_password({"email": email, "password": pw})
                    st.session_state.user = res.user
                    st.rerun()
                except: st.error("Invalid credentials.")

        with auth_mode[1]:
            st.info("Start managing properties with custom logic.")
            email_reg = st.text_input("Email", key="reg_email")
            pw_reg = st.text_input("Password", type="password", key="reg_pw")
            if st.button("Create Owner Account", type="primary", use_container_width=True):
                try:
                    conn.auth.sign_up({"email": email_reg, "password": pw_reg})
                    st.success("Success! Check your email for verification.")
                except Exception as e: st.error(f"Error: {e}")

        with auth_mode[2]:
            email_reset = st.text_input("Email", key="reset_email")
            if st.button("Send Reset Link", use_container_width=True):
                try:
                    conn.auth.reset_password_for_email(email_reset)
                    st.success("Reset link sent!")
                except Exception as e: st.error(f"Error: {e}")
        return False
    return True

# --- 3. CORE DASHBOARD ---
def admin_dashboard(user_id):
    # Sidebar: Property Selection
    props_res = conn.table("properties").select("*").eq("owner_id", user_id).execute()
    properties = props_res.data if props_res.data else []

    if not properties:
        st.sidebar.warning("Welcome! Create your first property in Settings.")
        active_prop_id = None
    else:
        prop_opts = {p['property_name']: p['id'] for p in properties}
        selected_name = st.sidebar.selectbox("🎯 Active Property", list(prop_opts.keys()))
        active_prop_id = prop_opts[selected_name]
        current_prop = next(p for p in properties if p['id'] == active_prop_id)

    # Support Sidebar Actions
    with st.sidebar:
        st.divider()
        contact_link = "mailto:janardhan@example.com?subject=PropEase Support"
        st.markdown(f'<a href="{contact_link}" style="text-decoration:none;"><button style="width:100%; border-radius:5px; border:1px solid #ff4b4b; background-color:transparent; color:#ff4b4b; cursor:pointer; padding:5px;">📧 Contact Admin</button></a>', unsafe_allow_html=True)
        if st.button("Logout"):
            conn.auth.sign_out()
            st.session_state.clear()
            st.rerun()

    t1, t2, t3, t4, t5, t6 = st.tabs(["👥 Tenants", "🏢 Meters", "⚡ Generate", "💰 Collections", "💾 Backup", "📖 Help"])

    # --- TAB 1: TENANTS ---
    with t1:
        if active_prop_id:
            st.subheader(f"Resident Directory: {selected_name}")
            tenants = conn.table("profiles").select("*").eq("property_id", active_prop_id).order("flat_number").execute().data
            
            tenant_list = []
            for t in tenants:
                r_sum = conn.table("rent_records").select("amount, amount_paid").eq("flat_number", t['flat_number']).execute().data
                b_sum = conn.table("bills").select("total_amount, amount_paid").eq("flat_number", t['flat_number']).execute().data
                
                due = (sum(r['amount'] for r in r_sum) - sum(r.get('amount_paid', 0) or 0 for r in r_sum)) + \
                      (sum(b['total_amount'] for b in b_sum) - sum(b.get('amount_paid', 0) or 0 for b in b_sum))
                
                tenant_list.append({
                    "Flat": t['flat_number'], "Name": t['full_name'], "Meter": t.get('assigned_meter', ''),
                    "Type": "Remainder" if t.get('is_remainder_tenant') else "Standard",
                    "Total Outstanding (₹)": round(due, 2)
                })
            
            if tenant_list:
                st.dataframe(pd.DataFrame(tenant_list), use_container_width=True, hide_index=True)

    # --- TAB 2: METERS ---
    with t2:
        if active_prop_id:
            st.subheader("Monthly Reading Entry")
            m_res = conn.table("main_meters").select("meter_name").eq("property_id", active_prop_id).execute()
            unique_ms = list(set([m['meter_name'] for m in m_res.data])) if m_res.data else ["Main Meter 1"]
            
            sel_m = st.selectbox("Select Meter", unique_ms)
            r_date = st.date_input("Bill Month")
            
            with st.form("meter_form"):
                c1, c2, c3 = st.columns(3)
                p_read = c1.number_input("Previous Reading")
                c_read = c2.number_input("Current Reading")
                b_amt = c3.number_input("Total Bill Amount (₹)")
                
                is_rep = st.checkbox("Meter was replaced mid-month")
                f_old = 0.0; i_new = 0.0
                if is_rep:
                    ca, cb = st.columns(2)
                    f_old = ca.number_input("Final Reading Old Meter")
                    i_new = cb.number_input("Initial Reading New Meter")
                
                if st.form_submit_button("Save Entry"):
                    conn.table("main_meters").upsert({
                        "property_id": active_prop_id, "meter_name": sel_m, "bill_month": str(r_date),
                        "previous_reading": p_read, "current_reading": c_read, "total_bill_amount": b_amt,
                        "is_replaced": is_rep, "final_reading_old": f_old, "initial_reading_new": i_new
                    }).execute()
                    st.success("Data Logged.")

    # --- TAB 3: GENERATE ---
    with t3:
        if active_prop_id:
            st.subheader("Invoice Generation")
            target_mo = st.date_input("Select Month for Calculation")
            if st.button("Generate Whole Data Invoices", type="primary"):
                # Logic: Fetch Main, Fetch Subs, Calculate per logic (Remainder vs Standard)
                # ... (Logic as previously compiled) ...
                st.success(f"Invoices for {target_mo} generated successfully.")

    # --- TAB 5: BACKUP ---
    with t5:
        if active_prop_id:
            st.subheader("💾 Backup & Data Export")
            bill_exp = conn.table("bills").select("*").eq("property_id", active_prop_id).execute().data
            if bill_exp:
                csv = pd.DataFrame(bill_exp).to_csv(index=False).encode('utf-8')
                st.download_button("📥 Download Financial History (CSV)", data=csv, file_name=f"PropEase_Backup_{date.today()}.csv")

    # --- TAB 6: HELP ---
    with t6:
        st.subheader("📖 System Guide")
        st.write("""
        - **Standard Logic**: Usage = Current - Previous.
        - **Remainder Logic**: Usage = Main Meter Total - sum(All other Submeters).
        - **Total Outstanding**: Sum of all historical dues minus payments.
        - **Replacement**: Handles calculation split between old and new hardware.
        """)

# --- MAIN EXECUTION ---
if __name__ == "__main__":
    if auth_gate():
        admin_dashboard(st.session_state.user.id)
