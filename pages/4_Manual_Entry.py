"""
pages/4_Manual_Entry.py — Manual Operational Metrics Entry
"""

import streamlit as st
from datetime import date, timedelta
from utils.db import fetch_one, execute_query, transaction

st.set_page_config(page_title="Manual Entry · Mosra Energy", layout="wide")

# ── Elegant Styling matching previous pages ───────────────────────────────────
st.markdown("""
<style>
[data-testid="stSidebar"] { background-color: #1a1a1a; }
[data-testid="stSidebar"] * { color: #ffffff !important; }

/* Primary Button Styling */
.stButton>button {
    background-color: #E63329;
    color: #ffffff;
    border: none;
    border-radius: 4px;
    font-weight: 600;
    padding: 0.5rem 1.5rem;
    transition: background-color 0.2s ease;
}
.stButton>button:hover {
    background-color: #c0271e;
    color: #ffffff;
}

/* Section Header Styling */
.section-header {
    font-size: 13px;
    font-weight: 700;
    color: #E63329;
    text-transform: uppercase;
    letter-spacing: 0.08em;
    margin: 20px 0 12px 0;
    border-bottom: 2px solid #f3f4f6;
    padding-bottom: 4px;
}

/* Metric Display Container */
.metric-summary-card {
    background-color: #f8f9fa;
    border-left: 4px solid #E63329;
    padding: 12px 16px;
    border-radius: 0 4px 4px 0;
    margin-top: 15px;
    font-weight: 600;
    font-size: 15px;
    color: #1a1a1a;
}
</style>
""", unsafe_allow_html=True)

st.markdown("## ✏️ Manual Metrics Entry")
st.caption("Enter operational figures sourced directly from weekly PDF memo reports.")

# ── Date Snap Helper ──────────────────────────────────────────────────────────
def get_previous_sunday(d: date) -> date:
    """Snaps any given date to the Sunday starting that week."""
    return d - timedelta(days=(d.weekday() + 1) % 7)

# ── Main Form Setup ───────────────────────────────────────────────────────────
col_site, col_start, col_end = st.columns(3)

with col_site:
    site = st.selectbox("Site", ["IFCM", "TRCM"], key="m_site")

with col_start:
    default_sunday = get_previous_sunday(date.today())
    
    # We keep the key here so the user's selection is tracked
    week_start = st.date_input(
        "Week Start (Sunday)",
        value=default_sunday,
        min_value=date(2025, 1, 1),
        key="m_ws",
    )

with col_end:
    # Always auto-computes to Saturday (6 days later)
    week_end = week_start + timedelta(days=6)
    
    # Swapped to text_input and removed the key to prevent session state locking
    st.text_input(
        "Week End (Saturday) — auto",
        value=week_end.strftime("%Y/%m/%d"),
        disabled=True
    )

# ── Load existing records if available ───────────────────────────────────────
existing = fetch_one(
    "SELECT * FROM weekly_manual_metrics WHERE site = %s AND week_start_date = %s",
    (site, week_start),
)
ex = existing or {}

def exv(key: str, default: float = 0.0) -> float:
    v = ex.get(key, default)
    return float(v) if v is not None else default

# ── Form Inputs ───────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">Sourcing & Production Metrics</div>', unsafe_allow_html=True)

col_m1, col_m2 = st.columns(2)
with col_m1:
    coal_local_miners = st.number_input(
        "Coal from Local Miners (MT)", value=exv("coal_from_local_miners_mt"),
        min_value=0.0, format="%.4f", step=0.01,
    )
    coal_ifcm = st.number_input(
        "Coal from IFCM (MT)", value=exv("coal_from_ifcm_mt"),
        min_value=0.0, format="%.4f", step=0.01,
    )
    coal_high_wall = st.number_input(
        "Coal from High Wall Mining (MT)", value=exv("coal_from_high_wall_mining_mt"),
        min_value=0.0, format="%.4f", step=0.01,
    )

