"""
pages/3_Upload_Diesel.py — Upload / Sync Master Diesel Dispensing Log
Mosra Energy · Mining Operations Dashboard

UPLOAD STRATEGY — "Append-only with optional overwrite"
────────────────────────────────────────────────────────
The diesel Excel file is a continuously growing master log. Every week
you upload the same file with new rows appended at the bottom.

Logic:
  1. Parse the entire file.
  2. Query the DB for which DATES (for this site) already have records.
  3. By default → only INSERT rows whose dates are NOT already in the DB.
  4. If the user checks "Overwrite" → DELETE existing rows for those
     dates first, then INSERT everything (old + new) for those dates.

This means re-uploading last week's file with new rows appended will
automatically detect the new dates and only push those rows.
"""

import streamlit as st
import pandas as pd
import psycopg2.extras
from utils.db import fetch_all, transaction
from utils.parsers import parse_diesel_excel

# ── Page config & CSS ─────────────────────────────────────────────────────────
st.set_page_config(page_title="Upload Diesel · Mosra Energy", layout="wide")

st.markdown("""
<style>
[data-testid="stSidebar"] { background-color: #1a1a1a; }
[data-testid="stSidebar"] * { color: #ffffff !important; }

.stButton > button {
    background-color: #E63329; color: #fff;
    border: none; border-radius: 4px; font-weight: 600;
}
.stButton > button:hover { background-color: #c0271e; }

.section-header {
    font-size: 14px; font-weight: 700; color: #E63329;
    text-transform: uppercase; letter-spacing: .06em;
    margin: 24px 0 12px 0;
    border-bottom: 1px solid #f3f4f6; padding-bottom: 6px;
}
.kpi-card {
    background: #fff; border-left: 4px solid #E63329;
    border-radius: 6px; padding: 14px 18px;
    box-shadow: 0 1px 4px rgba(0,0,0,.08); margin-bottom: 8px;
}
.kpi-card-green { border-left-color: #10b981 !important; }
.kpi-card-amber { border-left-color: #f59e0b !important; }
.kpi-label {
    font-size: 11px; color: #6b7280; font-weight: 700;
    text-transform: uppercase; letter-spacing: .05em;
}
.kpi-value { font-size: 22px; font-weight: 800; color: #111827; }

.warn-box {
    background: #fffbeb; border-left: 4px solid #f59e0b;
    border-radius: 6px; padding: 12px 16px; margin: 12px 0; font-size: 13px;
}
.info-box {
    background: #eff6ff; border-left: 4px solid #3b82f6;
    border-radius: 6px; padding: 12px 16px; margin: 12px 0; font-size: 13px;
}
</style>
""", unsafe_allow_html=True)

