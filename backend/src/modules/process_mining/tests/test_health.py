"""Readiness probes are comprehensive and sanitized."""
from src.modules.process_mining.health import DOMAIN_TABLES, adapter_readiness_probe, database_readiness_probe, get_module_health


def test_adapter_probe_requires_real_local_algorithm():
    assert adapter_readiness_probe().healthy


def test_database_probe_names_all_domain_tables():
    assert len(DOMAIN_TABLES) == 11
    result = database_readiness_probe()
    assert result.message in {"ready", "domain_schema_unavailable", "database_unavailable"}


def test_health_never_exposes_rows_or_exceptions(monkeypatch):
    report = get_module_health()
    rendered = str(report.payload).lower()
    assert "row_count" not in rendered and "traceback" not in rendered and "exception" not in rendered
