import streamlit as st
import pandas as pd
from datetime import date
from st_supabase_connection import SupabaseConnection
import random
import math
import time

# --- 1. CONFIGURATION & STYLING ---
st.set_page_config(page_title="PropEase Manager", page_icon="🏢", layout="wide")
conn = st.connection("supabase", type=SupabaseConnection)

def set_background():
    # DARK Frosted Glass UI for maximum readability
    st.markdown(
        """
        <style>
        .stApp {
            background-image: linear-gradient(rgba(15, 15, 15, 0.8), rgba(15, 15, 15, 0.8)), url("https://images.unsplash.com/photo-1560518883-ce09059eeffa?ixlib=rb-4.0.3&auto=format&fit=crop&w=1920&q=80");
            background-attachment: fixed;
            background-size: cover;
        }
        .block-container {
            background-color: rgba(30, 30, 30, 0.6);
            backdrop-filter: blur(12px);
            border-radius: 20px;
            padding: 2rem 3rem;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.7);
            margin-top: 2rem;
            margin-bottom: 2rem;
            border: 1px solid rgba(255, 255, 255, 0.1);
        }
        div[data-baseweb="input"], div[data-baseweb="select"], .stTextArea textarea {
            background-color: rgba(255, 255, 255, 0.05) !important;
            color: white !important;
        }
        h1, h2, h3, p, label { color: white !important; }
        </style>
        """,
        unsafe_allow_html=True
    )

set_background()

# --- 2. AUTHENTICATION & HELPERS ---
def generate_captcha():
    if 'captcha_num1' not in st.session_state:
        st.session_state.captcha_num1 = random.randint(1, 10)
        st.session_state.captcha_num2 = random.randint(1, 10)
    return st.session_state.captcha_num1, st.session_state.captcha_num2

def ensure_profile_exists(user_id, email):
    try:
        resp = conn.table("profiles").select("*").eq("id", user_id).execute()
        if not resp.data:
            conn.table("profiles").insert({
                "id": user_id, "email": email, "full_name": "User", "role": "tenant", "num_people": 0, "rent_amount": 0
            }).execute()
            resp = conn.table("profiles").select("*").eq("id", user_id).execute()
        return resp.data[0]
    except:
        return None

@st.dialog("⚠️ Confirm Logout")
def show_logout_dialog():
    st.write("Are you sure you want to end your session?")
    c1, c2 = st.columns(2)
    if c1.button("✅ Yes, Logout", use_container_width=True):
        conn.auth.sign_out()
        st.session_state.clear()
        st.rerun()
    if c2.button("❌ No, Stay", use_container_width=True):
        st.rerun()

def render_top_nav(profile):
    col_title, col_logout = st.columns([8, 1])
    with col_title:
        role_badge = "👑 Admin" if profile.get('role') == 'admin' else "👤 Tenant"
        st.title(f"PropEase: Welcome, {profile.get('full_name')} {role_badge}")
    with col_logout:
        st.write("") 
        if st.button("Logout", type="secondary", use_container_width=True):
            show_logout_dialog()
    st.divider()

def get_last_month_reading(flat_number, current_date, property_id):
    try:
        res = conn.table("sub_meter_readings").select("current_reading").eq("flat_number", flat_number).eq("property_id", property_id).lt("bill_month", str(current_date)).order("bill_month", desc=True).limit(1).execute()
        if res.data: return res.data[0]['current_reading']
    except: pass
    return 0