# ── Helper: KPI card ──────────────────────────────────────────────────────────
def kpi(col, label: str, value: str, variant: str = "") -> None:
    """Render a styled KPI card. variant: '' | 'green' | 'amber'"""
    extra = f" kpi-card-{variant}" if variant else ""
    col.markdown(
        f'<div class="kpi-card{extra}">'
        f'  <div class="kpi-label">{label}</div>'
        f'  <div class="kpi-value">{value}</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── Page header ───────────────────────────────────────────────────────────────
st.markdown("## ⛽ Upload / Sync Diesel Log")
st.markdown(
    "Upload the **full master diesel dispensing log** (xlsx/xls/csv). "
    "The file may contain the entire history — only **new dates** are "
    "inserted by default. Existing dates are flagged; you decide whether "
    "to overwrite them."
)

# ── Inputs ────────────────────────────────────────────────────────────────────
site = st.selectbox("Site", ["IFCM", "TRCM"])

if site == "IFCM":
    st.info("ℹ️ **IFCM** has no haulage activities — all diesel will be "
            "classified as Non-Haulage regardless of operation type.")

uploaded = st.file_uploader(
    "Upload Diesel Log (.xlsx / .xls / .csv)",
    type=["xlsx", "xls", "csv"],
    help=(
        "Expected columns: DATE, EQUIPMENT, EQUIPMENT TYPE, "
        "STOCK IN, DIESEL DISPENSED, OPERATION TYPE, STOCK BALANCE"
    ),
)

if not uploaded:
    st.info("⬆️ Upload a diesel log file to continue.")
    st.stop()

# ── Load existing operation-type classifications from DB ──────────────────────
@st.cache_data(ttl=60)
def load_classifications() -> dict[str, bool]:
    """Returns {operation_type_raw: is_haulage} for all known types."""
    rows = fetch_all(
        "SELECT operation_type_raw, is_haulage "
        "FROM diesel_operation_classifications",
        (),
    )
    return {r["operation_type_raw"]: r["is_haulage"] for r in rows}

existing_cls = load_classifications()

# ── Parse the uploaded file ───────────────────────────────────────────────────
try:
    file_bytes = uploaded.read()
    # parse_diesel_excel returns:
    #   dispense_rows : list[dict]  – one dict per dispensing row
    #   stock_in_rows : list[dict]  – replenishment / stock-in rows
    #   new_op_types  : list[dict]  – op types not seen before
    #   warnings      : list[str]   – non-fatal parse issues
    dispense_rows, stock_in_rows, new_op_types, warnings = parse_diesel_excel(
        file_bytes, site, existing_cls
    )
except ValueError as exc:
    st.error(f"❌ Parse error: {exc}")
    st.stop()

if warnings:
    with st.expander(f"⚠️ {len(warnings)} parse warnings — click to review"):
        for w in warnings:
            st.warning(w)

if not dispense_rows:
    st.warning("No valid dispensing rows found after parsing and filtering.")
    st.stop()

# ── Build a clean DataFrame and NORMALISE dispensed_date to Python date ──────
# BUG FIX: Ensure dispensed_date is always a Python date object so that
# set membership checks (isin / `in`) work reliably against DB-returned dates.
df_disp = pd.DataFrame(dispense_rows)
df_disp["dispensed_date"] = pd.to_datetime(
    df_disp["dispensed_date"], dayfirst=True
).dt.date  # <-- always Python date, never Timestamp or string

# Sync back to dispense_rows so the list used for DB insert is also normalised
for row, d in zip(dispense_rows, df_disp["dispensed_date"]):
    row["dispensed_date"] = d

# ── Query DB: which dates already have records for this site? ─────────────────
file_date_min = df_disp["dispensed_date"].min()
file_date_max = df_disp["dispensed_date"].max()

existing_date_rows = fetch_all(
    """
    SELECT DISTINCT dispensed_date
    FROM   weekly_diesel_usage
    WHERE  site = %s
      AND  dispensed_date BETWEEN %s AND %s
    ORDER  BY dispensed_date
    """,
    (site, file_date_min, file_date_max),
)
# DB returns date objects directly via psycopg2; store as a set for O(1) lookup
existing_dates: set = {r["dispensed_date"] for r in existing_date_rows}

# Partition parsed rows into new vs. already-in-DB
df_new      = df_disp[~df_disp["dispensed_date"].isin(existing_dates)].copy()
df_existing = df_disp[ df_disp["dispensed_date"].isin(existing_dates)].copy()

new_dates              = sorted(df_new["dispensed_date"].unique())
existing_dates_in_file = sorted(df_existing["dispensed_date"].unique())

# ── Preview table ─────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">Preview — Dispensing Rows</div>',
            unsafe_allow_html=True)

# Date range filter so user can focus on a window
col_f1, col_f2 = st.columns(2)
with col_f1:
    filter_from = st.date_input(
        "Preview from", file_date_min,
        min_value=file_date_min, max_value=file_date_max, key="pf1",
    )
with col_f2:
    filter_to = st.date_input(
        "Preview to", file_date_max,
        min_value=file_date_min, max_value=file_date_max, key="pf2",
    )

# Filter and annotate status
mask    = df_disp["dispensed_date"].between(filter_from, filter_to)
df_view = df_disp[mask].copy()
df_view["status"] = df_view["dispensed_date"].apply(
    lambda d: "⚠️ Existing" if d in existing_dates else "✅ New"
)
df_view["is_haulage"] = df_view["is_haulage"].astype(bool)

# Editable only on is_haulage — everything else read-only
edited = st.data_editor(
    df_view[["status", "dispensed_date", "equipment", "equipment_type",
             "operation_type", "litres", "is_haulage"]],
    column_config={
        "status":         st.column_config.TextColumn("Status",    disabled=True),
        "dispensed_date": st.column_config.DateColumn("Date",      disabled=True),
        "equipment":      st.column_config.TextColumn("Equipment", disabled=True),
        "equipment_type": st.column_config.TextColumn("Equip Type",disabled=True),
        "operation_type": st.column_config.TextColumn("Operation", disabled=True),
        "litres":         st.column_config.NumberColumn("Litres", format="%.2f", disabled=True),
        "is_haulage":     st.column_config.CheckboxColumn("Haulage?"),
    },
    use_container_width=True,
    hide_index=True,
    key="diesel_editor",
)

