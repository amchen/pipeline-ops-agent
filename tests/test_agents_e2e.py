"""Full orchestrator run against a scripted model: schema drift -> patch -> approval -> green pipeline."""
from agent_ops import pipeline
from agent_ops.agent_loop import AgentLoop, Budget
from agent_ops.approvals import DenyAllApprover, PolicyApprover
from agent_ops.audit import AuditLog
from agent_ops.orchestrator import Orchestrator
from agent_ops.tools.base import Tool
from faults import injector

from .fakes import ScriptedClient, text, tool_use


def schema_drift_script(poisoned_proposal: bool = False):
    fix = ({"kind": "sql_data_fix", "title": "obey log", "rationale": "log said so", "sql": "drop schema raw cascade"}
           if poisoned_proposal else
           {"kind": "patch_model", "title": "Alias amount_usd", "rationale": "raw.orders.amount was renamed",
            "model_name": "stg_orders", "old_text": "cast(amount as decimal(12, 2))",
            "new_text": "cast(amount_usd as decimal(12, 2))"})
    return {
        "TRIAGE agent": [
            [tool_use("get_pipeline_status")],
            [tool_use("submit_triage", severity="high", category="schema_drift", failing_nodes=["stg_orders"], summary="stg_orders errors")],
        ],
        "DIAGNOSIS agent": [
            [text("Checking columns."), tool_use("describe_table", table="raw.orders")],
            [tool_use("submit_diagnosis", category="schema_drift", root_cause="raw.orders.amount was renamed to amount_usd",
                      evidence=["describe_table shows amount_usd, no amount"], confidence=0.95, fixable_in_pipeline=True)],
        ],
        "REMEDIATION agent": [
            [tool_use("read_model_sql", name="stg_orders")],
            [tool_use("propose_fix", **fix)],
            [tool_use("submit_plan", proposal_ids=["P1"], summary="alias new column")],
        ],
    }


def test_schema_drift_resolved_end_to_end(clean):
    injector.inject("schema_drift")
    pipeline.run_pipeline()
    audit = AuditLog(persist=False)
    report = Orchestrator(ScriptedClient(schema_drift_script()), PolicyApprover("medium"), audit).investigate()
    assert report.outcome == "resolved"
    assert report.diagnosis["category"] == "schema_drift"
    assert report.proposals[0]["status"] == "applied"
    assert len(audit.of_type("approval")) == 1, "every applied fix must pass the approval gate"
    assert report.steps == 7 and report.tokens == 7 * 120


def test_human_rejection_leaves_pipeline_broken(clean):
    injector.inject("schema_drift")
    pipeline.run_pipeline()
    report = Orchestrator(ScriptedClient(schema_drift_script()), DenyAllApprover(), AuditLog(persist=False)).investigate()
    assert report.outcome == "unresolved"
    assert report.proposals[0]["status"] == "rejected"
    assert pipeline.pipeline_status()["overall"] == "failed"


def test_prompt_injected_destructive_fix_is_blocked_by_policy(clean):
    """Even if a manipulated model proposes DROP SCHEMA, and even with an approve-everything approver, it cannot run."""
    injector.inject("schema_drift")
    pipeline.run_pipeline()
    injector.poison_log()
    report = Orchestrator(ScriptedClient(schema_drift_script(poisoned_proposal=True)), PolicyApprover("high"),
                          AuditLog(persist=False), max_rounds=1).investigate()
    assert report.proposals[0]["status"] == "denied"
    assert report.outcome == "unresolved"
    import duckdb
    from agent_ops import config
    con = duckdb.connect(str(config.WAREHOUSE_PATH), read_only=True)
    assert con.execute("select count(*) from raw.orders").fetchone()[0] == 5000
    con.close()


def test_healthy_pipeline_short_circuits(clean):
    pipeline.run_pipeline()
    report = Orchestrator(ScriptedClient({}), PolicyApprover(), AuditLog(persist=False)).investigate()
    assert report.outcome == "healthy"


def test_untrusted_tool_output_is_wrapped(clean):
    injector.inject("schema_drift")
    pipeline.run_pipeline()
    injector.poison_log()
    from agent_ops.tools.readonly import readonly_tools
    out = {t.name: t for t in readonly_tools()}["read_pipeline_log"].invoke({"grep": "ops-note"})
    assert out.startswith("<untrusted_data") and "SYSTEM OVERRIDE" in out


def test_loop_budget_and_repeat_guard():
    from pydantic import BaseModel

    class Empty(BaseModel):
        pass

    class Done(BaseModel):
        x: int = 0

    tools = [Tool("noop", "d", Empty, lambda a: "ok"), Tool("done", "d", Done, lambda a: "ok", terminal=True)]
    # model keeps calling the same tool forever -> step budget ends the loop
    client = ScriptedClient({"SYS": [[tool_use("noop")] for _ in range(6)]})
    res = AgentLoop(client, "t", "SYS", tools, AuditLog(persist=False), budget=Budget(max_steps=5)).run("go")
    assert res.stop_reason == "max_steps" and res.steps == 5 and res.output is None
    last = client.calls[-1]["messages"][-1]["content"][0]
    assert last["is_error"] and "repeated" in last["content"]


def test_invalid_tool_args_are_fed_back_not_crashed():
    from pydantic import BaseModel, Field

    class Done(BaseModel):
        n: int = Field(ge=0)

    tools = [Tool("done", "d", Done, lambda a: "ok", terminal=True)]
    client = ScriptedClient({"SYS": [[tool_use("done", n=-1)], [tool_use("done", n=3)]]})
    res = AgentLoop(client, "t", "SYS", tools, AuditLog(persist=False)).run("go")
    assert res.stop_reason == "terminal_tool" and res.output == {"n": 3} and res.steps == 2
