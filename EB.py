import streamlit as st
import pandas as pd
from datetime import date
from st_supabase_connection import SupabaseConnection
import random
import math  # For Rounding Up

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="S. Vihar Electricity Manager", page_icon="⚡")
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
                del st.session_state.captcha_num1
                st.rerun()
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
        st.subheader("Update Family Size (For Water Calc)")
        users_resp = conn.table("profiles").select("*").eq("role", "tenant").order("full_name").execute()
        if users_resp.data:
            df_users = pd.DataFrame(users_resp.data)
            st.dataframe(df_users[['full_name', 'email', 'mobile', 'num_people']], hide_index=True)
            
            st.divider()
            st.write("#### Update a Tenant")
            user_opts = {u['full_name']: u for u in users_resp.data}
            sel_u_name = st.selectbox("Select Tenant to Edit", list(user_opts.keys()))
            sel_u = user_opts[sel_u_name]
            
            with st.form("update_people"):
                new_count = st.number_input(f"Number of People in {sel_u_name}'s Flat", value=sel_u.get('num_people', 0), min_value=0)
                if st.form_submit_button("Update Count"):
                    conn.table("profiles").update({"num_people": new_count}).eq("id", sel_u['id']).execute()
                    st.success(f"Updated! {sel_u_name} now has {new_count} people.")
                    st.rerun()

    # --- TAB 2: MAIN METERS CALCULATOR ---
    with tab2:
        st.subheader("Main Meter Readings")
        meter_type = st.radio("Select Floor:", ["Ground Meter", "Middle Meter", "Upper Meter"], horizontal=True)
        
        with st.form("main_meter_form"):
            st.markdown(f"### {meter_type} Calculation")
            bill_date = st.date_input("Bill Date", value=date.today())
            
            # MAIN READING INPUTS
            c1, c2, c3 = st.columns(3)
            mm_prev = c1.number_input("Main Prev", min_value=0, key="m_p")
            mm_curr = c2.number_input("Main Curr", min_value=0, key="m_c")
            mm_bill = c3.number_input("Total Bill Amount (₹)", min_value=0.0)
            
            mm_units = mm_curr - mm_prev
            mm_rate = 0.0
            if mm_units > 0:
                mm_rate = mm_bill / mm_units

            water_units = 0
            water_cost = 0.0

            # --- A. GROUND METER LOGIC (Water Calculation) ---
            if meter_type == "Ground Meter":
                st.info("💧 **Water Logic:** Ground - (101 + 102) = Total Water Units")
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
                
                st.divider()
                st.metric("💧 Total Water/Pump Units", f"{water_units}")
                
                # Fetch Total People for per-head calculation preview
                all_tenants = conn.table("profiles").select("num_people").eq("role", "tenant").execute()
                total_people = sum([t['num_people'] for t in all_tenants.data]) if all_tenants.data else 1
                if total_people == 0: total_people = 1
                
                per_head_units = water_units / total_people
                per_head_cost = per_head_units * mm_rate
                
                st.caption(f"Total People: {total_people} | Per Person Share: {per_head_units:.2f} Units")


            # --- B. MIDDLE METER LOGIC ---
            elif meter_type == "Middle Meter":
                st.info("ℹ️ **Logic:** Middle - 3BHK1(201) = 1BHK1(202)")
                c_sub1, c_sub2 = st.columns(2)
                m201_prev = c_sub1.number_input("201 Prev", min_value=0)
                m201_curr = c_sub2.number_input("201 Curr", min_value=0)
                m201_units = m201_curr - m201_prev
                if m201_units < 0: m201_units = 0
                m202_units = mm_units - m201_units
                if m202_units < 0: m202_units = 0
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
                if u302_units < 0: u302_units = 0
                st.metric("1BHK2 (302) Auto-Calc", f"{u302_units} Units")

            if st.form_submit_button("Save Main Meter Data"):
                try:
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
                    st.success(f"Saved {meter_type}! Rate: ₹{mm_rate:.2f}")
                except Exception as e:
                    st.error(f"Error saving: {e}")

    # --- TAB 3: GENERATE BILLS ---
    with tab3:
        st.subheader("Generate Tenant Bill")
        
        # 1. Fetch Latest Ground Meter Data for Water Logic
        gm_data = conn.table("main_meters").select("*").eq("meter_name", "Ground Meter").order("created_at", desc=True).limit(1).execute()
        
        gm_rate = 5.50
        total_water_units = 0
        
        if gm_data.data:
            gm_entry = gm_data.data[0]
            gm_rate = gm_entry['calculated_rate']
            total_water_units = gm_entry.get('water_units', 0)
        
        # 2. Calculate Per Person Water Unit Share
        all_tenants = conn.table("profiles").select("num_people").eq("role", "tenant").execute()
        total_people_count = sum([t['num_people'] for t in all_tenants.data]) if all_tenants.data else 1
        if total_people_count == 0: total_people_count = 1
        
        units_per_person = total_water_units / total_people_count
        
        # Display Stats for Admin
        st.info(f"📊 **Water Stats:** {total_water_units} Units ÷ {total_people_count} People = **{units_per_person:.2f} Units/Person**")

        # 3. Tenant Selection
        users_resp = conn.table("profiles").select("*").eq("role", "tenant").execute()
        tenant_options = {f"{u['full_name']} (Family: {u.get('num_people', 0)})": u for u in users_resp.data}
        
        if tenant_options:
            selected_label = st.selectbox("Select Tenant", list(tenant_options.keys()))
            selected_user = tenant_options[selected_label]
            
            # Auto Calc Tenant Water Share
            tenant_people = selected_user.get('num_people', 0)
            tenant_water_share_units = units_per_person * tenant_people
            tenant_water_cost = tenant_water_share_units * gm_rate
            
            with st.form("tenant_bill_gen"):
                c1, c2 = st.columns(2)
                prev = c1.number_input("Previous Reading", min_value=0)
                curr = c2.number_input("Current Reading", min_value=0)
                rate = st.number_input("Rate (₹)", value=float(gm_rate), format="%.2f")
                
                # Hidden/ReadOnly Water Logic for Form
                st.write(f"**Water Share:** {tenant_people} People × {units_per_person:.2f} Units = **{tenant_water_share_units:.2f} Units** (₹{tenant_water_cost:.2f})")
                
                elec_units = curr - prev
                elec_cost = elec_units * rate
                
                # TOTALS
                total_units_display = elec_units + tenant_water_share_units
                raw_total_amount = elec_cost + tenant_water_cost
                final_total_amount = math.ceil(raw_total_amount) # ROUND UP LOGIC
                
                st.divider()
                st.write(f"**Electricity:** {elec_units} Units (₹{elec_cost:.2f})")
                st.write(f"**Water Share:** {tenant_water_share_units:.2f} Units (₹{tenant_water_cost:.2f})")
                st.markdown(f"### Final Bill: ₹{final_total_amount} (Rounded Up)")
                
                if st.form_submit_button("Save Bill"):
                    try:
                        conn.table("bills").insert({
                            "user_id": selected_user['id'],
                            "customer_name": selected_user['full_name'],
                            "bill_month": str(date.today()),
                            "units_consumed": elec_units,  # Storing Elec Units Separately
                            "tenant_water_units": tenant_water_share_units, # Storing Water Units Separately
                            "rate_per_unit": rate,
                            "water_charge": tenant_water_cost,
                            "total_amount": final_total_amount,
                            "status": "Pending"
                        }).execute()
                        st.success(f"Bill Saved for {selected_user['full_name']}!")
                    except Exception as e:
                        st.error(f"Error: {e}")

    # --- TAB 4: RECORDS ---
    with tab4:
        st.subheader("Bill Records")
        res = conn.table("bills").select("*").order("created_at", desc=True).execute()
        if res.data:
            st.dataframe(pd.DataFrame(res.data))

