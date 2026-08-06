#!/usr/bin/env python3
"""
Legacy seed script — summit catalogs are stored encrypted via store_encrypted_catalogs.py.

This script only ensures the schema exists. It no longer inserts ${ENV:...} placeholders.
"""
from pathlib import Path

from pg_connect import connect_pg

SCHEMA_PATH = Path(__file__).with_name("init-schema.sql")


def main() -> None:
    conn = connect_pg()
    conn.autocommit = True
    try:
        with conn.cursor() as cur:
            cur.execute(SCHEMA_PATH.read_text())
        print("  Hub database schema ready")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
