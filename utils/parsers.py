"""
utils/parsers.py
Data extraction and cleaning helpers for Mosra Energy Excel/CSV uploads.
"""

import pandas as pd
import re
import io
import math
from numbers import Real
from collections import Counter

OPERATION_TYPO_MAP: dict[str, str] = {
    # OB & Overburden
    "OVERBURDEN OPERATION": "OB OPERATION",
    "OB OPERATION": "OB OPERATION",
    "OV": "OB OPERATION",

    # Haulage Variations
    "HAULAGE": "HAULAGE",
    "HAULAGES": "HAULAGE",
    "HAULLAGE": "HAULAGE",
    "HAULAGE TRAILER": "HAULAGE",
    "HAIB TRUCK": "HAULAGE",

    # Coal Mining & Loading
    "COAL MINNING": "COAL MINING",
    "COAL MINING": "COAL MINING",
    "COAL MININIG": "COAL MINING",
    "CAOL M": "COAL MINING",
    "COAL M": "COAL MINING",
    "COAL M'O": "COAL MINING",
    "COAL M'": "COAL MINING",
    "COALM": "COAL MINING",
    "COAL K": "COAL MINING",
    "TEST/COAL MINNING": "COAL MINING",
    "TEST/COAL MINING": "COAL MINING",
    "COAL LOADING": "COAL LOADING",
    "COAL LOADIND": "COAL LOADING",
    "COAL LOAD": "COAL LOADING",

    # Highwall Operations
    "HIGHWALL COAL MINING": "HIGHWALL MINING",
    "HIGHWALL MINERS": "HIGHWALL MINING",
    "HIGHWALL MINING": "HIGHWALL MINING",
    "HIGHWALL DEWATERING": "HIGHWALL DEWATERING",

    # Coal Sourcing & Stockpiling
    "LOCAL MINERS COAL PURCHASE": "LOCAL MINERS COAL PURCHASE",
    "LOCAL MINERS": "LOCAL MINERS COAL PURCHASE",
    "STOCK PILLING": "STOCKPILING",
    "STOCKPILING": "STOCKPILING",
    "COAL PILLING": "STOCKPILING",
    "SPILLAGE": "STOCKPILING",
    "SPILAGE": "STOCKPILING",
    "SPILLAGES": "STOCKPILING",
    "SPILLAGE FROM DISCHARGE": "STOCKPILING",

    # Maintenance, Servicing & Engine Running
    "MAINTERNACE": "MAINTENANCE",
    "MAINTENACE": "MAINTENANCE",
    "MAINTAINANCE": "MAINTENANCE",
    "MAINTENANCE": "MAINTENANCE",
    "MAINTENANCE WORK": "MAINTENANCE",
    "WORKSHOP USE": "MAINTENANCE",
    "SERVICE": "ENGINE SERVICING",
    "SERVICING": "ENGINE SERVICING",
    "ENGINE SERVICE": "ENGINE SERVICING",
    "ENGINE SERVICING": "ENGINE SERVICING",
    "ENGINE SEVICE": "ENGINE SERVICING",
    "ENGINEW SERVICE": "ENGINE SERVICING",
    "ENGINE WASH": "ENGINE WASHING",
    "ENGINEWASH": "ENGINE WASHING",
    "ENGINE WASHING": "ENGINE WASHING",
    "WASHING OF TOOLS": "ENGINE WASHING",
    "ENGINE RUNING": "TEST RUNNING",
    "ENGINE RUNINIG": "TEST RUNNING",
    "ENGINE RUNNING": "TEST RUNNING",
    "RUNING ENGINE": "TEST RUNNING",
    "RUNNIG OF ENGINE": "TEST RUNNING",
    "RUNNING OF ENGINE": "TEST RUNNING",
    "TEST RUNING": "TEST RUNNING",
    "TEST RUNNING": "TEST RUNNING",
    "DRIVING TEST": "TEST RUNNING",
    "PRACTICAL TEST": "TEST RUNNING",

    # Civil, Construction & Infrastructure
    "CIVIL WORKS": "CIVIL WORK",
    "CIVIL WORK": "CIVIL WORK",
    "ROAD CONSTRUCTION": "CIVIL WORK",
    "ROAD CONSTRUCTION WORK": "CIVIL WORK",
    "ROAD MAINTENANCE": "CIVIL WORK",
    "SITE OPERATION": "CIVIL WORK",
    "INSTALLATION": "CIVIL WORK",
    "CRUSHER PLANT": "CRUSHER PLANT",
    "CRUSHING": "CRUSHER PLANT",
    "CRUSHER MAINTERNACE": "CRUSHER MAINTENANCE",
    "CRUSHER MAINTENANCE": "CRUSHER MAINTENANCE",
    "POWERING OF OFFICE, WEIGHBRIDGE AND WORKSHOP GENERATOR": "POWER SUPPLY",
    "POWER SUPPLY": "POWER SUPPLY",
    "POWER SUPPY": "POWER SUPPLY",
    "GENERATOR": "POWER SUPPLY",
    "TOWER LIGHT": "POWER SUPPLY",

    # Water & Dust
    "WATER SUPPLY FOR DOMESTIC USE": "WATER SUPPLY",
    "WATER SUPPLYING": "WATER SUPPLY",
    "WATER SUPPLY": "WATER SUPPLY",
    "WATER TANKER": "WATER SUPPLY",
    "DUST SUPPRESSION": "DUST SUPPRESSION",

    # Diesel & Stock In
    "DIESEL DISPENSER OR SUPPLY": "DIESEL DISPENSER",
    "DIESEL DISPENCER": "DIESEL DISPENSER",
    "DIESEL DISPENSER 01": "DIESEL DISPENSER",
    "DIESEL DISPENSING": "DIESEL DISPENSER",
    "DIESEL SUPPLYING": "DIESEL DISPENSER",
    "DIESEL SUPPLY": "DIESEL DISPENSER",
    "DIESEL TANKER": "DIESEL DISPENSER",
    "DISPENSER": "DIESEL DISPENSER",
    "STOCK IN": "STOCK IN",
    "STOCKING": "STOCK IN",

    # Invalid / Corrupt Strings
    "2": "UNSPECIFIED",
}

