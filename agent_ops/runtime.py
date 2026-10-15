"""Proposal store and the (human-gated) executor for fixes.

Agents can only *propose* fixes. Applying a fix happens here, after the approval gate."""
from __future__ import annotations

import json
import re
import shutil
import time
from dataclasses import asdict, dataclass, field
from typing import Any, Literal

import duckdb

from . import config, pipeline
from .audit import AuditLog
from .policy import check_model_patch, classify_sql

FixKind = Literal["sql_data_fix", "patch_model", "rerun_pipeline", "escalate"]


@dataclass
class Proposal:
    id: str
    kind: FixKind
    title: str
    rationale: str
    risk: str
    denied_reason: str | None = None
    sql: str | None = None
    model_name: str | None = None
    old_text: str | None = None
    new_text: str | None = None
    escalation_summary: str | None = None
    status: str = "proposed"  # proposed | approved | rejected | applied | denied | failed
    result: Any = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class Runtime:
    audit: AuditLog
    proposals: dict[str, Proposal] = field(default_factory=dict)

    def new_proposal(self, **kwargs: Any) -> Proposal:
        pid = f"P{len(self.proposals) + 1}"
        kind = kwargs["kind"]
        risk, denied = "low", None
        if kind == "sql_data_fix":
            risk, denied = classify_sql(kwargs.get("sql") or "")
        elif kind == "patch_model":
            risk, denied = "medium", check_model_patch(kwargs.get("new_text") or "")
            if denied is None and self._find_model(kwargs.get("model_name") or "") is None:
                denied = f"unknown model '{kwargs.get('model_name')}'"
        prop = Proposal(id=pid, risk=risk, denied_reason=denied, status="denied" if denied else "proposed", **kwargs)
        self.proposals[pid] = prop
        self.audit.log("proposal", proposal=prop.to_dict())
        return prop

    # ---- execution (only called after approval) ----
    def apply(self, prop: Proposal) -> dict[str, Any]:
        if prop.denied_reason:
            raise PermissionError(f"Proposal {prop.id} is denied by policy: {prop.denied_reason}")
        try:
            if prop.kind == "sql_data_fix":
                result = self._apply_sql(prop)
            elif prop.kind == "patch_model":
                result = self._apply_patch(prop)
            elif prop.kind == "rerun_pipeline":
                result = {"pipeline": pipeline.run_pipeline()["overall"]}
            else:  # escalate
                result = self._escalate(prop)
            prop.status, prop.result = "applied", result
        except Exception as exc:  # noqa: BLE001 - recorded, then surfaced in the report
            prop.status, prop.result = "failed", str(exc)
            result = {"error": str(exc)}
        self.audit.log("apply", proposal_id=prop.id, status=prop.status, result=prop.result)
        return result

    def _apply_sql(self, prop: Proposal) -> dict[str, Any]:
        con = duckdb.connect(str(config.WAREHOUSE_PATH))
        try:
            con.execute(prop.sql)
            return {"executed": prop.sql}
        finally:
            con.close()

    def _find_model(self, name: str):
        for path in (config.PIPELINE_DIR / "models").rglob(f"{name}.sql"):
            return path
        return None

    def _apply_patch(self, prop: Proposal) -> dict[str, Any]:
        path = self._find_model(prop.model_name or "")
        if path is None:
            raise FileNotFoundError(prop.model_name)
        text = path.read_text()
        if text.count(prop.old_text or "") != 1:
            raise ValueError(f"old_text must match exactly once (found {text.count(prop.old_text or '')}).")
        backup_dir = config.RUNS_DIR / "backups"
        backup_dir.mkdir(parents=True, exist_ok=True)
        shutil.copy(path, backup_dir / f"{path.stem}.{int(time.time())}.sql.bak")
        path.write_text(text.replace(prop.old_text, prop.new_text))
        return {"patched": str(path.relative_to(config.PIPELINE_DIR))}

    def _escalate(self, prop: Proposal) -> dict[str, Any]:
        config.RUNS_DIR.mkdir(parents=True, exist_ok=True)
        record = {"ts": time.time(), "title": prop.title, "summary": prop.escalation_summary}
        with (config.RUNS_DIR / "escalations.jsonl").open("a") as fh:
            fh.write(json.dumps(record) + "\n")
        return {"escalated": True}
