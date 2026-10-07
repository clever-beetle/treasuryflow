import pytest
import os
import sqlite3
import sys
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))
from app import app as flask_app, init_db

@pytest.fixture
def app():
    flask_app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
        "RATELIMIT_ENABLED": False,
    })
    import utils
    utils.limiter.enabled = False
    init_db()
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()