def _normalise_op_type(raw: str) -> str:
    """Standardizes casing, strips whitespace, and maps typos to canonical operation names."""
    if pd.isna(raw):
        return "UNSPECIFIED"
    
    # 1. Strip whitespace, collapse extra inner spaces, uppercase
    cleaned = re.sub(r'\s+', ' ', str(raw).strip().upper())
    if cleaned in ("NAN", "NONE", ""):
        return "UNSPECIFIED"
    
    # 2. Check explicitly mapped lookup table
    if cleaned in OPERATION_TYPO_MAP:
        return OPERATION_TYPO_MAP[cleaned]
    
    # 3. Handle unmapped strings (e.g., specific haulage trips like "TRIP TO KANO")
    return cleaned

def parse_coal_excel(file_bytes: bytes):
    """
    Parses weekly coal inventory reports from Sheet 1 ('Stock Inventory').
    Extracts stock reference, item names, quantities, rates, and amounts.
    """
    file_stream = io.BytesIO(file_bytes)
    try:
        xls = pd.ExcelFile(file_stream, engine="openpyxl")
    except Exception as e:
        raise ValueError(f"Could not read Excel file: {e}")

    # Check for the required sheet
    target_sheet = None
    for sheet in xls.sheet_names:
        if "stock inventory" in sheet.strip().lower():
            target_sheet = sheet
            break
            
    if not target_sheet:
        raise ValueError(f"Sheet 'Stock Inventory' not found. Available sheets: {xls.sheet_names}")

    df_raw = pd.read_excel(xls, sheet_name=target_sheet, header=None)
    
    # Locate the header row containing 'Stock Ref.' or 'Stock Item'
    header_idx = None
    for i, row in df_raw.iterrows():
        row_str = " ".join([str(x).upper() for x in row.dropna()])
        if "STOCK REF" in row_str or "STOCK ITEM" in row_str:
            header_idx = i
            break
            
    if header_idx is None:
        raise ValueError("Could not locate header row in 'Stock Inventory' sheet.")

    # Slice data starting right after the header rows
    # Note: Sheet 1 has a multi-index header (Row header_idx is Item/UOM, header_idx+1 is Qty/Rate/Amount)
    df = df_raw.iloc[header_idx + 2:].copy().reset_index(drop=True)
    
    rows = []
    warnings = []

    for idx, row in df.iterrows():
        # Column mapping based on standard Stock Inventory layout:
        # Col 1: Stock Ref, Col 2: Stock Item, Col 3: UOM
        # Col 4,5,6: Opening (Qty, Rate, Amount)
        # Col 7,8: Stock In (Qty, Amount)
        # Col 9,10: Stock Out (Qty, Amount)
        # Col 11,12: Balance (Qty, Amount)
        stock_ref = str(row.iloc[1]).strip()
        if not stock_ref or stock_ref in ("nan", "None", "NaN"):
            continue
            
        stock_item = str(row.iloc[2]).strip()
        uom = str(row.iloc[3]).strip() if pd.notna(row.iloc[3]) else "Ton"

        def safe_float(val):
            try:
                return float(str(val).replace(",", "").strip())
            except (ValueError, TypeError):
                return 0.0

        opening_qty = safe_float(row.iloc[4])
        rate_ngn = safe_float(row.iloc[5])
        opening_amt = safe_float(row.iloc[6])
        
        stock_in_qty = safe_float(row.iloc[7])
        stock_in_amt = safe_float(row.iloc[8])
        
        stock_out_qty = safe_float(row.iloc[9])
        stock_out_amt = safe_float(row.iloc[10])
        
        balance_qty = safe_float(row.iloc[11])
        balance_amt = safe_float(row.iloc[12])

        rows.append({
            "stock_ref": stock_ref,
            "stock_item": stock_item,
            "uom": uom,
            "opening_qty": opening_qty,
            "rate_ngn": rate_ngn,
            "opening_amount_ngn": opening_amt,
            "stock_in_qty": stock_in_qty,
            "stock_in_amount_ngn": stock_in_amt,
            "stock_out_qty": stock_out_qty,
            "stock_out_amount_ngn": stock_out_amt,
            "stock_balance_qty": balance_qty,
            "balance_amount_ngn": balance_amt
        })

    if not rows:
        warnings.append("No inventory items (MOC01, MOC02, etc.) were found in the sheet.")

    return rows, warnings

