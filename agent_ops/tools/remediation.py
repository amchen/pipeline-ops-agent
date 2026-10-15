"""Tools for the remediation agent: propose fixes (no side effects) and finish with a plan."""
from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator

from ..runtime import Runtime
from .base import Tool


class ProposeFixArgs(BaseModel):
    kind: Literal["sql_data_fix", "patch_model", "rerun_pipeline", "escalate"]
    title: str = Field(max_length=120)
    rationale: str = Field(max_length=800, description="Why this fix addresses the diagnosed root cause.")
    sql: str | None = Field(None, max_length=2000, description="sql_data_fix only: ONE statement.")
    model_name: str | None = Field(None, description="patch_model only: dbt model name, e.g. 'stg_orders'.")
    old_text: str | None = Field(None, max_length=2000, description="patch_model only: exact text to replace (must occur once).")
    new_text: str | None = Field(None, max_length=2000, description="patch_model only: replacement text.")
    escalation_summary: str | None = Field(None, max_length=1500, description="escalate only: evidence for the owner.")

    @model_validator(mode="after")
    def _kind_fields(self) -> "ProposeFixArgs":
        need = {
            "sql_data_fix": ["sql"],
            "patch_model": ["model_name", "old_text", "new_text"],
            "escalate": ["escalation_summary"],
            "rerun_pipeline": [],
        }[self.kind]
        missing = [f for f in need if not getattr(self, f)]
        if missing:
            raise ValueError(f"kind={self.kind} requires: {', '.join(missing)}")
        return self


class SubmitPlanArgs(BaseModel):
    proposal_ids: list[str] = Field(min_length=1, description="Proposal ids to execute, in order.")
    summary: str = Field(max_length=800)


def remediation_tools(rt: Runtime) -> list[Tool]:
    def propose(a: ProposeFixArgs):
        prop = rt.new_proposal(**a.model_dump())
        out = {"proposal_id": prop.id, "risk": prop.risk, "status": prop.status}
        if prop.denied_reason:
            out["denied_reason"] = prop.denied_reason
            out["hint"] = "This proposal cannot run. Propose a safer alternative or escalate."
        return out

    def submit(a: SubmitPlanArgs):
        unknown = [p for p in a.proposal_ids if p not in rt.proposals]
        if unknown:
            from .base import ToolError

            raise ToolError(f"Unknown proposal ids: {unknown}")
        return {"accepted": True}

    return [
        Tool("propose_fix", "Record a fix proposal. Nothing is executed; a human approval gate decides later.", ProposeFixArgs, propose, writes=False),
        Tool("submit_plan", "Finish: submit the ordered proposal ids to be reviewed and executed.", SubmitPlanArgs, submit, terminal=True),
    ]
