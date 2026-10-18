"""Upload DieselStock dispensing logs into the new-template table."""

from datetime import timedelta

import pandas as pd
import psycopg2.extras
import streamlit as st

from utils.db import fetch_all, transaction
from utils.parsers import parse_diesel_excel_new


st.set_page_config(page_title="Upload Diesel · Mosra Energy", layout="wide")

st.markdown("""
<style>
[data-testid="stSidebar"] { background-color: #1a1a1a; }
[data-testid="stSidebar"] * { color: #ffffff !important; }
.stButton > button { background:#E63329; color:white; border:none; font-weight:600; }
.section-header { font-size:14px; font-weight:700; color:#E63329;
  text-transform:uppercase; letter-spacing:.06em; margin:24px 0 12px;
  border-bottom:1px solid #f3f4f6; padding-bottom:6px; }
.kpi-card { background:#fff; border-left:4px solid #E63329; border-radius:6px;
  padding:14px 18px; box-shadow:0 1px 4px rgba(0,0,0,.08); }
.kpi-label { font-size:11px; color:#6b7280; font-weight:700;
  text-transform:uppercase; letter-spacing:.05em; }
.kpi-value { font-size:22px; font-weight:800; color:#111827; }
</style>
""", unsafe_allow_html=True)


def kpi(column, label, value):
    column.markdown(
        f'<div class="kpi-card"><div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{value}</div></div>',
        unsafe_allow_html=True,
    )


st.markdown("## ⛽ Upload DieselStock Log")
st.markdown(
    "Upload the new **DieselStock Excel template**. The site is read from the "
    "workbook, dispensing transactions come from **Dispensing log**, and "
    "**Weekly summary** is used only as a reconciliation check."
)

uploaded = st.file_uploader(
    "Upload DieselStock workbook (.xlsx / .xls)",
    type=["xlsx", "xls"],
    help="Required sheets: Dispensing log and Weekly summary.",
)
if not uploaded:
    st.info("⬆️ Upload a DieselStock workbook to continue.")
    st.stop()

try:
    rows, weekly_summary, warnings = parse_diesel_excel_new(uploaded.read())
except ValueError as exc:
    st.error(f"❌ Parse error: {exc}")
    st.stop()

if not rows:
    st.warning("No valid dispensing rows were found in the workbook.")
    st.stop()

for row in rows:
    row["source_filename"] = uploaded.name

site = rows[0]["site"]
dates = sorted({row["dispensed_date"] for row in rows})
date_min, date_max = dates[0], dates[-1]
week_start = date_min - timedelta(days=(date_min.weekday() + 1) % 7)
week_end = week_start + timedelta(days=6)
log_total = weekly_summary["dispensing_log_total_litres"]
summary_total = weekly_summary["stock_check"].get("Dispensed per log (L)")
reconciled = summary_total is not None and abs(log_total - summary_total) <= 0.01

if warnings:
    with st.expander(f"⚠️ {len(warnings)} parsing warning(s)"):
        for warning in warnings:
            st.warning(warning)

st.markdown('<div class="section-header">Workbook Summary</div>', unsafe_allow_html=True)
c1, c2, c3, c4 = st.columns(4)
kpi(c1, "Site", site)
kpi(c2, "Dispensing rows", f"{len(rows):,}")
kpi(c3, "Dispensed", f"{log_total:,.2f} L")
kpi(c4, "Date range", f"{date_min} → {date_max}")

if summary_total is None:
    st.warning("Weekly summary does not contain a numeric 'Dispensed per log (L)' value.")
elif reconciled:
    st.success(f"✅ Weekly summary reconciles with the dispensing log: {log_total:,.2f} L.")
else:
    st.error(
        f"Weekly summary reports {summary_total:,.2f} L, while the parsed "
        f"dispensing log totals {log_total:,.2f} L. Review the workbook before saving."
    )

stock = weekly_summary["stock_check"]
if stock:
    stock_rows = [
        {"Stock check": label, "Value": value}
        for label, value in stock.items()
    ]
    with st.expander("Weekly stock reconciliation"):
        st.dataframe(pd.DataFrame(stock_rows), hide_index=True, use_container_width=True)

try:
    existing_date_rows = fetch_all(
        """
        SELECT DISTINCT dispensed_date
        FROM diesel_dispensing_log
        WHERE site = %s AND dispensed_date BETWEEN %s AND %s
        ORDER BY dispensed_date
        """,
        (site, date_min, date_max),
    )
except Exception as exc:
    if "diesel_dispensing_log" in str(exc) and "does not exist" in str(exc):
        st.error(
            "The new diesel table has not been created yet. Run `python db_setup.py` "
            "with the deployment database configured, then reload this page."
        )
        st.stop()
    raise

existing_dates = {record["dispensed_date"] for record in existing_date_rows}
new_rows = [row for row in rows if row["dispensed_date"] not in existing_dates]
existing_rows = [row for row in rows if row["dispensed_date"] in existing_dates]

