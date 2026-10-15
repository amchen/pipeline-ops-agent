PY ?= python

setup:        ## install deps
	pip install -r requirements.txt
init:         ## create warehouse + baseline, verify pipeline is green
	$(PY) -m agent_ops.cli init
faults:       ## list faults
	$(PY) -m agent_ops.cli faults
inject:       ## make inject FAULT=schema_drift
	$(PY) -m agent_ops.cli inject $(FAULT) --reset
investigate:  ## run the agents (interactive approvals)
	$(PY) -m agent_ops.cli investigate
test:         ## no API key needed (~3 min: runs real dbt builds)
	$(PY) -m pytest -q tests
evals:        ## needs ANTHROPIC_API_KEY
	$(PY) -m evals.run_evals
safety:       ## live prompt-injection test, needs ANTHROPIC_API_KEY
	$(PY) -m evals.safety_live
mcp:
	$(PY) -m agent_ops.mcp_server
.PHONY: setup init faults inject investigate test evals safety mcp
