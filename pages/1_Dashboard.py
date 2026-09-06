"""
pages/1_Dashboard.py — Mosra Energy Operations Dashboard
Dark mode theme. Supports WoW, MoM, YTD, and YoY comparison views.
Features a 3-tab layout with comprehensive per-site analytics, compact dynamic KPIs, and a split-width mining efficiency analysis section.
"""

import streamlit as st
import pandas as pd
import numpy as np
import plotly.graph_objects as go
from datetime import date, timedelta
from utils.db import fetch_all, fetch_one

st.set_page_config(page_title="Dashboard · Mosra Energy", layout="wide")

# ── Dark theme CSS ────────────────────────────────────────────────────────────
st.markdown("""
<style>
.stApp { background-color: #0f1117; }
.main .block-container { background-color: #0f1117; padding-top: 1.5rem; }
[data-testid="stSidebar"] { background-color: #1a1d27 !important; border-right: 1px solid #2a2d3a; }
[data-testid="stSidebar"] * { color: #e2e8f0 !important; }
html, body, [class*="css"] { color: #e2e8f0; }
label { color: #94a3b8 !important; font-size: 13px !important; }
.stSelectbox > div > div { background-color: #1e2130 !important; color: #e2e8f0 !important; border-color: #2a2d3a !important; }

/* ── KPI card ── */
.kpi-wrap {
    background: #1e2130;
    border-radius: 10px;
    padding: 18px 20px 14px 20px;
    border-left: 3px solid #E63329;
    margin-bottom: 10px;
    min-height: 125px;
}
.kpi-wrap-ytd { border-left-color: #3b82f6; }
.kpi-wrap-ifcm { border-left-color: #fbbf24; }
.kpi-label {
    font-size: 10px; font-weight: 700; color: #64748b;
    text-transform: uppercase; letter-spacing: .09em; margin-bottom: 7px;
}
.kpi-value { font-size: 24px; font-weight: 800; color: #f1f5f9; line-height: 1.15; }
.kpi-unit  { font-size: 12px; font-weight: 400; color: #64748b; margin-left: 3px; }
.kpi-prev-value { font-size: 13px; font-weight: 500; color: #94a3b8; margin-top: 4px; }
.kpi-delta-up   { font-size: 11px; font-weight: 600; color: #34d399; margin-top: 2px; }
.kpi-delta-down { font-size: 11px; font-weight: 600; color: #f87171; margin-top: 2px; }
.kpi-delta-flat { font-size: 11px; font-weight: 500; color: #475569; margin-top: 2px; }
.kpi-ytd-badge  {
    font-size: 10px; font-weight: 700; color: #fff;
    background: #3b82f6; border-radius: 4px;
    padding: 2px 7px; margin-top: 6px; display: inline-block;
}

/* ── Section header ── */
.sec-hdr {
    font-size: 11px; font-weight: 700; color: #E63329;
    text-transform: uppercase; letter-spacing: .1em;
    border-bottom: 1px solid #1e2130;
    padding-bottom: 6px; margin: 24px 0 16px 0;
}
.week-badge {
    display: inline-block; background: #1e2130; color: #e2e8f0;
    border: 1px solid #2a2d3a; border-radius: 6px;
    padding: 4px 12px; font-size: 12px; font-weight: 600; margin-right: 8px;
}
.week-badge-ytd  { background: #E63329; border-color: #E63329; color: #fff; }
.week-badge-prev { background: #131620; color: #64748b; border-color: #1e2130; }
.no-data { color: #334155; font-size: 13px; font-style: italic; padding: 24px 0; text-align: center; }
hr { border-color: #1e2130 !important; }
</style>
""", unsafe_allow_html=True)

# ── Colors & Layout ──
BRAND  = "#E63329"; DARK = "#3b82f6"; GREEN = "#34d399"
AMBER  = "#fbbf24"; BLUE = "#60a5fa"; PURPLE = "#a78bfa"; TEAL = "#2dd4bf"

LAY = dict(
    plot_bgcolor  = "#161824", paper_bgcolor = "#1e2130",
    font          = dict(color="#94a3b8", size=12, family="Inter, sans-serif"),
    xaxis         = dict(gridcolor="#252836", linecolor="#252836", tickcolor="#475569"),
    yaxis         = dict(gridcolor="#252836", linecolor="#252836", tickcolor="#475569"),
    legend        = dict(bgcolor="#1e2130", bordercolor="#2a2d3a", borderwidth=1, orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0, font=dict(color="#94a3b8")),
    margin        = dict(l=0, r=0, t=36, b=0),
)

