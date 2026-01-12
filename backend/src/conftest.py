import pytest


@pytest.fixture(autouse=True)
def override_saraise_mode(settings, request):
    """Force development mode for tests to bypass licensing globally, except for licensing tests."""
    # Do not override for licensing or auth tests which verify mode behavior
    path = str(request.fspath)
    if "core/licensing" in path or "core/auth" in path:
        return

    settings.SARAISE_MODE = "development"
