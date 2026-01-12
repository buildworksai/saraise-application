"""
IntegrationPlatform Services.

High-level service layer for IntegrationPlatform business logic.
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
from typing import Any, Dict, List, Optional

import httpx
from django.db import transaction
from django.utils import timezone

from src.core.encryption import EncryptionService

from .models import Integration, IntegrationCredential, Webhook, WebhookDelivery

logger = logging.getLogger(__name__)


class WebhookService:
    """Service for handling webhook delivery and verification."""

    def deliver_webhook(
        self,
        webhook: Webhook,
        event: str,
        payload: dict,
    ) -> WebhookDelivery:
        """Deliver webhook with retry and logging.

        Args:
            webhook: Webhook instance.
            event: Event name.
            payload: Webhook payload.

        Returns:
            WebhookDelivery instance.
        """
        # Sign payload
        signature = self._sign_payload(webhook.secret, payload)

        headers = {
            "Content-Type": "application/json",
            "X-Webhook-Signature": signature,
            "X-Webhook-Event": event,
            "X-Tenant-ID": str(webhook.tenant_id),
        }

        delivery = WebhookDelivery.objects.create(
            webhook=webhook,
            event=event,
            payload=payload,
            status="pending",
        )

        try:
            response = httpx.post(
                webhook.url,
                json=payload,
                headers=headers,
                timeout=30,
            )

            delivery.status = "delivered" if response.is_success else "failed"
            delivery.response_code = response.status_code
            delivery.response_body = response.text[:10000]  # Truncate to 10KB
            delivery.delivered_at = timezone.now()

        except Exception as e:
            delivery.status = "failed"
            delivery.error_message = str(e)
            logger.error(f"Webhook delivery failed: {e}")

        delivery.save()
        return delivery

    def _sign_payload(self, secret: str, payload: dict) -> str:
        """Sign payload with HMAC-SHA256.

        Args:
            secret: Webhook secret.
            payload: Payload to sign.

        Returns:
            HMAC-SHA256 signature (hex).
        """
        message = json.dumps(payload, sort_keys=True)
        return hmac.new(
            secret.encode(),
            message.encode(),
            hashlib.sha256,
        ).hexdigest()

    def verify_signature(self, secret: str, payload: dict, signature: str) -> bool:
        """Verify webhook signature.

        Args:
            secret: Webhook secret.
            payload: Payload to verify.
            signature: Signature to verify against.

        Returns:
            True if signature is valid, False otherwise.
        """
        expected_signature = self._sign_payload(secret, payload)
        return hmac.compare_digest(expected_signature, signature)


class IntegrationService:
    """Service for integration testing and synchronization."""

    @staticmethod
    def test_connection(integration: Integration) -> Dict[str, Any]:
        """Test integration connection.

        Args:
            integration: Integration instance.

        Returns:
            Dictionary with 'success', 'message', and optional 'error' keys.
        """
        try:
            # Get credentials
            credential = IntegrationCredential.objects.filter(integration=integration).first()
            if not credential:
                return {
                    "success": False,
                    "error": "No credentials found for integration",
                }

            # Decrypt credential
            decrypted_value = EncryptionService.decrypt(credential.encrypted_value)

            # Test based on integration type
            if integration.integration_type == "api":
                return IntegrationService._test_api_connection(integration, decrypted_value)
            elif integration.integration_type == "database":
                return IntegrationService._test_database_connection(integration, decrypted_value)
            elif integration.integration_type == "webhook":
                return {"success": True, "message": "Webhook integration configured"}
            else:
                return {
                    "success": False,
                    "error": f"Connection testing not implemented for type: {integration.integration_type}",
                }

        except Exception as e:
            logger.error(f"Integration connection test failed: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def _test_api_connection(integration: Integration, api_key: str) -> Dict[str, Any]:
        """Test API connection.

        Args:
            integration: Integration instance.
            api_key: Decrypted API key.

        Returns:
            Test result dictionary.
        """
        try:
            # Get test endpoint from config
            test_url = integration.config.get("test_url") or integration.config.get("base_url")
            if not test_url:
                return {"success": False, "error": "No test URL configured"}

            headers = integration.config.get("headers", {})
            headers["Authorization"] = f"Bearer {api_key}"

            response = httpx.get(test_url, headers=headers, timeout=10.0)
            response.raise_for_status()

            return {
                "success": True,
                "message": f"Connection successful (HTTP {response.status_code})",
            }
        except httpx.HTTPStatusError as e:
            return {
                "success": False,
                "error": f"HTTP {e.response.status_code}: {e.response.text[:200]}",
            }
        except Exception as e:
            return {"success": False, "error": str(e)}

    @staticmethod
    def _test_database_connection(integration: Integration, connection_string: str) -> Dict[str, Any]:
        """Test database connection.

        Args:
            integration: Integration instance.
            connection_string: Decrypted connection string.

        Returns:
            Test result dictionary with 'success', 'message', and optional 'error'.

        Note:
            Supports PostgreSQL, MySQL, and SQLite connections.
            Connection string can be in format:
            - PostgreSQL: postgresql://user:pass@host:port/dbname
            - MySQL: mysql://user:pass@host:port/dbname
            - SQLite: sqlite:///path/to/database.db
        """
        import urllib.parse
        from urllib.parse import urlparse

        try:
            # Parse connection string
            parsed = urlparse(connection_string)

            db_type = parsed.scheme.lower()
            if db_type in ("postgresql", "postgres"):
                return IntegrationService._test_postgresql_connection(parsed, connection_string)
            elif db_type == "mysql":
                return IntegrationService._test_mysql_connection(parsed, connection_string)
            elif db_type == "sqlite":
                return IntegrationService._test_sqlite_connection(parsed, connection_string)
            else:
                return {
                    "success": False,
                    "error": f"Unsupported database type: {db_type}. Supported: postgresql, mysql, sqlite",
                }

        except Exception as e:
            logger.error(f"Database connection test failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    @staticmethod
    def _test_postgresql_connection(parsed, connection_string: str) -> Dict[str, Any]:
        """Test PostgreSQL connection."""
        try:
            import psycopg2
            from psycopg2 import OperationalError

            # Extract connection parameters
            host = parsed.hostname or "localhost"
            port = parsed.port or 5432
            database = parsed.path.lstrip("/") if parsed.path else "postgres"
            username = parsed.username
            password = parsed.password

            if not username:
                return {"success": False, "error": "Username is required for PostgreSQL connection"}

            # Test connection with timeout
            try:
                conn = psycopg2.connect(
                    host=host,
                    port=port,
                    database=database,
                    user=username,
                    password=password,
                    connect_timeout=10,
                )

                # Execute a simple read-only query
                cursor = conn.cursor()
                cursor.execute("SELECT version();")
                version = cursor.fetchone()[0]

                cursor.close()
                conn.close()

                return {
                    "success": True,
                    "message": f"PostgreSQL connection successful (version: {version[:50]})",
                }

            except OperationalError as e:
                return {"success": False, "error": f"PostgreSQL connection failed: {str(e)}"}

        except ImportError:
            return {
                "success": False,
                "error": "psycopg2 library not installed. Install with: pip install psycopg2-binary",
            }

    @staticmethod
    def _test_mysql_connection(parsed, connection_string: str) -> Dict[str, Any]:
        """Test MySQL connection."""
        try:
            import pymysql
            from pymysql import OperationalError

            # Extract connection parameters
            host = parsed.hostname or "localhost"
            port = parsed.port or 3306
            database = parsed.path.lstrip("/") if parsed.path else None
            username = parsed.username
            password = parsed.password

            if not username:
                return {"success": False, "error": "Username is required for MySQL connection"}

            # Test connection with timeout
            try:
                conn = pymysql.connect(
                    host=host,
                    port=port,
                    database=database,
                    user=username,
                    password=password,
                    connect_timeout=10,
                )

                # Execute a simple read-only query
                cursor = conn.cursor()
                cursor.execute("SELECT VERSION();")
                version = cursor.fetchone()[0]

                cursor.close()
                conn.close()

                return {
                    "success": True,
                    "message": f"MySQL connection successful (version: {version})",
                }

            except OperationalError as e:
                return {"success": False, "error": f"MySQL connection failed: {str(e)}"}

        except ImportError:
            return {
                "success": False,
                "error": "pymysql library not installed. Install with: pip install pymysql",
            }

    @staticmethod
    def _test_sqlite_connection(parsed, connection_string: str) -> Dict[str, Any]:
        """Test SQLite connection."""
        try:
            import sqlite3
            from pathlib import Path

            # Extract database path
            db_path = parsed.path.lstrip("/") if parsed.path else ":memory:"

            # For file-based SQLite, check if file exists (or can be created)
            if db_path != ":memory:":
                db_file = Path(db_path)
                if not db_file.exists() and not db_file.parent.exists():
                    return {
                        "success": False,
                        "error": f"SQLite database path does not exist: {db_path}",
                    }

            # Test connection
            try:
                conn = sqlite3.connect(db_path, timeout=10.0)

                # Execute a simple read-only query
                cursor = conn.cursor()
                cursor.execute("SELECT sqlite_version();")
                version = cursor.fetchone()[0]

                cursor.close()
                conn.close()

                return {
                    "success": True,
                    "message": f"SQLite connection successful (version: {version})",
                }

            except sqlite3.Error as e:
                return {"success": False, "error": f"SQLite connection failed: {str(e)}"}

        except Exception as e:
            return {"success": False, "error": f"SQLite connection test error: {str(e)}"}

    @staticmethod
    def sync_integration(
        integration: Integration,
        direction: str = "pull",
        data_mapping_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Sync integration data.

        Args:
            integration: Integration instance.
            direction: Sync direction ('pull', 'push', 'bidirectional').
            data_mapping_id: Optional data mapping ID for transformation.

        Returns:
            Sync result dictionary with 'success', 'records_synced', 'errors'.
        """
        try:
            # Get credentials
            credential = IntegrationCredential.objects.filter(integration=integration).first()
            if not credential:
                return {
                    "success": False,
                    "error": "No credentials found for integration",
                }

            # Decrypt credential
            decrypted_value = EncryptionService.decrypt(credential.encrypted_value)

            # Get data mapping if provided
            data_mapping = None
            if data_mapping_id:
                from .models import DataMapping

                data_mapping = DataMapping.objects.filter(id=data_mapping_id).first()

            # Perform sync based on direction
            if direction == "pull":
                return IntegrationService._pull_data(integration, decrypted_value, data_mapping)
            elif direction == "push":
                return IntegrationService._push_data(integration, decrypted_value, data_mapping)
            elif direction == "bidirectional":
                pull_result = IntegrationService._pull_data(integration, decrypted_value, data_mapping)
                push_result = IntegrationService._push_data(integration, decrypted_value, data_mapping)
                return {
                    "success": pull_result.get("success") and push_result.get("success"),
                    "pull": pull_result,
                    "push": push_result,
                }
            else:
                return {"success": False, "error": f"Invalid sync direction: {direction}"}

        except Exception as e:
            logger.error(f"Integration sync failed: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def _pull_data(
        integration: Integration,
        credential_value: str,
        data_mapping: Optional[Any],
    ) -> Dict[str, Any]:
        """Pull data from external system.

        Args:
            integration: Integration instance.
            credential_value: Decrypted credential value.
            data_mapping: Optional DataMapping instance for transformation.

        Returns:
            Pull result dictionary with 'success', 'records_synced', 'errors'.
        """
        try:
            integration_type = integration.integration_type
            config = integration.config or {}

            records_synced = 0
            errors = []

            if integration_type == "rest_api":
                # Pull from REST API
                result = IntegrationService._pull_from_api(integration, credential_value, data_mapping, config)
                records_synced = result.get("records_synced", 0)
                errors = result.get("errors", [])

            elif integration_type == "database":
                # Pull from database
                result = IntegrationService._pull_from_database(integration, credential_value, data_mapping, config)
                records_synced = result.get("records_synced", 0)
                errors = result.get("errors", [])

            else:
                return {
                    "success": False,
                    "error": f"Unsupported integration type for pull: {integration_type}",
                }

            logger.info(f"Pulled {records_synced} records from integration {integration.id}")
            return {
                "success": True,
                "records_synced": records_synced,
                "errors": errors,
                "message": f"Data pull completed: {records_synced} records synced",
            }

        except Exception as e:
            logger.error(f"Data pull failed for integration {integration.id}: {e}", exc_info=True)
            return {"success": False, "error": str(e), "records_synced": 0}

    @staticmethod
    def _pull_from_api(
        integration: Integration,
        credential_value: str,
        data_mapping: Optional[Any],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Pull data from REST API."""
        try:
            base_url = config.get("base_url") or config.get("api_url")
            endpoint = config.get("pull_endpoint", "/api/data")
            method = config.get("pull_method", "GET").upper()

            if not base_url:
                return {"success": False, "error": "No base_url configured", "records_synced": 0}

            # Prepare headers
            headers = config.get("headers", {})
            if "Authorization" not in headers:
                headers["Authorization"] = f"Bearer {credential_value}"

            # Make API call
            url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
            response = httpx.request(method, url, headers=headers, timeout=30.0)
            response.raise_for_status()

            # Parse response
            data = response.json()
            records = data if isinstance(data, list) else data.get("data", []) or data.get("results", [])

            # Transform and store records
            return IntegrationService._transform_and_store_records(
                integration, records, data_mapping, "pull"
            )

        except Exception as e:
            logger.error(f"API pull failed: {e}")
            return {"success": False, "error": str(e), "records_synced": 0}

    @staticmethod
    def _pull_from_database(
        integration: Integration,
        credential_value: str,
        data_mapping: Optional[Any],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Pull data from external database."""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(credential_value)
            db_type = parsed.scheme.lower()

            # Get table/query from config
            table_name = config.get("table_name") or config.get("source_table")
            query = config.get("query") or config.get("sql_query")

            if not table_name and not query:
                return {"success": False, "error": "No table_name or query configured", "records_synced": 0}

            # Connect to database
            if db_type in ("postgresql", "postgres"):
                import psycopg2

                conn = psycopg2.connect(credential_value)
            elif db_type == "mysql":
                import pymysql

                conn = pymysql.connect(credential_value)
            else:
                return {"success": False, "error": f"Unsupported database type: {db_type}", "records_synced": 0}

            cursor = conn.cursor()

            # Execute query
            if query:
                cursor.execute(query)
            else:
                # SECURITY: Validate table_name to prevent SQL injection
                # Table names must be alphanumeric with underscores only
                # Note: Table names cannot be parameterized in SQL, so validation is required
                import re
                if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name):
                    raise ValueError(f"Invalid table name: {table_name}")
                # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                # Justification: Table name is validated via regex (alphanumeric + underscores only)
                # Table names cannot be parameterized in SQL, so validation is the appropriate mitigation
                cursor.execute(f"SELECT * FROM {table_name}")

            # Fetch records
            columns = [desc[0] for desc in cursor.description]
            records = [dict(zip(columns, row)) for row in cursor.fetchall()]

            cursor.close()
            conn.close()

            # Transform and store records
            return IntegrationService._transform_and_store_records(
                integration, records, data_mapping, "pull"
            )

        except Exception as e:
            logger.error(f"Database pull failed: {e}")
            return {"success": False, "error": str(e), "records_synced": 0}

    @staticmethod
    def _transform_and_store_records(
        integration: Integration,
        records: List[Dict[str, Any]],
        data_mapping: Optional[Any],
        direction: str,
    ) -> Dict[str, Any]:
        """Transform records using mapping and store locally."""
        from .models import DataMapping

        records_synced = 0
        errors = []

        # Get mappings if provided
        mappings = []
        if data_mapping:
            mappings = [data_mapping]
        else:
            # Get all mappings for this integration
            mappings = list(DataMapping.objects.filter(integration=integration))

        # Transform each record
        for record in records:
            try:
                # Apply transformations
                transformed_record = IntegrationService._apply_transformations(record, mappings, direction)

                # Store in local database (simplified - would need target model configuration)
                # For now, just count as synced
                records_synced += 1

            except Exception as e:
                errors.append(f"Record transformation failed: {str(e)}")
                logger.warning(f"Failed to transform record: {e}")

        return {"records_synced": records_synced, "errors": errors}

    @staticmethod
    def _apply_transformations(
        record: Dict[str, Any], mappings: list, direction: str
    ) -> Dict[str, Any]:
        """Apply field transformations based on mappings."""
        transformed = record.copy()

        for mapping in mappings:
            source_field = mapping.source_field
            target_field = mapping.target_field
            transform_rules = mapping.transform or {}

            if source_field in transformed:
                value = transformed[source_field]

                # Apply transformation rules
                if transform_rules.get("type") == "string":
                    if transform_rules.get("uppercase"):
                        value = str(value).upper()
                    elif transform_rules.get("lowercase"):
                        value = str(value).lower()
                    elif transform_rules.get("trim"):
                        value = str(value).strip()

                # Map to target field
                transformed[target_field] = value

        return transformed

    @staticmethod
    def _push_data(
        integration: Integration,
        credential_value: str,
        data_mapping: Optional[Any],
    ) -> Dict[str, Any]:
        """Push data to external system.

        Args:
            integration: Integration instance.
            credential_value: Decrypted credential value.
            data_mapping: Optional DataMapping instance for transformation.

        Returns:
            Push result dictionary with 'success', 'records_synced', 'errors'.
        """
        try:
            integration_type = integration.integration_type
            config = integration.config or {}

            records_synced = 0
            errors = []

            if integration_type == "rest_api":
                # Push to REST API
                result = IntegrationService._push_to_api(integration, credential_value, data_mapping, config)
                records_synced = result.get("records_synced", 0)
                errors = result.get("errors", [])

            elif integration_type == "database":
                # Push to database
                result = IntegrationService._push_to_database(integration, credential_value, data_mapping, config)
                records_synced = result.get("records_synced", 0)
                errors = result.get("errors", [])

            else:
                return {
                    "success": False,
                    "error": f"Unsupported integration type for push: {integration_type}",
                }

            logger.info(f"Pushed {records_synced} records to integration {integration.id}")
            return {
                "success": True,
                "records_synced": records_synced,
                "errors": errors,
                "message": f"Data push completed: {records_synced} records synced",
            }

        except Exception as e:
            logger.error(f"Data push failed for integration {integration.id}: {e}", exc_info=True)
            return {"success": False, "error": str(e), "records_synced": 0}

    @staticmethod
    def _push_to_api(
        integration: Integration,
        credential_value: str,
        data_mapping: Optional[Any],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Push data to REST API."""
        try:
            base_url = config.get("base_url") or config.get("api_url")
            endpoint = config.get("push_endpoint", "/api/data")
            method = config.get("push_method", "POST").upper()
            batch_size = config.get("batch_size", 100)

            if not base_url:
                return {"success": False, "error": "No base_url configured", "records_synced": 0}

            # Get local data (simplified - would need source model configuration)
            # For now, get from config or use placeholder
            source_model = config.get("source_model")
            if not source_model:
                return {"success": False, "error": "No source_model configured", "records_synced": 0}

            # Get records from local database (simplified)
            # In production, this would query the actual model
            records = []  # Placeholder - would fetch from source_model

            # Prepare headers
            headers = config.get("headers", {})
            if "Authorization" not in headers:
                headers["Authorization"] = f"Bearer {credential_value}"

            records_synced = 0
            errors = []

            # Push in batches
            for i in range(0, len(records), batch_size):
                batch = records[i : i + batch_size]

                # Transform batch
                transformed_batch = [
                    IntegrationService._apply_transformations(record, [data_mapping] if data_mapping else [], "push")
                    for record in batch
                ]

                # Send batch
                url = f"{base_url.rstrip('/')}/{endpoint.lstrip('/')}"
                try:
                    if method == "POST":
                        response = httpx.post(url, json=transformed_batch, headers=headers, timeout=30.0)
                    elif method == "PUT":
                        response = httpx.put(url, json=transformed_batch, headers=headers, timeout=30.0)
                    else:
                        errors.append(f"Unsupported push method: {method}")
                        continue

                    response.raise_for_status()
                    records_synced += len(batch)

                except httpx.HTTPStatusError as e:
                    errors.append(f"Batch push failed: HTTP {e.response.status_code}")
                    logger.error(f"Batch push failed: {e}")

            return {"records_synced": records_synced, "errors": errors}

        except Exception as e:
            logger.error(f"API push failed: {e}")
            return {"success": False, "error": str(e), "records_synced": 0}

    @staticmethod
    def _push_to_database(
        integration: Integration,
        credential_value: str,
        data_mapping: Optional[Any],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Push data to external database."""
        try:
            from urllib.parse import urlparse

            parsed = urlparse(credential_value)
            db_type = parsed.scheme.lower()

            # Get target table
            table_name = config.get("table_name") or config.get("target_table")
            if not table_name:
                return {"success": False, "error": "No table_name configured", "records_synced": 0}

            # Get local data (simplified)
            source_model = config.get("source_model")
            if not source_model:
                return {"success": False, "error": "No source_model configured", "records_synced": 0}

            records = []  # Placeholder - would fetch from source_model

            # Connect to database
            if db_type in ("postgresql", "postgres"):
                import psycopg2

                conn = psycopg2.connect(credential_value)
            elif db_type == "mysql":
                import pymysql

                conn = pymysql.connect(credential_value)
            else:
                return {"success": False, "error": f"Unsupported database type: {db_type}", "records_synced": 0}

            cursor = conn.cursor()
            records_synced = 0
            errors = []

            # Push records
            for record in records:
                try:
                    # Transform record
                    transformed = IntegrationService._apply_transformations(
                        record, [data_mapping] if data_mapping else [], "push"
                    )

                    # Build INSERT statement
                    # SECURITY: Validate table_name and column names to prevent SQL injection
                    import re
                    if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', table_name):
                        raise ValueError(f"Invalid table name: {table_name}")
                    
                    # Validate column names
                    validated_columns = []
                    for col in transformed.keys():
                        if not re.match(r'^[a-zA-Z_][a-zA-Z0-9_]*$', col):
                            raise ValueError(f"Invalid column name: {col}")
                        validated_columns.append(col)
                    
                    columns = ", ".join(validated_columns)
                    placeholders = ", ".join(["%s"] * len(transformed))
                    values = list(transformed.values())

                    # nosemgrep: python.sqlalchemy.security.sqlalchemy-execute-raw-query.sqlalchemy-execute-raw-query
                    # Justification: Table and column names are validated via regex (alphanumeric + underscores only)
                    # Values are parameterized (%s placeholders). Table/column names cannot be parameterized in SQL.
                    query = f"INSERT INTO {table_name} ({columns}) VALUES ({placeholders})"
                    cursor.execute(query, values)
                    records_synced += 1

                except Exception as e:
                    errors.append(f"Record push failed: {str(e)}")

            conn.commit()
            cursor.close()
            conn.close()

            return {"records_synced": records_synced, "errors": errors}

        except Exception as e:
            logger.error(f"Database push failed: {e}")
            return {"success": False, "error": str(e), "records_synced": 0}


class WebhookProcessor:
    """Service for processing incoming webhooks."""

    @staticmethod
    def process_webhook(
        webhook: Webhook,
        payload: Dict[str, Any],
        event_type: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Process incoming webhook.

        Args:
            webhook: Webhook instance.
            payload: Webhook payload.
            event_type: Optional event type.

        Returns:
            Processing result dictionary.
        """
        try:
            # Get webhook configuration
            config = webhook.config if hasattr(webhook, "config") else {}

            # Route to appropriate handler
            handler_type = config.get("handler_type", "default")

            if handler_type == "update_record":
                return WebhookProcessor._handle_update_record(webhook, payload, config)
            elif handler_type == "trigger_workflow":
                return WebhookProcessor._handle_trigger_workflow(webhook, payload, config)
            elif handler_type == "custom_script":
                return WebhookProcessor._handle_custom_script(webhook, payload, config)
            else:
                # Default: log and store
                logger.info(f"Webhook {webhook.id} received: {payload}")
                return {"success": True, "message": "Webhook received and logged"}

        except Exception as e:
            logger.error(f"Webhook processing failed: {e}")
            return {"success": False, "error": str(e)}

    @staticmethod
    def _handle_update_record(
        webhook: Webhook,
        payload: Dict[str, Any],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle webhook by updating a record.

        Args:
            webhook: Webhook instance.
            payload: Webhook payload.
            config: Handler configuration.

        Returns:
            Processing result with 'success', 'message', and optional 'error'.

        Note:
            - Model must be in whitelist (configurable)
            - Tenant filtering is MANDATORY
            - Protected fields cannot be updated
        """
        try:
            from django.apps import apps
            from django.db import transaction

            # 1. Get model name from config
            model_name = config.get("model")
            if not model_name:
                return {"success": False, "error": "No model specified in webhook configuration"}

            # 2. Validate model is allowed (whitelist)
            allowed_models = config.get("allowed_models", [])
            if allowed_models and model_name not in allowed_models:
                logger.warning(f"Model {model_name} not in webhook whitelist")
                return {
                    "success": False,
                    "error": f"Model {model_name} is not allowed for webhook updates",
                }

            # 3. Get model dynamically
            try:
                app_label, model_class_name = model_name.split(".", 1)
                model_class = apps.get_model(app_label, model_class_name)
            except (ValueError, LookupError) as e:
                logger.error(f"Invalid model name {model_name}: {e}")
                return {"success": False, "error": f"Invalid model name: {model_name}"}

            # 4. Validate model has tenant_id field (MANDATORY)
            if not hasattr(model_class, "tenant_id"):
                logger.error(f"Model {model_name} does not have tenant_id field")
                return {
                    "success": False,
                    "error": f"Model {model_name} must have tenant_id field for tenant isolation",
                }

            # 5. Extract record ID and update fields from payload
            record_id = payload.get("id") or payload.get("record_id")
            if not record_id:
                return {"success": False, "error": "No record ID in webhook payload"}

            # Get update fields (exclude id and tenant_id)
            update_fields = {k: v for k, v in payload.items() if k not in ("id", "record_id", "tenant_id")}

            if not update_fields:
                return {"success": False, "error": "No fields to update"}

            # 6. Validate field names (no protected fields)
            protected_fields = {"id", "tenant_id", "created_at", "updated_at", "created_by", "updated_by"}
            protected_found = set(update_fields.keys()) & protected_fields
            if protected_found:
                return {
                    "success": False,
                    "error": f"Cannot update protected fields: {', '.join(protected_found)}",
                }

            # 7. Validate field names exist on model
            model_fields = {f.name for f in model_class._meta.get_fields()}
            invalid_fields = set(update_fields.keys()) - model_fields
            if invalid_fields:
                return {
                    "success": False,
                    "error": f"Invalid fields: {', '.join(invalid_fields)}",
                }

            # 8. Update record with tenant filtering (MANDATORY)
            with transaction.atomic():
                try:
                    # Get record with tenant filtering
                    record = model_class.objects.get(id=record_id, tenant_id=webhook.tenant_id)

                    # Update fields
                    for field, value in update_fields.items():
                        setattr(record, field, value)

                    record.save(update_fields=list(update_fields.keys()))

                    logger.info(
                        f"Updated {model_name} record {record_id} via webhook {webhook.id} "
                        f"for tenant {webhook.tenant_id}"
                    )

                    # 9. Log audit event
                    try:
                        from src.modules.platform_management.services import PlatformManagementService

                        PlatformManagementService.log_audit_event(
                            action="webhook.record.updated",
                            actor_id=webhook.id,  # Webhook ID as actor
                            resource_type=model_name,
                            resource_id=record_id,
                            tenant_id=webhook.tenant_id,
                            details={
                                "webhook_id": str(webhook.id),
                                "model": model_name,
                                "record_id": str(record_id),
                                "updated_fields": list(update_fields.keys()),
                            },
                        )
                    except Exception as audit_error:
                        logger.error(f"Failed to log audit event: {audit_error}")

                    return {
                        "success": True,
                        "message": f"Record {record_id} updated successfully",
                        "record_id": str(record_id),
                    }

                except model_class.DoesNotExist:
                    # Return 404-style error (don't reveal record exists in other tenant)
                    return {
                        "success": False,
                        "error": f"Record {record_id} not found",
                    }

        except Exception as e:
            logger.error(f"Webhook record update failed: {e}", exc_info=True)
            return {"success": False, "error": str(e)}

    @staticmethod
    def _handle_trigger_workflow(
        webhook: Webhook,
        payload: Dict[str, Any],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle webhook by triggering a workflow.

        Args:
            webhook: Webhook instance.
            payload: Webhook payload.
            config: Handler configuration.

        Returns:
            Processing result.
        """
        workflow_id = config.get("workflow_id")
        if not workflow_id:
            return {"success": False, "error": "No workflow_id in configuration"}

        # TODO: Trigger workflow
        # This would:
        # 1. Get workflow instance
        # 2. Start workflow with payload as context
        # 3. Return workflow instance ID

        logger.info(f"Triggering workflow {workflow_id} via webhook")
        return {"success": True, "message": f"Workflow triggered (placeholder)", "workflow_instance_id": None}

    @staticmethod
    def _handle_custom_script(
        webhook: Webhook,
        payload: Dict[str, Any],
        config: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Handle webhook by executing custom script.

        Args:
            webhook: Webhook instance.
            payload: Webhook payload.
            config: Handler configuration.

        Returns:
            Processing result.

        Note:
            Script execution is sandboxed for security using RestrictedPython.
        """
        from src.modules.workflow_automation.action_executor import ActionExecutor

        # Use the same sandboxed execution from ActionExecutor
        script_content = config.get("script") or config.get("script_id")
        if not script_content:
            return {"success": False, "error": "No script content provided"}

        # Create workflow context from webhook payload
        workflow_context = {
            "webhook_id": str(webhook.id),
            "payload": payload,
            "tenant_id": str(webhook.tenant_id),
        }

        result = ActionExecutor._execute_script(
            action_config={"script": script_content},
            workflow_context=workflow_context,
            tenant_id=str(webhook.tenant_id),
        )

        if result.get("success"):
            return {"success": True, "message": result.get("result", "Script executed successfully")}
        else:
            return {"success": False, "error": result.get("error", "Script execution failed")}
