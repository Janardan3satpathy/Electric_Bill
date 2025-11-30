import streamlit as st
import pandas as pd
from datetime import date
from st_supabase_connection import SupabaseConnection
import random
import math

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="S. Vihar Electricity Manager", page_icon="⚡", layout="wide")
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

# --- 3. HELPER FUNCTIONS ---
def get_prev_reading(flat_number):
    try:
        # Fetch the most recent reading for this flat
        res = conn.table("sub_meter_readings").select("reading_value").eq("flat_number", flat_number).order("reading_date", desc=True).limit(1).execute()
        if res.data:
            return res.data[0]['reading_value']
    except:
        pass
    return 0

def get_meter_rate_for_flat(flat_number, rates_data):
    if not flat_number: return rates_data.get('Ground Meter', 0)
    if flat_number in ['101', '102']: return rates_data.get('Ground Meter', 0)
    if flat_number in ['201', '202']: return rates_data.get('Middle Meter', 0)
    if flat_number in ['301', '302', '401']: return rates_data.get('Upper Meter', 0)
    return rates_data.get('Ground Meter', 0)

# --- 4. ADMIN DASHBOARD ---

def admin_dashboard(user_details):
    st.title(f"Admin Dashboard 🛠️")
    
    tab1, tab2, tab3, tab4 = st.tabs(["👥 Tenants & Flats", "🏢 Main Meters", "⚡ Generate Bills", "📊 Records"])

    # --- TAB 1: MANAGE TENANT DETAILS ---
    with tab1:
        st.subheader("Link Tenants to Flats")
        users_resp = conn.table("profiles").select("*").eq("role", "tenant").order("full_name").execute()
        
        if users_resp.data:
            df_users = pd.DataFrame(users_resp.data)
            st.dataframe(df_users[['full_name', 'email', 'num_people', 'flat_number']], hide_index=True)
            
            st.divider()
            col1, col2 = st.columns(2)
            user_opts = {u['full_name']: u for u in users_resp.data}
            sel_u_name = col1.selectbox("Select Tenant", list(user_opts.keys()))
            sel_u = user_opts[sel_u_name]
            
            flat_opts = ["101", "102", "201", "202", "301", "302", "401", "Other"]
            current_flat = sel_u.get('flat_number')
            flat_index = flat_opts.index(current_flat) if current_flat in flat_opts else 7
            
            with st.form("update_tenant"):
                c1, c2 = st.columns(2)
                new_count = c1.number_input(f"People Count", value=sel_u.get('num_people', 0) or 0, min_value=0)
                new_flat = c2.selectbox("Assign Flat", flat_opts, index=flat_index)
                
                if st.form_submit_button("Update Profile"):
                    conn.table("profiles").update({"num_people": new_count, "flat_number": new_flat}).eq("id", sel_u['id']).execute()
                    st.success("✅ Updated!")
                    st.rerun()

    # --- TAB 2: MAIN METERS CALCULATOR ---
    with tab2:
        st.subheader("Main Meter Readings")
        col_sel1, col_sel2 = st.columns(2)
        meter_type = col_sel1.radio("Select Floor:", ["Ground Meter", "Middle Meter", "Upper Meter"], horizontal=True)
        bill_date = col_sel2.date_input("Bill Date", value=date.today())

        # Auto-fetch Main Meter Previous Reading
        main_prev = 0
        try:
            last_meter = conn.table("main_meters").select("current_reading").eq("meter_name", meter_type).neq("bill_month", str(bill_date)).order("created_at", desc=True).limit(1).execute()
            if last_meter.data: main_prev = last_meter.data[0]['current_reading']
        except: pass

        st.markdown(f"### 1. {meter_type}")
        col_m1, col_m2, col_m3 = st.columns(3)
        mm_prev = col_m1.number_input("Main Prev", min_value=0, value=int(main_prev or 0))
        mm_curr = col_m2.number_input("Main Curr", min_value=0, value=0) # Default 0 as requested
        mm_bill = col_m3.number_input("Total Bill (₹)", min_value=0.0)
        
        mm_units = mm_curr - mm_prev
        mm_rate = 0.0
        if mm_units > 0: mm_rate = mm_bill / mm_units
        st.info(f"**Consumption:** {mm_units} | **Rate:** ₹{mm_rate:.4f}")
        
        water_units = 0
        water_cost = 0.0
        sub_readings_to_save = [] 

        if meter_type == "Ground Meter":
            st.markdown("### 2. Sub-Meters (Editable)")
            c_g1, c_g2 = st.columns(2)
            
            p101_auto = get_prev_reading("101")
            c_g1.write("**G2BHK (101)**")
            g1_prev = c_g1.number_input("101 Prev", min_value=0, value=int(p101_auto), key="101p")
            g1_curr = c_g1.number_input("101 Curr", min_value=0, value=0, key="101c")
            g1_units = g1_curr - g1_prev
            sub_readings_to_save.append({"flat": "101", "val": g1_curr})
            
            p102_auto = get_prev_reading("102")
            c_g2.write("**G1RK (102)**")
            g2_prev = c_g2.number_input("102 Prev", min_value=0, value=int(p102_auto), key="102p")
            g2_curr = c_g2.number_input("102 Curr", min_value=0, value=0, key="102c")
            g2_units = g2_curr - g2_prev
            sub_readings_to_save.append({"flat": "102", "val": g2_curr})
            
            water_units = mm_units - (g1_units + g2_units)
            if water_units < 0: water_units = 0
            water_cost = water_units * mm_rate
            st.success(f"💧 Water: {water_units} Units (₹{water_cost:.2f})")

        elif meter_type == "Middle Meter":
            st.markdown("### 2. Sub-Meters (Editable)")
            c_m1, c_m2 = st.columns(2)
            
            p201_auto = get_prev_reading("201")
            c_m1.write("**3BHK1 (201)**")
            m201_prev = c_m1.number_input("201 Prev", min_value=0, value=int(p201_auto), key="201p")
            m201_curr = c_m1.number_input("201 Curr", min_value=0, value=0, key="201c")
            m201_units = m201_curr - m201_prev
            sub_readings_to_save.append({"flat": "201", "val": m201_curr})
            
            m202_units = mm_units - m201_units
            if m202_units < 0: m202_units = 0
            
            p202_auto = get_prev_reading("202")
            m202_curr = p202_auto + m202_units
            sub_readings_to_save.append({"flat": "202", "val": m202_curr})
            
            st.success(f"🏠 **202 Units (Auto):** {m202_units}")

        elif meter_type == "Upper Meter":
            st.markdown("### 2. Sub-Meters (Editable)")
            c_u1, c_u2 = st.columns(2)
            
            p301_auto = get_prev_reading("301")
            c_u1.write("**3BHK2 (301)**")
            u301_prev = c_u1.number_input("301 Prev", min_value=0, value=int(p301_auto), key="301p")
            u301_curr = c_u1.number_input("301 Curr", min_value=0, value=0, key="301c")
            u301_units = u301_curr - u301_prev
            sub_readings_to_save.append({"flat": "301", "val": u301_curr})
            
            p401_auto = get_prev_reading("401")
            c_u2.write("**1RK2 (401)**")
            u401_prev = c_u2.number_input("401 Prev", min_value=0, value=int(p401_auto), key="401p")
            u401_curr = c_u2.number_input("401 Curr", min_value=0, value=0, key="401c")
            u401_units = u401_curr - u401_prev
            sub_readings_to_save.append({"flat": "401", "val": u401_curr})
            
            u302_units = mm_units - (u301_units + u401_units)
            if u302_units < 0: u302_units = 0
            
            p302_auto = get_prev_reading("302")
            u302_curr = p302_auto + u302_units
            sub_readings_to_save.append({"flat": "302", "val": u302_curr})
            
            st.success(f"🏠 **302 Units (Auto):** {u302_units}")

        if st.button(f"Save {meter_type} & Sub-Meters"):
            try:
                # 1. Upsert Main Meter
                conn.table("main_meters").upsert({
                    "meter_name": meter_type,
                    "bill_month": str(bill_date),
                    "previous_reading": mm_prev,
                    "current_reading": mm_curr,
                    "units_consumed": mm_units,
                    "total_bill_amount": mm_bill,
                    "calculated_rate": mm_rate,
                    "water_units": water_units,
                    "water_cost": water_cost
                }, on_conflict="meter_name, bill_month").execute()
                
                # 2. Upsert Sub Meters
                for item in sub_readings_to_save:
                    conn.table("sub_meter_readings").upsert({
                        "flat_number": item['flat'],
                        "reading_date": str(bill_date),
                        "reading_value": item['val']
                    }, on_conflict="flat_number, reading_date").execute()
                    
                st.success("✅ Saved Main Meter!")
                st.write("✅ Saved Sub-Meters:", [s['flat'] for s in sub_readings_to_save]) # Confirmation
            except Exception as e:
                st.error(f"❌ Error: {e}")

    # --- TAB 3: GENERATE BILLS ---
    with tab3:
        st.subheader("Generate Monthly Bills")
        
        col_gen1, col_gen2 = st.columns(2)
        gen_date = col_gen1.date_input("Bill Date for Generation", value=date.today())
        
        rates_data = {}
        water_stats = {"units": 0, "rate": 0}
        
        try:
            mm_res = conn.table("main_meters").select("*").eq("bill_month", str(gen_date)).execute()
            for m in mm_res.data:
                rates_data[m['meter_name']] = m['calculated_rate']
                if m['meter_name'] == "Ground Meter":
                    water_stats["units"] = m.get('water_units', 0)
                    water_stats["rate"] = m.get('calculated_rate', 0)
        except: pass
        
        if not rates_data:
            st.warning("⚠️ No Main Meter data found for this date. Save Main Meters first.")
        else:
            st.success(f"Rates: Ground {rates_data.get('Ground Meter',0):.2f} | Middle {rates_data.get('Middle Meter',0):.2f} | Upper {rates_data.get('Upper Meter',0):.2f}")

            all_tenants = conn.table("profiles").select("*").eq("role", "tenant").order("flat_number").execute()
            total_people = sum([(t.get('num_people') or 0) for t in all_tenants.data]) if all_tenants.data else 1
            if total_people == 0: total_people = 1
            units_per_person = water_stats["units"] / total_people
            
            st.info(f"💧 Water Share: {water_stats['units']} Units ÷ {total_people} People = **{units_per_person:.2f} Units/Head**")

            st.markdown("### 📋 Tenant Bill Preview")
            
            h1, h2, h3, h4, h5, h6, h7 = st.columns([2, 1, 1, 1, 1, 1, 2])
            h1.write("**Tenant (Flat)**")
            h2.write("**Prev**")
            h3.write("**Curr**")
            h4.write("**Elec**")
            h5.write("**Water**")
            h6.write("**Total**")
            h7.write("**Action**")
            
            bill_batch = []

            if all_tenants.data:
                for t in all_tenants.data:
                    with st.expander(f"🧾 {t.get('full_name')} ({t.get('flat_number')}) - Click to View Calculation"):
                        flat = t.get('flat_number', 'Unknown')
                        name = t.get('full_name', 'Unknown')
                        
                        t_prev = 0
                        try:
                            last_bill = conn.table("bills").select("current_reading").eq("user_id", t['id']).order("created_at", desc=True).limit(1).execute()
                            if last_bill.data: t_prev = last_bill.data[0]['current_reading']
                        except: pass
                        
                        t_curr = 0
                        try:
                            curr_sub = conn.table("sub_meter_readings").select("reading_value").eq("flat_number", flat).eq("reading_date", str(gen_date)).execute()
                            if curr_sub.data: t_curr = curr_sub.data[0]['reading_value']
                        except: pass
                        
                        elec_units = t_curr - t_prev if t_curr > 0 else 0
                        rate = get_meter_rate_for_flat(flat, rates_data)
                        
                        people = t.get('num_people') or 0
                        water_share_units = units_per_person * people
                        
                        elec_cost = elec_units * rate
                        water_rate = rates_data.get('Ground Meter', 0)
                        water_cost = water_share_units * water_rate
                        
                        total_amt = math.ceil(elec_cost + water_cost)

                        col_d1, col_d2 = st.columns(2)
                        with col_d1:
                            st.write(f"**⚡ Electricity**")
                            st.write(f"`{elec_units} Units` × `₹{rate:.4f}` = **₹{elec_cost:.2f}**")
                            st.caption(f"({t_curr} Curr - {t_prev} Prev)")

                        with col_d2:
                            st.write(f"**💧 Water Share**")
                            st.write(f"`{water_share_units:.2f} Units` × `₹{water_rate:.4f}` = **₹{water_cost:.2f}**")
                            st.caption(f"({people} People × {units_per_person:.2f} Units/Head)")
                            
                        st.divider()
                        st.markdown(f"#### Total: ₹{elec_cost:.2f} + ₹{water_cost:.2f} = **₹{total_amt}**")

                        bill_obj = {
                            "user_id": t['id'], "customer_name": name, "bill_month": str(gen_date),
                            "previous_reading": t_prev, "current_reading": t_curr,
                            "units_consumed": elec_units, "tenant_water_units": water_share_units,
                            "rate_per_unit": rate, "water_charge": water_cost,
                            "total_amount": total_amt, "status": "Pending"
                        }
                        
                        if t_curr > 0:
                            bill_batch.append(bill_obj)
                            if st.button(f"Update/Gen Bill for {name}", key=f"btn_{t['id']}"):
                                conn.table("bills").upsert(bill_obj, on_conflict="user_id, bill_month").execute()
                                st.success(f"Bill Updated for {name}!")
                        else:
                            st.error("Missing reading.")

            st.divider()
            if st.button("🚀 UPDATE/GENERATE ALL BILLS (Batch)", type="primary"):
                if bill_batch:
                    try:
                        conn.table("bills").upsert(bill_batch, on_conflict="user_id, bill_month").execute()
                        st.balloons()
                        st.success(f"✅ Successfully processed {len(bill_batch)} bills!")
                    except Exception as e:
                        st.error(f"Batch failed: {e}")
                else:
                    st.warning("No valid readings found.")

    # --- TAB 4: RECORDS ---
    with tab4:
        st.subheader("Records")
        if st.button("Refresh"): st.rerun()
        res = conn.table("bills").select("*").order("created_at", desc=True).limit(10).execute()
        if res.data:
            st.dataframe(pd.DataFrame(res.data)[['customer_name', 'bill_month', 'total_amount', 'units_consumed', 'tenant_water_units']])

# --- 5. TENANT DASHBOARD ---
def tenant_dashboard(user_details):
    st.title(f"Welcome, {user_details.get('full_name')} 👋")
    res = conn.table("bills").select("*").eq("user_id", user_details['id']).order("created_at", desc=True).execute()
    
    if res.data:
        df = pd.DataFrame(res.data)
        latest = df.iloc[0]
        combined_units = (latest.get('units_consumed') or 0) + (latest.get('tenant_water_units') or 0)
        
        st.markdown(f"""
        <div style="padding:20px; border-radius:10px; background-color:#e8f4f8; border:1px solid #d1d5db;">
            <h3>Latest Bill: {latest['bill_month']}</h3>
            <h1 style="color:#0078D7;">₹{latest['total_amount']}</h1>
            <p>Total Units: {combined_units:.2f} | Rate: ₹{latest['rate_per_unit']:.2f}</p>
            <p>Status: <b>{latest['status']}</b></p>
        </div>
        """, unsafe_allow_html=True)
        st.dataframe(df[['bill_month', 'total_amount', 'status']], hide_index=True)
    else:
        st.info("No bills generated yet.")

# --- 6. MAIN ---
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