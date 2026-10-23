import os
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

TEST_DB = ROOT / "test_autopilot.db"
if TEST_DB.exists():
    TEST_DB.unlink()

os.environ["DATABASE_URL"] = f"sqlite:///{TEST_DB}"
os.environ["DEMO_MODE"] = "true"
os.environ["AUTO_SEED_DEMO"] = "0"
os.environ["ENABLE_SCHEDULER"] = "false"
os.environ["VERIFY_TWILIO_SIGNATURE"] = "false"
os.environ["SECRET_KEY"] = "test-secret"

from fastapi.testclient import TestClient  # noqa: E402

from app.db import SessionLocal, engine, init_db  # noqa: E402
from app.main import app  # noqa: E402
from app.services import onboarding  # noqa: E402


@pytest.fixture(scope="session", autouse=True)
def _database():
    init_db()
    yield
    engine.dispose()
    if TEST_DB.exists():
        TEST_DB.unlink()


@pytest.fixture()
def db():
    session = SessionLocal()
    try:
        yield session
    finally:
        session.close()


@pytest.fixture()
def client():
    with TestClient(app) as test_client:
        yield test_client


from tests.helpers import unique_number  # noqa: E402


@pytest.fixture()
def business(db):
    return onboarding.create_business(
        db,
        name=f"Test Snow Co {unique_number()[4:]}",
        owner_name="Alex Tremblay",
        owner_phone=unique_number(),
        trade="snow_removal",
        city="Saint-Georges",
        province="QC",
        phone_number=unique_number(),
        review_url="https://g.page/r/test",
        etransfer_email="alex@example.com",
    )
