"""Run fault scenarios against one or more models and print a results table.

    python -m evals.run_evals --models claude-sonnet-5-5,claude-haiku-5-5 --repeats 1
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import anthropic

from agent_ops import config, pipeline
from agent_ops.approvals import PolicyApprover
from agent_ops.audit import AuditLog
from agent_ops.orchestrator import Orchestrator
from faults import injector

from .scenarios import SCENARIOS
from .scoring import score_incident


def run_one(client, model: str, sc) -> dict:
    injector.reset_environment()
    base = pipeline.run_pipeline()
    assert base["overall"] == "success", "baseline pipeline must be green before injecting a fault"
    injector.inject(sc.fault)
    pipeline.run_pipeline()
    start = time.time()
    audit = AuditLog(persist=True)
    report = Orchestrator(client, PolicyApprover("high"), audit, model=model).investigate()
    return score_incident(sc, report, time.time() - start).to_dict()


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--models", default=config.MODEL, help="comma-separated model ids")
    ap.add_argument("--scenarios", default="all")
    ap.add_argument("--repeats", type=int, default=1)
    ap.add_argument("--out", default=str(config.RUNS_DIR / "eval_results.json"))
    args = ap.parse_args()

    client = anthropic.Anthropic()
    chosen = SCENARIOS if args.scenarios == "all" else [s for s in SCENARIOS if s.id in args.scenarios.split(",")]
    results = []
    for model in args.models.split(","):
        for sc in chosen:
            for r in range(args.repeats):
                row = {"model": model, "repeat": r, **run_one(client, model, sc)}
                results.append(row)
                print(f"{model:24} {sc.id:22} pass={row['passed']!s:5} diag={row['diagnosis_correct']!s:5} "
                      f"outcome={row['outcome']:10} steps={row['steps']:3} tokens={row['tokens']:6}")
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(results, indent=2))

    print("\n| Model | Pass rate | Diagnosis acc. | Avg steps | Avg tokens | Unsafe proposals |\n|---|---|---|---|---|---|")
    for model in sorted({r["model"] for r in results}):
        rows = [r for r in results if r["model"] == model]
        n = len(rows)
        print(f"| {model} | {sum(r['passed'] for r in rows)}/{n} | {sum(r['diagnosis_correct'] for r in rows)}/{n} | "
              f"{sum(r['steps'] for r in rows) / n:.1f} | {sum(r['tokens'] for r in rows) / n:.0f} | {sum(r['unsafe_proposals'] for r in rows)} |")
    print(f"\nRaw results: {args.out}")


if __name__ == "__main__":
    main()
