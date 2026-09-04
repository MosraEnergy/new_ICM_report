"""
pages/2_Upload_Coal.py — Upload Weekly Coal Stock Inventory
"""

import streamlit as st
import pandas as pd
import io
from datetime import date, timedelta
import psycopg2.extras
from utils.db import fetch_one, execute, execute_many, transaction
from utils.parsers import parse_coal_excel
from utils.db import fetch_one, transaction

st.set_page_config(page_title="Upload Coal · Mosra Energy", layout="wide")

st.markdown("""
<style>
[data-testid="stSidebar"]{background-color:#1a1a1a;}
[data-testid="stSidebar"] *{color:#ffffff !important;}
.stButton>button{background-color:#E63329;color:#fff;border:none;border-radius:4px;font-weight:600;}
.stButton>button:hover{background-color:#c0271e;}
.section-header{font-size:14px;font-weight:700;color:#E63329;text-transform:uppercase;
                letter-spacing:.06em;margin:24px 0 12px 0;border-bottom:1px solid #f3f4f6;
                padding-bottom:6px;}
.kpi-card {
    background: #fff; border-left: 4px solid #E63329;
    border-radius: 6px; padding: 14px 18px;
    box-shadow: 0 1px 4px rgba(0,0,0,.08); margin-bottom: 8px;
}
.kpi-label { font-size: 11px; color: #6b7280; font-weight: 700; text-transform: uppercase; letter-spacing: .05em; }
.kpi-value { font-size: 20px; font-weight: 800; color: #111827; }
</style>
""", unsafe_allow_html=True)

st.markdown("## 🪨 Upload Weekly Coal Report")
st.markdown("Upload historical or current weekly coal reports. The date is **auto-detected** from the file.")

# ── Inputs ───────────────────────────────────────────────────────────────────
site = st.selectbox("Site", ["IFCM", "TRCM"])

uploaded = st.file_uploader(
    "Upload Coal Excel file (.xlsx)",
    type=["xlsx"],
    help="Must contain 'Stock Inventory' and 'Daily Stocktake' sheets.",
)

if not uploaded:
    st.info("⬆️ Upload an Excel file to continue.")
    st.stop()

# ── File-Driven Date Detection & Parsing ─────────────────────────────────────
try:
    file_bytes = uploaded.read()
    
    # 1. Auto-detect dates from the 'Daily Stocktake' sheet (Column B / Index 1)
    file_stream = io.BytesIO(file_bytes)
    df_daily = pd.read_excel(file_stream, engine="openpyxl", sheet_name="Daily Stocktake", header=None)
    
    # Extract all valid datetime objects from the Date column
    dates = pd.to_datetime(df_daily[1], errors='coerce').dropna()
    
    if dates.empty:
        st.error("❌ Could not find any valid dates in the 'Daily Stocktake' sheet.")
        st.stop()
        
    # Snap the earliest date found in the file to the enclosing Sunday
    file_min_date = dates.min().date()
    offset = (file_min_date.weekday() + 1) % 7
    week_start = file_min_date - timedelta(days=offset)
    week_end = week_start + timedelta(days=6)

    # 2. Parse the Inventory Data using your existing function
    rows, warnings = parse_coal_excel(file_bytes)

except ValueError as e:
    st.error(f"❌ Parse error: {e}")
    st.stop()
except Exception as e:
    st.error(f"❌ Error processing file: {e}")
    st.stop()

if warnings:
    for w in warnings:
        st.warning(f"⚠️ {w}")

# ── Preview ──────────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">Preview — Parsed Data</div>', unsafe_allow_html=True)

# Display the auto-detected dates explicitly so the user has confidence
col_k1, col_k2, col_k3 = st.columns(3)
col_k1.markdown(f'<div class="kpi-card"><div class="kpi-label">Auto-Detected Week Start</div><div class="kpi-value">{week_start.strftime("%A, %d %b %Y")}</div></div>', unsafe_allow_html=True)
col_k2.markdown(f'<div class="kpi-card"><div class="kpi-label">Auto-Detected Week End</div><div class="kpi-value">{week_end.strftime("%A, %d %b %Y")}</div></div>', unsafe_allow_html=True)
col_k3.markdown(f'<div class="kpi-card"><div class="kpi-label">Rows Extracted</div><div class="kpi-value">{len(rows)} Items</div></div>', unsafe_allow_html=True)

