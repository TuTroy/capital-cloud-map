import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app import app as flask_app
from config import DB_PATH


@pytest.fixture
def client():
    flask_app.config["TESTING"] = True
    with flask_app.test_client() as c:
        yield c


@pytest.fixture
def real_db():
    """Verify the real DB exists and has data."""
    assert os.path.exists(DB_PATH), f"DB not found: {DB_PATH}"
    return DB_PATH


@pytest.fixture
def tmp_db(monkeypatch):
    """Create a temp DB for update_db tests, restore real DB path after."""
    import config
    import scripts.update_db as udb
    fd, path = tempfile.mkstemp(suffix=".db")
    os.close(fd)
    monkeypatch.setattr(config, "DB_PATH", path)
    monkeypatch.setattr(udb, "DB_PATH", path)
    yield path
    if os.path.exists(path):
        os.remove(path)
