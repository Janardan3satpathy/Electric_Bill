import streamlit as st
import pandas as pd
from datetime import date
from st_supabase_connection import SupabaseConnection
import random

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="S. Vihar Electricity Manager", page_icon="⚡")

# Initialize Connection
conn = st.connection("supabase", type=SupabaseConnection)

# --- 2. AUTHENTICATION FUNCTIONS ---

def generate_captcha():
    """Generates a simple math problem."""
    if 'captcha_num1' not in st.session_state:
        st.session_state.captcha_num1 = random.randint(1, 10)
        st.session_state.captcha_num2 = random.randint(1, 10)
    return st.session_state.captcha_num1, st.session_state.captcha_num2

def ensure_profile_exists(user_id, email):
    """
    Safety mechanism: If a user logs in but has no profile, create one.
    This fixes the 'Profile not found' error permanently.
    """
    try:
        # Try to get the profile
        resp = conn.table("profiles").select("*").eq("id", user_id).execute()
        if not resp.data:
            # Profile missing! Create it manually.
            st.warning("⚠️ Profile missing. Attempting auto-repair...")
            conn.table("profiles").insert({
                "id": user_id,
                "email": email,
                "full_name": "User", # Default name
                "role": "tenant"     # Default role
            }).execute()
            st.success("✅ Profile repaired! Please continue.")
            # Fetch again
            resp = conn.table("profiles").select("*").eq("id", user_id).execute()
        return resp.data[0]
    except Exception as e:
        st.error(f"Critical Error loading profile: {e}")
        return None

def login():
    st.subheader("🔐 Login")
    email = st.text_input("Email", key="login_email")
    password = st.text_input("Password", type="password", key="login_pass")
    
    if st.button("Sign In"):
        try:
            session = conn.auth.sign_in_with_password(dict(email=email, password=password))
            st.session_state.user = session.user
            st.success("Logged in successfully!")
            st.rerun()
        except Exception as e:
            st.error(f"Login failed: {e}")

def register():
    st.subheader("📝 Register New Tenant")
    
    with st.form("register_form"):
        col1, col2 = st.columns(2)
        with col1:
            full_name = st.text_input("Full Name (e.g., Niharika)")
            email = st.text_input("Email")
        with col2:
            mobile = st.text_input("Mobile Number")
            password = st.text_input("Password", type="password")

        # --- CAPTCHA SECTION ---
        st.divider()
        n1, n2 = generate_captcha()
        st.write(f"**Security Check:** What is {n1} + {n2}?")
        captcha_answer = st.number_input("Enter Answer", min_value=0, step=1)
        
        submitted = st.form_submit_button("Register")
        
        if submitted:
            # 1. Verify Captcha
            if captcha_answer != (n1 + n2):
                st.error("❌ Incorrect Captcha. Please try again.")
                # Reset captcha for next try
                del st.session_state.captcha_num1
                st.rerun()
                return

            # 2. Attempt Registration
            try:
                # A. Create Auth User
                response = conn.auth.sign_up(dict(
                    email=email, 
                    password=password,
                    options=dict(data=dict(full_name=full_name))
                ))
                
                if response.user:
                    user_id = response.user.id
                    
                    # B. FORCE INSERT PROFILE (The Fix)
                    # We do this manually to ensure it exists.
                    try:
                        conn.table("profiles").insert({
                            "id": user_id,
                            "email": email,
                            "full_name": full_name,
                            "mobile": mobile,
                            "role": "tenant"
                        }).execute()
                        st.success("✅ Account created successfully! You can now Login.")
                    except Exception as e:
                        # If insert fails, it might be because the Trigger actually worked. 
                        # We ignore duplicate errors but show others.
                        if "duplicate key" not in str(e):
                            st.warning(f"Note: Profile creation had a hiccup, but Account is ready. {e}")
                        else:
                            st.success("✅ Account created successfully! You can now Login.")
                
            except Exception as e:
                st.error(f"Registration failed: {e}")

def logout():
    conn.auth.sign_out()
    st.session_state.clear()
    st.rerun()

# --- 3. DASHBOARD LOGIC (Admin & Tenant) ---

def admin_dashboard(user_details):
    st.title(f"Admin Dashboard 🛠️")
    st.info(f"Logged in as: {user_details.get('full_name')} (Admin)")
    
    tab1, tab2 = st.tabs(["➕ Add Bill", "📊 All Records"])

    # --- TAB 1: ADD BILL ---
    with tab1:
        # Fetch tenants
        users_resp = conn.table("profiles").select("id, full_name, mobile").eq("role", "tenant").execute()
        tenant_options = {f"{u['full_name']} ({u.get('mobile', 'No #')})": u for u in users_resp.data}
        
        if not tenant_options:
            st.warning("No registered tenants found.")
        else:
            selected_label = st.selectbox("Select Tenant", list(tenant_options.keys()))
            selected_user = tenant_options[selected_label]
            
            with st.form("bill_gen"):
                c1, c2 = st.columns(2)
                prev = c1.number_input("Previous Reading", min_value=0)
                curr = c2.number_input("Current Reading", min_value=0)
                rate = st.number_input("Rate/Unit (₹)", value=5.50)
                water = st.number_input("Water Charge (₹)", value=100.0)
                
                units = curr - prev
                total = (units * rate) + water
                st.write(f"**Total Bill:** ₹{total:.2f}")
                
                if st.form_submit_button("Save Bill"):
                    try:
                        conn.table("bills").insert({
                            "user_id": selected_user['id'],
                            "customer_name": selected_user['full_name'],
                            "bill_month": str(date.today()),
                            "units_consumed": units,
                            "rate_per_unit": rate,
                            "water_charge": water,
                            "total_amount": total,
                            "status": "Pending"
                        }).execute()
                        st.success("Bill Saved!")
                    except Exception as e:
                        st.error(f"Error: {e}")

    # --- TAB 2: HISTORY ---
    with tab2:
        res = conn.table("bills").select("*").order("created_at", desc=True).execute()
        if res.data:
            st.dataframe(pd.DataFrame(res.data))
        else:
            st.info("No records found.")

def tenant_dashboard(user_details):
    st.title(f"Welcome, {user_details.get('full_name')} 👋")
    st.write(f"Mobile: {user_details.get('mobile', 'Not provided')}")
    
    # Securely fetch ONLY this user's bills
    res = conn.table("bills").select("*").eq("user_id", user_details['id']).order("created_at", desc=True).execute()
    
    if res.data:
        df = pd.DataFrame(res.data)
        latest = df.iloc[0]
        st.metric("Latest Bill", f"₹{latest['total_amount']}", f"{latest['bill_month']}")
        st.dataframe(df)
    else:
        st.info("No bills generated for you yet.")

# --- 4. MAIN APP FLOW ---
def main():
    if 'user' not in st.session_state:
        # Not logged in
        choice = st.sidebar.radio("Menu", ["Login", "Register"])
        if choice == "Login":
            login()
        else:
            register()
    else:
        # Logged in
        user = st.session_state.user
        
        # Auto-Repair Profile Check
        profile = ensure_profile_exists(user.id, user.email)
        
        if profile:
            with st.sidebar:
                st.write(f"User: {profile.get('full_name')}")
                st.button("Logout", on_click=logout)
            
            if profile.get('role') == 'admin':
                admin_dashboard(profile)
            else:
                tenant_dashboard(profile)

if __name__ == "__main__":
    main()