# --- 4. TENANT DASHBOARD (Combined View) ---

def tenant_dashboard(user_details):
    st.title(f"Welcome, {user_details.get('full_name')} 👋")
    
    res = conn.table("bills").select("*").eq("user_id", user_details['id']).order("created_at", desc=True).execute()
    
    if res.data:
        df = pd.DataFrame(res.data)
        latest = df.iloc[0]
        
        # Combine Units for display (Elec + Water Share)
        combined_units = latest['units_consumed'] + latest.get('tenant_water_units', 0)
        
        st.markdown(f"""
        <div style="padding:20px; border-radius:10px; background-color:#e8f4f8; border:1px solid #d1d5db;">
            <h3>Latest Bill: {latest['bill_month']}</h3>
            <h1 style="color:#0078D7;">₹{latest['total_amount']}</h1>
            <p style="font-size:18px;"><b>Total Units Consumed: {combined_units:.2f} Units</b></p>
            <p>Rate Applied: ₹{latest['rate_per_unit']:.2f} / unit</p>
            <p>Status: <b>{latest['status']}</b></p>
        </div>
        """, unsafe_allow_html=True)
        
        st.divider()
        st.write("### 📜 Billing History")
        
        # Prepare a clean table for tenant
        display_df = df.copy()
        # Create a Combined Units column
        display_df['Total Units'] = display_df['units_consumed'] + display_df['tenant_water_units'].fillna(0)
        # Rename columns for clarity
        display_df = display_df[['bill_month', 'Total Units', 'rate_per_unit', 'total_amount', 'status']]
        display_df.columns = ['Date', 'Total Units', 'Rate', 'Bill Amount (₹)', 'Status']
        
        st.dataframe(display_df, hide_index=True)
    else:
        st.info("No bills generated yet.")

# --- 5. MAIN ENTRY POINT ---
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