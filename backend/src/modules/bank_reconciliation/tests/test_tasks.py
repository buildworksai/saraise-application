from __future__ import annotations

from src.core.async_jobs.services import get_handler

from .. import tasks


def test_handlers_are_registered_under_stable_commands() -> None:
    assert get_handler("bank_reconciliation.import_statement") is not None
    assert get_handler("bank_reconciliation.generate_candidates") is not None


def test_job_payload_uuid_validation_is_fail_closed() -> None:
    try:
        tasks._uuid_payload({}, "import_id")
    except ValueError as exc:
        assert "import_id" in str(exc)
    else:
        raise AssertionError("Missing tenant-safe job identity was accepted")
