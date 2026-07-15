#!/usr/bin/env python3
"""Mutation test proving every former module exemption is covered by the ratchet."""

from __future__ import annotations

import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1]
FORMERLY_SUPPRESSED_FILES = (
    "saraise_backend/settings.py",
    "src/core/auth/policy_permissions.py",
    "src/core/auth/rbac.py",
    "src/core/compliance_models.py",
    "src/core/compliance_service.py",
    "src/core/licensing/client.py",
    "src/core/licensing/decorators.py",
    "src/core/licensing/middleware.py",
    "src/core/licensing/models.py",
    "src/core/licensing/services.py",
    "src/core/management/commands/seed_default_users.py",
    "src/core/module_installer.py",
    "src/core/module_signing.py",
    "src/core/module_upgrader.py",
    "src/core/notifications/services.py",
    "src/modules/accounting_finance/services.py",
    "src/modules/ai_agent_management/approval_service.py",
    "src/modules/ai_agent_management/audit_service.py",
    "src/modules/ai_agent_management/egress_service.py",
    "src/modules/ai_agent_management/evaluation/harness.py",
    "src/modules/ai_agent_management/quota_service.py",
    "src/modules/ai_agent_management/scheduler.py",
    "src/modules/ai_agent_management/secret_service.py",
    "src/modules/ai_agent_management/token_service.py",
    "src/modules/ai_agent_management/tool_registry.py",
    "src/modules/ai_agent_management/tool_service.py",
    "src/modules/asset_management/services.py",
    "src/modules/billing_subscriptions/services.py",
    "src/modules/crm/services.py",
    "src/modules/data_migration/services.py",
    "src/modules/integration_platform/services.py",
    "src/modules/metadata_modeling/serializers.py",
    "src/modules/metadata_modeling/services.py",
    "src/modules/platform_management/api.py",
    "src/modules/security_access_control/services.py",
    "src/modules/tenant_management/services.py",
    "src/modules/workflow_automation/action_executor.py",
)


def main() -> int:
    with tempfile.TemporaryDirectory(prefix="saraise-mypy-ratchet-") as temporary_directory:
        test_backend = Path(temporary_directory) / "backend"
        shutil.copytree(
            BACKEND_DIR,
            test_backend,
            ignore=shutil.ignore_patterns(".mypy_cache", ".pytest_cache", "__pycache__", "coverage*", "schema.*"),
        )

        for index, relative_path in enumerate(FORMERLY_SUPPRESSED_FILES):
            source_file = test_backend / relative_path
            with source_file.open("a", encoding="utf-8") as file_handle:
                file_handle.write(f"\n__mypy_ratchet_probe_{index}: str = {index}\n")

        result = subprocess.run(
            [sys.executable, "scripts/mypy_baseline.py", "check"],
            cwd=test_backend,
            capture_output=True,
            text=True,
            check=False,
        )
        output = result.stdout + result.stderr

        if result.returncode == 0:
            print(output, end="", file=sys.stderr)
            print("Mutation test failed: the ratchet accepted injected errors.", file=sys.stderr)
            return 1

        missing = [path for path in FORMERLY_SUPPRESSED_FILES if path not in output]
        if missing:
            print(output, end="", file=sys.stderr)
            print("Mutation test did not detect probes in:\n" + "\n".join(missing), file=sys.stderr)
            return 1

        print(f"MyPy ratchet mutation test passed for {len(FORMERLY_SUPPRESSED_FILES)} former exemptions.")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
