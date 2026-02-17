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

# --- NEW: LOGOUT DIALOG (MODAL) ---
@st.dialog("⚠️ Confirm Logout")
def show_logout_dialog():
    st.write("Are you sure you want to end your session?")
    st.write("The app will return to the login screen.")
    
    col1, col2 = st.columns(2)
    
    if col1.button("✅ Yes, Logout", use_container_width=True):
        perform_logout()
        
    if col2.button("❌ No, Stay", use_container_width=True):
        st.rerun() # Closes the dialog

def perform_logout():
    conn.auth.sign_out()
    st.session_state.clear()
    st.toast("Thank you for visiting the app! Visit again soon. 👋", icon="👋")
    time.sleep(1.5) # Give time to read toast
    st.rerun()

def render_top_nav(profile):
    col_title, col_logout = st.columns([8, 1])
    with col_title:
        role_badge = "👑 Admin" if profile.get('role') == 'admin' else "👤 Tenant"
        st.title(f"Welcome, {profile.get('full_name')} {role_badge}")
        
    with col_logout:
        st.write("") 
        st.write("") 
        # Clicking this now opens the MODAL dialog
        if st.button("Logout", type="secondary", use_container_width=True):
            show_logout_dialog()

    st.divider()

def login():
    st.subheader("🔐 Access S. Vihar Manager")
    email = st.text_input("Email", key="login_email")
    password = st.text_input("Password", type="password", key="login_pass")
    
    if st.button("Sign In", type="primary", use_container_width=True):
        try:
            session = conn.auth.sign_in_with_password(dict(email=email, password=password))
            st.session_state.user = session.user
            st.success("Logged in successfully!")
            time.sleep(0.5)
            st.rerun()
        except Exception as e:
            st.error(f"Login failed: {e}")

def register():
    st.subheader("📝 New User Registration")
    with st.form("reg"):
        c1, c2 = st.columns(2)
        name = c1.text_input("Full Name")
        email = c1.text_input("Email")
        mobile = c2.text_input("Mobile")
        password = c2.text_input("Password", type="password")
        
        st.divider()
        n1, n2 = generate_captcha()
        ans = st.number_input(f"{n1} + {n2} = ?", step=1)
        
        if st.form_submit_button("Register", use_container_width=True):
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

def get_last_month_reading(flat_number, current_date):
    try:
        res = conn.table("sub_meter_readings").select("current_reading").eq("flat_number", flat_number).lt("bill_month", str(current_date)).order("bill_month", desc=True).limit(1).execute()
        if res.data: return res.data[0]['current_reading']
    except: pass
    return 0

def get_meter_rate_for_flat(flat_number, rates_data):
    if not flat_number: return rates_data.get('Ground Meter', 0)
    if flat_number in ['101', '102']: return rates_data.get('Ground Meter', 0)
    if flat_number in ['201', '202']: return rates_data.get('Middle Meter', 0)
    if flat_number in ['301', '302', '401']: return rates_data.get('Upper Meter', 0)
    return rates_data.get('Ground Meter', 0)

# --- 3. ADMIN DASHBOARD ---

