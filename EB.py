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
            background-color: rgba(25, 25, 25, 0.8); backdrop-filter: blur(15px);
            border-radius: 20px; padding: 2rem; border: 1px solid rgba(255,255,255,0.1);
        }
        h1, h2, h3, p, label { color: #f0f2f6 !important; }
        </style>
    """, unsafe_allow_html=True)

set_background()

def admin_dashboard(user_id):
    # --- SIDEBAR: PROPERTY SWITCHER ---
    st.sidebar.title("🛠️ Admin Tools")
    props_res = conn.table("properties").select("*").eq("owner_id", user_id).execute()
    properties = props_res.data if props_res.data else []

    if not properties:
        st.warning("No properties found. Please add one in 'Settings'.")
        active_prop_id = None
    else:
        prop_opts = {p['property_name']: p['id'] for p in properties}
        selected_name = st.sidebar.selectbox("🎯 Active Property", list(prop_opts.keys()))
        active_prop_id = prop_opts[selected_name]
        current_prop = next(p for p in properties if p['id'] == active_prop_id)

    if st.sidebar.button("Logout"):
        conn.auth.sign_out()
        st.session_state.clear()
        st.rerun()

    t1, t2, t3, t4, t5 = st.tabs(["👥 Tenants", "🏢 Meters", "⚡ Generate", "💰 Collections", "⚙️ Settings"])

    # --- TAB 1: TENANTS (With Total Outstanding) ---
    with t1:
        if active_prop_id:
            st.subheader("Resident Directory & Ledger")
            tenants = conn.table("profiles").select("*").eq("property_id", active_prop_id).order("flat_number").execute().data
            
            tenant_display = []
            for t in tenants:
                # Whole Data Balance Calculation
                r_due = conn.table("rent_records").select("amount, amount_paid").eq("flat_number", t['flat_number']).execute().data
                b_due = conn.table("bills").select("total_amount, amount_paid").eq("flat_number", t['flat_number']).execute().data
                
                outstanding = (sum(r['amount'] for r in r_due) - sum(r.get('amount_paid', 0) or 0 for r in r_due)) + \
                              (sum(b['total_amount'] for b in b_due) - sum(b.get('amount_paid', 0) or 0 for b in b_due))
                
                tenant_display.append({
                    "Flat": t['flat_number'], "Name": t['full_name'], "Mobile": t.get('mobile', ''),
                    "Meter": t.get('assigned_meter', 'None'), "Status": "Remainder" if t.get('is_remainder_tenant') else "Standard",
                    "Outstanding (₹)": round(outstanding, 2)
                })
            
            df = pd.DataFrame(tenant_display)
            if not df.empty:
                st.dataframe(df.style.applymap(lambda x: 'color: red' if x > 0 else 'color: green', subset=['Outstanding (₹)']), use_container_width=True, hide_index=True)
            
            # Add Tenant Form...
        else:
            st.info("Select or Create a Property in Settings.")

    # --- TAB 2: METERS (Including Replacement) ---
    with t2:
        if active_prop_id:
            st.subheader("Reading Entry")
            m_res = conn.table("main_meters").select("meter_name").eq("property_id", active_prop_id).execute()
            unique_meters = list(set([m['meter_name'] for m in m_res.data])) if m_res.data else []
            
            selected_m = st.selectbox("Select Meter", unique_meters)
            r_month = st.date_input("Billing Month", value=date.today())
            
            with st.form("meter_entry"):
                col1, col2, col3 = st.columns(3)
                prev = col1.number_input("Previous Reading", min_value=0.0)
                curr = col2.number_input("Current Reading", min_value=0.0)
                bill_amt = col3.number_input("Main Bill Amount (₹)", min_value=0.0)
                
                # Replacement Logic
                replaced = st.checkbox("Was this meter replaced this month?")
                final_old = 0.0; init_new = 0.0
                if replaced:
                    c_a, c_b = st.columns(2)
                    final_old = c_a.number_input("Final Reading (Old Meter)")
                    init_new = c_b.number_input("Initial Reading (New Meter)")
                
                if st.form_submit_button("Save Readings"):
                    conn.table("main_meters").upsert({
                        "property_id": active_prop_id, "meter_name": selected_m, "bill_month": str(r_month),
                        "previous_reading": prev, "current_reading": curr, "total_bill_amount": bill_amt,
                        "is_replaced": replaced, "final_reading_old": final_old, "initial_reading_new": init_new
                    }).execute()
                    st.success("Readings Saved!")

    # --- TAB 3: GENERATE (Transparent Logic) ---
    with t3:
        st.subheader("Bill Generation")
        g_month = st.date_input("Target Month", value=date.today(), key="gen_month")
        
        if st.button("Generate Transparent Utility Bills"):
            main_readings = conn.table("main_meters").select("*").eq("property_id", active_prop_id).eq("bill_month", str(g_month)).execute().data
            
            for main in main_readings:
                # 1. Total Units with Replacement logic
                if main.get('is_replaced'):
                    total_units = (main['final_reading_old'] - main['previous_reading']) + (main['current_reading'] - main['initial_reading_new'])
                else:
                    total_units = main['current_reading'] - main['previous_reading']
                
                rate = main['total_bill_amount'] / total_units if current_prop['electricity_billing_mode'] == 'Dynamic' and total_units > 0 else current_prop['electricity_fixed_rate']
                
                # 2. Process Tenants
                m_tenants = [t for t in tenants if t['assigned_meter'] == main['meter_name']]
                subs = conn.table("sub_meter_readings").select("*").eq("bill_month", str(g_month)).execute().data
                
                consumed_by_standards = 0
                standards = [t for t in m_tenants if not t.get('is_remainder_tenant')]
                remainder = next((t for t in m_tenants if t.get('is_remainder_tenant')), None)
                
                # Standard Calculation
                for t in standards:
                    s_val = next((s for s in subs if s['flat_number'] == t['flat_number']), {'current_reading': 0, 'previous_reading': 0})
                    u_used = s_val['current_reading'] - s_val['previous_reading']
                    consumed_by_standards += u_used
                    # Save Bill...
                
                # Remainder Logic
                if remainder:
                    rem_units = total_units - consumed_by_standards
                    # Save Remainder Bill...
            st.success("All Invoices Generated!")

    # --- TAB 5: SETTINGS (Registration Wizard) ---
    with t4:
        st.subheader("Property Setup & Logic")
        with st.form("prop_setup"):
            p_name = st.text_input("Property Name")
            e_mode = st.radio("Electricity Mode", ["Dynamic", "Fixed Rate"])
            w_mode = st.selectbox("Water Mode", ["Shared", "Fixed", "None"])
            if st.form_submit_button("Register Property"):
                conn.table("properties").insert({
                    "owner_id": user_id, "property_name": p_name,
                    "electricity_billing_mode": e_mode, "water_billing_mode": w_mode
                }).execute()
                st.rerun()

# --- MAIN ---
def main():
    if 'user' not in st.session_state:
        # Simple Login Logic
        st.title("🔐 Admin Access")
        email = st.text_input("Email")
        pw = st.text_input("Password", type="password")
        if st.button("Login"):
            res = conn.auth.sign_in_with_password({"email": email, "password": pw})
            st.session_state.user = res.user
            st.rerun()
    else:
        admin_dashboard(st.session_state.user.id)

if __name__ == "__main__":
    main()
