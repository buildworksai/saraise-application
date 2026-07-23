import uuid

import pytest

from src.modules.notifications.health import liveness, readiness


def test_liveness_proves_process_only():
    payload = liveness()
    assert payload["module"] == "notifications"
    assert payload["status"] == "live"
    assert payload["live"] is True
    assert payload["checked_at"]


@pytest.mark.django_db
def test_readiness_fails_closed_without_configuration():
    payload, http_status = readiness(uuid.uuid4())
    assert http_status == 503
    assert payload["ready"] is False
    assert "exception" not in str(payload).lower()
