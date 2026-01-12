"""
Tests for ActionExecutor.

SPDX-License-Identifier: Apache-2.0
"""

import uuid
from unittest.mock import MagicMock, patch

import pytest
from django.test import TestCase

from src.modules.workflow_automation.action_executor import ActionExecutor


class ActionExecutorTestCase(TestCase):
    """Test cases for ActionExecutor."""

    def setUp(self):
        """Set up test fixtures."""
        self.tenant_id = str(uuid.uuid4())
        self.workflow_context = {
            "user_id": str(uuid.uuid4()),
            "workflow_instance_id": str(uuid.uuid4()),
        }

    def test_execute_database_update_success(self):
        """Test successful database update execution."""
        action_config = {
            "model": "billing_subscriptions.Invoice",
            "filters": {"id": str(uuid.uuid4())},
            "updates": {"status": "paid"},
            "max_records": 1000,
        }

        with patch("src.modules.workflow_automation.action_executor.apps") as mock_apps:
            mock_model = MagicMock()
            # Mock _meta properly
            mock_meta = MagicMock()
            mock_field_id = MagicMock()
            mock_field_id.name = "id"
            mock_field_tenant = MagicMock()
            mock_field_tenant.name = "tenant_id"
            mock_field_status = MagicMock()
            mock_field_status.name = "status"
            mock_meta.get_fields.return_value = [mock_field_id, mock_field_tenant, mock_field_status]
            mock_model._meta = mock_meta
            mock_model._meta.get_fields.return_value = [mock_field_id, mock_field_tenant, mock_field_status]
            
            # Mock queryset chain
            mock_queryset = MagicMock()
            mock_queryset.count.return_value = 1
            mock_queryset.update.return_value = 1
            mock_model.objects.filter.return_value = mock_queryset

            mock_apps.get_model.return_value = mock_model

            # Mock settings for allowed models
            with patch("src.modules.workflow_automation.action_executor.settings") as mock_settings:
                mock_settings.WORKFLOW_ALLOWED_UPDATE_MODELS = ["billing_subscriptions.Invoice"]
                
                # PlatformManagementService is imported inside the function
                with patch(
                    "src.modules.platform_management.services.PlatformManagementService.log_audit_event"
                ) as mock_log:
                    result = ActionExecutor._execute_database_update(
                        action_config, self.workflow_context, self.tenant_id
                    )

                    self.assertTrue(result["success"], f"Result: {result}")
                    self.assertEqual(result["records_updated"], 1)
                    # Verify audit logging was called
                    mock_log.assert_called_once()

    def test_execute_database_update_tenant_filtering(self):
        """Test that tenant_id is always included in filters."""
        action_config = {
            "model": "billing_subscriptions.Invoice",
            "filters": {"id": str(uuid.uuid4())},
            "updates": {"status": "paid"},
        }

        with patch("src.modules.workflow_automation.action_executor.apps") as mock_apps:
            mock_model = MagicMock()
            # Mock _meta properly
            mock_meta = MagicMock()
            mock_field_id = MagicMock()
            mock_field_id.name = "id"
            mock_field_tenant = MagicMock()
            mock_field_tenant.name = "tenant_id"
            mock_field_status = MagicMock()
            mock_field_status.name = "status"
            mock_meta.get_fields.return_value = [mock_field_id, mock_field_tenant, mock_field_status]
            mock_model._meta = mock_meta
            
            # Mock queryset chain
            mock_queryset = MagicMock()
            mock_queryset.count.return_value = 1
            mock_queryset.update.return_value = 1
            mock_model.objects.filter.return_value = mock_queryset

            mock_apps.get_model.return_value = mock_model

            # Mock settings for allowed models
            with patch("src.modules.workflow_automation.action_executor.settings") as mock_settings:
                mock_settings.WORKFLOW_ALLOWED_UPDATE_MODELS = ["billing_subscriptions.Invoice"]
                
                # PlatformManagementService is imported inside the function
                with patch(
                    "src.modules.platform_management.services.PlatformManagementService.log_audit_event"
                ) as mock_log:
                    result = ActionExecutor._execute_database_update(
                        action_config, self.workflow_context, self.tenant_id
                    )

                    # Verify tenant_id was added to filters
                    call_args = mock_model.objects.filter.call_args
                    self.assertIn("tenant_id", call_args[1] or call_args[0][0])
                    # Verify audit logging was called
                    mock_log.assert_called_once()

    def test_execute_database_update_protected_fields(self):
        """Test that protected fields cannot be updated."""
        action_config = {
            "model": "billing_subscriptions.Invoice",
            "filters": {"id": str(uuid.uuid4())},
            "updates": {"id": "new_id", "tenant_id": "new_tenant"},  # Protected fields
        }

        result = ActionExecutor._execute_database_update(
            action_config, self.workflow_context, self.tenant_id
        )

        self.assertFalse(result["success"])
        self.assertIn("protected fields", result["error"].lower())

    def test_execute_script_sandboxed(self):
        """Test sandboxed script execution."""
        action_config = {
            "script": "result = 'Hello, World!'",
            "max_execution_time": 30,
            "max_memory_mb": 100,
        }

        with patch("src.modules.workflow_automation.action_executor.compile_restricted") as mock_compile:
            mock_compile.return_value = compile("result = 'Hello, World!'", "<test>", "exec")

            with patch("src.modules.workflow_automation.action_executor.signal"):
                result = ActionExecutor._execute_script(
                    action_config, self.workflow_context, self.tenant_id
                )

                # Should execute successfully (mocked)
                self.assertIsNotNone(result)

    def test_execute_script_syntax_error(self):
        """Test script execution with syntax error."""
        action_config = {
            "script": "invalid python syntax !!!",
        }

        with patch("src.modules.workflow_automation.action_executor.compile_restricted") as mock_compile:
            mock_compile.side_effect = SyntaxError("Invalid syntax", ("<test>", 1, 1, "invalid"))

            result = ActionExecutor._execute_script(
                action_config, self.workflow_context, self.tenant_id
            )

            self.assertFalse(result["success"])
            self.assertIn("syntax error", result["error"].lower())
