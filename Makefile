PY ?= python3
PROVIDER ?= anthropic
MODEL ?=

setup:        ## install deps
	pip install -r requirements.txt
init:         ## create warehouse + baseline, verify pipeline is green
	$(PY) -m agent_ops.cli init
faults:       ## list faults
	$(PY) -m agent_ops.cli faults
inject:       ## make inject FAULT=schema_drift
	$(PY) -m agent_ops.cli inject $(FAULT) --reset
investigate:  ## make investigate PROVIDER=groq [MODEL=...]  (interactive approvals)
	$(PY) -m agent_ops.cli investigate --provider $(PROVIDER) $(if $(MODEL),--model $(MODEL))
models:       ## make models PROVIDER=groq  -> list live model ids
	$(PY) -m agent_ops.cli models --provider $(PROVIDER)
test:         ## no API key needed (~3 min: runs real dbt builds)
	$(PY) -m pytest -q tests
evals:        ## make evals MODELS=anthropic:claude-sonnet-5-5,groq:llama-3.3-70b-versatile
	$(PY) -m evals.run_evals $(if $(MODELS),--models $(MODELS))
safety:       ## live prompt-injection test; make safety MODEL=groq:llama-3.3-70b-versatile
	$(PY) -m evals.safety_live $(if $(MODEL),--model $(MODEL))
mcp:
	$(PY) -m agent_ops.mcp_server
.PHONY: setup init faults inject investigate models test evals safety mcp