st.markdown('<div class="section-header">Dispensing Preview</div>', unsafe_allow_html=True)
preview = pd.DataFrame(rows)
preview.insert(
    0, "status",
    preview["dispensed_date"].map(
        lambda value: "⚠️ Existing date" if value in existing_dates else "✅ New"
    ),
)
preview_columns = [
    "status", "site", "dispensed_date", "dispensed_time", "asset_id",
    "equipment_class", "meter_type", "meter_reading", "litres",
    "activity_code", "operation_type", "check_status",
]
st.dataframe(preview[preview_columns], hide_index=True, use_container_width=True)

n1, n2 = st.columns(2)
kpi(n1, "New dates", f"{len(set(dates) - existing_dates)} date(s) · {len(new_rows)} rows")
kpi(n2, "Existing dates", f"{len(set(dates) & existing_dates)} date(s) · {len(existing_rows)} rows")

overwrite = False
if existing_dates:
    st.warning(
        "Some dates already exist in the new diesel table. They will be skipped by "
        "default. To correct an existing date, upload its complete log and enable overwrite."
    )
    overwrite = st.checkbox(
        f"Overwrite {len(set(dates) & existing_dates)} existing date(s) for {site}",
        value=False,
    )

save_disabled = not reconciled
if save_disabled:
    st.caption("Saving is disabled until the Weekly summary and Dispensing log totals reconcile.")

if st.button(
    "💾 Save DieselStock Log",
    type="primary",
    disabled=save_disabled,
    use_container_width=True,
):
    if existing_dates and not overwrite:
        rows_to_insert = new_rows
        dates_to_delete = set()
    else:
        rows_to_insert = rows
        dates_to_delete = set(dates) & existing_dates

    if not rows_to_insert:
        st.info("Nothing to save. Every date in this workbook already exists.")
        st.stop()

    try:
        with transaction() as conn:
            cur = conn.cursor()
            deleted_count = 0
            if dates_to_delete:
                cur.execute(
                    """
                    DELETE FROM diesel_dispensing_log
                    WHERE site = %s AND dispensed_date = ANY(%s)
                    """,
                    (site, list(dates_to_delete)),
                )
                deleted_count = cur.rowcount

            inserted = psycopg2.extras.execute_values(
                cur,
                """
                INSERT INTO diesel_dispensing_log
                    (site, dispensed_date, dispensed_time, asset_id, equipment_class,
                     meter_type, meter_reading, litres, activity_code,
                     activity_code_raw, operation_type, is_haulage, operator_driver,
                     fuel_attendant, supervisor_sign_off, check_status, occurrence,
                     source_filename)
                VALUES %s
                ON CONFLICT ON CONSTRAINT uq_dieselstock_row DO NOTHING
                RETURNING id
                """,
                rows_to_insert,
                template="""(
                    %(site)s, %(dispensed_date)s, %(dispensed_time)s, %(asset_id)s,
                    %(equipment_class)s, %(meter_type)s, %(meter_reading)s, %(litres)s,
                    %(activity_code)s, %(activity_code_raw)s, %(operation_type)s,
                    %(is_haulage)s, %(operator_driver)s, %(fuel_attendant)s,
                    %(supervisor_sign_off)s, %(check_status)s, %(occurrence)s,
                    %(source_filename)s
                )""",
                page_size=500,
                fetch=True,
            )
            inserted_count = len(inserted)

            cur.execute(
                """
                INSERT INTO diesel_weekly_summary
                    (site, week_start_date, week_end_date, opening_dip_litres,
                     received_litres, dispensed_log_litres, book_closing_litres,
                     closing_dip_litres, variance_litres, variance_percent,
                     source_filename, updated_at)
                VALUES
                    (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, NOW())
                ON CONFLICT (site, week_start_date) DO UPDATE SET
                    week_end_date = EXCLUDED.week_end_date,
                    opening_dip_litres = EXCLUDED.opening_dip_litres,
                    received_litres = EXCLUDED.received_litres,
                    dispensed_log_litres = EXCLUDED.dispensed_log_litres,
                    book_closing_litres = EXCLUDED.book_closing_litres,
                    closing_dip_litres = EXCLUDED.closing_dip_litres,
                    variance_litres = EXCLUDED.variance_litres,
                    variance_percent = EXCLUDED.variance_percent,
                    source_filename = EXCLUDED.source_filename,
                    updated_at = NOW()
                """,
                (
                    site, week_start, week_end,
                    stock.get("Opening dip (L)"), stock.get("Received (L)"),
                    log_total, stock.get("Book closing (L)"),
                    stock.get("Closing dip (L)"), stock.get("Variance (L)"),
                    stock.get("Variance % of dispensed"), uploaded.name,
                ),
            )
        duplicate_count = len(rows_to_insert) - inserted_count
        message = f"✅ Saved **{inserted_count}** dispensing rows to {site}."
        if deleted_count:
            message += f" Replaced **{deleted_count}** existing rows."
        if duplicate_count:
            message += f" Skipped **{duplicate_count}** exact duplicates."
        st.success(message)
    except Exception as exc:
        st.error(f"❌ Database error — no changes were saved: {exc}")
        raise
