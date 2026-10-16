from datetime import datetime

import pytest
from fastapi.testclient import TestClient

from app.models import PRAGUE


@pytest.fixture(scope="session")
def client():
    from app.services import engine, side_effects

    engine.use_llm_default = lambda: False
    side_effects._background = lambda name, work: None

    from app import store
    from app.main import app

    store.set_demo_state(datetime(2026, 9, 9, 21, 50, tzinfo=PRAGUE), "dev")
    assert store.wait_ready(180)
    return TestClient(app)
