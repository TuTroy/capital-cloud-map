import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


@pytest.fixture(scope="session")
def _test_db():
    """DB path for tests: seed DB (default) or real DB (USE_REAL_DB=1)."""
    if os.environ.get("USE_REAL_DB"):
        from config import DB_PATH
        if not os.path.exists(DB_PATH):
            pytest.fail(f"USE_REAL_DB=1 but {DB_PATH} not found")
        return DB_PATH

    from tests.seed_db import seed_db

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    seed_db(path)
    yield path
    if os.path.exists(path):
        os.remove(path)


@pytest.fixture
def client(_test_db, monkeypatch):
    """Flask test client wired to the test DB."""
    import config
    import scripts.update_db as udb

    monkeypatch.setattr(config, "DB_PATH", _test_db)
    monkeypatch.setattr(udb, "DB_PATH", _test_db)

    from app import app as flask_app

    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def tmp_db(monkeypatch):
    """Empty temp DB for update_db tests. Isolated from _test_db."""
    import config
    import scripts.update_db as udb

    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(udb, "DB_PATH", path)
    yield path
    if os.path.exists(path):
        os.remove(path)
