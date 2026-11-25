"""Clean the messy CSVs in seeds/raw and load them into DuckDB (schema: raw)."""

from __future__ import annotations

import os
from pathlib import Path

import duckdb
from dotenv import load_dotenv

load_dotenv()

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "seeds" / "raw"
DB_PATH = Path(os.getenv("DBT_DUCKDB_PATH", ROOT / "duckdb" / "lab.duckdb"))


def _csv(path: Path) -> str:
    """Return a safely quoted path for use inside a DuckDB SQL string."""
    return path.as_posix().replace("'", "''")


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(str(DB_PATH))
    try:
        con.execute("CREATE SCHEMA IF NOT EXISTS raw")

        con.execute(f"""
            CREATE OR REPLACE TABLE raw.orders AS
            SELECT DISTINCT
                CAST(trim(order_id) AS BIGINT)     AS order_id,
                CAST(trim(customer_id) AS BIGINT)  AS customer_id,
                CAST(trim(order_date) AS DATE)     AS order_date,
                CAST(
                    replace(replace(trim(amount), '$', ''), ',', '') AS DECIMAL(12, 2)
                )                                  AS amount_usd,
                lower(trim(status))                AS status
            FROM read_csv_auto('{_csv(RAW_DIR / "orders.csv")}',
                               header = true, all_varchar = true)
            WHERE trim(order_id) <> '' AND trim(customer_id) <> ''
        """)

        con.execute(f"""
            CREATE OR REPLACE TABLE raw.customers AS
            SELECT DISTINCT
                CAST(trim(customer_id) AS BIGINT) AS customer_id,
                trim(name)                        AS customer_name,
                upper(trim(country_code))         AS country_code,
                CAST(trim(signup_date) AS DATE)   AS signup_date
            FROM read_csv_auto('{_csv(RAW_DIR / "customers.csv")}',
                               header = true, all_varchar = true)
            WHERE trim(customer_id) <> ''
        """)

        for table in ("orders", "customers"):
            count = con.execute(f"select count(*) from raw.{table}").fetchone()[0]
            print(f"raw.{table}: {count} rows")
    finally:
        con.close()


if __name__ == "__main__":
    main()
