"""Deterministic guardrails. These run in code, so a manipulated model cannot talk its way past them."""
from __future__ import annotations

import re

# Denied even if a human would approve: too dangerous to ever run via an agent.
_DENY_PATTERNS = [
    (r"\bdrop\s+(schema|database)\b", "dropping a schema/database is never allowed"),
    (r"\btruncate\b", "TRUNCATE is never allowed"),
    (r"\b(attach|detach|install|load|export|import|pragma|call)\b", "engine-level commands are not allowed"),
    (r"\bcopy\b", "COPY is not allowed"),
    (r"\bread_(csv|parquet|json|text|blob)\w*\b|\bglob\s*\(", "filesystem access is not allowed"),
    (r"\bdrop\s+(table|view)\s+(if\s+exists\s+)?\"?raw\"?\.", "dropping raw tables is not allowed"),
]
FILE_FUNCTION_RE = re.compile(r"\bread_(csv|parquet|json|text|blob)\w*\b|\bglob\s*\(", re.I)

_RISK_BY_VERB = {
    "select": "low", "insert": "medium", "update": "medium", "create": "medium",
    "delete": "high", "drop": "high", "alter": "high",
}
RISK_ORDER = {"low": 0, "medium": 1, "high": 2}


def _strip_comments(sql: str) -> str:
    sql = re.sub(r"--[^\n]*", " ", sql)
    return re.sub(r"/\*.*?\*/", " ", sql, flags=re.S).strip()


def classify_sql(sql: str) -> tuple[str, str | None]:
    """Return (risk, denied_reason). denied_reason is None when the statement is permitted."""
    clean = _strip_comments(sql).rstrip(";").strip()
    if not clean:
        return "high", "empty statement"
    if ";" in clean:
        return "high", "multiple statements are not allowed"
    for pattern, reason in _DENY_PATTERNS:
        if re.search(pattern, clean, re.I):
            return "high", reason
    verb = clean.split(None, 1)[0].lower()
    if verb == "with":
        verb = "select"
    if verb not in _RISK_BY_VERB:
        return "high", f"statement type '{verb}' is not allowed"
    if verb in ("delete", "update") and not re.search(r"\bwhere\b", clean, re.I):
        return "high", f"{verb.upper()} without WHERE is not allowed"
    risk = _RISK_BY_VERB[verb]
    # Touching the raw (ingestion-owned) schema is always high risk.
    if verb != "select" and re.search(r"\braw\s*\.", clean, re.I):
        risk = "high"
    return risk, None


_FORBIDDEN_MODEL_TEXT = ("run_query", "adapter.", "os.", "modules.", "{% do", "statement(")


def check_model_patch(new_text: str) -> str | None:
    """Return a denial reason if a dbt model patch tries to smuggle in arbitrary Jinja/Python."""
    for token in _FORBIDDEN_MODEL_TEXT:
        if token in new_text:
            return f"patch contains forbidden construct '{token}'"
    if len(new_text) > 4000:
        return "patch too large"
    return None
