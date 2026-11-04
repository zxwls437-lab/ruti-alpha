import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["RUTI_PBKDF2_ITERATIONS"] = "1000"
os.environ.pop("OPENAI_API_KEY", None)
os.environ["RUTI_LLM_COOLDOWN_SECONDS"] = "0"

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import User
from app.retrieval import ingredient_names
from app.scan import index as scan_index
from app import llm
from app.security import limiter


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    limiter.reset()
    ingredient_names.reset()
    scan_index.reset()
    llm.cache.reset()
    llm.cooldowns.reset()
    llm.usage.reset()
    with TestClient(app) as c:
        yield c


ALL_CONSENTS = {"age14": True, "terms": True, "privacy": True, "sensitive": True, "marketing": False}


def signup_body(username="testuser1", password="password123", **extra):
    return {"username": username, "password": password, "name": "테스터", "consents": dict(ALL_CONSENTS), **extra}


def signup(client, username="testuser1", password="password123"):
    r = client.post("/auth/signup", json=signup_body(username, password))
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def make_admin(client, username="admin1"):
    headers = signup(client, username)
    with SessionLocal() as db:
        user = db.query(User).filter_by(username=username).one()
        user.is_admin = True
        db.commit()
    return headers
