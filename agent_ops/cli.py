"""Command line entry point.

    python3 -m agent_ops.cli init                 # create warehouse + baseline snapshots
    python3 -m agent_ops.cli run                  # run the dbt pipeline and show status
    python3 -m agent_ops.cli faults               # list injectable faults
    python3 -m agent_ops.cli inject schema_drift  # break the pipeline (resets first with --reset)
    python3 -m agent_ops.cli investigate          # run the agents; asks you to approve every action
    python3 -m agent_ops.cli investigate --provider groq            # free open-weight model via Groq
    python3 -m agent_ops.cli models --provider openrouter           # list model ids a provider serves
    python3 -m agent_ops.cli reset
"""
from __future__ import annotations

import argparse
import json

from . import llm, pipeline
from .approvals import CLIApprover, PolicyApprover
from .audit import AuditLog
from .orchestrator import Orchestrator
from faults import injector


def main(argv: list[str] | None = None) -> None:
    ap = argparse.ArgumentParser(prog="pipeline-ops-agent")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("init")
    sub.add_parser("reset")
    sub.add_parser("run")
    sub.add_parser("faults")
    p_inj = sub.add_parser("inject")
    p_inj.add_argument("fault")
    p_inj.add_argument("--reset", action="store_true", help="reset to a clean state first")
    p_inv = sub.add_parser("investigate")
    p_inv.add_argument("--auto-approve", choices=["low", "medium", "high"], help="non-interactive: approve up to this risk")
    p_inv.add_argument("--provider", default=None, choices=llm.PROVIDERS, help="default: $LLM_PROVIDER or anthropic")
    p_inv.add_argument("--model", default=None, help="model id (default depends on provider)")
    p_mod = sub.add_parser("models", help="list model ids a provider currently serves")
    p_mod.add_argument("--provider", required=True, choices=[p for p in llm.PROVIDERS if p != "anthropic"])
    args = ap.parse_args(argv)

    if args.cmd == "init":
        injector.init_environment()
        status = pipeline.run_pipeline()
        print(f"Warehouse + baseline created. Pipeline: {status['overall']}")
    elif args.cmd == "reset":
        injector.reset_environment()
        print("Environment reset to baseline.")
    elif args.cmd == "run":
        status = pipeline.run_pipeline()
        print(json.dumps({k: status[k] for k in ("overall", "counts", "failed_nodes", "skipped_nodes")}, indent=2, default=str))
    elif args.cmd == "faults":
        for f in injector.FAULTS.values():
            print(f"{f.name:24} {f.description}")
    elif args.cmd == "inject":
        if args.reset:
            injector.reset_environment()
        fault = injector.inject(args.fault)
        print(f"Injected: {fault.name} ({fault.description}). Running pipeline...")
        print("Pipeline:", pipeline.run_pipeline()["overall"])
    elif args.cmd == "investigate":
        provider, model = llm.resolve(args.model, args.provider)
        approver = PolicyApprover(args.auto_approve) if args.auto_approve else CLIApprover()
        print(f"Provider: {provider}  Model: {model}")
        report = Orchestrator(llm.make_client(provider), approver, AuditLog(), model=model).investigate()
        print("\n" + report.summary())
    elif args.cmd == "models":
        for model_id in llm.make_client(args.provider).list_models():
            print(model_id)


if __name__ == "__main__":
    main()
