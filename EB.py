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
    
    # REORGANIZED TABS
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
        st.subheader("Actionable Dues (Mark as Paid)")
        
        users_resp = conn.table("profiles").select("*").eq("role", "tenant").order("flat_number").execute()
        user_opts = {f"{u['full_name']} ({u.get('flat_number', '?')})": u for u in users_resp.data}
        
        if not user_opts:
            st.warning("No tenants found.")
        else:
            sel_label = st.selectbox("Select Tenant to Update Payment", list(user_opts.keys()))
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
            
            with st.expander("🔻 View Details & Update", expanded=True):
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
            g2_curr = c_g2.number_input("102 Curr", value=0, key="102c")
            sub_readings_to_save.append({"flat": "102", "prev": g2_prev, "curr": g2_curr, "units": g2_curr - g2_prev})
            
            water_units = mm_units - ((g1_curr-g1_prev) + (g2_curr-g2_prev))
            if water_units < 0: water_units = 0
            water_cost = water_units * mm_rate

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

    # --- TAB 4: GENERATE BILLS (UPDATED WITH FINANCIAL SUMMARY) ---
    with tab4:
        st.subheader("Generate Monthly Bills")
        col_gen1, col_gen2 = st.columns(2)
        gen_date = col_gen1.date_input("Bill Date for Generation", value=date.today())
        
        # --- NEW: FINANCIAL SUMMARY ---
        st.markdown("### 📊 Financial Overview for Month")
        
        # 1. Admin Paid (Main Meters)
        admin_paid = 0
        mm_res = conn.table("main_meters").select("total_bill_amount").eq("bill_month", str(gen_date)).execute()
        if mm_res.data:
            admin_paid = sum([m['total_bill_amount'] for m in mm_res.data])
            
        # 2. Tenant Recovery (Generated Bills)
        tenant_recovery = 0
        bills_res = conn.table("bills").select("total_amount").eq("bill_month", str(gen_date)).execute()
        if bills_res.data:
            tenant_recovery = sum([b['total_amount'] for b in bills_res.data])
            
        f1, f2 = st.columns(2)
        f1.metric("💸 Total Admin Payment (Input)", f"₹{admin_paid}")
        f2.metric("💰 Total Tenant Bills (Recovery)", f"₹{tenant_recovery}")
        
        st.divider()
        col_A, col_B = st.columns(2)
        
        with col_A:
            st.markdown("### ⚡ Electricity Generation")
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
                st.warning("⚠️ Meters not saved for this date.")
            else:
                total_people = sum([(t.get('num_people') or 0) for t in users_resp.data]) if users_resp.data else 1
                if total_people == 0: total_people = 1
                units_per_person = water_stats["units"] / total_people
                
                elec_batch = []
                if users_resp.data:
                    for t in users_resp.data:
                        flat = t.get('flat_number', 'Unknown')
                        t_prev = 0; t_curr = 0; elec_units = 0
                        try:
                            sub_res = conn.table("sub_meter_readings").select("*").eq("flat_number", flat).eq("bill_month", str(gen_date)).execute()
                            if sub_res.data:
                                row = sub_res.data[0]
                                t_prev = row['previous_reading']
                                t_curr = row['current_reading']
                                elec_units = row['units_consumed']
                        except: pass
                        
                        if t_curr > 0:
                            rate = get_meter_rate_for_flat(flat, rates_data)
                            elec_cost = elec_units * rate
                            water_cost = (units_per_person * (t.get('num_people') or 0)) * rates_data.get('Ground Meter', 0)
                            total_elec_amt = math.ceil(elec_cost + water_cost)
                            
                            elec_obj = {
                                "user_id": t['id'], "customer_name": t['full_name'], "bill_month": str(gen_date),
                                "previous_reading": t_prev, "current_reading": t_curr,
                                "units_consumed": elec_units, "tenant_water_units": (units_per_person * (t.get('num_people') or 0)),
                                "rate_per_unit": rate, "water_charge": water_cost,
                                "total_amount": total_elec_amt, "status": "Pending"
                            }
                            elec_batch.append(elec_obj)
                            st.caption(f"✅ {t['full_name']}: ₹{total_elec_amt}")
                
                if st.button("🚀 Generate Electricity Bills", type="primary"):
                    if elec_batch:
                        for obj in elec_batch:
                            conn.table("bills").upsert(obj, on_conflict="user_id, bill_month").execute()
                        st.success(f"Generated {len(elec_batch)} Electricity Bills!")
                    else:
                        st.error("No valid meter readings found.")

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

    # --- TAB 5: RECORDS (SAFE MODE) ---
    with tab5:
        st.subheader("Records")
        r_opt = st.radio("View:", ["Electricity Bills", "Rent Records"])
        if st.button("Refresh"): st.rerun()
        
        if r_opt == "Electricity Bills":
            res = conn.table("bills").select("*").order("created_at", desc=True).limit(20).execute()
            if res.data: st.dataframe(pd.DataFrame(res.data)[['customer_name', 'bill_month', 'total_amount', 'status']])
        else:
            # Safe Fetch without Join
            rent_res = conn.table("rent_records").select("*").order("created_at", desc=True).limit(20).execute()
            if rent_res.data:
                # Fetch profiles map
                prof_res = conn.table("profiles").select("id, full_name").execute()
                p_map = {p['id']: p['full_name'] for p in prof_res.data}
                
                data = []
                for r in rent_res.data:
                    r['name'] = p_map.get(r['user_id'], 'Unknown')
                    data.append(r)
                st.dataframe(pd.DataFrame(data)[['name', 'bill_month', 'amount', 'status']])

    # --- TAB 6: OUTSTANDING SUMMARY (UPDATED WITH TOTAL ROW) ---
    with tab6:
        st.subheader("📉 Consolidated Outstanding Summary")
        
        summary_data = []
        
        # 1. Fetch All Tenants
        all_tenants = conn.table("profiles").select("*").eq("role", "tenant").execute()
        
        # 2. Fetch All Pending Records (Efficient)
        all_pending_elec = conn.table("bills").select("*").neq("status", "Paid").execute()
        all_pending_rent = conn.table("rent_records").select("*").neq("status", "Paid").execute()
        
        # Helper
        def get_user_total(uid, record_list, amount_key):
            return sum([r[amount_key] for r in record_list if r['user_id'] == uid])

        if all_tenants.data:
            for t in all_tenants.data:
                uid = t['id']
                name = t['full_name']
                flat = t.get('flat_number', 'N/A')
                
                rent_pending = get_user_total(uid, all_pending_rent.data, 'amount')
                elec_pending = get_user_total(uid, all_pending_elec.data, 'total_amount')
                total = rent_pending + elec_pending
                
                # Show everyone, even if 0 due (for complete report)
                summary_data.append({
                    "Tenant Name": name,
                    "Flat Number": flat,
                    "Rent Pending (₹)": rent_pending,
                    "Electricity Pending (₹)": elec_pending,
                    "Total Due (₹)": total
                })
        
        if summary_data:
            df_summary = pd.DataFrame(summary_data)
            
            # --- ADD TOTAL ROW ---
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
                hide_index=True,
                use_container_width=True
            )
        else:
            st.info("No tenant data available.")

