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
    st.markdown(
        """
        <style>
        .stApp {
            background-image: linear-gradient(rgba(15, 15, 15, 0.75), rgba(15, 15, 15, 0.75)), url("https://images.unsplash.com/photo-1560518883-ce09059eeffa?ixlib=rb-4.0.3&auto=format&fit=crop&w=1920&q=80");
            background-attachment: fixed;
            background-size: cover;
        }
        .block-container {
            background-color: rgba(30, 30, 30, 0.55);
            backdrop-filter: blur(10px);
            border-radius: 15px;
            padding: 2rem 3rem;
            box-shadow: 0 8px 32px 0 rgba(0, 0, 0, 0.5);
            margin-top: 2rem;
            margin-bottom: 2rem;
        }
        div[data-baseweb="input"], div[data-baseweb="select"] {
            background-color: rgba(255, 255, 255, 0.1);
        }
        </style>
        """,
        unsafe_allow_html=True
    )

set_background()

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

@st.dialog("⚠️ Confirm Logout")
def show_logout_dialog():
    st.write("Are you sure you want to end your session?")
    col1, col2 = st.columns(2)
    if col1.button("✅ Yes, Logout", use_container_width=True):
        conn.auth.sign_out()
        st.session_state.clear()
        st.rerun()
    if col2.button("❌ No, Stay", use_container_width=True):
        st.rerun()

def render_top_nav(profile):
    col_title, col_logout = st.columns([8, 1])
    with col_title:
        role_badge = "👑 Admin" if profile.get('role') == 'admin' else "👤 Tenant"
        st.title(f"Welcome, {profile.get('full_name')} {role_badge}")
    with col_logout:
        st.write("") 
        st.write("") 
        if st.button("Logout", type="secondary", use_container_width=True):
            show_logout_dialog()
    st.divider()

def login():
    st.subheader("🔐 Access PropEase Manager")
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

def get_last_month_reading(flat_number, current_date, property_id):
    try:
        res = conn.table("sub_meter_readings").select("current_reading").eq("flat_number", flat_number).eq("property_id", property_id).lt("bill_month", str(current_date)).order("bill_month", desc=True).limit(1).execute()
        if res.data: return res.data[0]['current_reading']
    except: pass
    return 0

