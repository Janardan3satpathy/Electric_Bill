import streamlit as st
import pandas as pd
from datetime import date
from st_supabase_connection import SupabaseConnection
import random
import math
import time

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="S. Vihar Property Manager", page_icon="🏠", layout="wide")
conn = st.connection("supabase", type=SupabaseConnection)

# --- 2. AUTHENTICATION & HELPER FUNCTIONS ---

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

def login():
    st.subheader("🔐 Login")
    email = st.text_input("Email", key="login_email")
    password = st.text_input("Password", type="password", key="login_pass")
    if st.button("Sign In"):
        try:
            session = conn.auth.sign_in_with_password(dict(email=email, password=password))
            st.session_state.user = session.user
            st.success("Logged in!")
            st.rerun()
        except Exception as e:
            st.error(f"Login failed: {e}")

def register():
    st.subheader("📝 Register Tenant")
    with st.form("reg"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Full Name")
        email = c1.text_input("Email")
        mobile = c2.text_input("Mobile")
        password = c2.text_input("Password", type="password")
        
        st.divider()
        n1, n2 = generate_captcha()
        ans = st.number_input(f"{n1} + {n2} = ?", step=1)
        
        if st.form_submit_button("Register"):
            if ans != (n1 + n2):
                st.error("Wrong Captcha")
            else:
                try:
                    res = conn.auth.sign_up(dict(email=email, password=password, options=dict(data=dict(full_name=name))))
                    if res.user:
                        conn.table("profiles").insert({
                            "id": res.user.id, "email": email, "full_name": name, "mobile": mobile, "role": "tenant", "num_people": 0, "rent_amount": 0
                        }).execute()
                        st.success("Registered! Please Login.")
                except Exception as e:
                    st.error(f"Error: {e}")

def logout():
    conn.auth.sign_out()
    st.session_state.clear()
    st.rerun()

def get_last_month_reading(flat_number, current_date):
    try:
        res = conn.table("sub_meter_readings").select("current_reading").eq("flat_number", flat_number).lt("bill_month", str(current_date)).order("bill_month", desc=True).limit(1).execute()
        if res.data:
            return res.data[0]['current_reading']
    except:
        pass
    return 0

def get_meter_rate_for_flat(flat_number, rates_data):
    if not flat_number: return rates_data.get('Ground Meter', 0)
    if flat_number in ['101', '102']: return rates_data.get('Ground Meter', 0)
    if flat_number in ['201', '202']: return rates_data.get('Middle Meter', 0)
    if flat_number in ['301', '302', '401']: return rates_data.get('Upper Meter', 0)
    return rates_data.get('Ground Meter', 0)

# --- 3. ADMIN DASHBOARD ---

def admin_dashboard(user_details):
    st.title(f"Property Manager 🏠")
    
    tab1, tab2, tab3, tab4, tab5 = st.tabs(["💰 Dues & Payments", "👥 Tenants & Flats", "🏢 Meters", "⚡ Generate Bills", "📊 Records"])

    # --- TAB 1: DUES & PAYMENTS ---
    with tab1:
        st.subheader("Tenant Dues Overview")
        
        users_resp = conn.table("profiles").select("*").eq("role", "tenant").order("flat_number").execute()
        user_opts = {f"{u['full_name']} ({u.get('flat_number', '?')})": u for u in users_resp.data}
        
        if not user_opts:
            st.warning("No tenants found.")
        else:
            sel_label = st.selectbox("Select Tenant to Check Dues", list(user_opts.keys()))
            sel_u = user_opts[sel_label]
            uid = sel_u['id']
            
            elec_res = conn.table("bills").select("*").eq("user_id", uid).neq("status", "Paid").execute()
            pending_elec = pd.DataFrame(elec_res.data)
            
            rent_res = conn.table("rent_records").select("*").eq("user_id", uid).neq("status", "Paid").execute()
            pending_rent = pd.DataFrame(rent_res.data)
            
            total_elec_due = pending_elec['total_amount'].sum() if not pending_elec.empty else 0
            total_rent_due = pending_rent['amount'].sum() if not pending_rent.empty else 0
            total_due = total_elec_due + total_rent_due
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Outstanding Due", f"₹{total_due}", delta_color="inverse")
            c2.metric("Rent Pending", f"₹{total_rent_due}")
            c3.metric("Electricity Pending", f"₹{total_elec_due}")
            
            st.divider()
            
            with st.expander("🔻 View & Update Detailed Dues", expanded=True):
                st.markdown("#### 🏠 Rent Dues")
                if not pending_rent.empty:
                    for idx, row in pending_rent.iterrows():
                        rc1, rc2, rc3 = st.columns([3, 2, 2])
                        rc1.write(f"Month: **{row['bill_month']}**")
                        rc2.write(f"₹{row['amount']}")
                        if rc3.button("Mark Rent Paid", key=f"rent_{row['id']}"):
                            conn.table("rent_records").update({"status": "Paid"}).eq("id", row['id']).execute()
                            st.toast(f"Rent for {row['bill_month']} cleared!")
                            time.sleep(1)
                            st.rerun()
                else:
                    st.success("No Rent Dues!")
                
                st.divider()
                
                st.markdown("#### ⚡ Electricity Dues")
                if not pending_elec.empty:
                    for idx, row in pending_elec.iterrows():
                        ec1, ec2, ec3 = st.columns([3, 2, 2])
                        ec1.write(f"Month: **{row['bill_month']}** ({row['status']})")
                        ec2.write(f"₹{row['total_amount']}")
                        if ec3.button("Mark Bill Paid", key=f"elec_{row['id']}"):
                            conn.table("bills").update({"status": "Paid"}).eq("id", row['id']).execute()
                            st.toast(f"Bill for {row['bill_month']} cleared!")
                            time.sleep(1)
                            st.rerun()
                else:
                    st.success("No Electricity Dues!")

    # --- TAB 2: MANAGE TENANT DETAILS ---
    with tab2:
        st.subheader("Tenant Allotment & Rent Settings")
        
        if users_resp.data:
            df_users = pd.DataFrame(users_resp.data)
            st.dataframe(df_users[['full_name', 'flat_number', 'rent_amount', 'mobile']], hide_index=True)
            
            st.divider()
            st.write("### Edit Tenant Profile")
            col1, col2 = st.columns(2)
            sel_u_edit_name = col1.selectbox("Select Tenant to Edit", list(user_opts.keys()), key="edit_sel")
            sel_u_edit = user_opts[sel_u_edit_name]
            
            flat_opts = ["101", "102", "201", "202", "301", "302", "401", "Other"]
            current_flat = sel_u_edit.get('flat_number')
            f_idx = flat_opts.index(current_flat) if current_flat in flat_opts else 7
            
            with st.form("update_tenant_full"):
                c1, c2 = st.columns(2)
                new_flat = c1.selectbox("Assign Flat", flat_opts, index=f_idx)
                new_rent = c2.number_input("Monthly Rent Amount (₹)", value=sel_u_edit.get('rent_amount', 0) or 0, min_value=0)
                
                c3, c4 = st.columns(2)
                new_count = c3.number_input("People Count", value=sel_u_edit.get('num_people', 0) or 0, min_value=0)
                new_mobile = c4.text_input("Mobile", value=sel_u_edit.get('mobile', ''))
                
                if st.form_submit_button("Update Tenant"):
                    conn.table("profiles").update({
                        "num_people": new_count, 
                        "flat_number": new_flat,
                        "mobile": new_mobile,
                        "rent_amount": new_rent
                    }).eq("id", sel_u_edit['id']).execute()
                    st.success("✅ Tenant details updated successfully!")
                    st.rerun()

    # --- TAB 3: MAIN METERS CALCULATOR ---
    with tab3:
        st.subheader("Input Meter Readings")
        col_sel1, col_sel2 = st.columns(2)
        meter_type = col_sel1.radio("Select Floor:", ["Ground Meter", "Middle Meter", "Upper Meter"], horizontal=True)
        bill_date = col_sel2.date_input("Bill Date", value=date.today())

        main_prev = 0
        try:
            last_meter = conn.table("main_meters").select("current_reading").eq("meter_name", meter_type).lt("bill_month", str(bill_date)).order("bill_month", desc=True).limit(1).execute()
            if last_meter.data: main_prev = last_meter.data[0]['current_reading']
        except: pass

        st.markdown(f"### 1. {meter_type} (Main)")
        col_m1, col_m2, col_m3 = st.columns(3)
        mm_prev = col_m1.number_input("Main Prev", min_value=0, value=int(main_prev or 0))
        mm_curr = col_m2.number_input("Main Curr", min_value=0, value=0)
        mm_bill = col_m3.number_input("Total Bill (₹)", min_value=0.0)
        
        mm_units = mm_curr - mm_prev
        mm_rate = 0.0
        if mm_units > 0: mm_rate = mm_bill / mm_units
        st.info(f"**Consumption:** {mm_units} | **Rate:** ₹{mm_rate:.4f}")
        
        water_units = 0
        water_cost = 0.0
        sub_readings_to_save = [] 

        if meter_type == "Ground Meter":
            st.markdown("### 2. Sub-Meters")
            c_g1, c_g2 = st.columns(2)
            p101 = get_last_month_reading("101", bill_date)
            g1_prev = c_g1.number_input("101 Prev", value=int(p101), key="101p")
            g1_curr = c_g1.number_input("101 Curr", value=0, key="101c")
            sub_readings_to_save.append({"flat": "101", "prev": g1_prev, "curr": g1_curr, "units": g1_curr - g1_prev})
            
            p102 = get_last_month_reading("102", bill_date)
            g2_prev = c_g2.number_input("102 Prev", value=int(p102), key="102p")
            g2_curr = c_g2.number_input("1
