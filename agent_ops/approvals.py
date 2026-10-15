"""The human-in-the-loop gate. Every state-changing proposal passes through an Approver."""
from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .policy import RISK_ORDER
from .runtime import Proposal


@dataclass
class Decision:
    approved: bool
    reason: str
    approver: str


class Approver(Protocol):
    def decide(self, proposal: Proposal) -> Decision: ...


def describe(p: Proposal) -> str:
    lines = [f"[{p.id}] {p.kind.upper()}  risk={p.risk.upper()}", f"  title:     {p.title}", f"  rationale: {p.rationale}"]
    if p.sql:
        lines.append(f"  sql:       {p.sql}")
    if p.kind == "patch_model":
        lines += [f"  model:     {p.model_name}", f"  - {p.old_text}", f"  + {p.new_text}"]
    if p.escalation_summary:
        lines.append(f"  escalation: {p.escalation_summary}")
    return "\n".join(lines)


class CLIApprover:
    """Interactive: a human reads the proposal and types y/N."""

    def decide(self, proposal: Proposal) -> Decision:
        print("\n" + "=" * 70 + "\nAPPROVAL REQUIRED\n" + describe(proposal))
        answer = input("Approve? [y/N] ").strip().lower()
        ok = answer in ("y", "yes")
        return Decision(ok, "human approved" if ok else "human rejected", "cli-human")


class DenyAllApprover:
    def decide(self, proposal: Proposal) -> Decision:
        return Decision(False, "deny-all approver", "deny-all")


class PolicyApprover:
    """Non-interactive approver for evals/CI: approves up to `max_risk`. Stands in for a human."""

    def __init__(self, max_risk: str = "medium"):
        self.max_risk = max_risk

    def decide(self, proposal: Proposal) -> Decision:
        ok = RISK_ORDER[proposal.risk] <= RISK_ORDER[self.max_risk]
        return Decision(ok, f"auto-policy (max_risk={self.max_risk})", "policy-approver")
