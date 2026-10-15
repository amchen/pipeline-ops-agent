import pytest

from agent_ops.policy import check_model_patch, classify_sql


@pytest.mark.parametrize("sql,risk", [
    ("select 1", "low"),
    ("with x as (select 1) select * from x", "low"),
    ("update staging.t set a = 1 where id = 2", "medium"),
    ("delete from some.t where id = 1", "high"),
    ("update raw.orders set amount = 1 where order_id = 1", "high"),  # raw is ingestion-owned
])
def test_permitted(sql, risk):
    r, denied = classify_sql(sql)
    assert denied is None and r == risk


@pytest.mark.parametrize("sql", [
    "drop schema raw cascade",
    "DROP   SCHEMA raw",
    "truncate raw.orders",
    "delete from raw.orders",                      # no WHERE
    "update raw.orders set amount = 0",            # no WHERE
    "select 1; drop table raw.orders",             # multi-statement
    "select * from read_csv('/etc/passwd')",
    "copy raw.orders to '/tmp/x.csv'",
    "attach '/tmp/other.db'",
    "drop table raw.orders",
    "/* sneaky */ drop schema raw",
    "grant all on raw.orders to public",           # unknown verb
])
def test_denied(sql):
    _, denied = classify_sql(sql)
    assert denied


def test_model_patch_guard():
    assert check_model_patch("select 1") is None
    assert check_model_patch("{{ run_query('drop schema raw') }}")
