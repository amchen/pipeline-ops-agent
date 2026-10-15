"""Thin wrapper around the dbt project: run it, parse its results, read its logs."""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

from . import config


def _paths() -> tuple[Path, Path, Path]:
    pdir = config.PIPELINE_DIR
    return (
        pdir / "target" / "run_results.json",
        pdir / "logs" / "last_run.log",
        pdir / "logs" / "last_run_meta.json",
    )


def run_pipeline(timeout: int = 300) -> dict[str, Any]:
    """Run `dbt build` (models + tests) and return the parsed status."""
    results_path, log_path, meta_path = _paths()
    log_path.parent.mkdir(parents=True, exist_ok=True)
    results_path.unlink(missing_ok=True)  # never read stale results

    env = {
        **os.environ,
        "WAREHOUSE_PATH": str(config.WAREHOUSE_PATH),
        "DBT_SEND_ANONYMOUS_USAGE_STATS": "false",
    }
    cmd = [
        sys.executable, "-m", "dbt.cli.main", "build",
        "--project-dir", str(config.PIPELINE_DIR),
        "--profiles-dir", str(config.PIPELINE_DIR),
        "--no-use-colors",
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=timeout)
    log_path.write_text(proc.stdout + ("\n" + proc.stderr if proc.stderr.strip() else ""))
    meta_path.write_text(json.dumps({"exit_code": proc.returncode}))
    return pipeline_status()


def pipeline_status() -> dict[str, Any]:
    """Summarise the most recent run from dbt's run_results.json."""
    results_path, _, meta_path = _paths()
    exit_code = None
    if meta_path.exists():
        exit_code = json.loads(meta_path.read_text()).get("exit_code")

    if not results_path.exists():
        return {
            "overall": "unknown" if exit_code is None else "failed",
            "exit_code": exit_code,
            "note": "No run_results.json: dbt may have failed before running any node. Read the log.",
            "nodes": [], "failed_nodes": [], "skipped_nodes": [],
        }

    data = json.loads(results_path.read_text())
    nodes = [
        {
            "node": r["unique_id"].split(".", 2)[-1] if r["unique_id"].count(".") >= 2 else r["unique_id"],
            "kind": r["unique_id"].split(".")[0],
            "status": r["status"],
            "message": (r.get("message") or "")[:300],
            "failures": r.get("failures"),
        }
        for r in data.get("results", [])
    ]
    failed = [n for n in nodes if n["status"] in ("error", "fail")]
    skipped = [n["node"] for n in nodes if n["status"] == "skipped"]
    overall = "success" if exit_code == 0 and not failed and not skipped else "failed"
    return {
        "overall": overall,
        "exit_code": exit_code,
        "counts": {s: sum(1 for n in nodes if n["status"] == s) for s in sorted({n["status"] for n in nodes})},
        "failed_nodes": failed,
        "skipped_nodes": skipped,
        "nodes": nodes,
    }


def read_log(tail_lines: int = 80, grep: str | None = None) -> str:
    _, log_path, _ = _paths()
    if not log_path.exists():
        return "(no log yet)"
    lines = log_path.read_text().splitlines()
    if grep:
        lines = [ln for ln in lines if grep.lower() in ln.lower()]
    return "\n".join(lines[-tail_lines:]) or "(no matching lines)"
