"""
Workflow Action Executor.

Executes workflow actions (database updates, API calls, scripts, etc.).

SPDX-License-Identifier: Apache-2.0
"""

import logging
import resource
import signal
import time
import uuid
from typing import Any, Dict

import httpx
from RestrictedPython import compile_restricted, safe_globals
from RestrictedPython.Guards import guarded_iter_unpack_sequence, guarded_unpack_sequence

from django.apps import apps
from django.conf import settings
from django.db import transaction

logger = logging.getLogger(__name__)

# Protected fields that cannot be updated via workflow actions
PROTECTED_FIELDS = {"id", "tenant_id", "created_at", "updated_at", "created_by", "updated_by"}

# Default model whitelist (can be overridden in settings)
DEFAULT_ALLOWED_MODELS = [
    "billing_subscriptions.Subscription",
    "billing_subscriptions.Invoice",
    "integration_platform.Integration",
    "workflow_automation.WorkflowInstance",
]


class ActionExecutor:
    """Executes workflow actions."""

    @staticmethod
    def execute_action(
        action_type: str,
        action_config: Dict[str, Any],
        workflow_context: Dict[str, Any],
        tenant_id: str,
    ) -> Dict[str, Any]:
        """Execute a workflow action.

        Args:
            action_type: Type of action (update_database, send_email, call_api, run_script).
            action_config: Action configuration from workflow step.
            workflow_context: Current workflow instance context data.
            tenant_id: Tenant ID.

        Returns:
            Action result dictionary with 'success' and 'result' keys.

        Raises:
            ValueError: If action type is unsupported or execution fails.
        """
        if action_type == "update_database":
            return ActionExecutor._execute_database_update(action_config, workflow_context, tenant_id)
        elif action_type == "send_email":
            return ActionExecutor._execute_send_email(action_config, workflow_context, tenant_id)
        elif action_type == "call_api":
            return ActionExecutor._execute_api_call(action_config, workflow_context, tenant_id)
        elif action_type == "run_script":
            return ActionExecutor._execute_script(action_config, workflow_context, tenant_id)
        else:
            raise ValueError(f"Unsupported action type: {action_type}")

    @staticmethod
    def _execute_database_update(
        action_config: Dict[str, Any],
        workflow_context: Dict[str, Any],
        tenant_id: str,
    ) -> Dict[str, Any]:
        """Execute database update action.

        Args:
            action_config: Action configuration with 'model', 'filters', 'updates'.
            workflow_context: Workflow context data.
            tenant_id: Tenant ID.

        Returns:
            Action result with 'success', 'records_updated', and optional 'error'.

        Raises:
            ValueError: If model validation fails or update is not allowed.
        """
        try:
            # 1. Validate model name
            model_name = action_config.get("model")
            if not model_name:
                return {"success": False, "error": "Model name is required"}

            # Get allowed models from settings or use default
            allowed_models = getattr(
                settings, "WORKFLOW_ALLOWED_UPDATE_MODELS", DEFAULT_ALLOWED_MODELS
            )

            if model_name not in allowed_models:
                logger.warning(f"Model {model_name} not in whitelist for workflow updates")
                return {
                    "success": False,
                    "error": f"Model {model_name} is not allowed for workflow updates",
                }

            # 2. Get model dynamically
            try:
                app_label, model_class_name = model_name.split(".", 1)
                model_class = apps.get_model(app_label, model_class_name)
            except (ValueError, LookupError) as e:
                logger.error(f"Invalid model name {model_name}: {e}")
                return {"success": False, "error": f"Invalid model name: {model_name}"}

            # 3. Validate model has tenant_id field
            if not hasattr(model_class, "tenant_id"):
                logger.error(f"Model {model_name} does not have tenant_id field")
                return {
                    "success": False,
                    "error": f"Model {model_name} must have tenant_id field for tenant isolation",
                }

            # 4. Validate and extract filters
            filters = action_config.get("filters", {})
            if not isinstance(filters, dict):
                return {"success": False, "error": "Filters must be a dictionary"}

            # Ensure tenant_id is in filters (MANDATORY for security)
            if "tenant_id" not in filters:
                filters["tenant_id"] = tenant_id
            elif filters["tenant_id"] != tenant_id:
                logger.warning(
                    f"Tenant ID mismatch: filter has {filters['tenant_id']}, "
                    f"workflow has {tenant_id}. Using workflow tenant_id."
                )
                filters["tenant_id"] = tenant_id

            # 5. Validate and extract updates
            updates = action_config.get("updates", {})
            if not isinstance(updates, dict):
                return {"success": False, "error": "Updates must be a dictionary"}

            if not updates:
                return {"success": False, "error": "No fields to update"}

            # 6. Validate field names (no protected fields)
            protected_fields_found = set(updates.keys()) & PROTECTED_FIELDS
            if protected_fields_found:
                return {
                    "success": False,
                    "error": f"Cannot update protected fields: {', '.join(protected_fields_found)}",
                }

            # 7. Validate field names exist on model
            model_fields = {f.name for f in model_class._meta.get_fields()}
            invalid_fields = set(updates.keys()) - model_fields
            if invalid_fields:
                return {
                    "success": False,
                    "error": f"Invalid fields: {', '.join(invalid_fields)}",
                }

            # 8. Check resource limits
            max_records = action_config.get("max_records", 1000)
            queryset = model_class.objects.filter(**filters)

            # Count records that would be updated
            record_count = queryset.count()
            if record_count > max_records:
                return {
                    "success": False,
                    "error": f"Update would affect {record_count} records, "
                    f"exceeds limit of {max_records}",
                }

            # 9. Execute update in transaction with audit logging
            with transaction.atomic():
                # Perform update
                updated_count = queryset.update(**updates)

                # 10. Log audit event
                try:
                    from src.modules.platform_management.services import PlatformManagementService

                    PlatformManagementService.log_audit_event(
                        action="workflow.database.update",
                        actor_id=workflow_context.get("user_id") or uuid.uuid4(),
                        resource_type=model_name,
                        tenant_id=tenant_id,
                        details={
                            "model": model_name,
                            "filters": filters,
                            "updates": updates,
                            "records_updated": updated_count,
                            "workflow_context": workflow_context.get("workflow_instance_id"),
                        },
                    )
                except Exception as audit_error:
                    # Log audit error but don't fail the update
                    logger.error(f"Failed to log audit event: {audit_error}")

                logger.info(
                    f"Database update: {updated_count} records updated in {model_name} "
                    f"for tenant {tenant_id}"
                )

                return {
                    "success": True,
                    "records_updated": updated_count,
                    "result": f"Updated {updated_count} record(s) in {model_name}",
                }

        except Exception as e:
            logger.error(f"Database update action failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    @staticmethod
    def _execute_send_email(
        action_config: Dict[str, Any],
        workflow_context: Dict[str, Any],
        tenant_id: str,
    ) -> Dict[str, Any]:
        """Execute send email action.

        Args:
            action_config: Action configuration with 'to', 'subject', 'template'.
            workflow_context: Workflow context data.
            tenant_id: Tenant ID.

        Returns:
            Action result.
        """
        from src.core.notifications import NotificationService

        to_email = action_config.get("to") or workflow_context.get("user_email", "")
        subject = action_config.get("subject", "Workflow Notification")
        message = action_config.get("message", "")

        if not to_email:
            return {"success": False, "error": "No recipient email specified"}

        # Create notification (which will send email if enabled)
        notification = NotificationService.create_notification(
            tenant_id=tenant_id,
            user_id=workflow_context.get("user_id", ""),
            title=subject,
            message=message,
            notification_type="workflow",
        )

        logger.info(f"Email sent via notification {notification.id}")
        return {"success": True, "result": f"Email sent to {to_email}"}

    @staticmethod
    def _execute_api_call(
        action_config: Dict[str, Any],
        workflow_context: Dict[str, Any],
        tenant_id: str,
    ) -> Dict[str, Any]:
        """Execute API call action.

        Args:
            action_config: Action configuration with 'url', 'method', 'headers', 'body'.
            workflow_context: Workflow context data.
            tenant_id: Tenant ID.

        Returns:
            Action result.
        """
        url = action_config.get("url")
        method = action_config.get("method", "GET").upper()
        headers = action_config.get("headers", {})
        body = action_config.get("body")

        if not url:
            return {"success": False, "error": "No URL specified"}

        try:
            if method == "GET":
                response = httpx.get(url, headers=headers, timeout=30.0)
            elif method == "POST":
                response = httpx.post(url, headers=headers, json=body, timeout=30.0)
            elif method == "PUT":
                response = httpx.put(url, headers=headers, json=body, timeout=30.0)
            elif method == "DELETE":
                response = httpx.delete(url, headers=headers, timeout=30.0)
            else:
                return {"success": False, "error": f"Unsupported HTTP method: {method}"}

            response.raise_for_status()
            return {"success": True, "result": response.json() if response.content else {}}

        except Exception as e:
            logger.error(f"API call failed: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def _execute_script(
        action_config: Dict[str, Any],
        workflow_context: Dict[str, Any],
        tenant_id: str,
    ) -> Dict[str, Any]:
        """Execute script action (sandboxed).

        Args:
            action_config: Action configuration with 'script' or 'script_id'.
            workflow_context: Workflow context data.
            tenant_id: Tenant ID.

        Returns:
            Action result with 'success', 'result', and optional 'error'.

        Note:
            Script execution is sandboxed for security with resource limits.
            - Max execution time: 30 seconds
            - Max memory: 100MB
            - No file system access
            - No network access
            - Limited builtins
        """
        try:
            # 1. Get script content
            script_content = action_config.get("script") or action_config.get("script_id")
            if not script_content:
                return {"success": False, "error": "No script content provided"}

            if isinstance(script_content, str) and len(script_content) > 100000:  # 100KB limit
                return {"success": False, "error": "Script exceeds maximum size (100KB)"}

            # 2. Validate script syntax and compile with RestrictedPython
            try:
                byte_code = compile_restricted(script_content, filename="<workflow_script>", mode="exec")
            except SyntaxError as e:
                logger.error(f"Script syntax error: {e}")
                return {"success": False, "error": f"Script syntax error: {str(e)}"}
            except Exception as e:
                return {"success": False, "error": f"Script compilation failed: {str(e)}"}

            # 3. Create safe execution environment
            # Limited builtins - only safe operations
            safe_builtins = {
                "__builtins__": {
                    "abs": abs,
                    "all": all,
                    "any": any,
                    "bool": bool,
                    "dict": dict,
                    "enumerate": enumerate,
                    "float": float,
                    "int": int,
                    "isinstance": isinstance,
                    "len": len,
                    "list": list,
                    "max": max,
                    "min": min,
                    "range": range,
                    "reversed": reversed,
                    "round": round,
                    "set": set,
                    "sorted": sorted,
                    "str": str,
                    "sum": sum,
                    "tuple": tuple,
                    "type": type,
                    "zip": zip,
                    "_getiter_": safe_globals["_getiter_"],
                    "_iter_unpack_": guarded_iter_unpack_sequence,
                    "_unpack_": guarded_unpack_sequence,
                },
                "_print_": lambda *args, **kwargs: None,  # Disable print
                "_getattr_": safe_globals["_getattr_"],
                "_write_": safe_globals["_write_"],
            }

            # Add workflow context to execution environment
            execution_globals = {
                **safe_builtins,
                "context": workflow_context,
                "tenant_id": tenant_id,
            }

            # 4. Set resource limits
            max_execution_time = action_config.get("max_execution_time", 30)  # seconds
            max_memory_mb = action_config.get("max_memory_mb", 100)

            # Set memory limit (in bytes)
            try:
                resource.setrlimit(
                    resource.RLIMIT_AS, (max_memory_mb * 1024 * 1024, max_memory_mb * 1024 * 1024)
                )
            except (ValueError, OSError) as e:
                logger.warning(f"Could not set memory limit: {e}")

            # 5. Execute script with timeout
            execution_result = {"output": None, "error": None}

            def timeout_handler(signum, frame):
                raise TimeoutError(f"Script execution exceeded {max_execution_time} seconds")

            # Set up timeout
            old_handler = signal.signal(signal.SIGALRM, timeout_handler)
            signal.alarm(max_execution_time)

            try:
                start_time = time.time()

                # Execute in restricted environment
                exec(byte_code, execution_globals, {})

                execution_time = time.time() - start_time

                # Get result (if script sets a 'result' variable)
                script_result = execution_globals.get("result")
                if script_result is None:
                    script_result = "Script executed successfully"

                # Limit result size (max 1MB)
                result_str = str(script_result)
                if len(result_str.encode("utf-8")) > 1024 * 1024:
                    result_str = result_str[:1024 * 100] + "... (truncated)"

                execution_result["output"] = result_str
                execution_result["execution_time"] = execution_time

            except TimeoutError as e:
                execution_result["error"] = str(e)
                logger.error(f"Script execution timeout: {e}")
            except Exception as e:
                execution_result["error"] = str(e)
                logger.error(f"Script execution error: {e}", exc_info=True)
            finally:
                # Restore signal handler
                signal.alarm(0)
                signal.signal(signal.SIGALRM, old_handler)

            # 6. Return result
            if execution_result["error"]:
                return {"success": False, "error": execution_result["error"]}

            logger.info(
                f"Script executed successfully in {execution_result.get('execution_time', 0):.2f}s "
                f"for tenant {tenant_id}"
            )

            return {
                "success": True,
                "result": execution_result["output"],
                "execution_time": execution_result.get("execution_time", 0),
            }

        except Exception as e:
            logger.error(f"Script execution action failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}
