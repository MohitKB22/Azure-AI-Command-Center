"""Test fixtures.

Every test runs against an isolated SQLite file and a temporary blob directory,
with the local (deterministic) providers selected. No network access is
required and no Azure credentials are ever read.
"""

from __future__ import annotations

import os
import tempfile
from pathlib import Path

import pytest

TMP = Path(tempfile.mkdtemp(prefix="aicc-tests-"))
os.environ.update(
    {
        "ENVIRONMENT": "local",
        "DEMO_MODE": "true",
        "DATABASE_URL": f"sqlite:///{TMP / 'test.db'}",
        "LOCAL_BLOB_DIR": str(TMP / "blobs"),
        "LLM_PROVIDER": "local",
        "EMBEDDING_PROVIDER": "local",
        "VECTOR_STORE": "local",
        "BLOB_PROVIDER": "local",
        "SECRET_KEY": "test-secret-key-that-is-long-enough-for-tests",
        "RATE_LIMIT_PER_MINUTE": "10000",
    }
)

from fastapi.testclient import TestClient  # noqa: E402

from app.core.db import Base, SessionLocal, engine  # noqa: E402
from app.db.seed import DEMO_PASSWORD, seed  # noqa: E402
from app.main import app  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def seeded_database():
    Base.metadata.drop_all(bind=engine)
    Base.metadata.create_all(bind=engine)
    seed(reset=False, with_runs=False)
    yield
    Base.metadata.drop_all(bind=engine)


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.rollback()
        session.close()


@pytest.fixture(scope="session")
def client():
    with TestClient(app) as test_client:
        yield test_client


def _token(client: TestClient, email: str) -> str:
    response = client.post(
        "/api/v1/auth/login", json={"email": email, "password": DEMO_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()["access_token"]


@pytest.fixture(scope="session")
def admin_headers(client) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(client, 'admin@contoso.com')}"}


@pytest.fixture(scope="session")
def viewer_headers(client) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(client, 'viewer@contoso.com')}"}


@pytest.fixture(scope="session")
def engineer_headers(client) -> dict[str, str]:
    return {"Authorization": f"Bearer {_token(client, 'engineer@contoso.com')}"}


@pytest.fixture()
def enabled_agent_id(client, admin_headers) -> str:
    response = client.get("/api/v1/agents?enabled=true", headers=admin_headers)
    assert response.status_code == 200
    items = response.json()["items"]
    assert items, "seed data should contain at least one enabled agent"
    return items[0]["id"]
