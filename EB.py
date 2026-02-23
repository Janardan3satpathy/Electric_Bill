import streamlit as st
import pandas as pd
from datetime import date
from st_supabase_connection import SupabaseConnection
import uuid
import time

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="PropEase Admin", page_icon="🏢", layout="wide")
conn = st.connection("supabase", type=SupabaseConnection)

# (Keeping your set_background() function...)
def set_background():
    st.markdown("""
        <style>
        .stApp {
            background-image: linear-gradient(rgba(15,15,15,0.85), rgba(15,15,15,0.85)), url("https://images.unsplash.com/photo-1560518883-ce09059eeffa?ixlib=rb-4.0.3&auto=format&fit=crop&w=1920&q=80");
            background-attachment: fixed; background-size: cover;
        }
        .block-container {
            background-color: rgba(25, 25, 25, 0.7); backdrop-filter: blur(15px);
            border-radius: 20px; padding: 2rem; border: 1px solid rgba(255,255,255,0.1);
        }
        h1, h2, h3, p, label { color: #f0f2f6 !important; }
        </style>
    """, unsafe_allow_html=True)

set_background()

def admin_dashboard(user_id):
    st.sidebar.title("🛠️ Admin Tools")
    if st.sidebar.button("Logout"):
        conn.auth.sign_out()
        st.session_state.clear()
        st.rerun()

    # --- PROPERTY CONTEXT ---
    props_res = conn.table("properties").select("*").execute()
    properties = props_res.data if props_res.data else []

    if not properties:
        st.error("❌ No Properties Found.")
        return

    prop_opts = {p['property_name']: p['id'] for p in properties}
    selected_name = st.selectbox("🎯 Active Property", list(prop_opts.keys()))
    active_prop_id = prop_opts[selected_name]
    
    st.sidebar.success(f"Connected to: {selected_name}")

    t1, t2, t3, t4 = st.tabs(["👥 Tenants", "🏢 Meters", "⚡ Generate", "⚙️ Settings"])

    # --- TAB 1: TENANTS ---
    with t1:
        st.subheader("Resident Directory")
        
        # Pull existing tenants
        tenants_res = conn.table("profiles").select("*").eq("property_id", active_prop_id).order("flat_number").execute()
        
        if tenants_res.data:
            df = pd.DataFrame(tenants_res.data)
            st.dataframe(df[['full_name', 'flat_number', 'rent_amount', 'num_people', 'assigned_meter']], use_container_width=True, hide_index=True)
        else:
            st.warning("Building is currently empty.")

        st.divider()
        
        # --- QUICK ADD FORM ---
        with st.expander("➕ Add New Tenant to this Building"):
            with st.form("quick_add_tenant"):
                col1, col2 = st.columns(2)
                t_name = col1.text_input("Tenant Name")
                f_no = col2.text_input("Flat/Shop Number")
                
                col3, col4 = st.columns(2)
                rent = col3.number_input("Monthly Rent (₹)", min_value=0, step=500)
                ppl = col4.number_input("People Count", min_value=1, step=1)
                
                meter = st.selectbox("Meter Assignment", ["Ground Meter", "Middle Meter", "Upper Meter", "Main Meter"])
                
                if st.form_submit_button("✅ Save Tenant"):
                    if t_name and f_no:
                        try:
                            # Inserting without an email and with a generated UUID
                            new_id = str(uuid.uuid4())
                            conn.table("profiles").insert({
                                "id": new_id,
                                "full_name": t_name,
                                "flat_number": f_no,
                                "rent_amount": rent,
                                "num_people": ppl,
                                "assigned_meter": meter,
                                "property_id": active_prop_id,
                                "role": "tenant"
                            }).execute()
                            st.success(f"Tenant {t_name} added successfully!")
                            time.sleep(1)
                            st.rerun()
                        except Exception as e:
                            st.error(f"Failed to add tenant: {e}")
                    else:
                        st.warning("Please fill in Name and Flat Number.")

    # (Other tabs logic...)
    with t4:
        st.subheader("⚙️ Settings")
        st.write(f"Property ID: `{active_prop_id}`")

# --- MAIN ---
def main():
    if 'user' not in st.session_state:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.markdown("<h2 style='text-align: center;'>🔐 Admin Login</h2>", unsafe_allow_html=True)
            email = st.text_input("Email")
            pw = st.text_input("Password", type="password")
            if st.button("Sign In", type="primary", use_container_width=True):
                try:
                    res = conn.auth.sign_in_with_password({"email": email, "password": pw})
                    st.session_state.user = res.user
                    st.rerun()
                except:
                    st.error("Invalid Login Credentials")
    else:
        admin_dashboard(st.session_state.user.id)

if __name__ == "__main__":
    main()