# --- 5. TENANT DASHBOARD ---
def tenant_dashboard(user_details):
    st.title(f"Welcome, {user_details.get('full_name')} 👋")
    
    elec_res = conn.table("bills").select("*").eq("user_id", user_details['id']).neq("status", "Paid").execute()
    rent_res = conn.table("rent_records").select("*").eq("user_id", user_details['id']).neq("status", "Paid").execute()
    
    total_due = sum([b['total_amount'] for b in elec_res.data]) + sum([r['amount'] for r in rent_res.data])
    
    if total_due > 0:
        st.error(f"⚠️ Total Outstanding Due: ₹{total_due}")
        
        with st.expander("💳 PAY DUES (UPI)", expanded=True):
            upi_id = "s.vihar@upi"
            upi_url = f"upi://pay?pa={upi_id}&pn=S_Vihar_Society&am={total_due}&cu=INR"
            qr_api = f"https://api.qrserver.com/v1/create-qr-code/?size=250x250&data={upi_url}"
            
            c1, c2 = st.columns([1, 2])
            c1.image(qr_api, caption=f"Scan to Pay ₹{total_due}")
            c2.write("1. Scan QR\n2. Pay Amount\n3. Notify Admin")
    else:
        st.success("🎉 No Pending Dues!")

    st.divider()
    
    c1, c2 = st.columns(2)
    with c1:
        st.subheader("⚡ Electricity Dues")
        if elec_res.data:
            for b in elec_res.data:
                st.write(f"**{b['bill_month']}**: ₹{b['total_amount']} ({b['status']})")
                if b['status'] == 'Pending':
                    if st.button(f"Mark Paid (Elec {b['bill_month']})", key=f"t_elec_{b['id']}"):
                        conn.table("bills").update({"status": "Verifying"}).eq("id", b['id']).execute()
                        st.rerun()
        else:
            st.info("No electricity dues.")
            
    with c2:
        st.subheader("🏠 Rent Dues")
        if rent_res.data:
            for r in rent_res.data:
                st.write(f"**{r['bill_month']}**: ₹{r['amount']} ({r['status']})")
                if r['status'] == 'Pending':
                    if st.button(f"Mark Paid (Rent {r['bill_month']})", key=f"t_rent_{r['id']}"):
                        conn.table("rent_records").update({"status": "Verifying"}).eq("id", r['id']).execute()
                        st.rerun()
        else:
            st.info("No rent dues.")

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