def _diesel_header(value):
    return re.sub(r"\s+", "_", str(value).strip().lower())


def _diesel_table(file_bytes, site):
    """Select a raw-data sheet, never a pivot/summary or another site's data."""
    stream = io.BytesIO(file_bytes)
    if file_bytes.startswith((b"PK", b"\xd0\xcf\x11\xe0")):
        # Let pandas choose openpyxl for xlsx and xlrd for legacy xls.
        with pd.ExcelFile(stream) as workbook:
            sheets = {name: pd.read_excel(workbook, sheet_name=name, header=None)
                      for name in workbook.sheet_names}
    else:
        sheets = {"CSV": pd.read_csv(stream, header=None)}

    candidates = []
    for name, frame in sheets.items():
        for idx, row in frame.iterrows():
            headers = {_diesel_header(v) for v in row.dropna()}
            if (headers & {"date", "dispensed_date"}
                    and headers & {"equipment", "equipment_name"}
                    and headers & {"diesel_dispensed", "litres", "qty"}
                    and headers & {"operation", "operation_type"}):
                named_sites = set(re.findall(r"\b(?:TRCM|IFCM)\b", name.upper()))
                if named_sites and site not in named_sites:
                    break
                candidates.append((name, frame, idx, site in named_sites))
                break
    preferred = [candidate for candidate in candidates if candidate[3]]
    candidates = preferred or candidates
    if len(candidates) != 1:
        raise ValueError(
            f"Expected one dispensing sheet for {site}; found "
            f"{[c[0] for c in candidates]}. Supply one complete raw-data sheet "
            "with DATE, EQUIPMENT, DIESEL DISPENSED and OPERATION TYPE headers."
        )
    name, frame, header_idx, _ = candidates[0]
    excluded = [sheet for sheet in sheets if sheet != name]
    notices = []
    if excluded:
        notices.append(
            f"Reading '{name}' only. Excluded sheets: {', '.join(excluded)}. "
            "If any are continuation logs, combine them into one raw-data sheet before uploading."
        )
    return frame, header_idx, notices


