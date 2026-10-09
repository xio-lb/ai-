import itertools
import sys
import tempfile
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parent.parent
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

# Point every store at throwaway databases before app modules import them, so a
# test run never reads or writes the developer's real data files.
_TEST_DB_DIR = Path(tempfile.mkdtemp(prefix="travel-planner-tests-"))

from app.services import auth_service, cache_service, observability, tasks_service  # noqa: E402

auth_service.DB_PATH = _TEST_DB_DIR / "auth.db"
tasks_service.DB_PATH = _TEST_DB_DIR / "tasks.db"
cache_service.DB_PATH = _TEST_DB_DIR / "amap_cache.db"
observability.DB_PATH = _TEST_DB_DIR / "observability.db"

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402
from app.schemas.trip import TripPlan  # noqa: E402
from app.services import history_service, memory_service  # noqa: E402

history_service.DB_PATH = _TEST_DB_DIR / "trip_history.db"
memory_service.DB_PATH = _TEST_DB_DIR / "trip_history.db"

_REGISTER_SEQ = itertools.count(1)


def _register(client: TestClient, email: str, password: str = "test-password-123") -> dict:
    local, _, domain = email.partition("@")
    unique_email = f"{local}+{next(_REGISTER_SEQ)}@{domain}"
    response = client.post(
        "/api/auth/register",
        json={"email": unique_email, "password": password, "display_name": local},
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    payload["email"] = unique_email
    return payload


def _auth_headers(payload: dict) -> dict:
    return {"Authorization": f"Bearer {payload['token']}"}