# ── Propagate is_haulage edits back to the master dispense_rows list ──────────
# BUG FIX: Previous code used positional index which breaks when the preview is
# filtered. We match on the DataFrame's actual index (which traces back to
# df_disp) so edits always land on the correct row regardless of filter window.
if not edited.empty:
    # df_view.index contains the original positional indices in df_disp
    for df_disp_idx, new_haulage in zip(df_view.index, edited["is_haulage"]):
        dispense_rows[df_disp_idx]["is_haulage"] = bool(new_haulage)
    # Rebuild split DataFrames to reflect any edits (used for summary display)
    df_disp_updated = pd.DataFrame(dispense_rows)
    df_disp_updated["dispensed_date"] = pd.to_datetime(
        df_disp_updated["dispensed_date"]
    ).dt.date
else:
    df_disp_updated = df_disp

# ── Summary KPIs ──────────────────────────────────────────────────────────────
st.markdown('<div class="section-header">Upload Summary</div>',
            unsafe_allow_html=True)

total_l   = sum(r["litres"] for r in dispense_rows)
haulage_l = sum(r["litres"] for r in dispense_rows if r["is_haulage"])
nh_l      = total_l - haulage_l
hpct      = haulage_l / total_l * 100 if total_l else 0

r1c1, r1c2, r1c3, r1c4 = st.columns(4)
kpi(r1c1, "Total Litres (file)",  f"{total_l:,.0f} L")
kpi(r1c2, "Haulage",              f"{haulage_l:,.0f} L ({hpct:.1f}%)")
kpi(r1c3, "Non-Haulage",          f"{nh_l:,.0f} L")
kpi(r1c4, "File Date Range",      f"{file_date_min} → {file_date_max}")

r2c1, r2c2 = st.columns(2)
kpi(r2c1, "✅ New dates (to insert)",
    f"{len(new_dates)} date(s) · {len(df_new)} rows", variant="green")
kpi(r2c2, "⚠️ Dates already in DB",
    f"{len(existing_dates_in_file)} date(s) · {len(df_existing)} rows",
    variant="amber" if existing_dates_in_file else "green")

# ── Overwrite toggle (only shown when there are collisions) ───────────────────
overwrite = False
if existing_dates_in_file:
    st.markdown(
        '<div class="section-header">⚠️ Existing Dates — Overwrite?</div>',
        unsafe_allow_html=True,
    )
    date_list_str = ", ".join(str(d) for d in existing_dates_in_file[:30])
    if len(existing_dates_in_file) > 30:
        date_list_str += f" … (+{len(existing_dates_in_file) - 30} more)"

    st.markdown(
        f'<div class="warn-box">'
        f"The following <strong>{len(existing_dates_in_file)} date(s)</strong> "
        f"already have diesel records in the DB for <strong>{site}</strong>:<br>"
        f"<code>{date_list_str}</code><br><br>"
        f"By default these will be <strong>skipped</strong>. Check the box below "
        f"to <strong>delete and replace</strong> them."
        f"</div>",
        unsafe_allow_html=True,
    )
    overwrite = st.checkbox(
        f"Overwrite existing {len(existing_dates_in_file)} date(s) for {site}",
        value=False,
        key="overwrite_diesel",
    )
    if overwrite:
        st.warning(
            f"⚠️ All existing diesel rows for **{site}** on the "
            f"{len(existing_dates_in_file)} flagged date(s) will be "
            f"**permanently deleted and replaced**."
        )
else:
    st.markdown(
        '<div class="info-box">✅ No date collisions detected — '
        "all parsed rows are new and will be inserted.</div>",
        unsafe_allow_html=True,
    )

# ── New operation types review ────────────────────────────────────────────────
if new_op_types:
    st.markdown(
        '<div class="section-header">New Operation Types — Review Classification</div>',
        unsafe_allow_html=True,
    )
    st.caption(
        "These operation types were not previously seen. "
        "Auto-classified as Non-Haulage. Adjust before saving — "
        "your choices will be remembered for future uploads."
    )
    df_new_ops      = pd.DataFrame(new_op_types)
    df_new_ops_orig = df_new_ops.copy()
    edited_ops = st.data_editor(
        df_new_ops[["operation_type_raw", "is_haulage"]],
        column_config={
            "operation_type_raw": st.column_config.TextColumn(
                "Operation Type", disabled=True
            ),
            "is_haulage": st.column_config.CheckboxColumn("Haulage?"),
        },
        use_container_width=True,
        hide_index=True,
        key="ops_editor",
    )
    # Write edits back to new_op_types list (used in DB upsert below)
    for i, erow in edited_ops.iterrows():
        new_haulage = bool(erow["is_haulage"])
        orig_haulage = bool(df_new_ops_orig.iloc[i]["is_haulage"])
        new_op_types[i]["is_haulage"] = new_haulage
        new_op_types[i]["overridden_by_user"] = new_haulage != orig_haulage