def _diesel_date(value):
    if pd.isna(value):
        raise ValueError("Missing date")
    if isinstance(value, Real):
        parsed = pd.to_datetime(value, unit="D", origin="1899-12-30")
    elif isinstance(value, str) and re.fullmatch(r"\d{5}(?:\.\d+)?", value.strip()):
        parsed = pd.to_datetime(float(value), unit="D", origin="1899-12-30")
    elif isinstance(value, str) and re.match(r"^\d{4}-\d{2}-\d{2}(?:$|[ T])", value.strip()):
        parsed = pd.Timestamp(value.strip())
    else:
        parsed = pd.to_datetime(value, dayfirst=True)
    if pd.isna(parsed):
        raise ValueError("Missing date")
    return parsed.date()


def _diesel_litres(value):
    """Accept numbers and explicit litre units, without changing signs or digits."""
    cleaned = str(value).strip()
    cleaned = re.sub(r"\s*(?:litres?|liters?|l)\s*$", "", cleaned, flags=re.I)
    if not re.fullmatch(r"[+-]?(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d+)?", cleaned):
        raise ValueError("Invalid litres")
    result = float(cleaned.replace(",", ""))
    if not math.isfinite(result) or result < 0:
        raise ValueError("Litres must be finite and non-negative")
    return result