# ── Header ──
st.markdown("""
<div style="display:flex;align-items:center;gap:14px;margin-bottom:6px;">
  <div style="background:#E63329;border-radius:8px;padding:8px 10px;font-size:22px;line-height:1;">⛏️</div>
  <div>
    <div style="font-size:19px;font-weight:800;color:#f1f5f9;line-height:1.1;letter-spacing:-.01em;">
      MOSRA ENERGY LIMITED
    </div>
    <div style="font-size:10px;color:#E63329;font-weight:700;letter-spacing:.15em;margin-top:2px;">
      EXECUTIVE OPERATIONS DASHBOARD
    </div>
  </div>
</div>
""", unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════════════
# TOP-LEVEL FILTERS
# ════════════════════════════════════════════════════════════════════════════
st.markdown("<hr style='margin: 10px 0 15px 0;'>", unsafe_allow_html=True)
col_ctrl1, col_ctrl2 = st.columns([1, 2])

with col_ctrl1:
    view_mode = st.radio(
        "Comparison Mode",
        options=["WoW", "MoM", "YTD", "YoY"],
        index=0,
        horizontal=True,
        help="WoW (Week vs Week), MoM (MTD vs MTD), YTD (No delta), YoY (YTD vs Prior Year YTD)"
    )

all_weeks_query = """
    SELECT DISTINCT week_start_date FROM (
        SELECT (week_start_date - INTERVAL '1 day' * EXTRACT(DOW FROM week_start_date)::integer)::date AS week_start_date 
        FROM weekly_manual_metrics
        UNION
        SELECT (week_start_date - INTERVAL '1 day' * EXTRACT(DOW FROM week_start_date)::integer)::date AS week_start_date 
        FROM weekly_coal_inventory
        UNION
        SELECT (dispensed_date - INTERVAL '1 day' * EXTRACT(DOW FROM dispensed_date)::integer)::date AS week_start_date 
        FROM weekly_diesel_usage
    ) combined_weeks
    WHERE week_start_date IS NOT NULL AND week_start_date <= CURRENT_DATE
    ORDER BY week_start_date DESC
"""
all_weeks = fetch_all(all_weeks_query)

if not all_weeks:
    st.markdown('<div class="no-data">⚠️ No data found yet — upload weekly reports first.</div>', unsafe_allow_html=True)
    st.stop()

week_options = [r["week_start_date"] for r in all_weeks]

with col_ctrl2:
    selected_ws = st.selectbox(
        "Select Week",
        options=week_options,
        format_func=lambda d: d.strftime("Week of Sunday, %d %b %Y"),
        index=0,
    )

prev_options = [w for w in week_options if w < selected_ws]
prev_ws  = prev_options[0] if prev_options else None
has_prev = prev_ws is not None

# ════════════════════════════════════════════════════════════════════════════
# DYNAMIC QUERY BUILDER
# ════════════════════════════════════════════════════════════════════════════
params = {"ws": selected_ws, "prev_ws": prev_ws}

def get_query_conditions(prefix=""):
    if prefix == "du.":
        col = f"({prefix}dispensed_date - INTERVAL '1 day' * EXTRACT(DOW FROM {prefix}dispensed_date)::integer)::date"
    else:
        col = f"{prefix}week_start_date"
    
    we_expr = f"({col} + INTERVAL '6 days')"
    
    if view_mode == "WoW":
        cur = f"{col} = %(ws)s"
        prv = f"{col} = %(prev_ws)s" if has_prev else "1=0"
    elif view_mode == "MoM":
        cur = f"DATE_TRUNC('month', {we_expr}) = DATE_TRUNC('month', %(ws)s::date + INTERVAL '6 days') AND {col} <= %(ws)s"
        prv = f"DATE_TRUNC('month', {we_expr}) = DATE_TRUNC('month', %(ws)s::date + INTERVAL '6 days' - INTERVAL '1 month') AND {col} <= %(ws)s - INTERVAL '28 days'"
    elif view_mode == "YTD":
        cur = f"{col} >= DATE_TRUNC('year', %(ws)s::date) AND {col} <= %(ws)s"
        prv = "1=0"
    elif view_mode == "YoY":
        cur = f"{col} >= DATE_TRUNC('year', %(ws)s::date) AND {col} <= %(ws)s"
        prv = f"{col} >= DATE_TRUNC('year', %(ws)s::date - INTERVAL '1 year') AND {col} <= %(ws)s - INTERVAL '52 weeks'"
        
    return cur, prv

def fetch_manual(where_clause, site_val):
    p = params.copy(); p["site"] = site_val
    return fetch_one(f"""
        SELECT SUM(coal_mined_mt) AS coal_mined, SUM(coal_from_local_miners_mt) AS coal_local,
               SUM(coal_from_high_wall_mining_mt) AS coal_highwall, SUM(coal_from_ifcm_mt) AS coal_from_ifcm,
               SUM(coal_from_manejo_mt) AS coal_manejo, SUM(coal_from_ogboyaga_mt) AS coal_ogboyaga,
               SUM(total_coal_stocked_mt) AS total_stocked, SUM(bcm_excavated_bcm) AS bcm_excavated,
               SUM(coal_dispatched_mt) AS coal_dispatched
        FROM weekly_manual_metrics WHERE {where_clause} AND site = %(site)s""", p) or {}

def fetch_coal(where_clause, site_val):
    p = params.copy(); p["site"] = site_val
    return fetch_one(f"""
        SELECT SUM(wci.stock_out_qty) AS stock_out_qty, SUM(wci.stock_out_amount_ngn) AS stock_out_ngn,
               SUM(wci.stock_balance_qty) AS balance_qty, SUM(wci.balance_amount_ngn) AS balance_ngn
        FROM weekly_coal_inventory wci WHERE {where_clause} AND wci.site = %(site)s""", p) or {}

def fetch_diesel(where_clause, site_val):
    p = params.copy(); p["site"] = site_val
    return fetch_one(f"""
        SELECT SUM(du.litres) AS total, SUM(du.litres) FILTER(WHERE du.is_haulage) AS haulage,
               SUM(du.litres) FILTER(WHERE NOT du.is_haulage) AS non_haulage
        FROM weekly_diesel_usage du WHERE {where_clause} AND du.site = %(site)s""", p) or {}

def fetch_internal_diesel(where_clause, site_val):
    p = params.copy(); p["site"] = site_val
    return fetch_one(f"""
        SELECT SUM(du.litres) AS internal_diesel FROM weekly_diesel_usage du
        WHERE {where_clause} AND du.site = %(site)s
          AND UPPER(TRIM(du.operation_type)) IN ('COAL MINING', 'COAL LOADING', 'OB OPERATION')
    """, p) or {}

cur_m_wh, prv_m_wh = get_query_conditions("")
cur_c_wh, prv_c_wh = get_query_conditions("wci.")
cur_d_wh, prv_d_wh = get_query_conditions("du.")

trcm_m = fetch_manual(cur_m_wh, 'TRCM'); ptrcm_m = fetch_manual(prv_m_wh, 'TRCM')
trcm_c = fetch_coal(cur_c_wh, 'TRCM');   ptrcm_c = fetch_coal(prv_c_wh, 'TRCM')
trcm_d = fetch_diesel(cur_d_wh, 'TRCM'); ptrcm_d = fetch_diesel(prv_d_wh, 'TRCM')
trcm_di = fetch_internal_diesel(cur_d_wh, 'TRCM'); ptrcm_di = fetch_internal_diesel(prv_d_wh, 'TRCM')

ifcm_m = fetch_manual(cur_m_wh, 'IFCM'); pifcm_m = fetch_manual(prv_m_wh, 'IFCM')
ifcm_c = fetch_coal(cur_c_wh, 'IFCM');   pifcm_c = fetch_coal(prv_c_wh, 'IFCM')
ifcm_d = fetch_diesel(cur_d_wh, 'IFCM'); pifcm_d = fetch_diesel(prv_d_wh, 'IFCM')
ifcm_di = fetch_internal_diesel(cur_d_wh, 'IFCM'); pifcm_di = fetch_internal_diesel(prv_d_wh, 'IFCM')

# ════════════════════════════════════════════════════════════════════════════
# BADGE & TABS SETUP
# ════════════════════════════════════════════════════════════════════════════
sel_we = selected_ws + pd.Timedelta(days=6)
if view_mode == "WoW":
    badge = f'<span class="week-badge">📅 {selected_ws.strftime("%d %b %Y")} → {sel_we.strftime("%d %b %Y")}</span>'
    if has_prev: badge += f'<span class="week-badge week-badge-prev">vs {prev_ws.strftime("%d %b %Y")}</span>'
elif view_mode == "MoM":
    badge = f'<span class="week-badge">📅 MTD ({sel_we.strftime("%B %Y")})</span><span class="week-badge week-badge-prev">vs Prior MTD</span>'
elif view_mode == "YTD":
    badge = f'<span class="week-badge week-badge-ytd">📅 YTD — 1 Jan {selected_ws.year} → {selected_ws.strftime("%d %b %Y")}</span>'
elif view_mode == "YoY":
    badge = f'<span class="week-badge week-badge-ytd">📅 YTD ({selected_ws.year})</span><span class="week-badge week-badge-prev">vs YTD ({selected_ws.year - 1})</span>'

st.markdown(badge, unsafe_allow_html=True)
st.markdown("<div style='margin-bottom:12px;'></div>", unsafe_allow_html=True)

tab_sum, tab_trcm, tab_ifcm = st.tabs(["📊 TRCM vs IFCM Summary", "⛏️ TRCM Details", "🚜 IFCM Details"])

# ════════════════════════════════════════════════════════════════════════════
# KPI HTML HELPERS
# ════════════════════════════════════════════════════════════════════════════
def delta_html(cur_val, prv_val):
    if view_mode == "YTD": return '<span class="kpi-ytd-badge">YTD TOTAL</span>'
    if prv_val is None: return '<div class="kpi-delta-flat">— no prior data</div>'
    diff = float(cur_val or 0) - float(prv_val)
    base = float(prv_val)
    pct  = (diff / base * 100) if base else 0
    sign = "▲" if diff >= 0 else "▼"
    cls  = "kpi-delta-up" if diff >= 0 else "kpi-delta-down"
    return f'<div class="{cls}">{sign} {abs(diff):,.1f} <span style="opacity:.7;font-weight:500">({abs(pct):.1f}%)</span></div>'

def kpi(col, label, val, unit="", prev=None, prefix="", is_ifcm=False):
    val_f = float(val or 0)
    fmt   = f"{prefix}{val_f:,.0f}" if prefix == "₦" else f"{prefix}{val_f:,.1f}"
    prev_html = ""
    if prev is not None and view_mode != "YTD":
        prev_f = float(prev)
        p_fmt = f"{prefix}{prev_f:,.0f}" if prefix == "₦" else f"{prefix}{prev_f:,.1f}"
        prev_html = f'<div class="kpi-prev-value">Prev: {p_fmt} {unit}</div>'

    extra_class = " kpi-wrap-ifcm" if is_ifcm else ""
    if view_mode in ["YTD", "YoY"]: extra_class += " kpi-wrap-ytd"
    
    col.markdown(
        f'<div class="kpi-wrap{extra_class}">'
        f'<div class="kpi-label">{label}</div>'
        f'<div class="kpi-value">{fmt}<span class="kpi-unit">{unit}</span></div>'
        f'{prev_html}{delta_html(val, prev)}</div>',
        unsafe_allow_html=True,
    )

def calc_di(di_dict, m_dict):
    d = float(di_dict.get("internal_diesel") or 0)
    c = float(m_dict.get("coal_mined") or 0)
    return (d / c) if c > 0 else 0.0

def vline(fig, col_name, df):
    if view_mode == "WoW" and not df.empty and selected_ws in df[col_name].values:
        fig.add_vline(x=str(selected_ws), line_dash="dot", line_color="#E63329", line_width=1.5, opacity=0.7)

def format_week_range(ws_val):
    if isinstance(ws_val, str):
        ws_dt = pd.to_datetime(ws_val).date()
    else:
        ws_dt = ws_val
    we_dt = ws_dt + timedelta(days=6)
    return f"{ws_dt.strftime('%d/%m/%Y')}-{we_dt.strftime('%d/%m/%Y')}"

# ════════════════════════════════════════════════════════════════════════════
# HELPER: RENDER SITE SPECIFIC TAB
# ════════════════════════════════════════════════════════════════════════════
def render_site_tab(site_name, cur_m, prv_m, cur_c, prv_c, cur_d, prv_d, cur_di, prv_di):
    is_ifcm = (site_name == "IFCM")
    pie_label = {"WoW": "This Week", "MoM": "This Month (MTD)", "YoY": "YTD vs Last Year"}.get(view_mode, "YTD")

    def should_show(label, val, prev):
        if not is_ifcm:
            return True
        val_f = float(val or 0)
        prv_f = float(prev or 0)
        mandatory = ["Coal Mined", "Total Coal Stocked", "BCM Excavated", "Coal Sold (Stock Out)", "Sales Revenue", "Total Diesel Used"]
        return val_f > 0 or prv_f > 0 or label in mandatory

    # 1. Dynamic KPI Grid
    kpi_groups = [
        ("Coal Production & Sourcing", [
            ("Coal Mined", cur_m.get("coal_mined"), "MT", prv_m.get("coal_mined"), ""),
            ("Coal — Local Miners", cur_m.get("coal_local"), "MT", prv_m.get("coal_local"), ""),
            ("Coal — High Wall", cur_m.get("coal_highwall"), "MT", prv_m.get("coal_highwall"), ""),
            ("BCM Excavated", cur_m.get("bcm_excavated"), "BCM", prv_m.get("bcm_excavated"), ""),
            ("Coal from IFCM", cur_m.get("coal_from_ifcm"), "MT", prv_m.get("coal_from_ifcm"), ""),
            ("Coal from Manejo", cur_m.get("coal_manejo"), "MT", prv_m.get("coal_manejo"), ""),
            ("Coal from Ogboyaga", cur_m.get("coal_ogboyaga"), "MT", prv_m.get("coal_ogboyaga"), ""),
            ("Total Coal Stocked", cur_m.get("total_stocked"), "MT", prv_m.get("total_stocked"), ""),
        ]),
        ("Sales & Inventory", [
            ("Coal Sold (Stock Out)", cur_c.get("stock_out_qty"), "MT", prv_c.get("stock_out_qty"), ""),
            ("Sales Revenue", cur_c.get("stock_out_ngn"), "", prv_c.get("stock_out_ngn"), "₦"),
            ("Closing Stock Balance", cur_c.get("balance_qty"), "MT", prv_c.get("balance_qty"), ""),
            ("Stock Balance Value", cur_c.get("balance_ngn"), "", prv_c.get("balance_ngn"), "₦"),
        ]),
        ("Diesel Consumption", [
            ("Total Diesel Used", cur_d.get("total"), "L", prv_d.get("total"), ""),
            ("Haulage Diesel", cur_d.get("haulage"), "L", prv_d.get("haulage"), ""),
            ("Non-Haulage Diesel", cur_d.get("non_haulage"), "L", prv_d.get("non_haulage"), ""),
            ("Mining Diesel / Ton", calc_di(cur_di, cur_m), "L/MT", calc_di(prv_di, prv_m) if prv_m.get("coal_mined") else None, ""),
        ])
    ]

    for section_title, items in kpi_groups:
        visible_items = [item for item in items if should_show(item[0], item[1], item[3])]
        if not visible_items:
            continue
            
        st.markdown(f'<div class="sec-hdr">{section_title}</div>', unsafe_allow_html=True)
        
        for i in range(0, len(visible_items), 4):
            batch = visible_items[i:i+4]
            cols = st.columns(4)
            for col_idx, (label, val, unit, prev, prefix) in enumerate(batch):
                kpi(cols[col_idx], label, val, unit, prev, prefix, is_ifcm=is_ifcm)

    # 2. Query Site Dataframes for Charts
    p_site = params.copy()
    p_site["site"] = site_name

    df_m = pd.DataFrame(fetch_all(f"""
        SELECT week_start_date, SUM(coal_mined_mt) AS coal_mined, SUM(bcm_excavated_bcm) AS bcm_excavated
        FROM weekly_manual_metrics WHERE week_start_date >= DATE_TRUNC('year', %(ws)s::date) AND week_start_date <= CURRENT_DATE AND site = %(site)s
        GROUP BY week_start_date ORDER BY week_start_date""", p_site))

    df_c = pd.DataFrame(fetch_all(f"""
        SELECT wci.week_start_date, SUM(wci.stock_out_qty) AS stock_out_qty, SUM(wci.stock_out_amount_ngn) AS stock_out_ngn
        FROM weekly_coal_inventory wci WHERE wci.week_start_date >= DATE_TRUNC('year', %(ws)s::date) AND wci.week_start_date <= CURRENT_DATE AND wci.site = %(site)s
        GROUP BY wci.week_start_date ORDER BY wci.week_start_date""", p_site))

    df_d = pd.DataFrame(fetch_all(f"""
        SELECT (du.dispensed_date - INTERVAL '1 day' * EXTRACT(DOW FROM du.dispensed_date)::integer)::date AS week_start,
               SUM(du.litres) FILTER(WHERE du.is_haulage) AS haulage, SUM(du.litres) FILTER(WHERE NOT du.is_haulage) AS non_haulage
        FROM weekly_diesel_usage du WHERE du.dispensed_date >= DATE_TRUNC('year', %(ws)s::date) AND du.dispensed_date <= CURRENT_DATE AND du.site = %(site)s
        GROUP BY 1 ORDER BY 1""", p_site))

    # 3. Detailed Analytics Section Title
    st.markdown(f'<div class="sec-hdr">Detailed Analytics — {site_name}</div>', unsafe_allow_html=True)

    # 4. Charts: Row 1 (Pie Charts)
    c1, c2 = st.columns(2)
    with c1:
        st.markdown(f'<div style="color:#94a3b8;font-size:12px;font-weight:600;margin-bottom:6px;">Coal Sourcing Breakdown — {pie_label}</div>', unsafe_allow_html=True)
        src = {
            "Mined": float(cur_m.get("coal_mined") or 0),
            "Local": float(cur_m.get("coal_local") or 0),
            "High Wall": float(cur_m.get("coal_highwall") or 0),
            "IFCM": float(cur_m.get("coal_from_ifcm") or 0),
            "Manejo": float(cur_m.get("coal_manejo") or 0),
            "Ogboyaga": float(cur_m.get("coal_ogboyaga") or 0),
        }
        src = {k: v for k, v in src.items() if v > 0}
        if src:
            fig1 = go.Figure(go.Pie(
                labels=list(src.keys()), values=list(src.values()), hole=0.52,
                marker=dict(colors=[BRAND, BLUE, GREEN, AMBER, PURPLE, TEAL], line=dict(color="#1e2130", width=2)),
                textinfo="label+percent", textfont=dict(size=11, color="#e2e8f0"),
                hovertemplate="<b>%{label}</b><br>%{value:,.1f} MT<br>%{percent}<extra></extra>",
            ))
            fig1.update_layout(**LAY, height=300, annotations=[dict(text=f"<b>{sum(src.values()):,.0f}</b><br><span style='font-size:10px'>MT</span>", x=0.5, y=0.5, showarrow=False, font=dict(color="#f1f5f9", size=14))])
            st.plotly_chart(fig1, use_container_width=True)
        else:
            st.markdown('<div class="no-data">No sourcing data available.</div>', unsafe_allow_html=True)

    with c2:
        st.markdown(f'<div style="color:#94a3b8;font-size:12px;font-weight:600;margin-bottom:6px;">Diesel Split — {pie_label}</div>', unsafe_allow_html=True)
        tot_d = float(cur_d.get("total") or 0)
        h_d = float(cur_d.get("haulage") or 0)
        nh_d = float(cur_d.get("non_haulage") or 0)
        if tot_d > 0:
            fig2 = go.Figure(go.Pie(
                labels=["Haulage", "Non-Haulage"], values=[h_d, nh_d], hole=0.55,
                marker=dict(colors=[TEAL, AMBER], line=dict(color="#1e2130", width=2)),
                texttemplate="<b>%{label}</b><br>%{percent}", textfont=dict(size=11, color="#e2e8f0"),
                hovertemplate="<b>%{label}</b><br>%{value:,.0f} L (%{percent})<extra></extra>",
            ))
            fig2.update_layout(**LAY, height=300, annotations=[dict(text=f"<b>{tot_d:,.0f}</b><br><span>L total</span>", x=0.5, y=0.5, showarrow=False, font=dict(color="#f1f5f9", size=13))])
            st.plotly_chart(fig2, use_container_width=True)
        else:
            st.markdown('<div class="no-data">No diesel data available.</div>', unsafe_allow_html=True)

    # 5. Charts: Row 2 (Sales & Stripping Ratio)
    c3, c4 = st.columns(2)
    with c3:
        st.markdown('<div style="color:#94a3b8;font-size:12px;font-weight:600;margin-bottom:6px;">Weekly Sales Revenue (₦)</div>', unsafe_allow_html=True)
        if not df_c.empty:
            fig3 = go.Figure()
            fig3.add_scatter(x=df_c["week_start_date"], y=df_c["stock_out_ngn"].astype(float), mode="lines+markers", fill="tozeroy", fillcolor="rgba(230,51,41,0.12)", line=dict(color=BRAND, width=2), marker=dict(size=6, color=BRAND, line=dict(color="#1e2130", width=1)), name="Sales ₦", hovertemplate="₦%{y:,.0f}<extra></extra>")
            vline(fig3, "week_start_date", df_c)
            fig3.update_layout(**LAY, height=300, xaxis_title="Week", yaxis_title="₦", yaxis_tickformat=",.0f")
            st.plotly_chart(fig3, use_container_width=True)
        else:
            st.markdown('<div class="no-data">No sales revenue history yet.</div>', unsafe_allow_html=True)

    with c4:
        st.markdown('<div style="color:#94a3b8;font-size:12px;font-weight:600;margin-bottom:6px;">Weekly Stripping Ratio Trend (BCM / MT)</div>', unsafe_allow_html=True)
        st.info("💡 **Stripping Ratio (BCM/MT):** Measures waste moved per ton of coal mined. A higher bar means more overburden was moved relative to coal output.")
        
        if not df_m.empty:
            df_m["coal_mined"] = df_m["coal_mined"].fillna(0).astype(float)
            df_m["bcm_excavated"] = df_m["bcm_excavated"].fillna(0).astype(float)
            df_m["stripping_ratio"] = np.where(df_m["coal_mined"] > 0, df_m["bcm_excavated"] / df_m["coal_mined"], 0)
            
            fig4 = go.Figure()
            fig4.add_bar(x=df_m["week_start_date"], y=df_m["stripping_ratio"], marker_color=PURPLE, opacity=0.75, name="Ratio", hovertemplate="%{y:,.2f} BCM/MT<extra></extra>")
            
            if len(df_m) > 1:
                x_numeric = np.arange(len(df_m))
                y_data = df_m["stripping_ratio"].values
                z = np.polyfit(x_numeric, y_data, 1) 
                p = np.poly1d(z)
                fig4.add_scatter(x=df_m["week_start_date"], y=p(x_numeric), mode="lines", name="Trend", line=dict(color="#f87171", width=2.5, dash="dash"), hoverinfo="skip")
            
            vline(fig4, "week_start_date", df_m)
            fig4.update_layout(**LAY, height=300, xaxis_title="Week", yaxis_title="BCM / MT", showlegend=False)
            st.plotly_chart(fig4, use_container_width=True)
        else:
            st.markdown('<div class="no-data">No stripping ratio history yet.</div>', unsafe_allow_html=True)

    # 6. Charts: Row 3 (Diesel Consumption & Cumulative Sales)
    c5, c6 = st.columns(2)
    with c5:
        st.markdown('<div style="color:#94a3b8;font-size:12px;font-weight:600;margin-bottom:6px;">Weekly Diesel Consumption</div>', unsafe_allow_html=True)
        if not df_d.empty:
            fig5 = go.Figure()
            fig5.add_bar(x=df_d["week_start"], y=df_d["haulage"].astype(float), name="Haulage", marker_color=TEAL, opacity=0.9, hovertemplate="<b>Haulage</b><br>%{y:,.0f} L<extra></extra>")
            fig5.add_bar(x=df_d["week_start"], y=df_d["non_haulage"].astype(float), name="Non-Haulage", marker_color=AMBER, opacity=0.9, hovertemplate="<b>Non-Haulage</b><br>%{y:,.0f} L<extra></extra>")
            vline(fig5, "week_start", df_d)
            fig5.update_layout(**LAY, height=300, barmode="stack", xaxis_title="Week", yaxis_title="Litres", yaxis_tickformat=",.0f")
            st.plotly_chart(fig5, use_container_width=True)
        else:
            st.markdown('<div class="no-data">No diesel history yet.</div>', unsafe_allow_html=True)

    with c6:
        st.markdown(f'<div style="color:#94a3b8;font-size:12px;font-weight:600;margin-bottom:6px;">Cumulative Coal Sold — YTD ({selected_ws.year}) (MT)</div>', unsafe_allow_html=True)
        if not df_c.empty:
            df_c["cum_sold"] = df_c["stock_out_qty"].astype(float).cumsum()
            fig6 = go.Figure()
            fig6.add_scatter(x=df_c["week_start_date"], y=df_c["cum_sold"], mode="lines+markers", fill="tozeroy", fillcolor="rgba(52,211,153,0.15)", line=dict(color=GREEN, width=2.5), marker=dict(size=6, color=GREEN, line=dict(color="#1e2130", width=1)), name="Cum. Sold", hovertemplate="%{y:,.1f} MT<extra></extra>")
            vline(fig6, "week_start_date", df_c)
            fig6.update_layout(**LAY, height=300, xaxis_title="Week", yaxis_title="Cumulative MT", yaxis_tickformat=",.0f")
            st.plotly_chart(fig6, use_container_width=True)
        else:
            st.markdown('<div class="no-data">No cumulative sales history yet.</div>', unsafe_allow_html=True)

    # 7. Split Section: BCM vs Coal Mined Scatterplot (50%) + Low Efficiency Table (50%)
    st.markdown('<div class="sec-hdr">🎯 Mining Efficiency Matrix — BCM vs Coal Mined</div>', unsafe_allow_html=True)
    st.info("📌 **Efficiency Matrix:** Compares total BCM excavated (horizontal X-axis) against Coal Mined in MT (vertical Y-axis). **Red points indicate low-efficiency weeks** with high overburden stripping relative to coal recovered (high stripping ratio).")

    if not df_m.empty:
        df_m["coal_mined"] = df_m["coal_mined"].fillna(0).astype(float)
        df_m["bcm_excavated"] = df_m["bcm_excavated"].fillna(0).astype(float)
        df_m["stripping_ratio"] = np.where(df_m["coal_mined"] > 0, df_m["bcm_excavated"] / df_m["coal_mined"], 0)
        df_m["week_range_str"] = df_m["week_start_date"].apply(format_week_range)

        # Flag high stripping ratio weeks (e.g., SR >= 75th percentile or SR > 8.0)
        sr_threshold = df_m["stripping_ratio"].quantile(0.75) if len(df_m) > 4 else 8.0
        colors = ["#f87171" if sr >= sr_threshold and sr > 0 else "#60a5fa" for sr in df_m["stripping_ratio"]]
        sizes = [14 if sr >= sr_threshold and sr > 0 else 9 for sr in df_m["stripping_ratio"]]

        col_scat, col_tbl = st.columns(2)

        with col_scat:
            st.markdown('<div style="color:#94a3b8;font-size:12px;font-weight:600;margin-bottom:6px;"', unsafe_allow_html=True)
            fig_scatter = go.Figure()
            fig_scatter.add_trace(go.Scatter(
                x=df_m["bcm_excavated"],
                y=df_m["coal_mined"],
                mode="markers+text",
                marker=dict(
                    size=sizes,
                    color=colors,
                    line=dict(width=1.5, color="#1e2130")
                ),
                text=[f"SR: {sr:.1f}" if sr >= sr_threshold and sr > 0 else "" for sr in df_m["stripping_ratio"]],
                textposition="top center",
                textfont=dict(color="#f87171", size=10, family="Inter, sans-serif"),
                customdata=np.stack((
                    df_m["week_range_str"],
                    df_m["stripping_ratio"]
                ), axis=-1),
                hovertemplate=(
                    "<b>📅 Period: %{customdata[0]}</b><br><br>" +
                    "⛏️ <b>Coal Mined:</b> %{y:,.1f} MT<br>" +
                    "🚜 <b>BCM Excavated:</b> %{x:,.0f} BCM<br>" +
                    "📊 <b>Stripping Ratio:</b> %{customdata[1]:,.2f} BCM/MT" +
                    "<extra></extra>"
                )
            ))

            fig_scatter.update_layout(
                **LAY,
                height=380,
                xaxis_title="BCM Excavated",
                yaxis_title="Coal Mined (MT)",
                showlegend=False
            )
            st.plotly_chart(fig_scatter, use_container_width=True)

        with col_tbl:
            st.markdown('<div style="color:#94a3b8;font-size:12px;font-weight:600;margin-bottom:6px;">⚠️ Flagged Low-Efficiency Weeks</div>', unsafe_allow_html=True)
            df_low = df_m[(df_m["stripping_ratio"] >= sr_threshold) & (df_m["stripping_ratio"] > 0)].copy()
            df_low = df_low.sort_values(by="stripping_ratio", ascending=False)

            if not df_low.empty:
                rows_html = "".join([
                    f'<tr style="background:{"#1a1d27" if i % 2 == 0 else "#161824"};">'
                    f'<td style="padding:8px 12px;font-weight:600;color:#f87171;">{row["week_range_str"]}</td>'
                    f'<td style="padding:8px 12px;text-align:right;color:#f1f5f9;">{row["coal_mined"]:,.1f} MT</td>'
                    f'<td style="padding:8px 12px;text-align:right;color:#f1f5f9;">{row["bcm_excavated"]:,.0f} BCM</td>'
                    f'<td style="padding:8px 12px;text-align:right;font-weight:800;color:#f87171;">{row["stripping_ratio"]:,.2f}</td></tr>'
                    for i, (_, row) in enumerate(df_low.iterrows())
                ])
                st.markdown(f"""
                    <div style="overflow-y:auto;max-height:340px;border-radius:10px;border:1px solid #2a2d3a;margin-top:6px;">
                      <table style="width:100%;border-collapse:collapse;font-size:12px;font-family:Inter,sans-serif;">
                        <thead>
                          <tr style="background:#252836;position:sticky;top:0;z-index:1;">
                            <th style="padding:8px 12px;text-align:left;color:#64748b;font-size:10px;font-weight:700;text-transform:uppercase;">Period (dd/mm/yyyy - dd/mm/yyyy)</th>
                            <th style="padding:8px 12px;text-align:right;color:#64748b;font-size:10px;font-weight:700;text-transform:uppercase;">Coal Mined</th>
                            <th style="padding:8px 12px;text-align:right;color:#64748b;font-size:10px;font-weight:700;text-transform:uppercase;">BCM Excavated</th>
                            <th style="padding:8px 12px;text-align:right;color:#64748b;font-size:10px;font-weight:700;text-transform:uppercase;">Stripping Ratio</th>
                          </tr>
                        </thead>
                        <tbody>{rows_html}</tbody>
                      </table>
                    </div>
                """, unsafe_allow_html=True)
            else:
                st.markdown('<div class="no-data">No low-efficiency weeks flagged for this period.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="no-data">No BCM vs. Coal Mining data available yet.</div>', unsafe_allow_html=True)

    # 8. Equipment Diesel Table
    st.markdown('<div class="sec-hdr">🚜 Equipment Diesel Usage</div>', unsafe_allow_html=True)
    df_eq = pd.DataFrame(fetch_all(f"""
        SELECT du.equipment_name AS equipment, COALESCE(NULLIF(TRIM(du.equipment_type),''), 'UNKNOWN') AS equipment_type, SUM(du.litres) AS litres
        FROM weekly_diesel_usage du WHERE {cur_d_wh} AND du.site = %(site)s
        GROUP BY du.equipment_name, du.equipment_type ORDER BY litres DESC""", p_site))

    if not df_eq.empty:
        df_eq["litres"] = pd.to_numeric(df_eq["litres"], errors="coerce").fillna(0.0)
        df_eq = df_eq[df_eq["equipment"].notna() & (df_eq["equipment"].str.strip() != "")]
        usage_col = "Diesel Usage YTD (L)" if view_mode == "YTD" else "Diesel Usage — Current Period (L)"
        
        df_disp = df_eq.rename(columns={"equipment": "Equipment ID", "equipment_type": "Equipment Type", "litres": usage_col}).copy()
        df_disp[usage_col] = df_disp[usage_col].apply(lambda x: f"{x:,.0f}")

        sq = st.text_input("🔍 Search equipment or type", placeholder="Type to filter...", key=f"search_{site_name}")
        df_f = df_disp[df_disp.astype(str).apply(lambda row: sq.lower() in ' '.join(row).lower(), axis=1)] if sq else df_disp

        col_dl, col_info = st.columns([1, 4])
        with col_dl:
            st.download_button("📥 Download CSV", data=df_f.to_csv(index=False), file_name=f"{site_name}_diesel_{view_mode}.csv", mime="text/csv", key=f"dl_{site_name}")
        with col_info:
            st.markdown(f'<div style="color:#94a3b8;font-size:12px;padding-top:8px;">{len(df_f)} of {len(df_disp)} records</div>', unsafe_allow_html=True)

        if not df_f.empty:
            rows_html = "".join([
                f'<tr style="background:{"#1a1d27" if i % 2 == 0 else "#161824"};">'
                f'<td style="padding:8px 14px;font-weight:600;color:#f1f5f9;">{row["Equipment ID"]}</td>'
                f'<td style="padding:8px 14px;color:#94a3b8;">{row["Equipment Type"]}</td>'
                f'<td style="padding:8px 14px;text-align:right;font-weight:700;color:#34d399;font-variant-numeric:tabular-nums;">{row[usage_col]}</td></tr>'
                for i, (_, row) in enumerate(df_f.iterrows())
            ])
            st.markdown(f"""
                <div style="overflow-y:auto;max-height:350px;border-radius:10px;border:1px solid #2a2d3a;margin-top:12px;">
                  <table style="width:100%;border-collapse:collapse;font-size:13px;font-family:Inter,sans-serif;">
                    <thead>
                      <tr style="background:#252836;position:sticky;top:0;z-index:1;">
                        <th style="padding:10px 14px;text-align:left;color:#64748b;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;">Equipment ID</th>
                        <th style="padding:10px 14px;text-align:left;color:#64748b;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;">Equipment Type</th>
                        <th style="padding:10px 14px;text-align:right;color:#64748b;font-size:10px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;">{usage_col}</th>
                      </tr>
                    </thead>
                    <tbody>{rows_html}</tbody>
                  </table>
                </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown('<div class="no-data">No results match your search.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="no-data">No diesel equipment data for the selected period.</div>', unsafe_allow_html=True)

# ════════════════════════════════════════════════════════════════════════════
# TAB 1: SUMMARY (TRCM vs IFCM)
# ════════════════════════════════════════════════════════════════════════════
with tab_sum:
    st.markdown('<div class="sec-hdr">Side-by-Side Executive Summary</div>', unsafe_allow_html=True)
    
    col_t, col_i = st.columns(2)
    with col_t:
        st.markdown("<h4 style='color:#E63329; margin-bottom: 2px;'>⛏️ TRCM Output</h4>", unsafe_allow_html=True)
        t1, t2 = st.columns(2)
        kpi(t1, "Coal Mined", trcm_m.get("coal_mined"), "MT", ptrcm_m.get("coal_mined"))
        kpi(t2, "BCM Excavated", trcm_m.get("bcm_excavated"), "BCM", ptrcm_m.get("bcm_excavated"))
        t3, t4 = st.columns(2)
        kpi(t3, "Total Coal Stocked", trcm_m.get("total_stocked"), "MT", ptrcm_m.get("total_stocked"))
        kpi(t4, "Diesel Consumed", trcm_d.get("total"), "L", ptrcm_d.get("total"))
        t5, t6 = st.columns(2)
        kpi(t5, "Coal Sold", trcm_c.get("stock_out_qty"), "MT", ptrcm_c.get("stock_out_qty"))
        kpi(t6, "Revenue", trcm_c.get("stock_out_ngn"), "", ptrcm_c.get("stock_out_ngn"), prefix="₦")

    with col_i:
        st.markdown("<h4 style='color:#fbbf24; margin-bottom: 2px;'>🚜 IFCM Output</h4>", unsafe_allow_html=True)
        i1, i2 = st.columns(2)
        kpi(i1, "Coal Mined", ifcm_m.get("coal_mined"), "MT", pifcm_m.get("coal_mined"), is_ifcm=True)
        kpi(i2, "BCM Excavated", ifcm_m.get("bcm_excavated"), "BCM", pifcm_m.get("bcm_excavated"), is_ifcm=True)
        i3, i4 = st.columns(2)
        kpi(i3, "Total Coal Stocked", ifcm_m.get("total_stocked"), "MT", pifcm_m.get("total_stocked"), is_ifcm=True)
        kpi(i4, "Diesel Consumed", ifcm_d.get("total"), "L", pifcm_d.get("total"), is_ifcm=True)
        i5, i6 = st.columns(2)
        kpi(i5, "Coal Sold", ifcm_c.get("stock_out_qty"), "MT", pifcm_c.get("stock_out_qty"), is_ifcm=True)
        kpi(i6, "Revenue", ifcm_c.get("stock_out_ngn"), "", pifcm_c.get("stock_out_ngn"), prefix="₦", is_ifcm=True)

    st.markdown('<div class="sec-hdr">Visual Comparison</div>', unsafe_allow_html=True)
    metrics = ["Coal Mined (MT)", "Coal Sold (MT)", "Total Stocked (MT)", "Diesel Used (L)"]
    trcm_vals = [float(trcm_m.get("coal_mined") or 0), float(trcm_c.get("stock_out_qty") or 0), float(trcm_m.get("total_stocked") or 0), float(trcm_d.get("total") or 0)]
    ifcm_vals = [float(ifcm_m.get("coal_mined") or 0), float(ifcm_c.get("stock_out_qty") or 0), float(ifcm_m.get("total_stocked") or 0), float(ifcm_d.get("total") or 0)]
    
    fig_comp = go.Figure(data=[
        go.Bar(name='TRCM', x=metrics, y=trcm_vals, marker_color=BRAND),
        go.Bar(name='IFCM', x=metrics, y=ifcm_vals, marker_color=AMBER)
    ])
    fig_comp.update_layout(**LAY, barmode='group', height=350, yaxis_title="Volume / Litres")
    st.plotly_chart(fig_comp, use_container_width=True)

# ════════════════════════════════════════════════════════════════════════════
# TABS 2 & 3: TRCM & IFCM DETAILS
# ════════════════════════════════════════════════════════════════════════════
with tab_trcm:
    render_site_tab("TRCM", trcm_m, ptrcm_m, trcm_c, ptrcm_c, trcm_d, ptrcm_d, trcm_di, ptrcm_di)

with tab_ifcm:
    render_site_tab("IFCM", ifcm_m, pifcm_m, ifcm_c, pifcm_c, ifcm_d, pifcm_d, ifcm_di, pifcm_di)
