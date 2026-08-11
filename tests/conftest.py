import pytest
import os
import sqlite3
from app import app as flask_app

@pytest.fixture
def app():
    flask_app.config.update({
        "TESTING": True,
        "WTF_CSRF_ENABLED": False,
    })
    
    yield flask_app


@pytest.fixture
def client(app):
    return app.test_client()