def parse_diesel_excel_old(file_bytes: bytes, site: str, existing_cls: dict[str, bool]):
    """
    Parses daily diesel dispensing logs (Excel/CSV).
    Handles messy headers, merged date cells, numeric string cleaning,
    and returns clean dictionary records ready for database transactions.
    """
    site = site.strip().upper()
    if site not in {"TRCM", "IFCM"}:
        raise ValueError(f"Unknown site: {site}")
    df_raw, header_idx, warnings = _diesel_table(file_bytes, site)

    # 3. Extract column names and slice the DataFrame directly in memory
    raw_headers = df_raw.iloc[header_idx].fillna("").astype(str).tolist()
    df = df_raw.iloc[header_idx + 1:].copy().reset_index(drop=True)
    df.columns = raw_headers

    # 4. Standardize Column Headers
    df.columns = [_diesel_header(c) for c in df.columns]

    col_mapping = {
        "date": "dispensed_date",
        "dispensed_date": "dispensed_date",
        "equipment": "equipment_name",
        "equipment_name": "equipment_name",
        "equipment_type": "equipment_type",
        "operation": "operation_type",
        "operation_type": "operation_type",
        "diesel_dispensed": "litres",
        "litres": "litres",
        "qty": "litres",
        "mine": "site",
    }
    
    df = df.rename(columns=lambda x: col_mapping.get(x, x))

    required_cols = ["dispensed_date", "equipment_name", "operation_type", "litres"]
    missing_cols = [c for c in required_cols if c not in df.columns]
    
    if missing_cols:
        raise ValueError(
            f"Missing required columns in file: {missing_cols}. Found: {list(df.columns)}"
        )

    if any(list(df.columns).count(c) > 1 for c in required_cols + ["site"]):
        raise ValueError("Duplicate diesel column headers; use one column per field.")

    if "site" in df.columns:
        row_sites = df["site"].astype("string").str.strip().str.upper()
        df = df[row_sites.eq(site).fillna(False)].copy()

    # 5. Forward-fill dates to capture rows beneath Excel merged cells
    df["dispensed_date"] = df["dispensed_date"].infer_objects(copy=False).ffill()
    df = df.dropna(subset=["litres"])

    dispense_rows = []
    new_op_types_dict = {}

    # 6. Row-by-row cleaning and type conversions
    for idx, row in df.iterrows():
        row_number = header_idx + idx + 2
        labels = [str(row[c]).strip().upper() for c in
                  ("dispensed_date", "equipment_name", "operation_type")]
        if any(re.fullmatch(r"(?:GRAND\s+TOTAL|SUB\s*TOTAL|TOTAL)(?:\s*\(L\))?", v)
               for v in labels):
            warnings.append(f"Row {row_number}: Summary row excluded.")
            continue
        try:
            d_date = _diesel_date(row["dispensed_date"])
        except Exception:
            warnings.append(f"Row {row_number}: Invalid date format '{row['dispensed_date']}'. Skipped.")
            continue

        raw_litres = str(row["litres"])
        try:
            litres_val = _diesel_litres(raw_litres)
            if litres_val <= 0:
                continue
        except ValueError:
            warnings.append(f"Row {row_number}: Invalid litres value '{raw_litres}'. Skipped.")
            continue

        equip_name = str(row["equipment_name"]).strip().upper()
        if equip_name in ("NAN", "", "NONE"):
            equip_name = None
            warnings.append(f"Row {row_number}: Missing equipment; retained {litres_val:g} L as unassigned.")
            
        equip_type = str(row.get("equipment_type", "")).strip().upper()
        if equip_type in ("NAN", "NONE"):
            equip_type = None

        # Normalize the operation type using the new helper
        op_type = _normalise_op_type(row["operation_type"])

        # Determine haulage classification
        if site == "IFCM":
            is_haulage = False 
        else:
            is_haulage = existing_cls.get(op_type, None)

            # Register unseen operation types automatically
            if is_haulage is None:
                is_haulage = op_type == "HAULAGE"
                new_op_types_dict[op_type] = {
                    "operation_type_raw": op_type,
                    "is_haulage": is_haulage,
                    "overridden_by_user": False
                }

        dispense_rows.append({
            "site": site,
            "dispensed_date": d_date,
            "equipment": equip_name,
            "equipment_type": equip_type,
            "operation_type": op_type,
            "litres": litres_val,
            "is_haulage": bool(is_haulage),
            "source_filename": getattr(file_bytes, "name", "upload")
        })

    # Equal dispensing amounts on the same day can be separate transactions.
    # Retain their multiplicity while giving repeat uploads a stable identity.
    occurrences = Counter()
    for record in dispense_rows:
        key = tuple(record[c] for c in
                    ("site", "dispensed_date", "equipment", "operation_type", "litres"))
        occurrences[key] += 1
        record["occurrence"] = occurrences[key]
    new_op_types = list(new_op_types_dict.values())
    return dispense_rows, [], new_op_types, warnings


# DieselStock activity codes mapped to the canonical operation names already
# used by the historical diesel table and dashboard.
DIESEL_ACTIVITY_CODE_MAP: dict[str, str] = {
    "OB": "OB OPERATION",
    "CM": "COAL MINING",
    "CL": "COAL LOADING",
    "CR": "CRUSHER PLANT",
    "RD": "CIVIL WORK",
    "PW": "POWER SUPPLY",
    "DW": "HIGHWALL DEWATERING",
    "HL": "HAULAGE",
    "WS": "MAINTENANCE",
    "ST": "STAFF TRANSPORT",
    "LC": "LOCAL MINERS COAL PURCHASE",
    "HW": "HIGHWALL MINING",
    "OT": "OTHER",
}


