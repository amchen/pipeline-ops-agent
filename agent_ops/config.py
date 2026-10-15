"""Central configuration. Every path can be overridden by environment variable."""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PIPELINE_DIR = Path(os.getenv("PIPELINE_DIR", ROOT / "pipeline")).resolve()
DATA_DIR = Path(os.getenv("DATA_DIR", ROOT / "data")).resolve()
RUNS_DIR = Path(os.getenv("RUNS_DIR", ROOT / "runs")).resolve()

WAREHOUSE_PATH = Path(os.getenv("WAREHOUSE_PATH", DATA_DIR / "warehouse.duckdb")).resolve()
BASELINE_PATH = DATA_DIR / "baseline.duckdb"
MODELS_BASELINE_DIR = DATA_DIR / "models_baseline"

MODEL = os.getenv("AGENT_MODEL", "claude-sonnet-5-5")
MAX_TOKENS_PER_CALL = int(os.getenv("AGENT_MAX_TOKENS_PER_CALL", "2048"))
MAX_STEPS_PER_AGENT = int(os.getenv("AGENT_MAX_STEPS", "12"))
MAX_TOTAL_TOKENS_PER_AGENT = int(os.getenv("AGENT_MAX_TOTAL_TOKENS", "60000"))

# The "as of" reference time baked into the synthetic data (see seed.py).
AS_OF = "2026-10-13 00:00:00"
