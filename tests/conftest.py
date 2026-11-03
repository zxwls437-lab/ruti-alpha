import os

os.environ["DATABASE_URL"] = "sqlite://"
os.environ["RUTI_PBKDF2_ITERATIONS"] = "1000"
os.environ.pop("OPENAI_API_KEY", None)

import pytest
from fastapi.testclient import TestClient

from app.db import Base, SessionLocal, engine
from app.main import app
from app.models import User
from app.security import limiter


@pytest.fixture()
def client():
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    limiter.reset()
    with TestClient(app) as c:
        yield c


def signup(client, username="testuser1", password="password123"):
    r = client.post("/auth/signup", json={"username": username, "password": password})
    assert r.status_code == 201, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


def make_admin(client, username="admin1"):
    headers = signup(client, username)
    with SessionLocal() as db:
        user = db.query(User).filter_by(username=username).one()
        user.is_admin = True
        db.commit()
    return headers