def _clean_optional_text(value, uppercase=False):
    if pd.isna(value) or not str(value).strip():
        return None
    cleaned = re.sub(r"\s+", " ", str(value).strip())
    return cleaned.upper() if uppercase else cleaned


def _dieselstock_site(frame):
    """Read the site value from the metadata rows above the dispensing header."""
    for _, row in frame.head(5).iterrows():
        values = list(row)
        for index, value in enumerate(values[:-1]):
            if str(value).strip().upper() == "SITE":
                site = _clean_optional_text(values[index + 1], uppercase=True)
                if site in {"TRCM", "IFCM"}:
                    return site
                raise ValueError(f"Unknown site in DieselStock workbook: {site!r}")
    raise ValueError("DieselStock workbook does not identify its site in the Dispensing log.")


def _dieselstock_activity(value):
    raw = _clean_optional_text(value)
    if raw is None:
        return None, None, "UNSPECIFIED"
    match = re.match(r"^([A-Z]{2})\s*(?:-|–|—)\s*(.+)$", raw, flags=re.I)
    code = match.group(1).upper() if match else raw.strip().upper()
    operation_type = DIESEL_ACTIVITY_CODE_MAP.get(code)
    if operation_type is None:
        raise ValueError(f"Unknown DieselStock activity code: {raw!r}")
    return raw, code, operation_type


def _dieselstock_time(value):
    if pd.isna(value) or value == "":
        return None
    parsed = pd.to_datetime(str(value), errors="coerce")
    if pd.isna(parsed):
        raise ValueError("Invalid time")
    return parsed.time().replace(microsecond=0)


