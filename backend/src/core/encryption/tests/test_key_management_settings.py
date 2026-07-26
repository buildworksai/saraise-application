"""Fresh-process tests for environment-backed key-management configuration."""

import json
import os
import subprocess
import sys

from cryptography.fernet import Fernet


def test_encryption_key_environment_is_loaded_in_fresh_process():
    key = Fernet.generate_key().decode("ascii")
    environment = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "saraise_backend.settings",
        "SARAISE_MODE": "development",
        "SARAISE_ENCRYPTION_KEYS": json.dumps({"primary": key}),
        "SARAISE_ACTIVE_ENCRYPTION_KEY_ID": "primary",
    }
    result = subprocess.run(
        [
            sys.executable,
            "-c",
            (
                "import django; django.setup(); "
                "from src.core.encryption.key_management import SettingsKeyRingBackend; "
                "print(SettingsKeyRingBackend().active_key_id)"
            ),
        ],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout.strip() == "primary"


def test_partial_encryption_key_environment_fails_closed_in_fresh_process():
    environment = {
        **os.environ,
        "DJANGO_SETTINGS_MODULE": "saraise_backend.settings",
        "SARAISE_MODE": "development",
        "SARAISE_ENCRYPTION_KEYS": json.dumps({"primary": Fernet.generate_key().decode("ascii")}),
        "SARAISE_ACTIVE_ENCRYPTION_KEY_ID": "",
    }
    result = subprocess.run(
        [sys.executable, "-c", "import django; django.setup()"],
        env=environment,
        capture_output=True,
        text=True,
        check=False,
    )

    assert result.returncode != 0
    assert "must be configured together" in result.stderr