with col_m2:
    coal_manejo = st.number_input(
        "Coal from Manejo (MT)", value=exv("coal_from_manejo_mt"),
        min_value=0.0, format="%.4f", step=0.01,
    )
    coal_ogboyaga = st.number_input(
        "Coal from Ogboyaga (MT)", value=exv("coal_from_ogboyaga_mt"),
        min_value=0.0, format="%.4f", step=0.01,
    )
    coal_mined = st.number_input(
        "Coal Mined (MT)", value=exv("coal_mined_mt"),
        min_value=0.0, format="%.4f", step=0.01,
    )

st.markdown('<div class="section-header">Excavation</div>', unsafe_allow_html=True)
bcm_excavated = st.number_input(
    "BCM Excavated (BCM)", value=exv("bcm_excavated_bcm"),
    min_value=0.0, format="%.4f", step=0.01,
)

st.markdown('<div class="section-header">Dispatch</div>', unsafe_allow_html=True)
coal_dispatched = st.number_input(
    "Coal Loaded / Dispatched (MT)", value=exv("coal_dispatched_mt"),
    min_value=0.0, format="%.4f", step=0.01,
)

# Dynamic Coal Stocked Calculation
total_coal_stocked = (
    coal_local_miners + coal_manejo + coal_ifcm +
    coal_ogboyaga + coal_high_wall + coal_mined
)

st.markdown(
    f'<div class="metric-summary-card">Calculated Total Coal Stocked: {total_coal_stocked:,.4f} MT</div>',
    unsafe_allow_html=True
)

st.write("") # Spacing

# ── Duplicate Check & Persistence ─────────────────────────────────────────────
allow_save = True
if existing:
    st.warning(f"⚠️ Metrics for **{site}** starting **{week_start}** already exist in the database.")
    overwrite = st.checkbox("Overwrite existing metrics for this site/week", value=False)
    if not overwrite:
        allow_save = False

if st.button("💾 Save Metrics", type="primary", disabled=not allow_save):
    try:
        execute_query("""
            INSERT INTO weekly_manual_metrics (
                site, week_start_date, week_end_date,
                coal_from_local_miners_mt, coal_from_manejo_mt,
                coal_from_ifcm_mt, coal_from_ogboyaga_mt,
                coal_from_high_wall_mining_mt, coal_mined_mt,
                bcm_excavated_bcm, total_coal_stocked_mt,
                coal_dispatched_mt, updated_at
            ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
            ON CONFLICT (site, week_start_date) DO UPDATE SET
                week_end_date                 = EXCLUDED.week_end_date,
                coal_from_local_miners_mt     = EXCLUDED.coal_from_local_miners_mt,
                coal_from_manejo_mt           = EXCLUDED.coal_from_manejo_mt,
                coal_from_ifcm_mt             = EXCLUDED.coal_from_ifcm_mt,
                coal_from_ogboyaga_mt         = EXCLUDED.coal_from_ogboyaga_mt,
                coal_from_high_wall_mining_mt = EXCLUDED.coal_from_high_wall_mining_mt,
                coal_mined_mt                 = EXCLUDED.coal_mined_mt,
                bcm_excavated_bcm             = EXCLUDED.bcm_excavated_bcm,
                total_coal_stocked_mt         = EXCLUDED.total_coal_stocked_mt,
                coal_dispatched_mt            = EXCLUDED.coal_dispatched_mt,
                updated_at                    = NOW();
        """, (
            site, week_start, week_end,
            float(coal_local_miners), float(coal_manejo),
            float(coal_ifcm), float(coal_ogboyaga),
            float(coal_high_wall), float(coal_mined),
            float(bcm_excavated), float(total_coal_stocked),
            float(coal_dispatched)
        ), commit=True)

        st.success(f"✅ Operational metrics successfully saved for **{site}** ({week_start} to {week_end}).")
    except Exception as e:
        st.error(f"❌ Database error: {e}")