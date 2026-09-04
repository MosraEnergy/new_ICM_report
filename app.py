"""
app.py — Mosra Energy Limited · Mining Operations Dashboard
Entry point. Streamlit multi-page app.
"""

import streamlit as st

st.set_page_config(
    page_title="Mosra Energy · Operations Dashboard",
    page_icon="⛏️",
    layout="wide",
    initial_sidebar_state="expanded",
)
# cutoff_lower = pd.Timestamp("2026-01-01")
    # cutoff_upper = pd.Timestamp.today().normalize()
    
    # df = df[(df["DATE"] >= cutoff_lower) & (df["DATE"] <= cutoff_upper)].copy()
# ── Brand CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #1a1a1a;
    }
    [data-testid="stSidebar"] * {
        color: #ffffff !important;
    }
    /* Primary accent */
    .stButton > button {
        background-color: #E63329;
        color: #ffffff;
        border: none;
        border-radius: 4px;
        font-weight: 600;
    }
    .stButton > button:hover {
        background-color: #c0271e;
        color: #ffffff;
    }
    /* KPI card */
    .kpi-card {
        background: #ffffff;
        border-left: 4px solid #E63329;
        border-radius: 6px;
        padding: 16px 20px;
        box-shadow: 0 1px 4px rgba(0,0,0,0.08);
        margin-bottom: 8px;
    }
    .kpi-label {
        font-size: 12px;
        color: #6b7280;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 4px;
    }
    .kpi-value {
        font-size: 26px;
        font-weight: 700;
        color: #111827;
        line-height: 1.2;
    }
    .kpi-sub {
        font-size: 12px;
        color: #9ca3af;
        margin-top: 2px;
    }
    /* Section header */
    .section-header {
        font-size: 15px;
        font-weight: 700;
        color: #E63329;
        text-transform: uppercase;
        letter-spacing: 0.06em;
        margin: 24px 0 12px 0;
        border-bottom: 1px solid #f3f4f6;
        padding-bottom: 6px;
    }
    /* Page title */
    .page-title {
        font-size: 24px;
        font-weight: 800;
        color: #111827;
        margin-bottom: 4px;
    }
    .page-subtitle {
        font-size: 14px;
        color: #6b7280;
        margin-bottom: 24px;
    }
</style>
""", unsafe_allow_html=True)

st.markdown("""
<div style="display:flex;align-items:center;gap:12px;margin-bottom:8px;">
    <span style="font-size:32px;">⛏️</span>
    <div>
        <div style="font-size:22px;font-weight:800;color:#111827;line-height:1.1;">
            MOSRA ENERGY LIMITED
        </div>
        <div style="font-size:13px;color:#E63329;font-weight:600;letter-spacing:0.08em;">
            MINING OPERATIONS DASHBOARD
        </div>
    </div>
</div>
<hr style="border:none;border-top:2px solid #E63329;margin:8px 0 20px 0;">
""", unsafe_allow_html=True)

st.markdown("""
Use the **sidebar navigation** to access each section:

| Page | Purpose |
|---|---|
| 📊 Dashboard | KPIs, charts, YTD summaries |
| 🪨 Upload Coal Report | Weekly coal stock inventory |
| ⛽ Upload Diesel Log | Master diesel dispensing log |
| ✏️ Manual Entry | Operational metrics & client dispatch |

---
**Sites covered:** IFCM (Idowu Falola Coal Mines) · TRCM (Tunde Ramos Coal Mines)  
**Data period:** 1 Jan 2026 – present  
""")
