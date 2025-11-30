import streamlit as st
import pandas as pd
from datetime import date
from st_supabase_connection import SupabaseConnection

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="S. Vihar Electricity Manager", page_icon="⚡")

# Initialize Connection
conn = st.connection("supabase", type=SupabaseConnection)

# --- 2. AUTHENTICATION FUNCTIONS ---
def login():
    st.subheader("Login")
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
    st.subheader("Register New Tenant")
    email = st.text_input("Email", key="reg_email")
    password = st.text_input("Password", type="password", key="reg_pass")
    full_name = st.text_input("Full Name (e.g., Niharika)", key="reg_name")
    
    if st.button("Register"):
        try:
            # Metadata is passed to the trigger we made in SQL
            conn.auth.sign_up(dict(
                email=email, 
                password=password, 
                options=dict(data=dict(full_name=full_name))
            ))
            st.success("Registration successful! Please Log In.")
        except Exception as e:
            st.error(f"Registration failed: {e}")

def logout():
    conn.auth.sign_out()
    if 'user' in st.session_state:
        del st.session_state.user
    if 'role' in st.session_state:
        del st.session_state.role
    st.rerun()

# --- 3. HELPER: GET USER ROLE ---
def get_user_role(user_id):
    try:
        # We query the profiles table. RLS ensures we can only see what we are allowed to.
        response = conn.table("profiles").select("role, full_name").eq("id", user_id).single().execute()
        return response.data
    except:
        return None

# --- 4. ADMIN DASHBOARD ---
def admin_dashboard(user_details):
    st.title(f"Admin Dashboard 🛠️")
    st.write(f"Welcome, {user_details['full_name']}")
    
    tab1, tab2, tab3 = st.tabs(["➕ Add Bill", "📊 All Records", "📈 Summary"])

    # --- TAB 1: ADD BILL ---
    with tab1:
        st.subheader("Generate Tenant Bill")
        
        # 1. Select Tenant
        # Fetch all profiles who are tenants
        users_resp = conn.table("profiles").select("id, full_name, email").eq("role", "tenant").execute()
        tenant_options = {u['full_name']: u['id'] for u in users_resp.data}
        
        if not tenant_options:
            st.warning("No tenants registered yet.")
        else:
            with st.form("bill_gen_form"):
                selected_name = st.selectbox("Select Tenant", list(tenant_options.keys()))
                selected_uid = tenant_options[selected_name]
                
                col1, col2 = st.columns(2)
                with col1:
                    bill_date = st.date_input("Bill Date", value=date.today())
                    prev_reading = st.number_input("Previous Reading", min_value=0)
                with col2:
                    curr_reading = st.number_input("Current Reading", min_value=0)
                    water_amt = st.number_input("Water Charge (₹)", value=100.0)

                # Rate Calculator helper
                st.info("💡 Rate Calc: If Total Bill is ₹5000 for 1000 Units, Rate = 5.0")
                rate = st.number_input("Rate Per Unit (₹)", value=5.50, format="%.4f")
                
                # Auto Calculate
                units_consumed = curr_reading - prev_reading
                if units_consumed < 0: units_consumed = 0
                calc_total = (units_consumed * rate) + water_amt

                st.write(f"**Calculated Total:** ({units_consumed} units × ₹{rate}) + ₹{water_amt} = **₹{calc_total:.2f}**")
                
                submit = st.form_submit_button("Save Bill")
                
                if submit:
                    try:
                        conn.table("bills").insert({
                            "user_id": selected_uid,
                            "bill_month": str(bill_date),
                            "current_reading": curr_reading,
                            "previous_reading": prev_reading,
                            "units_consumed": units_consumed,
                            "rate_per_unit": rate,
                            "water_charge": water_amt,
                            "total_amount": calc_total,
                            "status": "Pending"
                        }).execute()
                        st.success(f"Bill generated for {selected_name}!")
                    except Exception as e:
                        st.error(f"Error: {e}")

    # --- TAB 2: VIEW ALL DATA ---
    with tab2:
        st.subheader("Master Database")
        # Fetch all bills joined with profile names
        # Note: Supabase-py join syntax: table(col, foreign_table(col))
        response = conn.table("bills").select("*, profiles(full_name)").order("bill_month", desc=True).execute()
        
        if response.data:
            df = pd.DataFrame(response.data)
            # Flatten the profile name
            df['Tenant Name'] = df['profiles'].apply(lambda x: x['full_name'] if x else 'Unknown')
            df = df.drop(columns=['profiles', 'user_id', 'created_at'])
            
            # Reorder cols
            cols = ['bill_month', 'Tenant Name', 'units_consumed', 'rate_per_unit', 'total_amount', 'status']
            st.dataframe(df[cols])
        else:
            st.info("No bills found.")

    # --- TAB 3: SUMMARY ---
    with tab3:
        if 'df' in locals():
            total_collected = df['total_amount'].sum()
            total_units = df['units_consumed'].sum()
            st.metric("Total Revenue Collected", f"₹{total_collected:,.2f}")
            st.metric("Total Units Billed", f"{total_units}")

# --- 5. TENANT DASHBOARD ---
def tenant_dashboard(user_details):
    st.title(f"Hello, {user_details['full_name']} 👋")
    
    # Summary Cards
    # Since RLS is on, this query ONLY returns this user's data
    response = conn.table("bills").select("*").order("bill_month", desc=True).execute()
    
    if response.data:
        df = pd.DataFrame(response.data)
        
        # Most recent bill
        latest = df.iloc[0]
        
        col1, col2, col3 = st.columns(3)
        col1.metric("Latest Bill Amount", f"₹{latest['total_amount']:.2f}")
        col2.metric("Units Consumed", f"{latest['units_consumed']}")
        col3.metric("Status", latest['status'])
        
        st.divider()
        st.subheader("Your Billing History")
        st.dataframe(df[['bill_month', 'previous_reading', 'current_reading', 'rate_per_unit', 'water_charge', 'total_amount', 'status']])
    else:
        st.info("You have no bills generated yet.")

# --- 6. MAIN APP FLOW ---
def main():
    if 'user' not in st.session_state:
        auth_mode = st.sidebar.radio("Menu", ["Login", "Register Tenant"])
        if auth_mode == "Login":
            login()
        else:
            register()
    else:
        # User is logged in
        user = st.session_state.user
        
        # Get Role details
        profile = get_user_role(user.id)
        
        if profile:
            with st.sidebar:
                st.write(f"Logged in as: **{profile['full_name']}**")
                st.button("Logout", on_click=logout)
            
            if profile['role'] == 'admin':
                admin_dashboard(profile)
            else:
                tenant_dashboard(profile)
        else:
            st.error("Profile not found. Please contact support.")
            st.button("Logout", on_click=logout)

if __name__ == "__main__":
    main()