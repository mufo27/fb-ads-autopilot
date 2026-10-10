"""Thin Postgres helper (psycopg3)"""
import psycopg
from .config import get_settings


def conn():
    return psycopg.connect(get_settings().DATABASE_URL, autocommit=True)


def query(sql, params=None):
    with conn() as c:
        with c.cursor() as cur:
            cur.execute(sql, params or ())
            cols = [d.name for d in cur.description] if cur.description else []
            return [dict(zip(cols, r)) for r in cur.fetchall()]


def execute(sql, params=None):
    with conn() as c:
        with c.cursor() as cur:
            cur.execute(sql, params or ())
            return cur.rowcount
