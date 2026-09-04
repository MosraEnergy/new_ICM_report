"""
utils/db.py
Thread-safe database connection pool & query helpers for Streamlit.
"""

import streamlit as st
import psycopg2
import psycopg2.extras
from psycopg2 import pool
from contextlib import contextmanager
import os
import numpy as np
from psycopg2.extensions import register_adapter, AsIs

# Explicitly register numpy types for psycopg2 compatibility (NumPy 2.0+ safe)
register_adapter(np.int64, AsIs)
register_adapter(np.int32, AsIs)
register_adapter(np.float64, AsIs)
register_adapter(np.float32, AsIs)
register_adapter(np.bool_, lambda val: AsIs('true' if val else 'false'))

@st.cache_resource
def get_connection_pool():
    """
    Creates a thread-safe connection pool. 
    Cached by Streamlit so it persists across reruns.
    """
    if "DATABASE_URL" in st.secrets:
        url = st.secrets["DATABASE_URL"]
    elif "postgres" in st.secrets and "url" in st.secrets["postgres"]:
        url = st.secrets["postgres"]["url"]
    else:
        url = os.environ.get("DATABASE_URL")
        
    if not url:
        raise ValueError("Database URL not found in st.secrets or environment variables.")
        
    return psycopg2.pool.ThreadedConnectionPool(
        minconn=1,
        maxconn=20,
        dsn=url
    )

@contextmanager
def transaction():
    """
    Context manager to check out a connection from the pool,
    yield it for use, and automatically commit/rollback.
    """
    db_pool = get_connection_pool()
    conn = db_pool.getconn()
    conn.cursor_factory = psycopg2.extras.RealDictCursor
    conn.autocommit = False
    
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        db_pool.putconn(conn)

def fetch_all(query: str, params=None) -> list[dict]:
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return [dict(r) for r in cur.fetchall()]

def fetch_one(query: str, params=None) -> dict | None:
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            row = cur.fetchone()
            return dict(row) if row else None

def execute_query(query: str, params=None, fetch=False, commit=False):
    """Legacy support wrapper. Prefer transaction() for complex operations."""
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            if fetch:
                return [dict(r) for r in cur.fetchall()]

def execute(query: str, params=None) -> int:
    """Executes a single query and returns the row count."""
    with transaction() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            return cur.rowcount

def execute_many(query: str, params_list: list) -> int:
    """Executes a batch of queries for bulk inserts/updates."""
    with transaction() as conn:
        with conn.cursor() as cur:
            psycopg2.extras.execute_batch(cur, query, params_list, page_size=500)
            return cur.rowcount