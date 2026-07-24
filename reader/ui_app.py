import streamlit as st
import requests
import pandas as pd

# Set page configurations
st.set_page_config(
    page_title="RFQ Intelligence Dashboard",
    page_icon="📊",
    layout="wide",
)

# Custom CSS styling for premium look and feel
st.markdown("""
    <style>
    .main-title {
        background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%);
        color: white;
        padding: 2.5rem;
        border-radius: 12px;
        margin-bottom: 2rem;
        text-align: center;
        box-shadow: 0 4px 15px rgba(30, 60, 114, 0.2);
    }
    .main-title h1 {
        margin: 0;
        font-family: 'Outfit', 'Inter', sans-serif;
        font-size: 2.6rem;
        font-weight: 700;
        letter-spacing: -0.5px;
    }
    .main-title p {
        margin: 0.6rem 0 0 0;
        opacity: 0.9;
        font-size: 1.15rem;
        font-weight: 300;
    }
    .metric-card {
        background-color: #f8f9fa;
        border-radius: 10px;
        padding: 1.75rem;
        box-shadow: 0 4px 6px rgba(0, 0, 0, 0.03);
        border-left: 5px solid #2a5298;
        margin-bottom: 1.5rem;
    }
    .metric-value {
        font-size: 1.8rem;
        font-weight: bold;
        color: #2a5298;
    }
    </style>
""", unsafe_allow_html=True)

# Header Section
st.markdown("""
    <div class="main-title">
        <h1>📊 RFQ Intelligence Platform</h1>
        <p>Real-time Supplier Analysis and Quotation Comparison</p>
    </div>
""", unsafe_allow_html=True)

API_BASE_URL = "http://localhost:8000"

# Fetch RFQ list from FastAPI backend
try:
    rfqs_resp = requests.get(f"{API_BASE_URL}/rfqs")
    if rfqs_resp.status_code == 200:
        rfqs = rfqs_resp.json()
    else:
        rfqs = []
except Exception:
    rfqs = []

# Sidebar Navigation and connection status
st.sidebar.header("Navigation")
if not rfqs:
    st.sidebar.error("Disconnected from API server")
    st.sidebar.warning("Make sure the FastAPI server is running (`uvicorn api:app --port 8000`) inside the reader directory.")
    rfq_options = []
else:
    st.sidebar.success("Connected to API Server")
    rfq_options = [r["rfq_number"] for r in rfqs]

selected_rfq = st.sidebar.selectbox("Select RFQ Number", rfq_options if rfq_options else ["No RFQs found"])

if selected_rfq and selected_rfq != "No RFQs found":
    # Get active RFQ details
    rfq_detail = next((r for r in rfqs if r["rfq_number"] == selected_rfq), None)
    
    col1, col2 = st.columns([1, 3])
    
    with col1:
        st.markdown('<div class="metric-card">', unsafe_allow_html=True)
        st.subheader("RFQ Details")
        st.write(f"**Number:** {selected_rfq}")
        if rfq_detail:
            st.write(f"**Description:** {rfq_detail.get('part_description') or 'Not Specified'}")
            status = str(rfq_detail.get('status', 'open')).upper()
            st.write(f"**Status:** {status}")
        st.markdown('</div>', unsafe_allow_html=True)
        
    with col2:
        st.subheader("Supplier Comparison Grid")
        try:
            comp_resp = requests.get(f"{API_BASE_URL}/rfqs/{selected_rfq}/comparison")
            if comp_resp.status_code == 200:
                comparison_data = comp_resp.json()
            else:
                comparison_data = []
        except Exception as e:
            st.error(f"Error loading comparison: {e}")
            comparison_data = []
            
        if comparison_data:
            df = pd.DataFrame(comparison_data)
            
            # Format headers
            df.columns = [c.replace("_", " ").title() for c in df.columns]
            
            # Render styled dataframe with lowest price highlighted in green
            st.dataframe(df.style.highlight_min(axis=0, subset=["Price"], color="#d4edda"), use_container_width=True)
            
            # Bar chart visualization
            st.subheader("Quote Price Comparison Chart (INR)")
            df_chart = df[["Supplier", "Price"]].copy()
            df_chart = df_chart.set_index("Supplier")
            st.bar_chart(df_chart)
        else:
            st.info("No supplier quotations have been processed for this RFQ yet.")
else:
    st.info("No active RFQs detected in database. Please run an email extraction pipeline to automatically register RFQs and supplier quotes.")
