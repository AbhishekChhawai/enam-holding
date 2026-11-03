import os, sys, tempfile
from pathlib import Path

# Isolate tests from real data and from any API key in the environment.
_tmp = tempfile.mkdtemp(prefix="finn-test-")
os.environ["FINN_DATA_DIR"] = _tmp
# FINN_TEST_DB_URL runs the same suite against Postgres (e.g. postgresql://finn:finn@localhost/finn_test).
os.environ["FINN_DB_URL"] = os.environ.get("FINN_TEST_DB_URL") or f"sqlite:///{_tmp}/test.db"
os.environ["GEMINI_API_KEY"] = ""
os.environ["FINN_LIVE_REFRESH"] = "0"
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

FIXTURES = Path(__file__).parent / "fixtures"


def pytest_sessionstart(session):
    """Start every run from an empty schema, whichever database is configured."""
    from finn.db import Base, engine
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
