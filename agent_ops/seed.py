"""Synthetic warehouse: raw.customers, raw.orders, raw.pipeline_meta (deterministic)."""
from __future__ import annotations

from pathlib import Path

import duckdb

from . import config


def create_warehouse(path: Path | None = None, n_customers: int = 500, n_orders: int = 5000) -> Path:
    path = Path(path or config.WAREHOUSE_PATH)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        path.unlink()
    con = duckdb.connect(str(path))
    try:
        con.execute("create schema raw")
        con.execute(
            f"""
            create table raw.customers as
            select
                i as customer_id,
                'Customer ' || i as name,
                (['NA', 'EMEA', 'APAC', 'LATAM'])[1 + (i % 4)] as region,
                date '2025-01-01' + cast(i % 400 as integer) as signup_date
            from range(1, {n_customers + 1}) as t(i)
            """
        )
        con.execute(
            f"""
            create table raw.orders as
            select
                i as order_id,
                cast(1 + (hash(i) % {n_customers}) as integer) as customer_id,
                timestamp '{config.AS_OF}'
                    - to_minutes(cast(1 + (hash(i * 7) % 43200) as bigint)) as order_ts,
                round(5 + (hash(i * 13) % 49500) / 100.0, 2) as amount,
                (['completed', 'completed', 'completed', 'refunded', 'pending'])
                    [1 + cast(hash(i * 3) % 5 as integer)] as status
            from range(1, {n_orders + 1}) as t(i)
            """
        )
        con.execute(f"create table raw.pipeline_meta as select timestamp '{config.AS_OF}' as as_of")
    finally:
        con.close()
    return path
