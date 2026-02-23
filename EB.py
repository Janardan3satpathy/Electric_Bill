import streamlit as st
import pandas as pd
from datetime import date
from st_supabase_connection import SupabaseConnection
import math
import time

# --- 1. CONFIGURATION ---
st.set_page_config(page_title="PropEase Admin", page_icon="🏠", layout="wide")
conn = st.connection("supabase", type=SupabaseConnection)

# (Keeping your set_background() function here...)
def set_background():
    st.markdown("""
        <style>
        .stApp {
            background-image: linear-gradient(rgba(15,15,15,0.8), rgba(15,15,15,0.8)), url("https://images.unsplash.com/photo-1560518883-ce09059eeffa?ixlib=rb-4.0.3&auto=format&fit=crop&w=1920&q=80");
            background-attachment: fixed; background-size: cover;
        }
        .block-container {
            background-color: rgba(30, 30, 30, 0.6); backdrop-filter: blur(12px);
            border-radius: 20px; padding: 2rem 3rem; color: white;
        }
        </style>
    """, unsafe_allow_html=True)

set_background()

# --- 2. CORE FUNCTIONS ---

def login():
    st.subheader("🔐 Admin Portal")
    email = st.text_input("Admin Email")
    password = st.text_input("Password", type="password")
    if st.button("Sign In", type="primary", use_container_width=True):
        try:
            session = conn.auth.sign_in_with_password(dict(email=email, password=password))
            st.session_state.user = session.user
            st.rerun()
        except Exception as e:
            st.error("Access Denied: Invalid Admin Credentials")

def admin_dashboard(user_id):
    # Top Bar
    c1, c2 = st.columns([8, 1])
    c1.title("🏢 PropEase Management System")
    if c2.button("Logout"):
        conn.auth.sign_out()
        st.session_state.clear()
        st.rerun()
    st.divider()

    # Property Context
    props_res = conn.table("properties").select("*").eq("owner_id", user_id).execute()
    if not props_res.data:
        st.warning("No properties found. Please create one in 'Settings'.")
        active_prop_id = None
    else:
        prop_opts = {p['property_name']: p['id'] for p in props_res.data}
        sel_prop = st.selectbox("🎯 Active Building", list(prop_opts.keys()))
        active_prop_id = prop_opts[sel_prop]

    # Tabs (Removed Feedback and simplified others)
    tabs = st.tabs(["💰 Payments", "👥 Tenants", "🏢 Meters", "⚡ Generate", "📊 Records", "⚙️ Settings"])

    # (Your existing Admin Dashboard logic for tabs 1-7 goes here...)
    # Note: Inside your 'Tenants' tab, you can now add a button to 
    # "Add New Tenant" directly since they don't need to register themselves!

# --- 3. MAIN ENTRY ---
def main():
    if 'user' not in st.session_state:
        # Removed the Tabs for Login/Register. Only Login remains.
        col1, col2, col3 = st.columns([1, 2, 1])
        with col2:
            login()
    else:
        # We assume anyone logged in is an Admin/Owner now
        admin_dashboard(st.session_state.user.id)

if __name__ == "__main__":
    main()