def parse_diesel_excel_new(file_bytes: bytes, site: str | None = None):
    """Parse a DieselStock workbook's Dispensing log and Weekly summary.

    ``site`` is optional because the new template contains its own site field. If
    supplied (for example, from an upload-page selector), it is used as a safety
    check and must match the workbook. Returns ``(dispensing_rows, summary,
    warnings)``. Every dispensing row contains a ``site`` value.
    """
    selected_site = site.strip().upper() if site else None
    if selected_site and selected_site not in {"TRCM", "IFCM"}:
        raise ValueError(f"Unknown selected site: {selected_site}")

    try:
        with pd.ExcelFile(io.BytesIO(file_bytes)) as workbook:
            sheet_lookup = {name.strip().lower(): name for name in workbook.sheet_names}
            missing = [name for name in ("dispensing log", "weekly summary")
                       if name not in sheet_lookup]
            if missing:
                raise ValueError(
                    "DieselStock workbook is missing required sheet(s): "
                    + ", ".join(missing)
                )
            log_raw = pd.read_excel(
                workbook, sheet_name=sheet_lookup["dispensing log"], header=None
            )
            summary_raw = pd.read_excel(
                workbook, sheet_name=sheet_lookup["weekly summary"], header=None
            )
    except ValueError:
        raise
    except Exception as exc:
        raise ValueError(f"Could not read DieselStock workbook: {exc}") from exc

    workbook_site = _dieselstock_site(log_raw)
    if selected_site and workbook_site != selected_site:
        raise ValueError(
            f"Selected site {selected_site} does not match workbook site {workbook_site}."
        )

    header_idx = None
    expected_headers = {
        "date", "time", "asset_id", "class", "meter_type",
        "meter_reading_at_fill", "litres_dispensed", "activity_code",
    }
    for idx, row in log_raw.iterrows():
        headers = {_diesel_header(value) for value in row.dropna()}
        if expected_headers.issubset(headers):
            header_idx = idx
            break
    if header_idx is None:
        raise ValueError(
            "Could not find the DieselStock header row in 'Dispensing log'."
        )

    headers = [_diesel_header(value) for value in log_raw.iloc[header_idx].fillna("")]
    log = log_raw.iloc[header_idx + 1:].copy()
    log.columns = headers
    warnings = []
    rows = []
    occurrences = Counter()

    for dataframe_idx, row in log.iterrows():
        row_number = dataframe_idx + 1
        if pd.isna(row.get("litres_dispensed")):
            continue
        try:
            dispensed_date = _diesel_date(row.get("date"))
            dispensed_time = _dieselstock_time(row.get("time"))
            litres = _diesel_litres(row.get("litres_dispensed"))
            activity_code_raw, activity_code, operation_type = _dieselstock_activity(
                row.get("activity_code")
            )
        except ValueError as exc:
            warnings.append(f"Dispensing log row {row_number}: {exc}. Skipped.")
            continue
        if litres <= 0:
            continue

        asset_id = _clean_optional_text(row.get("asset_id"), uppercase=True)
        if asset_id is None:
            warnings.append(
                f"Dispensing log row {row_number}: Missing Asset ID; "
                f"retained {litres:g} L as unassigned."
            )
        meter_reading = row.get("meter_reading_at_fill")
        if pd.isna(meter_reading):
            meter_reading = None
        else:
            try:
                meter_reading = float(meter_reading)
            except (TypeError, ValueError):
                warnings.append(
                    f"Dispensing log row {row_number}: Invalid meter reading "
                    f"{meter_reading!r}; stored as blank."
                )
                meter_reading = None

        record = {
            "site": workbook_site,
            "dispensed_date": dispensed_date,
            "dispensed_time": dispensed_time,
            "asset_id": asset_id,
            "equipment_class": _clean_optional_text(row.get("class")),
            "meter_type": _clean_optional_text(row.get("meter_type")),
            "meter_reading": meter_reading,
            "litres": litres,
            "activity_code_raw": activity_code_raw,
            "activity_code": activity_code,
            "operation_type": operation_type,
            "is_haulage": operation_type == "HAULAGE",
            "operator_driver": _clean_optional_text(row.get("operator_/_driver")),
            "fuel_attendant": _clean_optional_text(row.get("fuel_attendant")),
            "supervisor_sign_off": _clean_optional_text(row.get("supervisor_sign-off")),
            "check_status": _clean_optional_text(row.get("check"), uppercase=True),
        }
        identity = tuple(record[key] for key in (
            "site", "dispensed_date", "dispensed_time", "asset_id",
            "activity_code", "litres",
        ))
        occurrences[identity] += 1
        record["occurrence"] = occurrences[identity]
        rows.append(record)

    summary = {
        "site": workbook_site,
        "activity_totals": {},
        "class_totals": {},
        "stock_check": {},
        "dispensing_log_total_litres": sum(row["litres"] for row in rows),
    }
    for _, row in summary_raw.iterrows():
        activity = _clean_optional_text(row.iloc[0] if len(row) > 0 else None)
        activity_litres = row.iloc[1] if len(row) > 1 else None
        equipment_class = _clean_optional_text(row.iloc[4] if len(row) > 4 else None)
        class_litres = row.iloc[5] if len(row) > 5 else None
        stock_label = _clean_optional_text(row.iloc[8] if len(row) > 8 else None)
        stock_value = row.iloc[9] if len(row) > 9 else None
        if (activity and isinstance(activity_litres, Real)
                and math.isfinite(float(activity_litres))):
            summary["activity_totals"][activity] = float(activity_litres)
        if (equipment_class and isinstance(class_litres, Real)
                and math.isfinite(float(class_litres))):
            summary["class_totals"][equipment_class] = float(class_litres)
        if (stock_label and isinstance(stock_value, Real)
                and math.isfinite(float(stock_value))):
            summary["stock_check"][stock_label] = float(stock_value)

    stated_total = summary["stock_check"].get("Dispensed per log (L)")
    if stated_total is not None and abs(stated_total - summary["dispensing_log_total_litres"]) > 0.01:
        warnings.append(
            "Weekly summary mismatch: 'Dispensed per log (L)' is "
            f"{stated_total:g} L, but parsed dispensing rows total "
            f"{summary['dispensing_log_total_litres']:g} L."
        )
    return rows, summary, warnings


