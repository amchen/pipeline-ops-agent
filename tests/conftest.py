"""Isolate warehouse/data/run directories in a temp dir BEFORE agent_ops is imported."""
import os
import tempfile

_tmp = tempfile.mkdtemp(prefix="poa-test-")
os.environ["DATA_DIR"] = os.path.join(_tmp, "data")
os.environ["RUNS_DIR"] = os.path.join(_tmp, "runs")
os.environ.pop("WAREHOUSE_PATH", None)

import pytest  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _env():
    from faults import injector

    injector.init_environment()
    yield
    injector.reset_environment()  # leave repo models pristine


@pytest.fixture()
def clean():
    from faults import injector

    injector.reset_environment()
    yield
