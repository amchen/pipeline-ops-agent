import json

import pytest

from agent_ops.tools.base import ToolError
from agent_ops.tools.readonly import readonly_tools

T = {t.name: t for t in readonly_tools()}


def call(tool_name, /, **kw):
    return T[tool_name].invoke(kw)


def test_sql_select_ok(clean):
    out = call("run_readonly_sql", query="select count(*) as n from raw.orders")
    assert "5000" in out and "<untrusted_data" in out


@pytest.mark.parametrize("q", [
    "delete from raw.orders where order_id = 1",
    "drop table raw.orders",
    "select 1; select 2",
    "select * from read_csv('/etc/passwd')",
])
def test_sql_rejects_writes_and_files(clean, q):
    with pytest.raises(ToolError):
        call("run_readonly_sql", query=q)


def test_readonly_connection_really_cannot_write(clean):
    # Even if validation were bypassed, the connection itself is read-only.
    from agent_ops.tools.readonly import _ro_conn
    import duckdb

    con = _ro_conn()
    with pytest.raises(duckdb.Error):
        con.execute("delete from raw.orders")
    con.close()


def test_describe_and_list(clean):
    d = json.loads(call("describe_table", table="raw.orders"))
    assert d["row_count"] == 5000
    assert {"order_id", "customer_id", "order_ts", "amount", "status"} <= {c["name"] for c in d["columns"]}
    assert any(t["table"] == "orders" for t in json.loads(call("list_tables", schema_name="raw")))
    with pytest.raises(ToolError):
        call("describe_table", table="raw.nope")


def test_schema_validation_errors_are_model_readable():
    with pytest.raises(ToolError, match="Invalid arguments"):
        call("describe_table", table="raw.orders; drop table x")


def test_runbook_search_and_model_read(clean):
    assert "schema_drift" in call("search_runbooks", query="column renamed schema drift binder error")
    assert "amount" in call("read_model_sql", name="stg_orders")
    with pytest.raises(ToolError):
        call("read_model_sql", name="../../etc/passwd")


def test_least_privilege_toolsets():
    from agent_ops.agents import build_diagnosis, build_remediation, build_triage
    from agent_ops.audit import AuditLog
    from agent_ops.runtime import Runtime

    audit = AuditLog(persist=False)
    triage = set(build_triage(None, audit).tools)
    diag = set(build_diagnosis(None, audit).tools)
    rem = set(build_remediation(None, Runtime(audit)).tools)
    assert "propose_fix" not in triage | diag
    assert "run_readonly_sql" not in triage
    assert not any(n.startswith("apply") for n in triage | diag | rem), "no agent may apply fixes"
