"""
utils/parsers.py
Data extraction and cleaning helpers for Mosra Energy Excel/CSV uploads.
"""

import pandas as pd
import re
import io

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
    if pd.isna(raw) or raw in ("NAN", "NONE", ""):
        return "UNSPECIFIED"
    
    # 1. Strip whitespace, collapse extra inner spaces, uppercase
    cleaned = re.sub(r'\s+', ' ', str(raw).strip().upper())
    
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

def parse_diesel_excel(file_bytes: bytes, site: str, existing_cls: dict[str, bool]):
    """
    Parses daily diesel dispensing logs (Excel/CSV).
    Handles messy headers, merged date cells, numeric string cleaning,
    and returns clean dictionary records ready for database transactions.
    """
    file_stream = io.BytesIO(file_bytes)
    
    # 1. Read file exactly ONCE into memory without fixed headers
    try:
        df_raw = pd.read_excel(file_stream, engine="openpyxl", header=None)
    except Exception:
        file_stream.seek(0)
        df_raw = pd.read_csv(file_stream, header=None)

    # 2. Dynamically locate the true header row
    header_idx = None
    for i, row in df_raw.iterrows():
        row_str = " ".join([str(x).upper() for x in row.dropna()])
        if "DATE" in row_str and "EQUIPMENT" in row_str:
            header_idx = i
            break
            
    if header_idx is None:
        header_idx = 1 if df_raw.iloc[0].isna().all() else 0

    # 3. Extract column names and slice the DataFrame directly in memory
    raw_headers = df_raw.iloc[header_idx].fillna("").astype(str).tolist()
    df = df_raw.iloc[header_idx + 1:].copy().reset_index(drop=True)
    df.columns = raw_headers

    # 4. Standardize Column Headers
    df.columns = [str(c).strip().lower().replace(" ", "_").replace("\n", "_") for c in df.columns]

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
        "qty": "litres"
    }
    
    df = df.rename(columns=lambda x: col_mapping.get(x, x))

    warnings = []
    required_cols = ["dispensed_date", "equipment_name", "operation_type", "litres"]
    missing_cols = [c for c in required_cols if c not in df.columns]
    
    if missing_cols:
        raise ValueError(
            f"Missing required columns in file: {missing_cols}. Found: {list(df.columns)}"
        )

    # 5. Forward-fill dates to capture rows beneath Excel merged cells
    df["dispensed_date"] = df["dispensed_date"].ffill()
    df = df.dropna(subset=["litres"])

    dispense_rows = []
    new_op_types_dict = {}

    # 6. Row-by-row cleaning and type conversions
    for idx, row in df.iterrows():
        try:
            d_date = pd.to_datetime(row["dispensed_date"], dayfirst=True).date()
        except Exception:
            warnings.append(f"Row {idx+2}: Invalid date format '{row['dispensed_date']}'. Skipped.")
            continue

        raw_litres = str(row["litres"])
        clean_litres_str = re.sub(r"[^\d.]", "", raw_litres)
        try:
            litres_val = float(clean_litres_str)
            if litres_val <= 0:
                continue
        except ValueError:
            warnings.append(f"Row {idx+2}: Invalid litres value '{raw_litres}'. Skipped.")
            continue

        equip_name = str(row["equipment_name"]).strip().upper()
        if equip_name in ("NAN", "", "NONE"):
            continue
            
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
                is_haulage = False 
                new_op_types_dict[op_type] = {
                    "operation_type_raw": op_type,
                    "is_haulage": False,
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

    new_op_types = list(new_op_types_dict.values())
    return dispense_rows, [], new_op_types, warnings