# --- 3. ADMIN DASHBOARD ---
def admin_dashboard(user_details):
    render_top_nav(user_details)
    
    # --- PROPERTY SELECTION ---
    try:
        props_res = conn.table("properties").select("*").eq("owner_id", user_details['id']).execute()
        properties = props_res.data
    except:
        properties = []

    if properties:
        prop_opts = {p['property_name']: p['id'] for p in properties}
        selected_prop_name = st.selectbox("🎯 Select Active Property", list(prop_opts.keys()))
        active_prop_id = prop_opts[selected_prop_name]
        current_prop = next(p for p in properties if p['id'] == active_prop_id)
    else:
        st.warning("No properties found. Please go to the '⚙️ Properties' tab to create your first building.")
        active_prop_id = None

    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "💰 Payments", "👥 Tenants", "🏢 Meters", "⚡ Generate", "📊 Records", "📉 Dues", "⚙️ Settings", "💬 Feedback"
    ])

    # --- TAB 7 (SETTINGS) FIRST FOR EASY SETUP ---
    with tab7:
        st.subheader("⚙️ Property & Billing Settings")
        with st.expander("➕ Create New Property", expanded=not active_prop_id):
            with st.form("add_prop_form"):
                new_p_name = st.text_input("Property Name")
                new_p_addr = st.text_input("Address")
                if st.form_submit_button("Create Property"):
                    try:
                        conn.table("properties").insert({
                            "owner_id": user_details['id'], "property_name": new_p_name, "address": new_p_addr,
                            "water_billing_mode": "S. Vihar Style (Shared)", "electricity_billing_mode": "Dynamic Main Meter"
                        }).execute()
                        st.success("✅ Property Created! Refreshing...")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        st.error(f"❌ Error: {e}")

        if active_prop_id:
            st.divider()
            with st.form("update_logic"):
                st.write(f"### Custom Logic for {selected_prop_name}")
                w_opts = ["No Water Bill (Electricity Only)", "S. Vihar Style (Shared)", "Fixed Rate Per Flat", "Fixed Rate Per Person"]
                sel_w = st.selectbox("Water Calculation", w_opts, index=w_opts.index(current_prop.get('water_billing_mode', "S. Vihar Style (Shared)")))
                w_fixed = st.number_input("Fixed Water Rate (₹)", value=float(current_prop.get('water_fixed_rate', 0.0)))
                
                e_opts = ["Dynamic Main Meter", "Fixed Rate Per Unit"]
                sel_e = st.selectbox("Electricity Calculation", e_opts, index=e_opts.index(current_prop.get('electricity_billing_mode', "Dynamic Main Meter")))
                e_fixed = st.number_input("Fixed Electricity Rate (₹)", value=float(current_prop.get('electricity_fixed_rate', 8.0)))
                
                if st.form_submit_button("💾 Save Rules"):
                    conn.table("properties").update({
                        "water_billing_mode": sel_w, "water_fixed_rate": w_fixed,
                        "electricity_billing_mode": sel_e, "electricity_fixed_rate": e_fixed
                    }).eq("id", active_prop_id).execute()
                    st.success("Logic Updated!")
                    st.rerun()

    if not active_prop_id: st.stop()

    # Shared Tenant Data for active property
    users_resp = conn.table("profiles").select("*").eq("role", "tenant").eq("property_id", active_prop_id).order("flat_number").execute()

    # --- TAB 1: PAYMENTS ---
    with tab1:
        st.subheader("Payment Verifications")
        pen_e = conn.table("bills").select("*").eq("status", "Verifying").eq("property_id", active_prop_id).execute()
        pen_r = conn.table("rent_records").select("*, profiles(full_name)").eq("status", "Verifying").eq("property_id", active_prop_id).execute()
        
        if not pen_e.data and not pen_r.data: st.info("No pending verifications.")
        else:
            for b in pen_e.data:
                with st.expander(f"⚡ Elec: {b['customer_name']} (₹{b['total_amount']})"):
                    if st.button("Approve", key=f"ae_{b['id']}"): 
                        conn.table("bills").update({"status":"Paid", "amount_paid": b['total_amount']}).eq("id", b['id']).execute()
                        st.rerun()
            for r in pen_r.data:
                name = r['profiles']['full_name'] if r['profiles'] else "Tenant"
                with st.expander(f"🏠 Rent: {name} (₹{r['amount']})"):
                    if st.button("Approve", key=f"ar_{r['id']}"): 
                        conn.table("rent_records").update({"status":"Paid", "amount_paid": r['amount']}).eq("id", r['id']).execute()
                        st.rerun()

    # --- TAB 2: TENANTS ---
    with tab2:
        if users_resp.data:
            df = pd.DataFrame(users_resp.data)
            st.dataframe(df[['full_name', 'flat_number', 'assigned_meter', 'rent_amount']], hide_index=True)
            sel_u = {f"{u['full_name']}": u for u in users_resp.data}[st.selectbox("Edit Tenant", [u['full_name'] for u in users_resp.data])]
            with st.form("edit_t"):
                c1, c2 = st.columns(2)
                f_no = c1.text_input("Flat No", value=sel_u['flat_number'])
                m_name = c2.text_input("Main Meter Name", value=sel_u.get('assigned_meter', 'Main Meter'))
                rent = c1.number_input("Rent", value=float(sel_u['rent_amount']))
                ppl = c2.number_input("People", value=int(sel_u['num_people']))
                if st.form_submit_button("Update"):
                    conn.table("profiles").update({"flat_number": f_no, "assigned_meter": m_name, "rent_amount": rent, "num_people": ppl}).eq("id", sel_u['id']).execute()
                    st.rerun()

    # --- TAB 3: METERS ---
    with tab3:
        st.subheader("Meter Reading Input")
        meter_names = sorted(list(set([t.get('assigned_meter', 'Main Meter') for t in users_resp.data])))
        if not meter_names: meter_names = ["Main Meter"]
        
        c1, c2 = st.columns(2)
        m_type = c1.selectbox("Select Meter", meter_names)
        b_date = c2.date_input("Bill Date", value=date.today(), key="m_date")
        
        prev_r = 0
        last_m = conn.table("main_meters").select("current_reading").eq("meter_name", m_type).eq("property_id", active_prop_id).lt("bill_month", str(b_date)).order("bill_month", desc=True).limit(1).execute()
        if last_m.data: prev_r = last_m.data[0]['current_reading']
        
        c1, c2, c3 = st.columns(3)
        m_p = c1.number_input("Prev", value=int(prev_r))
        m_c = c2.number_input("Curr", value=0, key="m_c")
        m_b = c3.number_input("Bill (₹)", value=0.0)
        
        units = m_c - m_p
        rate = m_b / units if units > 0 else 0
        st.info(f"Rate: ₹{rate:.4f} per unit")
        
        sub_saves = []
        tot_sub = 0
        for t in [u for u in users_resp.data if u.get('assigned_meter') == m_type]:
            st.write(f"**{t['full_name']} ({t['flat_number']})**")
            p_v = get_last_month_reading(t['flat_number'], b_date, active_prop_id)
            c1, c2 = st.columns(2)
            sp = c1.number_input(f"Prev", value=int(p_v), key=f"sp_{t['id']}")
            sc = c2.number_input(f"Curr", value=0, key=f"sc_{t['id']}")
            tot_sub += (sc - sp)
            sub_saves.append({"flat": t['flat_number'], "prev": sp, "curr": sc, "units": sc - sp})
        
        water_u = max(0, units - tot_sub)
        if st.button("Save Readings"):
            conn.table("main_meters").upsert({"property_id": active_prop_id, "meter_name": m_type, "bill_month": str(b_date), "previous_reading": m_p, "current_reading": m_c, "units_consumed": units, "total_bill_amount": m_b, "calculated_rate": rate, "water_units": water_u, "water_cost": water_u * rate}, on_conflict="property_id, meter_name, bill_month").execute()
            for s in sub_saves:
                conn.table("sub_meter_readings").upsert({"property_id": active_prop_id, "flat_number": s['flat'], "bill_month": str(b_date), "previous_reading": s['prev'], "current_reading": s['curr'], "units_consumed": s['units']}, on_conflict="property_id, flat_number, bill_month").execute()
            st.success("Saved!")

    # --- TAB 4: GENERATE ---
    with tab4:
        gen_date = st.date_input("Billing Month", value=date.today(), key="gen_d")
        mm_res = conn.table("main_meters").select("*").eq("bill_month", str(gen_date)).eq("property_id", active_prop_id).execute()
        rates_map = {m['meter_name']: m['calculated_rate'] for m in mm_res.data} if mm_res.data else {}
        w_units = next((m['water_units'] for m in mm_res.data if m['meter_name'] == 'Ground Meter'), 0) if mm_res.data else 0
        
        sub_res = conn.table("sub_meter_readings").select("*").eq("bill_month", str(gen_date)).eq("property_id", active_prop_id).execute()
        sub_map = {s['flat_number']: s for s in sub_res.data} if sub_res.data else {}
        
        active_ppl = sum([t['num_people'] for t in users_resp.data if sub_map.get(t['flat_number'], {}).get('units_consumed', 0) > 0])
        active_ppl = max(1, active_ppl)
        
        if st.button("Generate All Bills"):
            for t in users_resp.data:
                e_units = sub_map.get(t['flat_number'], {}).get('units_consumed', 0)
                if e_units > 0:
                    e_r = current_prop['electricity_fixed_rate'] if current_prop['electricity_billing_mode'] == "Fixed Rate Per Unit" else rates_map.get(t['assigned_meter'], 0)
                    w_c = 0
                    if current_prop['water_billing_mode'] == "Fixed Rate Per Flat": w_c = current_prop['water_fixed_rate']
                    elif current_prop['water_billing_mode'] == "Fixed Rate Per Person": w_c = current_prop['water_fixed_rate'] * t['num_people']
                    elif current_prop['water_billing_mode'] == "S. Vihar Style (Shared)": w_c = (w_units / active_ppl) * t['num_people'] * rates_map.get('Ground Meter', 0)
                    
                    total = math.ceil((e_units * e_r) + w_c)
                    conn.table("bills").upsert({"property_id": active_prop_id, "user_id": t['id'], "customer_name": t['full_name'], "bill_month": str(gen_date), "units_consumed": e_units, "total_amount": total, "status": "Pending"}, on_conflict="property_id, user_id, bill_month").execute()
            st.success("Bills Generated!")

    # --- TAB 6: DUES & CSV ---
    with tab6:
        st.subheader("Consolidated Dues")
        # Simplified logic for display
        st.write("Generating CSV...")
        # Dataframe generation logic here
        # st.download_button("Download CSV", data=df.to_csv(), file_name="dues.csv")

# --- 4. TENANT DASHBOARD ---
def tenant_dashboard(user_details):
    render_top_nav(user_details)
    st.write("### Your Monthly Dues")
    # Fetch logic for individual tenant based on property_id
    st.info("Check your 'Electricity' and 'Rent' sections below.")

# --- 5. MAIN ---
def main():
    if 'user' not in st.session_state:
        c1, c2, c3 = st.columns([1, 2, 1]) 
        with c2:
            t1, t2 = st.tabs(["Login", "Register"])
            with t1:
                e = st.text_input("Email")
                p = st.text_input("Pass", type="password")
                if st.button("Login"):
                    res = conn.auth.sign_in_with_password({"email":e, "password":p})
                    st.session_state.user = res.user
                    st.rerun()
            with t2:
                register()
    else:
        profile = ensure_profile_exists(st.session_state.user.id, st.session_state.user.email)
        if profile['role'] == 'admin': admin_dashboard(profile)
        else: tenant_dashboard(profile)

if __name__ == "__main__":
    main()
