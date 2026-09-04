"""
db_setup.py
Creates database tables for Mosra Energy.
Reads DATABASE_URL from the environment or .streamlit/secrets.toml.
"""

import os
import sys
import psycopg2

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

# Secure credential routing
DATABASE_URL = os.environ.get("DATABASE_URL")

if not DATABASE_URL:
    try:
        import toml
        secrets = toml.load(os.path.join(".streamlit", "secrets.toml"))
        DATABASE_URL = secrets.get("DATABASE_URL") or secrets.get("postgres", {}).get("url")
    except Exception:
        pass

if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL environment variable or Streamlit secret is not set.")
    sys.exit(1)

DDL = """
-- ==========================================
-- 1. DIESEL MODULE
-- ==========================================
CREATE TABLE IF NOT EXISTS diesel_operation_classifications (
    operation_type_raw  TEXT PRIMARY KEY,
    is_haulage          BOOLEAN NOT NULL DEFAULT FALSE,
    overridden_by_user  BOOLEAN NOT NULL DEFAULT FALSE,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

CREATE TABLE IF NOT EXISTS weekly_diesel_usage (
    id              SERIAL PRIMARY KEY,
    site            VARCHAR(10) NOT NULL CHECK (site IN ('IFCM', 'TRCM')),
    dispensed_date  DATE NOT NULL,
    week_start_date DATE GENERATED ALWAYS AS (
        (dispensed_date - INTERVAL '1 day' * EXTRACT(DOW FROM dispensed_date)::integer)::date
    ) STORED,
    equipment_name  TEXT,
    equipment_type  TEXT,
    operation_type  TEXT,
    litres          NUMERIC(10,2) NOT NULL DEFAULT 0,
    is_haulage      BOOLEAN NOT NULL DEFAULT FALSE,
    source_filename VARCHAR(255),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- Safely add the unique constraint if it doesn't exist
DO $$ 
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'uq_diesel_row') THEN
        ALTER TABLE weekly_diesel_usage 
        ADD CONSTRAINT uq_diesel_row UNIQUE NULLS NOT DISTINCT (site, dispensed_date, equipment_name, operation_type, litres);
    END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_diesel_site_date ON weekly_diesel_usage (site, dispensed_date);
CREATE INDEX IF NOT EXISTS idx_diesel_week_start ON weekly_diesel_usage (site, week_start_date);

-- ==========================================
-- 2. COAL INVENTORY MODULE
-- ==========================================
CREATE TABLE IF NOT EXISTS weekly_coal_inventory (
    id                  SERIAL PRIMARY KEY,
    site                VARCHAR(10) NOT NULL CHECK (site IN ('IFCM', 'TRCM')),
    week_start_date     DATE NOT NULL,
    week_end_date       DATE NOT NULL,
    stock_ref           TEXT NOT NULL,
    stock_item          TEXT NOT NULL,
    uom                 TEXT NOT NULL DEFAULT 'Ton',
    
    opening_qty         NUMERIC(14,4) NOT NULL DEFAULT 0,
    stock_in_qty        NUMERIC(14,4) NOT NULL DEFAULT 0,
    stock_out_qty       NUMERIC(14,4) NOT NULL DEFAULT 0,
    stock_balance_qty   NUMERIC(14,4) NOT NULL DEFAULT 0,
    
    rate_ngn            NUMERIC(14,2) NOT NULL DEFAULT 0,
    
    opening_amount_ngn  NUMERIC(18,2) NOT NULL DEFAULT 0,
    stock_in_amount_ngn NUMERIC(18,2) NOT NULL DEFAULT 0,
    stock_out_amount_ngn NUMERIC(18,2) NOT NULL DEFAULT 0,
    balance_amount_ngn  NUMERIC(18,2) NOT NULL DEFAULT 0,
    
    created_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT NOW(),

    -- Enforce Sunday start (EXTRACT DOW returns 0 for Sunday)
    CONSTRAINT chk_week_start_is_sunday CHECK (EXTRACT(DOW FROM week_start_date) = 0),
    
    -- Enforce exactly 6 days length (Sunday to Saturday)
    CONSTRAINT chk_week_end_is_saturday CHECK (week_end_date = week_start_date + INTERVAL '6 days'),

    -- Prevent duplicate weekly submissions for the same site and item
    CONSTRAINT uq_site_week_item UNIQUE (site, week_start_date, stock_ref)
);

-- ==========================================
-- 3. MANUAL METRICS MODULE (Sourcing, Excavation, Dispatch)
-- ==========================================
CREATE TABLE IF NOT EXISTS weekly_manual_metrics (
    id                            SERIAL PRIMARY KEY,
    site                          VARCHAR(10) NOT NULL CHECK (site IN ('IFCM', 'TRCM')),
    week_start_date               DATE NOT NULL,
    week_end_date                 DATE NOT NULL,
    
    coal_from_local_miners_mt     NUMERIC(15, 4) DEFAULT 0.0,
    coal_from_manejo_mt           NUMERIC(15, 4) DEFAULT 0.0,
    coal_from_ifcm_mt             NUMERIC(15, 4) DEFAULT 0.0,
    coal_from_ogboyaga_mt         NUMERIC(15, 4) DEFAULT 0.0,
    coal_from_high_wall_mining_mt NUMERIC(15, 4) DEFAULT 0.0,
    coal_mined_mt                 NUMERIC(15, 4) DEFAULT 0.0,
    
    bcm_excavated_bcm             NUMERIC(15, 4) DEFAULT 0.0,
    total_coal_stocked_mt         NUMERIC(15, 4) DEFAULT 0.0,
    coal_dispatched_mt            NUMERIC(15, 4) DEFAULT 0.0,
    
    notes                         TEXT,
    
    created_at                    TIMESTAMPTZ DEFAULT NOW(),
    updated_at                    TIMESTAMPTZ DEFAULT NOW(),

    -- Date constraints
    CONSTRAINT chk_manual_week_start_is_sunday CHECK (EXTRACT(DOW FROM week_start_date) = 0),
    CONSTRAINT chk_manual_week_end_is_saturday CHECK (week_end_date = week_start_date + INTERVAL '6 days'),
    
    -- Ensure one record per site per week
    CONSTRAINT uq_site_manual_week UNIQUE (site, week_start_date)
);
"""

def setup():
    print("Connecting to database…")
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.autocommit = True
        with conn.cursor() as cur:
            cur.execute(DDL)
        conn.close()
        print("✅ Database updated successfully (Diesel, Coal Inventory, and Manual Metrics tables active).")
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    setup()