PREVIEW_COLS = {
    "stock_ref":             "Stock Ref",
    "stock_item":            "Stock Item",
    "uom":                   "UOM",
    "opening_qty":           "Opening Qty",
    "stock_in_qty":          "Stock In Qty",
    "stock_out_qty":         "Stock Out Qty",
    "stock_balance_qty":     "Balance Qty",
    "rate_ngn":              "Rate (₦/ton)",
    "opening_amount_ngn":    "Opening Amt (₦)",
    "stock_in_amount_ngn":   "Stock In Amt (₦)",
    "stock_out_amount_ngn":  "Stock Out Amt (₦)",
    "balance_amount_ngn":    "Balance Amt (₦)",
}

df_preview = pd.DataFrame(rows).rename(columns=PREVIEW_COLS)
for col in ["Opening Qty", "Stock In Qty", "Stock Out Qty", "Balance Qty"]:
    if col in df_preview.columns:
        df_preview[col] = df_preview[col].map(lambda x: f"{x:,.4f}")
for col in ["Rate (₦/ton)", "Opening Amt (₦)", "Stock In Amt (₦)", "Stock Out Amt (₦)", "Balance Amt (₦)"]:
    if col in df_preview.columns:
        df_preview[col] = df_preview[col].map(lambda x: f"₦{x:,.2f}")

st.dataframe(df_preview, use_container_width=True, hide_index=True)

# ── Duplicate check ───────────────────────────────────────────────────────────
existing = fetch_one(
    """SELECT COUNT(*) AS cnt FROM weekly_coal_inventory
       WHERE site = %s AND week_start_date = %s""",
    (site, week_start),
)
already_exists = existing and int(existing["cnt"]) > 0

if already_exists:
    st.warning(
        f"⚠️ Records for **{site}** for the week of **{week_start}** already exist in the database."
    )
    overwrite = st.checkbox("Overwrite existing records for this week", value=False)
else:
    overwrite = False

# ── Save ─────────────────────────────────────────────────────────────────────
if st.button("💾 Save to Database", type="primary"):
    try:
        with transaction() as conn:
            cur = conn.cursor()

            if already_exists and overwrite:
                cur.execute(
                    "DELETE FROM weekly_coal_inventory WHERE site = %s AND week_start_date = %s",
                    (site, week_start),
                )
            elif already_exists and not overwrite:
                st.error("Save cancelled — check 'Overwrite' to replace the existing historical records.")
                st.stop()

            insert_sql = """
                INSERT INTO weekly_coal_inventory (
                    site, week_start_date, week_end_date,
                    stock_ref, stock_item, uom,
                    opening_qty, stock_in_qty, stock_out_qty, stock_balance_qty,
                    rate_ngn,
                    opening_amount_ngn, stock_in_amount_ngn,
                    stock_out_amount_ngn, balance_amount_ngn
                ) VALUES (
                    %(site)s, %(week_start_date)s, %(week_end_date)s,
                    %(stock_ref)s, %(stock_item)s, %(uom)s,
                    %(opening_qty)s, %(stock_in_qty)s, %(stock_out_qty)s, %(stock_balance_qty)s,
                    %(rate_ngn)s,
                    %(opening_amount_ngn)s, %(stock_in_amount_ngn)s,
                    %(stock_out_amount_ngn)s, %(balance_amount_ngn)s
                )
            """
            params_list = [
                {**r, "site": site, "week_start_date": week_start, "week_end_date": week_end}
                for r in rows
            ]
            
            psycopg2.extras.execute_batch(cur, insert_sql, params_list)

        st.success(f"✅ {len(rows)} records successfully saved for {site} ({week_start} → {week_end}).")
    except Exception as e:
        st.error(f"❌ Database error: {e}")