# --- 3. ADMIN DASHBOARD ---
def admin_dashboard(user_details):
    render_top_nav(user_details)
    
    st.subheader("🏢 Property Context")
    try:
        props_res = conn.table("properties").select("*").eq("owner_id", user_details['id']).execute()
        properties = props_res.data
    except Exception:
        properties = []

    if properties:
        prop_opts = {p['property_name']: p['id'] for p in properties}
        selected_prop_name = st.selectbox("Select Active Property", list(prop_opts.keys()))
        active_prop_id = prop_opts[selected_prop_name]
    else:
        st.warning("No properties found. Please add a property in the '⚙️ Properties' tab to start.")
        active_prop_id = None
    st.divider()
    
    tab1, tab2, tab3, tab4, tab5, tab6, tab7, tab8 = st.tabs([
        "💰 Dues & Payments", "👥 Tenants & Flats", "🏢 Meters", "⚡ Generate Monthly", 
        "📊 Records", "📉 Outstanding Summary", "⚙️ Properties", "💬 Feedback"
    ])

    if not active_prop_id and st.session_state.get('active_tab') != "⚙️ Properties":
        st.info("Please navigate to the '⚙️ Properties' tab to set up your first property.")
        
        # We still want to render Tab 7 so they can create the property!
        with tab7:
            st.subheader("⚙️ Property Settings")
            with st.expander("➕ Add New Property"):
            with st.form("add_prop_form"):
                new_prop_name = st.text_input("New Property Name")
                new_prop_addr = st.text_input("Property Address")
                if st.form_submit_button("Create Property"):
                    try:
                        # Capture the result to check for errors
                        res = conn.table("properties").insert({
                            "owner_id": user_details['id'], 
                            "property_name": new_prop_name, 
                            "address": new_prop_addr,
                            "water_billing_mode": "S. Vihar Style (Shared)", 
                            "electricity_billing_mode": "Dynamic Main Meter"
                        }).execute()
                        
                        # If we get here, it worked!
                        st.success(f"✅ Property '{new_prop_name}' created successfully!")
                        time.sleep(1)
                        st.rerun()
                    except Exception as e:
                        # This will tell us EXACTLY why it's not confirming
                        st.error(f"❌ Database Error: {e}")
        return

    users_resp = conn.table("profiles").select("*").eq("role", "tenant").eq("property_id", active_prop_id).order("flat_number").execute() if active_prop_id else None

    # --- TAB 1: DUES & PAYMENTS ---
    with tab1:
        st.subheader("1. Payment Verification Queue (Online Claims)")
        pending_approvals = conn.table("bills").select("*").eq("status", "Verifying").eq("property_id", active_prop_id).execute()
        rent_approvals = conn.table("rent_records").select("*, profiles(full_name)").eq("status", "Verifying").eq("property_id", active_prop_id).execute()
        
        rent_verify_data = []
        if rent_approvals and rent_approvals.data:
            for r in rent_approvals.data:
                r['customer_name'] = r['profiles']['full_name'] if r['profiles'] else "Unknown"
                rent_verify_data.append(r)

        if (not pending_approvals or not pending_approvals.data) and not rent_verify_data:
            st.info("No online payment claims waiting for verification.")
        else:
            if pending_approvals and pending_approvals.data:
                for bill in pending_approvals.data:
                    paid = bill.get('amount_paid', 0) or 0
                    total = bill.get('total_amount', 0)
                    rem = total - paid
                    with st.expander(f"⚡ Verify Elec: {bill['customer_name']} - Claim for Remaining ₹{rem}"):
                        c1, c2, c3 = st.columns([2, 1, 1])
                        c1.write(f"Month: {bill['bill_month']}")
                        if c2.button("Approve Full", key=f"app_elec_{bill['id']}"):
                            conn.table("bills").update({"status": "Paid", "amount_paid": total}).eq("id", bill['id']).execute()
                            st.rerun()
                        if c3.button("Reject", key=f"rej_elec_{bill['id']}"):
                            conn.table("bills").update({"status": "Pending"}).eq("id", bill['id']).execute()
                            st.rerun()

            for r in rent_verify_data:
                paid = r.get('amount_paid', 0) or 0
                total = r.get('amount', 0)
                rem = total - paid
                with st.expander(f"🏠 Verify Rent: {r['customer_name']} - Claim for Remaining ₹{rem}"):
                    c1, c2, c3 = st.columns([2, 1, 1])
                    c1.write(f"Month: {r['bill_month']}")
                    if c2.button("Approve Full", key=f"app_rent_{r['id']}"):
                        conn.table("rent_records").update({"status": "Paid", "amount_paid": total}).eq("id", r['id']).execute()
                        st.rerun()
                    if c3.button("Reject", key=f"rej_rent_{r['id']}"):
                        conn.table("rent_records").update({"status": "Pending"}).eq("id", r['id']).execute()
                        st.rerun()

        st.divider()
        st.subheader("2. Manual Payment Entry")
        if users_resp and users_resp.data:
            user_opts = {f"{u['full_name']} ({u.get('flat_number', '?')})": u for u in users_resp.data}
            sel_label = st.selectbox("Select Tenant", list(user_opts.keys()))
            uid = user_opts[sel_label]['id']
            
            elec_res = conn.table("bills").select("*").eq("user_id", uid).eq("property_id", active_prop_id).neq("status", "Paid").execute()
            rent_res = conn.table("rent_records").select("*").eq("user_id", uid).eq("property_id", active_prop_id).neq("status", "Paid").execute()
            
            total_elec_due = sum([(item['total_amount'] - (item.get('amount_paid', 0) or 0)) for item in elec_res.data])
            total_rent_due = sum([(item['amount'] - (item.get('amount_paid', 0) or 0)) for item in rent_res.data])
            
            c1, c2, c3 = st.columns(3)
            c1.metric("Total Pending", f"₹{total_elec_due + total_rent_due}")
            c2.metric("Rent Pending", f"₹{total_rent_due}")
            c3.metric("Electricity Pending", f"₹{total_elec_due}")
            
            if rent_res.data:
                st.markdown("**🏠 Rent Dues**")
                for r in rent_res.data:
                    paid = r.get('amount_paid', 0) or 0
                    rem = r['amount'] - paid
                    with st.expander(f"Pay Rent: {r['bill_month']} | Due: ₹{rem}"):
                        rc1, rc2 = st.columns(2)
                        p_mode = rc1.selectbox("Mode", ["Cash", "Online"], key=f"pm_r_{r['id']}")
                        p_date = rc2.date_input("Date", value=date.today(), key=f"pd_r_{r['id']}")
                        p_type = st.selectbox("Type", ["Full Payment", "Partial Payment"], key=f"pt_r_{r['id']}")
                        
                        pay_amt = rem if p_type == "Full Payment" else st.number_input("Amount", min_value=1, max_value=int(rem), value=1, key=f"amt_r_{r['id']}")
                        tx_id = st.text_input("Txn ID", key=f"tx_r_{r['id']}") if p_mode == "Online" else ""
                        
                        if st.button(f"✅ Record (₹{pay_amt})", key=f"btn_r_{r['id']}"):
                            new_paid = paid + pay_amt
                            status = "Paid" if new_paid >= r['amount'] else "Partial"
                            conn.table("rent_records").update({"status": status, "amount_paid": new_paid, "payment_mode": p_mode, "payment_date": str(p_date), "txn_id": tx_id}).eq("id", r['id']).execute()
                            st.rerun()

            if elec_res.data:
                st.markdown("**⚡ Electricity Dues**")
                for b in elec_res.data:
                    paid = b.get('amount_paid', 0) or 0
                    rem = b['total_amount'] - paid
                    with st.expander(f"Pay Bill: {b['bill_month']} | Due: ₹{rem}"):
                        ec1, ec2 = st.columns(2)
                        p_mode = ec1.selectbox("Mode", ["Cash", "Online"], key=f"pm_e_{b['id']}")
                        p_date = ec2.date_input("Date", value=date.today(), key=f"pd_e_{b['id']}")
                        p_type = st.selectbox("Type", ["Full Payment", "Partial Payment"], key=f"pt_e_{b['id']}")
                        
                        pay_amt = rem if p_type == "Full Payment" else st.number_input("Amount", min_value=1, max_value=int(rem), value=1, key=f"amt_e_{b['id']}")
                        tx_id = st.text_input("Txn ID", key=f"tx_e_{b['id']}") if p_mode == "Online" else ""
                        
                        if st.button(f"✅ Record (₹{pay_amt})", key=f"btn_e_{b['id']}"):
                            new_paid = paid + pay_amt
                            status = "Paid" if new_paid >= b['total_amount'] else "Partial"
                            conn.table("bills").update({"status": status, "amount_paid": new_paid, "payment_mode": p_mode, "payment_date": str(p_date), "txn_id": tx_id}).eq("id", b['id']).execute()
                            st.rerun()

    # --- TAB 2: MANAGE TENANT DETAILS ---
    with tab2:
        st.subheader("Tenant Allotment & Rent Settings")
        if users_resp and users_resp.data:
            df_users = pd.DataFrame(users_resp.data)
            st.dataframe(df_users[['full_name', 'flat_number', 'assigned_meter', 'rent_amount', 'mobile']], hide_index=True)
            
            st.divider()
            user_opts = {f"{u['full_name']} ({u.get('flat_number', '?')})": u for u in users_resp.data}
            sel_u_edit = user_opts[st.selectbox("Select Tenant to Edit", list(user_opts.keys()), key="edit_sel")]
            
            with st.form("update_tenant_full"):
                c1, c2 = st.columns(2)
                new_flat = c1.text_input("Flat/Shop Number", value=sel_u_edit.get('flat_number', ''))
                new_meter = c2.text_input("Assigned Main Meter Name", value=sel_u_edit.get('assigned_meter', 'Main Meter'))
                
                c3, c4 = st.columns(2)
                new_rent = c3.number_input("Monthly Rent Amount (₹)", value=sel_u_edit.get('rent_amount', 0) or 0, min_value=0)
                new_count = c4.number_input("People Count (For Water)", value=sel_u_edit.get('num_people', 0) or 0, min_value=0)
                new_mobile = st.text_input("Mobile", value=sel_u_edit.get('mobile', ''))
                
                if st.form_submit_button("Update Tenant"):
                    conn.table("profiles").update({
                        "num_people": new_count, "flat_number": new_flat, "assigned_meter": new_meter,
                        "mobile": new_mobile, "rent_amount": new_rent, "property_id": active_prop_id
                    }).eq("id", sel_u_edit['id']).execute()
                    st.success("✅ Tenant updated!")
                    st.rerun()

    # --- TAB 3: DYNAMIC METERS CALCULATOR ---
    with tab3:
        st.subheader("Input Meter Readings")
        tenants = users_resp.data if users_resp and users_resp.data else []
        meter_names = sorted(list(set([t.get('assigned_meter', 'Main Meter') for t in tenants])))
        if not meter_names: meter_names = ["Main Meter"]

        c_s1, c_s2 = st.columns(2)
        meter_type = c_s1.selectbox("Select Meter:", meter_names)
        bill_date = c_s2.date_input("Bill Date", value=date.today())

        main_prev = 0
        try:
            last_m = conn.table("main_meters").select("current_reading").eq("meter_name", meter_type).eq("property_id", active_prop_id).lt("bill_month", str(bill_date)).order("bill_month", desc=True).limit(1).execute()
            if last_m.data: main_prev = last_m.data[0]['current_reading']
        except: pass

        st.markdown(f"### 1. {meter_type} (Main)")
        c_m1, c_m2, c_m3 = st.columns(3)
        mm_prev = c_m1.number_input("Main Prev", min_value=0, value=int(main_prev))
        mm_curr = c_m2.number_input("Main Curr", min_value=0, value=0)
        mm_bill = c_m3.number_input("Total Bill (₹)", min_value=0.0)
        
        mm_units = mm_curr - mm_prev
        mm_rate = 0.0 if mm_units <= 0 else mm_bill / mm_units
        st.info(f"**Consumption:** {mm_units} | **Rate:** ₹{mm_rate:.4f}")

        st.markdown("### 2. Connected Sub-Meters")
        flats_on_meter = [t for t in tenants if t.get('assigned_meter', 'Main Meter') == meter_type]
        sub_saves = []
        tot_sub = 0

        if flats_on_meter:
            for idx, f_t in enumerate(flats_on_meter):
                f_no = f_t.get('flat_number', f'T_{idx}')
                c1, c2 = st.columns(2)
                p_val = get_last_month_reading(f_no, bill_date, active_prop_id)
                st.write(f"**{f_t.get('full_name', 'Unk')} ({f_no})**")
                f_p = c1.number_input(f"Prev", value=int(p_val), key=f"p_{f_no}_{idx}")
                f_c = c2.number_input(f"Curr", value=0, key=f"c_{f_no}_{idx}")
                f_u = f_c - f_p
                tot_sub += f_u
                sub_saves.append({"flat": f_no, "prev": f_p, "curr": f_c, "units": f_u})
                st.markdown("---")
        else:
            st.info("No tenants assigned to this meter.")

        water_units = max(0, mm_units - tot_sub)
        water_cost = water_units * mm_rate
        st.warning(f"💧 **Common/Water Usage:** {water_units} Units (Cost: ₹{water_cost:.2f})")

        if st.button(f"Save {meter_type} Readings", type="primary"):
            try:
                conn.table("main_meters").upsert({
                    "property_id": active_prop_id, "meter_name": meter_type, "bill_month": str(bill_date),
                    "previous_reading": mm_prev, "current_reading": mm_curr, "units_consumed": mm_units,
                    "total_bill_amount": mm_bill, "calculated_rate": mm_rate, "water_units": water_units, "water_cost": water_cost
                }, on_conflict="property_id, meter_name, bill_month").execute()
                
                for item in sub_saves:
                    conn.table("sub_meter_readings").upsert({
                        "property_id": active_prop_id, "flat_number": item['flat'], "bill_month": str(bill_date),
                        "previous_reading": item['prev'], "current_reading": item['curr'], "units_consumed": item['units']
                    }, on_conflict="property_id, flat_number, bill_month").execute()
                st.success(f"✅ Saved!")
            except Exception as e:
                st.error(f"❌ Error: {e}")

    # --- TAB 4: GENERATE BILLS (DYNAMIC ENGINE) ---
    with tab4:
        st.subheader("Generate Monthly Bills")
        gen_date = st.date_input("Bill Date for Generation", value=date.today(), key="gen_date")
        
        current_prop = next((p for p in properties if p['id'] == active_prop_id), {})
        w_mode = current_prop.get('water_billing_mode', 'S. Vihar Style (Shared)')
        w_rate = float(current_prop.get('water_fixed_rate', 0.0))
        e_mode = current_prop.get('electricity_billing_mode', 'Dynamic Main Meter')
        e_rate = float(current_prop.get('electricity_fixed_rate', 8.0))
        
        mm_res = conn.table("main_meters").select("total_bill_amount, meter_name, calculated_rate, water_units").eq("bill_month", str(gen_date)).eq("property_id", active_prop_id).execute()
        bills_res = conn.table("bills").select("total_amount").eq("bill_month", str(gen_date)).eq("property_id", active_prop_id).execute()
        
        f1, f2 = st.columns(2)
        f1.metric("💸 Admin Payment", f"₹{sum([m['total_bill_amount'] for m in mm_res.data]) if mm_res.data else 0}")
        f2.metric("💰 Tenant Recovery", f"₹{sum([b['total_amount'] for b in bills_res.data]) if bills_res.data else 0}")
        st.divider()
        
        col_A, col_B = st.columns(2)
        with col_A:
            st.markdown("### ⚡ Electricity & 💧 Water")
            rates_data = {m['meter_name']: m['calculated_rate'] for m in mm_res.data} if mm_res.data else {}
            # Fallback to Ground Meter stats for S. Vihar style logic if it exists
            w_stats_units = next((m['water_units'] for m in (mm_res.data or []) if m['meter_name'] == 'Ground Meter'), 0)
            
            sub_res = conn.table("sub_meter_readings").select("*").eq("bill_month", str(gen_date)).eq("property_id", active_prop_id).execute()
            sub_map = {row['flat_number']: row for row in sub_res.data} if sub_res.data else {}
            
            tenants = users_resp.data if users_resp and users_resp.data else []
            tot_active_ppl = sum([t.get('num_people', 0) for t in tenants if sub_map.get(t.get('flat_number', ''), {}).get('units_consumed', 0) > 0])
            tot_active_ppl = max(1, tot_active_ppl) # Avoid division by zero
            
            units_per_person = w_stats_units / tot_active_ppl
            dyn_w_rate = rates_data.get('Ground Meter', 0)
            
            elec_batch = []
            for t in tenants:
                flat = t.get('flat_number', 'Unk')
                t_ppl = t.get('num_people', 0)
                r_data = sub_map.get(flat, {})
                e_units = r_data.get('units_consumed', 0)
                
                if e_units > 0:
                    rate = e_rate if e_mode == "Fixed Rate Per Unit" else rates_data.get(t.get('assigned_meter', 'Main Meter'), 0)
                    e_cost = e_units * rate
                    
                    w_cost = 0.0
                    t_w_units = 0
                    if w_mode == "No Water Bill (Electricity Only)": w_cost = 0.0
                    elif w_mode == "Fixed Rate Per Flat": w_cost = w_rate
                    elif w_mode == "Fixed Rate Per Person": w_cost = w_rate * t_ppl
                    else: 
                        t_w_units = units_per_person * t_ppl
                        w_cost = t_w_units * dyn_w_rate
                        
                    tot_amt = math.ceil(e_cost + w_cost)
                    elec_batch.append({
                        "property_id": active_prop_id, "user_id": t['id'], "customer_name": t['full_name'], 
                        "bill_month": str(gen_date), "previous_reading": r_data.get('previous_reading', 0), 
                        "current_reading": r_data.get('current_reading', 0), "units_consumed": e_units, 
                        "tenant_water_units": t_w_units, "rate_per_unit": rate, "water_charge": w_cost,
                        "total_amount": tot_amt, "status": "Pending"
                    })
                    with st.expander(f"✅ {t['full_name']}: ₹{tot_amt}"):
                        st.caption(f"Elec: {e_units}u @ ₹{rate:.2f} = ₹{e_cost:.2f} | Water: ₹{w_cost:.2f}")
                else:
                    st.info(f"⚠️ {t['full_name']}: 0 units (Inactive)")

            if st.button("🚀 Generate Utility Bills", type="primary", disabled=len(elec_batch)==0):
                for obj in elec_batch: conn.table("bills").upsert(obj, on_conflict="property_id, user_id, bill_month").execute()
                st.success(f"Generated {len(elec_batch)} Bills!")

        with col_B:
            st.markdown("### 🏠 Rent")
            rent_batch = [{"property_id": active_prop_id, "user_id": t['id'], "bill_month": str(gen_date), "amount": t.get('rent_amount',0), "status": "Pending"} for t in tenants if t.get('rent_amount',0) > 0]
            for r in rent_batch: st.caption(f"✅ ₹{r['amount']}")
            if st.button("🚀 Generate Rent Bills", type="primary", disabled=len(rent_batch)==0):
                for obj in rent_batch: conn.table("rent_records").upsert(obj, on_conflict="property_id, user_id, bill_month").execute()
                st.success(f"Generated {len(rent_batch)} Rent Records!")

    # --- TAB 5: RECORDS ---
    with tab5:
        r_opt = st.radio("View:", ["Electricity Bills", "Rent Records"])
        if r_opt == "Electricity Bills":
            res = conn.table("bills").select("*").eq("property_id", active_prop_id).order("created_at", desc=True).limit(20).execute()
            if res.data: st.dataframe(pd.DataFrame(res.data)[['customer_name', 'bill_month', 'total_amount', 'amount_paid', 'status']])
        else:
            rent_res = conn.table("rent_records").select("*, profiles(full_name)").eq("property_id", active_prop_id).order("created_at", desc=True).limit(20).execute()
            if rent_res.data:
                for r in rent_res.data: r['name'] = r['profiles']['full_name'] if r.get('profiles') else 'Unk'
                st.dataframe(pd.DataFrame(rent_res.data)[['name', 'bill_month', 'amount', 'amount_paid', 'status']])

    # --- TAB 6: OUTSTANDING SUMMARY (CSV EXPORT) ---
    with tab6:
        st.subheader("📉 Consolidated Outstanding Summary")
        all_pen_e = conn.table("bills").select("*").eq("property_id", active_prop_id).neq("status", "Paid").execute()
        all_pen_r = conn.table("rent_records").select("*").eq("property_id", active_prop_id).neq("status", "Paid").execute()
        
        sum_data = []
        tenants = users_resp.data if users_resp and users_resp.data else []
        for t in tenants:
            uid = t['id']
            r_pen = sum([(r['amount'] - (r.get('amount_paid',0) or 0)) for r in all_pen_r.data if r['user_id'] == uid]) if all_pen_r.data else 0
            e_pen = sum([(b['total_amount'] - (b.get('amount_paid',0) or 0)) for b in all_pen_e.data if b['user_id'] == uid]) if all_pen_e.data else 0
            sum_data.append({"Tenant Name": t['full_name'], "Rent Due": r_pen, "Elec Due": e_pen, "Total Due": r_pen + e_pen})
            
        if sum_data:
            df_sum = pd.DataFrame(sum_data)
            df_final = pd.concat([df_sum, pd.DataFrame({"Tenant Name": ["TOTAL"], "Rent Due": [df_sum["Rent Due"].sum()], "Elec Due": [df_sum["Elec Due"].sum()], "Total Due": [df_sum["Total Due"].sum()]})], ignore_index=True)
            st.dataframe(df_final, hide_index=True, use_container_width=True)
            st.download_button("📥 Download CSV", data=df_final.to_csv(index=False).encode('utf-8'), file_name=f'dues_{selected_prop_name}_{date.today()}.csv', mime='text/csv')

    # --- TAB 7: MANAGE PROPERTIES ---
    with tab7:
        st.subheader("⚙️ Property Settings")
        with st.expander("➕ Add New Property"):
            with st.form("add_prop_form"):
                new_prop_name = st.text_input("New Property Name")
                new_prop_addr = st.text_input("Property Address")
                if st.form_submit_button("Create Property"):
                    conn.table("properties").insert({
                        "owner_id": user_details['id'], "property_name": new_prop_name, "address": new_prop_addr,
                        "water_billing_mode": "S. Vihar Style (Shared)", "electricity_billing_mode": "Dynamic Main Meter"
                    }).execute()
                    st.success("Property created! Please refresh.")
                    st.rerun()

        if active_prop_id:
            st.divider()
            current_prop = next((p for p in properties if p['id'] == active_prop_id), {})
            with st.form("update_billing_settings"):
                w_opts = ["No Water Bill (Electricity Only)", "S. Vihar Style (Shared)", "Fixed Rate Per Flat", "Fixed Rate Per Person"]
                w_mode = current_prop.get('water_billing_mode', 'S. Vihar Style (Shared)')
                sel_w_mode = st.selectbox("Water Rules", w_opts, index=w_opts.index(w_mode) if w_mode in w_opts else 1)
                w_rate = st.number_input("Fixed Water Amount (₹) if applicable", value=float(current_prop.get('water_fixed_rate', 0.0)))

                e_opts = ["Dynamic Main Meter", "Fixed Rate Per Unit"]
                e_mode = current_prop.get('electricity_billing_mode', 'Dynamic Main Meter')
                sel_e_mode = st.selectbox("Electricity Rules", e_opts, index=e_opts.index(e_mode) if e_mode in e_opts else 0)
                e_rate = st.number_input("Fixed Rate Per Unit (₹)", value=float(current_prop.get('electricity_fixed_rate', 8.0)))

                if st.form_submit_button("💾 Save Settings", type="primary"):
                    conn.table("properties").update({
                        "water_billing_mode": sel_w_mode, "water_fixed_rate": w_rate,
                        "electricity_billing_mode": sel_e_mode, "electricity_fixed_rate": e_rate
                    }).eq("id", active_prop_id).execute()
                    st.success("Settings updated!")
                    st.rerun()

    # --- TAB 8: FEEDBACK ---
    with tab8:
        st.subheader("💬 Support & Feedback")
        with st.form("feedback_form"):
            f_msg = st.text_area("Your message:")
            if st.form_submit_button("Submit"):
                conn.table("feedback").insert({"owner_id": user_details['id'], "message": f_msg}).execute()
                st.success("Submitted!")

