from __future__ import annotations

import duckdb

import process_seeds


def test_process_seeds_creates_clean_tables(tmp_path, monkeypatch) -> None:
    raw = tmp_path / "raw"
    raw.mkdir()
    (raw / "orders.csv").write_text(
        "order_id,customer_id,order_date,amount,status\n"
        '1,10,2026-01-01,"$10.50", COMPLETED \n'
        '1,10,2026-01-01,"$10.50", COMPLETED \n'
    )
    (raw / "customers.csv").write_text(
        "customer_id,name,country_code,signup_date\n10, Alice ,us,2025-12-01\n"
    )
    db = tmp_path / "test.duckdb"

    monkeypatch.setattr(process_seeds, "RAW_DIR", raw)
    monkeypatch.setattr(process_seeds, "DB_PATH", db)
    process_seeds.main()

    con = duckdb.connect(str(db), read_only=True)
    try:
        assert con.execute(
            "select order_id, amount_usd, status from raw.orders"
        ).fetchall() == [(1, 10.50, "completed")]
        assert con.execute("select country_code from raw.customers").fetchall() == [
            ("US",)
        ]
    finally:
        con.close()