def admin_dashboard(user_details):
    render_top_nav(user_details)
    
    tab1, tab2, tab3, tab4, tab5, tab6 = st.tabs([
        "💰 Dues & Payments", 
        "👥 Tenants & Flats", 
        "🏢 Meters", 
        "⚡ Generate Monthly", 
        "📊 Records",
        "📉 Outstanding Summary"
    ])

    # --- TAB 1: DUES & PAYMENTS ---
    with tab1:
        st.subheader("1. Payment Verification Queue (Online Claims)")
        pending_approvals = conn.table("bills").select("*").eq("status", "Verifying").execute()
        rent_approvals = conn.table("rent_records").select("*, profiles(full_name)").eq("status", "Verifying").execute()
        
        rent_verify_data = []
        if rent_approvals.data:
            for r in rent_approvals.data:
                r['customer_name'] = r['profiles']['full_name'] if r['profiles'] else "Unknown"
                rent_verify_data.append(r)

        if not pending_approvals.data and not rent_verify_data:
            st.info("No online payment claims waiting for verification.")
        else:
            for bill in pending_approvals.data:
                paid_so_far = bill.get('amount_paid', 0) or 0
                total = bill.get('total_amount', 0)
                remaining = total - paid_so_far
                
                with st.expander(f"⚡ Verify Elec: {bill['customer_name']} - Claim for Remaining ₹{remaining}"):
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"Month: {bill['bill_month']}")
                    if c2.button("Approve Full", key=f"app_elec_{bill['id']}"):
                        conn.table("bills").update({"status": "Paid", "amount_paid": total}).eq("id", bill['id']).execute()
                        st.success("Approved!")
                        time.sleep(0.5)
                        st.rerun()
                    if c3.button("Reject", key=f"rej_elec_{bill['id']}"):
                        conn.table("bills").update({"status": "Pending"}).eq("id", bill['id']).execute()
                        st.error("Rejected.")
                        time.sleep(0.5)
                        st.rerun()

            for r in rent_verify_data:
                paid_so_far = r.get('amount_paid', 0) or 0
                total = r.get('amount', 0)
                remaining = total - paid_so_far

                with st.expander(f"🏠 Verify Rent: {r['customer_name']} - Claim for Remaining ₹{remaining}"):
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"Month: {r['bill_month']}")
                    if c2.button("Approve Full", key=f"app_rent_{r['id']}"):
                        conn.table("rent_records").update({"status": "Paid", "amount_paid": total}).eq("id", r['id']).execute()
                        st.success("Approved!")
                        time.sleep(0.5)
                        st.rerun()
                    if c3.button("Reject", key=f"rej_rent_{r['id']}"):
                        conn.table("rent_records").update({"status": "Pending"}).eq("id", r['id']).execute()
                        st.error("Rejected.")
                        time.sleep(0.5)
                        st.rerun()

        st.divider()

        # --- MANUAL PAYMENT ENTRY ---
        st.subheader("2. Manual Payment Entry (Full or Partial)")
        users_resp = conn.table("profiles").select("*").eq("role", "tenant").order("flat_number").execute()
        user_opts = {f"{u['full_name']} ({u.get('flat_number', '?')})": u for u in users_resp.data}
        
        if user_opts:
            sel_label = st.selectbox("Select Tenant", list(user_opts.keys()))
            sel_u = user_opts[sel_label]
            uid = sel_u['id']
            
            elec_res = conn.table("bills").select("*").eq("user_id", uid).neq("status", "Paid").execute()
            rent_res = conn.table("rent_records").select("*").eq("user_id", uid).neq("status", "Paid").execute()
            
            total_elec_due = sum([(item['total_amount'] - (item.get('amount_paid', 0) or 0)) for item in elec_res.data])
            total_rent_due = sum([(item['amount'] - (item.get('amount_paid', 0) or 0)) for item in rent_res.data])
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Pending", f"₹{total_elec_due + total_rent_due}")
            c2.metric("Rent Pending", f"₹{total_rent_due}")
            c3.metric("Electricity Pending", f"₹{total_elec_due}")
            
            st.write("### 📝 Record Payment Details")
            
            # --- RENT PAYMENTS ---
            if rent_res.data:
                st.markdown("**🏠 Rent Dues**")
                for r in rent_res.data:
                    already_paid = r.get('amount_paid', 0) or 0
                    total_amount = r['amount']
                    remaining = total_amount - already_paid
                    
                    status_label = f" (Paid: ₹{already_paid})" if already_paid > 0 else ""
                    
                    with st.expander(f"Pay Rent: {r['bill_month']} | Due: ₹{remaining}{status_label}"):
                        rc1, rc2 = st.columns(2)
                        pay_mode = rc1.selectbox("Payment Mode", ["Cash", "Online (UPI/Bank)"], key=f"pm_rent_{r['id']}")
                        pay_date = rc2.date_input("Date of Payment", value=date.today(), key=f"pd_rent_{r['id']}")
                        
                        st.divider()
                        
                        pt1, pt2 = st.columns(2)
                        payment_type = pt1.selectbox("Payment Type", ["Full Payment", "Partial Payment"], index=0, key=f"pt_rent_{r['id']}")
                        
                        final_paying_amount = 0
                        if payment_type == "Full Payment":
                            final_paying_amount = remaining
                            pt2.info(f"✅ Full Amount: ₹{final_paying_amount}")
                            st.success("New Balance: ₹0")
                        else:
                            final_paying_amount = pt2.number_input("Enter Partial Amount (₹)", min_value=1, max_value=int(remaining), value=1, key=f"amt_rent_{r['id']}")
                            bal = remaining - final_paying_amount
                            st.warning(f"🧮 **Calc:** ₹{remaining} - ₹{final_paying_amount} = **₹{bal} (Remaining)**")

                        txn_id = ""
                        if pay_mode == "Online (UPI/Bank)":
                            txn_id = st.text_input("Transaction ID / Ref No", key=f"tx_rent_{r['id']}")
                        
                        if st.button(f"✅ Record Payment (₹{final_paying_amount})", key=f"btn_rent_{r['id']}"):
                            new_total_paid = already_paid + final_paying_amount
                            new_status = "Paid" if new_total_paid >= total_amount else "Partial"
                            conn.table("rent_records").update({"status": new_status, "amount_paid": new_total_paid, "payment_mode": pay_mode, "payment_date": str(pay_date), "txn_id": txn_id}).eq("id", r['id']).execute()
                            if new_status == "Paid": st.success("Rent Fully Paid! 🎉")
                            else: st.info(f"Partial Payment Recorded.")
                            time.sleep(1)
                            st.rerun()
            
            # --- ELECTRICITY PAYMENTS ---
            if elec_res.data:
                st.divider()
                st.markdown("**⚡ Electricity Dues**")
                for b in elec_res.data:
                    already_paid = b.get('amount_paid', 0) or 0
                    total_amount = b['total_amount']
                    remaining = total_amount - already_paid
                    status_label = f" (Paid: ₹{already_paid})" if already_paid > 0 else ""

                    with st.expander(f"Pay Bill: {b['bill_month']} | Due: ₹{remaining}{status_label}"):
                        ec1, ec2 = st.columns(2)
                        pay_mode = ec1.selectbox("Payment Mode", ["Cash", "Online (UPI/Bank)"], key=f"pm_elec_{b['id']}")
                        pay_date = ec2.date_input("Date of Payment", value=date.today(), key=f"pd_elec_{b['id']}")
                        
                        st.divider()
                        
                        et1, et2 = st.columns(2)
                        payment_type = et1.selectbox("Payment Type", ["Full Payment", "Partial Payment"], index=0, key=f"pt_elec_{b['id']}")
                        
                        final_paying_amount = 0
                        if payment_type == "Full Payment":
                            final_paying_amount = remaining
                            et2.info(f"✅ Full Amount: ₹{final_paying_amount}")
                            st.success("New Balance: ₹0")
                        else:
                            final_paying_amount = et2.number_input("Enter Partial Amount (₹)", min_value=1, max_value=int(remaining), value=1, key=f"amt_elec_{b['id']}")
                            bal = remaining - final_paying_amount
                            st.warning(f"🧮 **Calc:** ₹{remaining} - ₹{final_paying_amount} = **₹{bal} (Remaining)**")

                        txn_id = ""
                        if pay_mode == "Online (UPI/Bank)":
                            txn_id = st.text_input("Transaction ID / Ref No", key=f"tx_elec_{b['id']}")
                        
                        if st.button(f"✅ Record Payment (₹{final_paying_amount})", key=f"btn_elec_{b['id']}"):
                            new_total_paid = already_paid + final_paying_amount
                            new_status = "Paid" if new_total_paid >= total_amount else "Partial"
                            conn.table("bills").update({"status": new_status, "amount_paid": new_total_paid, "payment_mode": pay_mode, "payment_date": str(pay_date), "txn_id": txn_id}).eq("id", b['id']).execute()
                            if new_status == "Paid": st.success("Bill Fully Paid! 🎉")
                            else: st.info(f"Partial Payment Recorded.")
                            time.sleep(1)
                            st.rerun()

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
            g2_curr = c_g2.number_input("102 Curr", value=0, key="102c")
            sub_readings_to_save.append({"flat": "102", "prev": g2_prev, "curr": g2_curr, "units": g2_curr - g2_prev})
            
            water_units = mm_units - ((g1_curr-g1_prev) + (g2_curr-g2_prev))
            if water_units < 0: water_units = 0
            water_cost = water_units * mm_rate
            st.warning(f"💧 **Common/Water Usage:** {water_units} Units (Cost: ₹{water_cost:.2f})")

        elif meter_type == "Middle Meter":
            st.markdown("### 2. Sub-Meters")
            c_m1, c_m2 = st.columns(2)
            p201 = get_last_month_reading("201", bill_date)
            m201_prev = c_m1.number_input("201 Prev", value=int(p201), key="201p")
            m201_curr = c_m1.number_input("201 Curr", value=0, key="201c")
            m201_units = m201_curr - m201_prev
            sub_readings_to_save.append({"flat": "201", "prev": m201_prev, "curr": m201_curr, "units": m201_units})
            
            m202_units = mm_units - m201_units
            if m202_units < 0: m202_units = 0
            p202 = get_last_month_reading("202", bill_date)
            sub_readings_to_save.append({"flat": "202", "prev": p202, "curr": p202 + m202_units, "units": m202_units})

        elif meter_type == "Upper Meter":
            st.markdown("### 2. Sub-Meters")
            c_u1, c_u2 = st.columns(2)
            p301 = get_last_month_reading("301", bill_date)
            u301_prev = c_u1.number_input("301 Prev", value=int(p301), key="301p")
            u301_curr = c_u1.number_input("301 Curr", value=0, key="301c")
            u301_units = u301_curr - u301_prev
            sub_readings_to_save.append({"flat": "301", "prev": u301_prev, "curr": u301_curr, "units": u301_units})
            
            p401 = get_last_month_reading("401", bill_date)
            u401_prev = c_u2.number_input("401 Prev", value=int(p401), key="401p")
            u401_curr = c_u2.number_input("401 Curr", value=0, key="401c")
            u401_units = u401_curr - u401_prev
            sub_readings_to_save.append({"flat": "401", "prev": u401_prev, "curr": u401_curr, "units": u401_units})
            
            u302_units = mm_units - (u301_units + u401_units)
            if u302_units < 0: u302_units = 0
            p302 = get_last_month_reading("302", bill_date)
            sub_readings_to_save.append({"flat": "302", "prev": p302, "curr": p302 + u302_units, "units": u302_units})

        if st.button(f"Save {meter_type} Readings"):
            try:
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
                
                for item in sub_readings_to_save:
                    conn.table("sub_meter_readings").upsert({
                        "flat_number": item['flat'],
                        "bill_month": str(bill_date),
                        "previous_reading": item['prev'],
                        "current_reading": item['curr'],
                        "units_consumed": item['units']
                    }, on_conflict="flat_number, bill_month").execute()
                    
                st.success(f"✅ Saved Readings!")
            except Exception as e:
                st.error(f"❌ Error: {e}")

    # --- TAB 4: GENERATE BILLS (UPDATED LOGIC) ---
    with tab4:
        st.subheader("Generate Monthly Bills")
        col_gen1, col_gen2 = st.columns(2)
        gen_date = col_gen1.date_input("Bill Date for Generation", value=date.today())
        
        st.markdown("### 📊 Financial Overview for Month")
        admin_paid = 0
        mm_res = conn.table("main_meters").select("total_bill_amount").eq("bill_month", str(gen_date)).execute()
        if mm_res.data:
            admin_paid = sum([m['total_bill_amount'] for m in mm_res.data])
            
        tenant_recovery = 0
        bills_res = conn.table("bills").select("total_amount").eq("bill_month", str(gen_date)).execute()
        if bills_res.data:
            tenant_recovery = sum([b['total_amount'] for b in bills_res.data])
            
        f1, f2 = st.columns(2)
        f1.metric("💸 Total Admin Payment", f"₹{admin_paid}")
        f2.metric("💰 Total Tenant Recovery", f"₹{tenant_recovery}")
        
        st.divider()
        col_A, col_B = st.columns(2)
        
        # --- ELECTRICITY GENERATION (UPDATED ACTIVE TENANT LOGIC) ---
        with col_A:
            st.markdown("### ⚡ Electricity Generation")
            rates_data = {}
            water_stats = {"units": 0, "rate": 0}
            try:
                for m in mm_res.data:
                    rates_data[m['meter_name']] = m['calculated_rate']
                    if m['meter_name'] == "Ground Meter":
                        water_stats["units"] = m.get('water_units', 0)
                        water_stats["rate"] = m.get('calculated_rate', 0)
            except: pass

            if not rates_data:
                st.warning("⚠️ Meters not saved for this date.")
            else:
                water_rate = rates_data.get('Ground Meter', 0)
                sub_res_all = conn.table("sub_meter_readings").select("*").eq("bill_month", str(gen_date)).execute()
                sub_map = {row['flat_number']: row for row in sub_res_all.data} if sub_res_all.data else {}
                
                processed_tenants = []
                total_active_people = 0
                
                if users_resp.data:
                    for t in users_resp.data:
                        flat = t.get('flat_number', 'Unknown')
                        t_people = t.get('num_people') or 0
                        reading_data = sub_map.get(flat, {})
                        
                        elec_units = reading_data.get('units_consumed', 0)
                        t_prev = reading_data.get('previous_reading', 0)
                        t_curr = reading_data.get('current_reading', 0)
                        
                        is_active = elec_units > 0
                        if is_active:
                            total_active_people += t_people
                        
                        processed_tenants.append({
                            'tenant': t,
                            'elec_units': elec_units,
                            't_prev': t_prev,
                            't_curr': t_curr,
                            't_people': t_people,
                            'is_active': is_active
                        })
                
                if total_active_people == 0: total_active_people = 1 
                units_per_person = water_stats["units"] / total_active_people
                
                elec_batch = []
                for item in processed_tenants:
                    t = item['tenant']
                    elec_units = item['elec_units']
                    is_active = item['is_active']
                    flat = t.get('flat_number', 'Unknown')
                    
                    rate = get_meter_rate_for_flat(flat, rates_data)
                    elec_cost = elec_units * rate
                    
                    if is_active:
                        t_people = item['t_people']
                        tenant_water_share_units = units_per_person * t_people
                        water_cost = tenant_water_share_units * water_rate
                        total_elec_amt = math.ceil(elec_cost + water_cost)
                        
                        elec_obj = {
                            "user_id": t['id'], "customer_name": t['full_name'], "bill_month": str(gen_date),
                            "previous_reading": item['t_prev'], "current_reading": item['t_curr'],
                            "units_consumed": elec_units, "tenant_water_units": tenant_water_share_units,
                            "rate_per_unit": rate, "water_charge": water_cost,
                            "total_amount": total_elec_amt, "status": "Pending"
                        }
                        elec_batch.append(elec_obj)
                        
                        with st.expander(f"✅ {t['full_name']}: ₹{total_elec_amt}"):
                            st.write("**1. Electricity**")
                            st.caption(f"{elec_units} units × ₹{rate:.2f}/unit = **₹{elec_cost:.2f}**")
                            st.write("**2. Water Share**")
                            st.caption(f"({water_stats['units']} Units / {total_active_people} Active People) × {t_people} Tenant People = {tenant_water_share_units:.2f} Units")
                            st.caption(f"{tenant_water_share_units:.2f} Units × ₹{water_rate:.2f}/Unit = **₹{water_cost:.2f}**")
                            st.divider()
                            st.write(f"**Grand Total:** ₹{elec_cost:.2f} + ₹{water_cost:.2f} = **₹{total_elec_amt}**")
                    else:
                        with st.expander(f"⚠️ {t['full_name']} (Inactive)"):
                            st.info("Electricity consumption is 0. Water charge is skipped.")
                            st.caption(f"Electricity: 0 units | Water: ₹0")

                if st.button("🚀 Generate Electricity Bills", type="primary", disabled=len(elec_batch)==0):
                    if elec_batch:
                        for obj in elec_batch:
                            conn.table("bills").upsert(obj, on_conflict="user_id, bill_month").execute()
                        st.success(f"Generated {len(elec_batch)} Electricity Bills!")

        # RENT GENERATION
        with col_B:
            st.markdown("### 🏠 Rent Generation")
            rent_batch = []
            if users_resp.data:
                for t in users_resp.data:
                    rent_amt = t.get('rent_amount') or 0
                    if rent_amt > 0:
                        rent_obj = {
                            "user_id": t['id'], "bill_month": str(gen_date),
                            "amount": rent_amt, "status": "Pending"
                        }
                        rent_batch.append(rent_obj)
                        st.caption(f"✅ {t['full_name']}: ₹{rent_amt}")
            
            if st.button("🚀 Generate Rent Bills", type="primary"):
                if rent_batch:
                    for obj in rent_batch:
                        conn.table("rent_records").upsert(obj, on_conflict="user_id, bill_month").execute()
                    st.success(f"Generated {len(rent_batch)} Rent Records!")
                else:
                    st.warning("No tenants with rent amount > 0 found.")

    # --- TAB 5: RECORDS ---
    with tab5:
        st.subheader("Records")
        r_opt = st.radio("View:", ["Electricity Bills", "Rent Records"])
        if st.button("Refresh"): st.rerun()
        
        if r_opt == "Electricity Bills":
            res = conn.table("bills").select("*").order("created_at", desc=True).limit(20).execute()
            if res.data: 
                clean_data = []
                for item in res.data:
                    item['txn_id'] = item.get('txn_id') or '-'
                    item['payment_mode'] = item.get('payment_mode') or '-'
                    clean_data.append(item)
                st.dataframe(pd.DataFrame(clean_data)[['customer_name', 'bill_month', 'total_amount', 'amount_paid', 'status', 'payment_mode', 'txn_id']])
        else:
            rent_res = conn.table("rent_records").select("*").order("created_at", desc=True).limit(20).execute()
            if rent_res.data:
                prof_res = conn.table("profiles").select("id, full_name").execute()
                p_map = {p['id']: p['full_name'] for p in prof_res.data}
                clean_data = []
                for r in rent_res.data:
                    r['name'] = p_map.get(r['user_id'], 'Unknown')
                    r['txn_id'] = r.get('txn_id') or '-'
                    r['payment_mode'] = r.get('payment_mode') or '-'
                    clean_data.append(r)
                st.dataframe(pd.DataFrame(clean_data)[['name', 'bill_month', 'amount', 'amount_paid', 'status', 'payment_mode', 'txn_id']])

    # --- TAB 6: OUTSTANDING SUMMARY ---
    with tab6:
        st.subheader("📉 Consolidated Outstanding Summary")
        
        summary_data = []
        all_tenants = conn.table("profiles").select("*").eq("role", "tenant").execute()
        all_pending_elec = conn.table("bills").select("*").neq("status", "Paid").execute()
        all_pending_rent = conn.table("rent_records").select("*").neq("status", "Paid").execute()
        
        def get_user_total(uid, record_list, amount_key):
            return sum([(r[amount_key] - (r.get('amount_paid', 0) or 0)) for r in record_list if r['user_id'] == uid])

        if all_tenants.data:
            for t in all_tenants.data:
                uid = t['id']
                rent_pending = get_user_total(uid, all_pending_rent.data, 'amount')
                elec_pending = get_user_total(uid, all_pending_elec.data, 'total_amount')
                total = rent_pending + elec_pending
                
                summary_data.append({
                    "Tenant Name": t['full_name'],
                    "Flat Number": t.get('flat_number', 'N/A'),
                    "Rent Pending (₹)": rent_pending,
                    "Electricity Pending (₹)": elec_pending,
                    "Total Due (₹)": total
                })
        
        if summary_data:
            df_summary = pd.DataFrame(summary_data)
            total_row = pd.DataFrame({
                "Tenant Name": ["TOTAL"],
                "Flat Number": ["-"],
                "Rent Pending (₹)": [df_summary["Rent Pending (₹)"].sum()],
                "Electricity Pending (₹)": [df_summary["Electricity Pending (₹)"].sum()],
                "Total Due (₹)": [df_summary["Total Due (₹)"].sum()]
            })
            df_final = pd.concat([df_summary, total_row], ignore_index=True)
            
            st.dataframe(
                df_final.style.format({
                    "Rent Pending (₹)": "₹{:.2f}", 
                    "Electricity Pending (₹)": "₹{:.2f}", 
                    "Total Due (₹)": "₹{:.2f}"
                }).apply(lambda x: ['font-weight: bold' if x.name == len(df_final)-1 else '' for i in x], axis=1), 
                hide_index=True, use_container_width=True
            )
        else:
            st.info("No tenant data available.")