# --- 5. TENANT DASHBOARD ---
def tenant_dashboard(user_details):
    render_top_nav(user_details)
    
    # Tenants also need to pull by their assigned property!
    active_prop_id = user_details.get('property_id')
    
    elec_res = conn.table("bills").select("*").eq("user_id", user_details['id']).eq("property_id", active_prop_id).neq("status", "Paid").execute() if active_prop_id else None
    rent_res = conn.table("rent_records").select("*").eq("user_id", user_details['id']).eq("property_id", active_prop_id).neq("status", "Paid").execute() if active_prop_id else None
    
    e_data = elec_res.data if elec_res and elec_res.data else []
    r_data = rent_res.data if rent_res and rent_res.data else []
    
    elec_due = sum([(b['total_amount'] - (b.get('amount_paid', 0) or 0)) for b in e_data])
    rent_due = sum([(r['amount'] - (r.get('amount_paid', 0) or 0)) for r in r_data])
    total_due = elec_due + rent_due
    
    if total_due > 0:
        st.error(f"⚠️ Total Outstanding Due: ₹{total_due}")
        with st.expander("💳 PAY DUES (UPI)", expanded=True):
            upi_url = f"upi://pay?pa=propease@upi&pn=PropEase&am={total_due}&cu=INR"
            c1, c2 = st.columns([1, 2])
            c1.image(f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={upi_url}", caption=f"Pay ₹{total_due}")
            c2.write("1. Scan QR\n2. Pay Amount\n3. Click 'I have Paid' below")
            
            if c2.button("✅ I have Paid"):
                for b in e_data: conn.table("bills").update({"status": "Verifying"}).eq("id", b['id']).execute()
                for r in r_data: conn.table("rent_records").update({"status": "Verifying"}).eq("id", r['id']).execute()
                st.success("Sent for verification!")
                time.sleep(1)
                st.rerun()
    else:
        st.success("🎉 No Pending Dues!")

    st.divider()
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("⚡ Electricity Dues")
        for b in e_data: st.write(f"**{b['bill_month']}**: Rem ₹{b['total_amount'] - (b.get('amount_paid',0) or 0)} - {b['status']}")
    with c2:
        st.subheader("🏠 Rent Dues")
        for r in r_data: st.write(f"**{r['bill_month']}**: Rem ₹{r['amount'] - (r.get('amount_paid',0) or 0)} - {r['status']}")

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
            if profile.get('role') == 'admin': admin_dashboard(profile)
            else: tenant_dashboard(profile)

if __name__ == "__main__":
    main()

