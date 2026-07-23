"""Non-leaking health contract proofs."""

from src.modules.purchase_management.serializers import ModuleHealthSerializer


def test_health_contract_rejects_fabricated_status():
    serializer = ModuleHealthSerializer(data={"status": "ready", "checks": {}, "raw_exception": "secret"})
    assert not serializer.is_valid()
    assert "raw_exception" in serializer.errors
