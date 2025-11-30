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
        users_resp = conn.table("profiles").select("*").eq("role", "tenant").order("full_name").execute()
        if users_resp.data:
            df_users = pd.DataFrame(users_resp.data)
            st.dataframe(df_users[['full_name', 'email', 'mobile', 'num_people']], hide_index=True)
            
            st.divider()
            st.write("#### Update Count")
            user_opts = {u['full_name']: u for u in users_resp.data}
            sel_u_name = st.selectbox("Select Tenant to Update", list(user_opts.keys()))
            sel_u = user_opts[sel_u_name]
            
            c_up1, c_up2 = st.columns(2)
            new_count = c_up1.number_input(f"People in {sel_u_name}'s Flat", value=sel_u.get('num_people', 0) or 0, min_value=0)
            
            if c_up2.button("Update Database"):
                try:
                    conn.table("profiles").update({"num_people": new_count}).eq("id", sel_u['id']).execute()
                    st.success(f"✅ Updated {sel_u_name} to {new_count} people!")
                    st.rerun()
                except Exception as e:
                    st.error(f"Update failed: {e}")

    # --- TAB 2: MAIN METERS CALCULATOR ---
    with tab2:
        st.subheader("Main Meter Readings")
        meter_type = st.radio("Select Floor:", ["Ground Meter", "Middle Meter", "Upper Meter"], horizontal=True)
        
        # Auto-fetch Main Meter Previous Reading Only
        try:
            last_meter_data = conn.table("main_meters").select("current_reading").eq("meter_name", meter_type).order("created_at", desc=True).limit(1).execute()
            default_prev = last_meter_data.data[0]['current_reading'] if last_meter_data.data else 0
        except:
            default_prev = 0

        # --- LIVE INPUTS ---
        st.markdown(f"### 1. {meter_type} (Main)")
        col_m1, col_m2, col_m3 = st.columns(3)
        mm_prev = col_m1.number_input("Main Prev", min_value=0, value=int(default_prev))
        mm_curr = col_m2.number_input("Main Curr", min_value=0, value=int(default_prev))
        mm_bill = col_m3.number_input("Total Bill (₹)", min_value=0.0)
        
        # Live Math
        mm_units = mm_curr - mm_prev
        mm_rate = 0.0
        if mm_units > 0:
            mm_rate = mm_bill / mm_units
        
        st.info(f"**Main Consumption:** {mm_units} Units | **Rate:** ₹{mm_rate:.4f}")
        
        water_units = 0
        water_cost = 0.0

        # --- FLOOR SPECIFIC LOGIC ---
        if meter_type == "Ground Meter":
            st.markdown("### 2. Sub-Meters (Flats)")
            c_g1, c_g2 = st.columns(2)
            
            # Submeter 101 (Start at 0 to avoid bugs)
            c_g1.write("**G2BHK (101)**")
            g1_prev = c_g1.number_input("101 Prev", min_value=0, key="g1p")
            g1_curr = c_g1.number_input("101 Curr", min_value=0, key="g1c")
            g1_units = g1_curr - g1_prev
            
            # Submeter 102
            c_g2.write("**G1RK (102)**")
            g2_prev = c_g2.number_input("102 Prev", min_value=0, key="g2p")
            g2_curr = c_g2.number_input("102 Curr", min_value=0, key="g2c")
            g2_units = g2_curr - g2_prev
            
            # Logic: Main - (101 + 102)
            flat_units = g1_units + g2_units
            water_units = mm_units - flat_units
            if water_units < 0: water_units = 0
            water_cost = water_units * mm_rate
            
            st.divider()
            st.markdown(f"**Math:** `{mm_units} (Main) - ({g1_units} + {g2_units}) = {water_units} (Water)`")
            st.success(f"💧 **Water Units:** {water_units}  (Cost: ₹{water_cost:.2f})")

        elif meter_type == "Middle Meter":
            st.markdown("### 2. Sub-Meters")
            c_m1, c_m2 = st.columns(2)
            st.write("**3BHK1 (201)**")
            m201_prev = c_m1.number_input("201 Previous", min_value=0, key="m201p")
            m201_curr = c_m2.number_input("201 Current", min_value=0, key="m201c")
            
            m201_units = m201_curr - m201_prev
            m202_units = mm_units - m201_units # Remainder is 202
            if m202_units < 0: m202_units = 0
            
            st.divider()
            st.markdown(f"**Math:** `{mm_units} (Main) - {m201_units} (201) = {m202_units} (202)`")
            st.success(f"🏠 **202 Units (Auto):** {m202_units}")

        elif meter_type == "Upper Meter":
            st.markdown("### 2. Sub-Meters")
            c_u1, c_u2 = st.columns(2)
            
            c_u1.write("**3BHK2 (301)**")
            u301_prev = c_u1.number_input("301 Prev", min_value=0, key="u3p")
            u301_curr = c_u1.number_input("301 Curr", min_value=0, key="u3c")
            
            c_u2.write("**1RK2 (401)**")
            u401_prev = c_u2.number_input("401 Prev", min_value=0, key="u4p")
            u401_curr = c_u2.number_input("401 Curr", min_value=0, key="u4c")
            
            u_sub_total = (u301_curr - u301_prev) + (u401_curr - u401_prev)
            u302_units = mm_units - u_sub_total
            if u302_units < 0: u302_units = 0
            
            st.divider()
            st.markdown(f"**Math:** `{mm_units} (Main) - ({u301_curr-u301_prev} + {u401_curr-u401_prev}) = {u302_units} (302)`")
            st.success(f"🏠 **302 Units (Auto):** {u302_units}")

        # --- SAVE BUTTON ---
        st.divider()
        if st.button(f"Save {meter_type} Reading"):
            try:
                conn.table("main_meters").insert({
                    "meter_name": meter_type,
                    "bill_month": str(date.today()),
                    "previous_reading": mm_prev,
                    "current_reading": mm_curr,
                    "units_consumed": mm_units,
                    "total_bill_amount": mm_bill,
                    "calculated_rate": mm_rate,
                    "water_units": water_units,
                    "water_cost": water_cost
                }).execute()
                st.success("✅ Saved successfully!")
            except Exception as e:
                st.error(f"❌ Save Failed: {e}")

    # --- TAB 3: GENERATE BILLS ---
    with tab3:
        st.subheader("Generate Tenant Bill")
        
        # 1. Fetch Latest Ground Meter Data
        gm_data = conn.table("main_meters").select("*").eq("meter_name", "Ground Meter").order("created_at", desc=True).limit(1).execute()
        
        gm_rate = 5.50
        total_water_units = 0
        
        if gm_data.data:
            gm_entry = gm_data.data[0]
            gm_rate = gm_entry.get('calculated_rate') or 5.50
            total_water_units = gm_entry.get('water_units') or 0
        
        # 2. Calculate Water Per Person
        all_tenants = conn.table("profiles").select("num_people").eq("role", "tenant").execute()
        total_people_count = 0
        if all_tenants.data:
            total_people_count = sum([(t.get('num_people') or 0) for t in all_tenants.data])
            
        if total_people_count == 0: total_people_count = 1
        units_per_person = total_water_units / total_people_count
        
        st.info(f"📊 **Water Calculation:** {total_water_units} Units ÷ {total_people_count} People = **{units_per_person:.2f} Units/Person**")

        # 3. Select Tenant
        users_resp = conn.table("profiles").select("*").eq("role", "tenant").execute()
        tenant_options = {f"{u['full_name']}": u for u in users_resp.data}
        
        if tenant_options:
            selected_label = st.selectbox("Select Tenant", list(tenant_options.keys()))
            selected_user = tenant_options[selected_label]
            
            # Auto-Fetch Previous Reading
            last_bill = conn.table("bills").select("current_reading").eq("user_id", selected_user['id']).order("created_at", desc=True).limit(1).execute()
            t_prev_def = last_bill.data[0]['current_reading'] if last_bill.data else 0
            
            # --- LIVE BILL CALCULATOR ---
            c_t1, c_t2 = st.columns(2)
            t_prev = c_t1.number_input("Previous", min_value=0, value=int(t_prev_def))
            t_curr = c_t2.number_input("Current", min_value=0, value=int(t_prev_def))
            t_rate = st.number_input("Rate (₹)", value=float(gm_rate), format="%.4f")
            
            # Calculations
            t_elec_units = t_curr - t_prev
            t_people = selected_user.get('num_people') or 0
            t_water_units = units_per_person * t_people
            
            t_elec_cost = t_elec_units * t_rate
            t_water_cost = t_water_units * t_rate
            
            t_total_raw = t_elec_cost + t_water_cost
            t_total_final = math.ceil(t_total_raw)
            
            st.markdown(f"""
            #### 🧾 Bill Preview
            - **Electricity:** {t_elec_units} units
            - **Water Share:** {t_water_units:.2f} units ({t_people} people)
            - **Total Units:** {t_elec_units + t_water_units:.2f}
            - **Final Amount:** **₹{t_total_final}**
            """)
            
            if st.button("Save Tenant Bill"):
                try:
                    conn.table("bills").insert({
                        "user_id": selected_user['id'],
                        "customer_name": selected_user['full_name'],
                        "bill_month": str(date.today()),
                        "previous_reading": t_prev,
                        "current_reading": t_curr,
                        "units_consumed": t_elec_units,
                        "tenant_water_units": t_water_units,
                        "rate_per_unit": t_rate,
                        "water_charge": t_water_cost,
                        "total_amount": t_total_final,
                        "status": "Pending"
                    }).execute()
                    st.success("✅ Bill Saved Successfully!")
                except Exception as e:
                    st.error(f"❌ Error: {e}")

    # --- TAB 4: RECORDS ---
    with tab4:
        st.subheader("Records")
        if st.button("Refresh"): st.rerun()
        res = conn.table("bills").select("*").order("created_at", desc=True).limit(10).execute()
        if res.data:
            st.dataframe(pd.DataFrame(res.data)[['customer_name', 'bill_month', 'total_amount', 'units_consumed', 'tenant_water_units']])

# --- 4. TENANT DASHBOARD ---
def tenant_dashboard(user_details):
    st.title(f"Welcome, {user_details.get('full_name')} 👋")
    
    res = conn.table("bills").select("*").eq("user_id", user_details['id']).order("created_at", desc=True).execute()
    
    if res.data:
        df = pd.DataFrame(res.data)
        latest = df.iloc[0]
        
        # Combine Units
        w_units = latest.get('tenant_water_units') or 0
        e_units = latest.get('units_consumed') or 0
        combined_units = e_units + w_units
        
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
        display_df['tenant_water_units'] = display_df['tenant_water_units'].fillna(0)
        display_df['units_consumed'] = display_df['units_consumed'].fillna(0)
        display_df['Total Units'] = display_df['units_consumed'] + display_df['tenant_water_units']
        
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