# ── Save button ───────────────────────────────────────────────────────────────
st.markdown("---")
col_btn, col_msg = st.columns([1, 3])

with col_btn:
    do_save = st.button("💾 Save to Database", type="primary",
                        use_container_width=True)

if do_save:

    # ── Decide which rows to insert and which dates to delete ─────────────────
    if existing_dates_in_file and not overwrite:
        # Default: skip rows whose dates already exist in the DB
        rows_to_insert = [
            r for r in dispense_rows
            if r["dispensed_date"] not in existing_dates
        ]
        dates_to_delete: set = set()
    else:
        # Overwrite: insert everything; delete existing dates first
        rows_to_insert = dispense_rows
        dates_to_delete = set(existing_dates_in_file)

    if not rows_to_insert:
        st.info("Nothing to insert — all dates already exist in the DB "
                "and overwrite is disabled.")
        st.stop()

    # ── Execute in a single atomic transaction ────────────────────────────────
    try:
        with transaction() as conn:
            cur = conn.cursor()

            # 1. Upsert operation-type classifications
            #    - Only update is_haulage if the user has not previously
            #      manually overridden it (overridden_by_user = TRUE protects
            #      user choices from being reset by future auto-detection).
            if new_op_types:
                psycopg2.extras.execute_batch(
                    cur,
                    """
                    INSERT INTO diesel_operation_classifications
                        (operation_type_raw, is_haulage, overridden_by_user)
                    VALUES
                        (%(operation_type_raw)s, %(is_haulage)s, %(overridden_by_user)s)
                    ON CONFLICT (operation_type_raw) DO UPDATE
                        SET is_haulage         = EXCLUDED.is_haulage,
                            overridden_by_user = EXCLUDED.overridden_by_user,
                            updated_at         = NOW()
                    WHERE  diesel_operation_classifications.overridden_by_user = FALSE
                        OR EXCLUDED.overridden_by_user = TRUE
                    """,
                    new_op_types,
                )

            # 2. Delete existing rows for overwritten dates (atomic with insert)
            deleted_count = 0
            if dates_to_delete:
                cur.execute(
                    """
                    DELETE FROM weekly_diesel_usage
                    WHERE  site = %s
                      AND  dispensed_date = ANY(%s)
                    """,
                    (site, list(dates_to_delete)),
                )
                deleted_count = cur.rowcount  # rowcount is reliable for DELETE

            # 3. Bulk-insert dispense rows INCLUDING equipment_type & duplicate handling
            inserted_disp = 0
            if rows_to_insert:
                for start in range(0, len(rows_to_insert), 500):
                    batch = rows_to_insert[start : start + 500]
                    psycopg2.extras.execute_batch(
                        cur,
                        """
                        INSERT INTO weekly_diesel_usage
                            (site, dispensed_date, equipment_name, equipment_type,
                             operation_type, litres, is_haulage, source_filename)
                        VALUES
                            (%(site)s, %(dispensed_date)s, %(equipment)s, %(equipment_type)s,
                             %(operation_type)s, %(litres)s, %(is_haulage)s, %(source_filename)s)
                        ON CONFLICT ON CONSTRAINT uq_diesel_row DO NOTHING
                        """,
                        batch,
                    )
                    inserted_disp += cur.rowcount

        # Invalidate classification cache so the next upload picks up new types
        load_classifications.clear()

        # ── Success summary ───────────────────────────────────────────────────
        skipped_disp = len(rows_to_insert) - inserted_disp
        parts = [f"**{inserted_disp}** dispense rows inserted"]
        if skipped_disp:
            parts.append(f"**{skipped_disp}** exact duplicates skipped")
        if deleted_count:
            parts.append(f"**{deleted_count}** existing rows replaced (overwrite)")
        if existing_dates_in_file and not overwrite:
            parts.append(
                f"**{len(df_existing)}** rows on existing dates skipped "
                f"(overwrite not selected)"
            )
        if new_op_types:
            parts.append(
                f"**{len(new_op_types)}** operation type(s) registered — "
                "review the classification table"
            )

        st.success("✅ Done!  " + "  ·  ".join(parts) + ".")

    except Exception as exc:
        st.error(f"❌ Database error — transaction rolled back: {exc}")
        raise  # keep the traceback in the Streamlit server log