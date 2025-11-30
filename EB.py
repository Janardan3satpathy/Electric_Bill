import streamlit as st
import pandas as pd
from datetime import date
from st_supabase_connection import SupabaseConnection
import random
import math

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="S. Vihar Electricity Manager", page_icon="⚡")
conn = st.connection("supabase", type=SupabaseConnection)

# --- 2. AUTHENTICATION ---

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
                "id": user_id, "email": email, "full_name": "User", "role": "tenant", "num_people": 0
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
                            "id": res.user.id, "email": email, "full_name": name, "mobile": mobile, "role": "tenant", "num_people": 0
                        }).execute()
                        st.success("Registered! Please Login.")
                except Exception as e:
                    st.error(f"Error: {e}")

def logout():
    conn.auth.sign_out()
    st.session_state.clear()
    st.rerun()

# --- 3. ADMIN DASHBOARD ---

def admin_dashboard(user_details):
    st.title(f"Admin Dashboard 🛠️")
    
    tab1, tab2, tab3, tab4 = st.tabs(["👥 Manage Tenants", "🏢 Main Meters", "⚡ Generate Bills", "📊 Records"])

    # --- TAB 1: MANAGE TENANT DETAILS ---
    with tab1:
        st.subheader("Update Family Size")
        # Fetch fresh data every time
        users_resp = conn.table("profiles").select("*").eq("role", "tenant").order("full_name").execute()
        
        if users_resp.data:
            df_users = pd.DataFrame(users_resp.data)
            st.dataframe(df_users[['full_name', 'email', 'mobile', 'num_people']], hide_index=True)
            
            st.divider()
            st.write("#### Update Count")
            user_opts = {u['full_name']: u for u in users_resp.data}
            sel_u_name = st.selectbox("Select Tenant", list(user_opts.keys()))
            sel_u = user_opts[sel_u_name]
            
            # Using a form to submit updates
            with st.form("update_people_form"):
                new_count = st.number_input(f"People in {sel_u_name}'s Flat", value=sel_u.get('num_people', 0), min_value=0)
                
                if st.form_submit_button("Update Database"):
                    try:
                        conn.table("profiles").update({"num_people": new_count}).eq("id", sel_u['id']).execute()
                        st.success(f"Successfully updated {sel_u_name} to {new_count} people!")
                        st.rerun()
                    except Exception as e:
                        st.error(f"Update failed. Check RLS policies. Error: {e}")

    # --- TAB 2: MAIN METERS CALCULATOR ---
    with tab2:
        st.subheader("Main Meter Readings")
        meter_type = st.radio("Select Floor:", ["Ground Meter", "Middle Meter", "Upper Meter"], horizontal=True)
        
        # --- AUTO-FETCH PREVIOUS READING LOGIC ---
        # Get the LAST record for this specific meter
        last_meter_data = conn.table("main_meters").select("current_reading").eq("meter_name", meter_type).order("created_at", desc=True).limit(1).execute()
        
        default_prev = 0
        if last_meter_data.data:
            default_prev = last_meter_data.data[0]['current_reading']
            st.info(f"🔄 Auto-fetched Previous Reading from last bill: **{default_prev}**")
        else:
            st.warning("No previous history found. Please enter manually.")

        with st.form("main_meter_form"):
            bill_date = st.date_input("Bill Date", value=date.today())
            
            # MAIN READING INPUTS
            c1, c2, c3 = st.columns(3)
            # Use value=default_prev to pre-fill the box
            mm_prev = c1.number_input("Main Prev", min_value=0, value=default_prev)
            mm_curr = c2.number_input("Main Curr", min_value=0, value=default_prev) # Start at prev to avoid negative
            mm_bill = c3.number_input("Total Bill Amount (₹)", min_value=0.0)
            
            mm_units = mm_curr - mm_prev
            mm_rate = 0.0
            if mm_units > 0:
                mm_rate = mm_bill / mm_units

            water_units = 0
            water_cost = 0.0

            # --- A. GROUND METER LOGIC ---
            if meter_type == "Ground Meter":
                st.info("💧 **Water Logic:** Ground - (101 + 102)")
                colA, colB = st.columns(2)
                with colA:
                    st.write("**G2BHK (101)**")
                    g1_prev = st.number_input("101 Prev", min_value=0)
                    g1_curr = st.number_input("101 Curr", min_value=0)
                with colB:
                    st.write("**G1RK (102)**")
                    g2_prev = st.number_input("102 Prev", min_value=0)
                    g2_curr = st.number_input("102 Curr", min_value=0)
                
                flat_units = (g1_curr - g1_prev) + (g2_curr - g2_prev)
                water_units = mm_units - flat_units
                if water_units < 0: water_units = 0
                water_cost = water_units * mm_rate
                
                st.metric("💧 Total Water Units", f"{water_units}")

            # --- B. MIDDLE METER LOGIC ---
            elif meter_type == "Middle Meter":
                st.info("ℹ️ **Logic:** Middle - 201 = 202")
                c_sub1, c_sub2 = st.columns(2)
                m201_prev = c_sub1.number_input("201 Prev", min_value=0)
                m201_curr = c_sub2.number_input("201 Curr", min_value=0)
                m201_units = m201_curr - m201_prev
                m202_units = mm_units - m201_units
                st.metric("1BHK1 (202) Auto-Calc", f"{m202_units} Units")

            # --- C. UPPER METER LOGIC ---
            elif meter_type == "Upper Meter":
                st.info("ℹ️ **Logic:** Upper - (301 + 401) = 302")
                colU1, colU2 = st.columns(2)
                u301_prev = colU1.number_input("301 Prev", min_value=0)
                u301_curr = colU1.number_input("301 Curr", min_value=0)
                u401_prev = colU2.number_input("401 Prev", min_value=0)
                u401_curr = colU2.number_input("401 Curr", min_value=0)
                
                u_sub_units = (u301_curr - u301_prev) + (u401_curr - u401_prev)
                u302_units = mm_units - u_sub_units
                st.metric("1BHK2 (302) Auto-Calc", f"{u302_units} Units")

            st.divider()
            st.metric(f"Rate ({meter_type})", f"₹{mm_rate:.2f}")

            if st.form_submit_button("Save Main Meter Data"):
                conn.table("main_meters").insert({
                    "meter_name": meter_type,
                    "bill_month": str(bill_date),
                    "previous_reading": mm_prev,
                    "current_reading": mm_curr,
                    "units_consumed": mm_units,
                    "total_bill_amount": mm_bill,
                    "calculated_rate": mm_rate,
                    "water_units": water_units,
                    "water_cost": water_cost
                }).execute()
                st.success(f"Saved {meter_type}!")

    # --- TAB 3: GENERATE BILLS ---
    with tab3:
        st.subheader("Generate Tenant Bill")
        
        # 1. Fetch Latest Ground Meter Data
        gm_data = conn.table("main_meters").select("*").eq("meter_name", "Ground Meter").order("created_at", desc=True).limit(1).execute()
        
        gm_rate = 5.50
        total_water_units = 0
        
        if gm_data.data:
            gm_entry = gm_data.data[0]
            gm_rate = gm_entry['calculated_rate']
            total_water_units = gm_entry.get('water_units', 0)
        
        # 2. Calculate Water Logic
        all_tenants = conn.table("profiles").select("num_people").eq("role", "tenant").execute()
        total_people_count = sum([t['num_people'] for t in all_tenants.data]) if all_tenants.data else 1
        if total_people_count == 0: total_people_count = 1
        units_per_person = total_water_units / total_people_count
        
        st.info(f"Water: {total_water_units} Units ÷ {total_people_count} People = **{units_per_person:.2f} Units/Person**")

        # 3. Tenant Selection
        users_resp = conn.table("profiles").select("*").eq("role", "tenant").execute()
        tenant_options = {f"{u['full_name']}": u for u in users_resp.data}
        
        if tenant_options:
            selected_label = st.selectbox("Select Tenant", list(tenant_options.keys()))
            selected_user = tenant_options[selected_label]
            
            # --- AUTO-FETCH TENANT PREVIOUS READING ---
            last_bill = conn.table("bills").select("current_reading").eq("user_id", selected_user['id']).order("created_at", desc=True).limit(1).execute()
            
            t_prev_default = 0
            if last_bill.data:
                t_prev_default = last_bill.data[0]['current_reading']
                st.success(f"🔄 Last reading for {selected_user['full_name']}: **{t_prev_default}**")
            
            # Form
            with st.form("tenant_bill_gen"):
                c1, c2 = st.columns(2)
                # Auto-filled previous reading
                prev = c1.number_input("Previous Reading", min_value=0, value=t_prev_default)
                curr = c2.number_input("Current Reading", min_value=0, value=t_prev_default)
                rate = st.number_input("Rate (₹)", value=float(gm_rate), format="%.2f")
                
                # Water Logic
                tenant_people = selected_user.get('num_people', 0)
                tenant_water_share_units = units_per_person * tenant_people
                tenant_water_cost = tenant_water_share_units * gm_rate
                
                st.write(f"**Water Share:** {tenant_people} People = {tenant_water_share_units:.2f} Units")
                
                elec_units = curr - prev
                elec_cost = elec_units * rate
                raw_total = elec_cost + tenant_water_cost
                final_total = math.ceil(raw_total)
                
                st.markdown(f"### Final Bill: ₹{final_total}")
                
                if st.form_submit_button("Save Bill"):
                    conn.table("bills").insert({
                        "user_id": selected_user['id'],
                        "customer_name": selected_user['full_name'],
                        "bill_month": str(date.today()),
                        "previous_reading": prev,
                        "current_reading": curr,
                        "units_consumed": elec_units,
                        "tenant_water_units": tenant_water_share_units,
                        "rate_per_unit": rate,
                        "water_charge": tenant_water_cost,
                        "total_amount": final_total,
                        "status": "Pending"
                    }).execute()
                    st.success(f"Bill Saved!")

    # --- TAB 4: RECORDS ---
    with tab4:
        st.subheader("Bill Records")
        res = conn.table("bills").select("*").order("created_at", desc=True).execute()
        if res.data:
            st.dataframe(pd.DataFrame(res.data))

