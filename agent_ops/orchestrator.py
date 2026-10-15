"""Triage -> diagnosis -> remediation -> human-gated execution -> verification."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

from . import pipeline
from .agent_loop import AgentResult, Budget
from .agents import build_diagnosis, build_remediation, build_triage
from .approvals import Approver, describe
from .audit import AuditLog
from .runtime import Runtime


@dataclass
class IncidentReport:
    outcome: str  # healthy | resolved | escalated | unresolved
    triage: dict[str, Any] | None = None
    diagnosis: dict[str, Any] | None = None
    proposals: list[dict[str, Any]] = field(default_factory=list)
    decisions: list[dict[str, Any]] = field(default_factory=list)
    final_status: dict[str, Any] | None = None
    agent_results: list[AgentResult] = field(default_factory=list)

    @property
    def steps(self) -> int:
        return sum(r.steps for r in self.agent_results)

    @property
    def tokens(self) -> int:
        return sum(r.total_tokens for r in self.agent_results)

    def summary(self) -> str:
        d = self.diagnosis or {}
        lines = [f"Outcome: {self.outcome.upper()}", f"Category: {d.get('category')}", f"Root cause: {d.get('root_cause')}"]
        for p in self.proposals:
            lines.append(f"  - {p['id']} {p['kind']} [{p['risk']}] -> {p['status']}: {p['title']}")
        lines.append(f"Steps: {self.steps}  Tokens: {self.tokens}")
        return "\n".join(lines)


class Orchestrator:
    def __init__(self, client: Any, approver: Approver, audit: AuditLog | None = None,
                 model: str | None = None, budget: Budget | None = None, max_rounds: int = 2):
        self.client, self.approver, self.model, self.budget = client, approver, model, budget
        self.audit = audit or AuditLog()
        self.max_rounds = max_rounds

    def investigate(self) -> IncidentReport:
        status = pipeline.pipeline_status()
        if status["overall"] == "success":
            return IncidentReport(outcome="healthy", final_status=status)

        rt = Runtime(self.audit)
        report = IncidentReport(outcome="unresolved", final_status=status)
        escalated = False
        context = ""

        for round_no in range(1, self.max_rounds + 1):
            self.audit.log("round_start", round=round_no)
            status_note = f"Pipeline status:\n{json.dumps({k: status[k] for k in ('overall', 'failed_nodes', 'skipped_nodes')}, default=str)}"

            triage = build_triage(self.client, self.audit, self.model, self.budget).run(f"{status_note}\n{context}\nTriage this failure.")
            report.agent_results.append(triage)
            report.triage = triage.output

            diag = build_diagnosis(self.client, self.audit, self.model, self.budget).run(
                f"{status_note}\nTriage result: {json.dumps(triage.output)}\n{context}\nFind the root cause.")
            report.agent_results.append(diag)
            report.diagnosis = diag.output
            if diag.output is None:
                break

            before = set(rt.proposals)
            rem = build_remediation(self.client, rt, self.model, self.budget).run(
                f"Diagnosis: {json.dumps(diag.output)}\n{context}\nPropose and submit a fix plan.")
            report.agent_results.append(rem)
            plan_ids = (rem.output or {}).get("proposal_ids") or [p for p in rt.proposals if p not in before]

            applied_fix = False
            for pid in plan_ids:
                prop = rt.proposals.get(pid)
                if prop is None or prop.status in ("denied", "applied"):
                    continue
                decision = self.approver.decide(prop)
                self.audit.log("approval", proposal_id=pid, approved=decision.approved, reason=decision.reason, approver=decision.approver)
                report.decisions.append({"proposal_id": pid, **decision.__dict__})
                if not decision.approved:
                    prop.status = "rejected"
                    continue
                prop.status = "approved"
                rt.apply(prop)
                if prop.status == "applied":
                    if prop.kind == "escalate":
                        escalated = True
                    else:
                        applied_fix = True

            if applied_fix:
                status = pipeline.run_pipeline()
                report.final_status = status
                if status["overall"] == "success":
                    break
                context = f"Previous fix attempt did not resolve the failure. Applied: {[p.to_dict() for p in rt.proposals.values() if p.status == 'applied']}"
            else:
                break

        report.proposals = [p.to_dict() for p in rt.proposals.values()]
        if report.final_status and report.final_status["overall"] == "success":
            report.outcome = "resolved"
        elif escalated:
            report.outcome = "escalated"
        self.audit.log("incident_done", outcome=report.outcome, steps=report.steps, tokens=report.tokens)
        return report


def print_proposal(p: dict[str, Any]) -> None:  # convenience for the CLI
    from .runtime import Proposal

    print(describe(Proposal(**{k: v for k, v in p.items() if k in Proposal.__dataclass_fields__})))