# --- 5. TENANT DASHBOARD ---
def tenant_dashboard(user_details):
    render_top_nav(user_details)
    
    elec_res = conn.table("bills").select("*").eq("user_id", user_details['id']).neq("status", "Paid").execute()
    rent_res = conn.table("rent_records").select("*").eq("user_id", user_details['id']).neq("status", "Paid").execute()
    
    elec_due = sum([(b['total_amount'] - (b.get('amount_paid', 0) or 0)) for b in elec_res.data])
    rent_due = sum([(r['amount'] - (r.get('amount_paid', 0) or 0)) for r in rent_res.data])
    total_due = elec_due + rent_due
    
    if total_due > 0:
        st.error(f"⚠️ Total Outstanding Due: ₹{total_due}")
        with st.expander("💳 PAY DUES (UPI)", expanded=True):
            upi_id = "s.vihar@upi"
            upi_url = f"upi://pay?pa={upi_id}&pn=S_Vihar_Society&am={total_due}&cu=INR"
            qr_api = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={upi_url}"
            c1, c2 = st.columns([1, 2])
            c1.image(qr_api, caption=f"Scan to Pay ₹{total_due}")
            c2.write("1. Scan QR\n2. Pay Amount\n3. Click 'I have Paid' below")
            
            if c2.button("✅ I have Paid (Cash/Online)"):
                for b in elec_res.data:
                    conn.table("bills").update({"status": "Verifying"}).eq("id", b['id']).execute()
                for r in rent_res.data:
                    conn.table("rent_records").update({"status": "Verifying"}).eq("id", r['id']).execute()
                st.success("Sent for verification!")
                time.sleep(1)
                st.rerun()
    else:
        st.success("🎉 No Pending Dues!")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("⚡ Electricity Dues")
        if elec_res.data:
            for b in elec_res.data:
                paid = b.get('amount_paid', 0) or 0
                rem = b['total_amount'] - paid
                st.write(f"**{b['bill_month']}**: Remaining ₹{rem} (Paid: ₹{paid}) - {b['status']}")
        else: st.info("No electricity dues.")
            
    with c2:
        st.subheader("🏠 Rent Dues")
        if rent_res.data:
            for r in rent_res.data:
                paid = r.get('amount_paid', 0) or 0
                rem = r['amount'] - paid
                st.write(f"**{r['bill_month']}**: Remaining ₹{rem} (Paid: ₹{paid}) - {r['status']}")
        else: st.info("No rent dues.")

# --- 6. MAIN ---
def main():
    if 'user' not in st.session_state:
        c1, c2, c3 = st.columns([1, 2, 1]) 
        with c2:
            tab1, tab2 = st.tabs(["Login", "Register"])
            with tab1: login()
            with tab2: register()
    else:
        user = st.session_state.user
        profile = ensure_profile_exists(user.id, user.email)
        if profile:
            if profile.get('role') == 'admin':
                admin_dashboard(profile)
            else:
                tenant_dashboard(profile)

if __name__ == "__main__":
    main()