# --- 4. TENANT DASHBOARD ---
def tenant_dashboard(user_details):
    st.title(f"Welcome, {user_details.get('full_name')} 👋")
    
    res = conn.table("bills").select("*").eq("user_id", user_details['id']).order("created_at", desc=True).execute()
    
    if res.data:
        df = pd.DataFrame(res.data)
        latest = df.iloc[0]
        combined_units = latest['units_consumed'] + latest.get('tenant_water_units', 0)
        
        st.markdown(f"""
        <div style="padding:20px; border-radius:10px; background-color:#e8f4f8; border:1px solid #d1d5db;">
            <h3>Latest Bill: {latest['bill_month']}</h3>
            <h1 style="color:#0078D7;">₹{latest['total_amount']}</h1>
            <p>Total Units: {combined_units:.2f} | Rate: ₹{latest['rate_per_unit']:.2f}</p>
            <p>Status: <b>{latest['status']}</b></p>
        </div>
        """, unsafe_allow_html=True)
        
        st.divider()
        st.write("### 📜 History")
        display_df = df.copy()
        display_df['Total Units'] = display_df['units_consumed'] + display_df['tenant_water_units'].fillna(0)
        st.dataframe(display_df[['bill_month', 'Total Units', 'total_amount', 'status']], hide_index=True)
    else:
        st.info("No bills generated yet.")

# --- 5. MAIN ---
def main():
    if 'user' not in st.session_state:
        choice = st.sidebar.radio("Menu", ["Login", "Register"])
        if choice == "Login": login()
        else: register()
    else:
        user = st.session_state.user
        profile = ensure_profile_exists(user.id, user.email)
        
        if profile:
            with st.sidebar:
                st.write(f"👤 {profile.get('full_name')}")
                st.button("Logout", on_click=logout)
            
            if profile.get('role') == 'admin':
                admin_dashboard(profile)
            else:
                tenant_dashboard(profile)

if __name__ == "__main__":
    main()