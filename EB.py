import streamlit as st
import pandas as pd
from datetime import date
from st_supabase_connection import SupabaseConnection
import math
import time

# --- 1. CONFIGURATION & STYLING ---
st.set_page_config(page_title="PropEase Admin", page_icon="🏢", layout="wide")
conn = st.connection("supabase", type=SupabaseConnection)

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
        .stTabs [data-baseweb="tab"] { color: white !important; }
        </style>
    """, unsafe_allow_html=True)

set_background()

# --- 2. ADMIN DASHBOARD ---

def admin_dashboard(user_id):
    # Sidebar Info
    st.sidebar.title("🛠️ Admin Tools")
    st.sidebar.write(f"Logged in: `{st.session_state.user.email}`")
    
    if st.sidebar.button("Logout"):
        conn.auth.sign_out()
        st.session_state.clear()
        st.rerun()

    # --- PROPERTY SELECTION ---
    # We look for the property you claimed: db0cd063-e2f2-493f-8d0c-4d61138d33d1
    props_res = conn.table("properties").select("*").execute()
    properties = props_res.data if props_res.data else []

    if not properties:
        st.error("❌ No Properties Found in Database.")
        st.info("Please run the SQL commands to link your Auth ID to the Property ID.")
        return

    prop_opts = {p['property_name']: p['id'] for p in properties}
    selected_name = st.selectbox("🎯 Active Property", list(prop_opts.keys()))
    active_prop_id = prop_opts[selected_name]
    
    # DEBUG: Show current connection
    st.sidebar.success(f"Connected to: {selected_name}")
    st.sidebar.caption(f"Prop ID: {active_prop_id}")

    # --- TABS ---
    t1, t2, t3, t4, t5 = st.tabs(["👥 Tenants", "🏢 Meters", "⚡ Generate", "📊 Records", "⚙️ Settings"])

    # TAB 1: TENANTS
    with t1:
        st.subheader("Resident Directory")
        # Pull all tenants linked to this specific property
        tenants_res = conn.table("profiles").select("*").eq("property_id", active_prop_id).order("flat_number").execute()
        
        if tenants_res.data:
            df = pd.DataFrame(tenants_res.data)
            # Filter and rename for display
            display_df = df[['full_name', 'flat_number', 'rent_amount', 'num_people', 'assigned_meter']]
            st.dataframe(display_df, use_container_width=True, hide_index=True)
        else:
            st.warning("No tenants found for this property.")
            st.info("If you have tenants in the database, ensure their 'property_id' matches the ID in the sidebar.")

    # TAB 2: METERS
    with t2:
        st.subheader("Input Meter Readings")
        # Logic for meter entry...
        st.info("Ready for reading input for the current month.")

    # TAB 5: SETTINGS
    with t5:
        st.subheader("⚙️ System Configuration")
        with st.expander("Database Status"):
            st.write("Auth ID:", user_id)
            st.write("Active Property ID:", active_prop_id)
        
        st.divider()
        if st.button("🔄 Force Refresh Cache"):
            st.rerun()

# --- 3. LOGIN & MAIN ---

def main():
    if 'user' not in st.session_state:
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            st.write("")
            st.write("")
            st.markdown("<h2 style='text-align: center;'>🔐 PropEase Admin</h2>", unsafe_allow_html=True)
            email = st.text_input("Admin Email")
            pw = st.text_input("Password", type="password")
            if st.button("Sign In", type="primary", use_container_width=True):
                try:
                    res = conn.auth.sign_in_with_password({"email": email, "password": pw})
                    st.session_state.user = res.user
                    st.rerun()
                except Exception as e:
                    st.error("Invalid Login. Please check your credentials.")
    else:
        admin_dashboard(st.session_state.user.id)

if __name__ == "__main__":
    main()
