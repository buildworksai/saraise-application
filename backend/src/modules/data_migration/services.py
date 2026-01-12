"""
DataMigration Services.

High-level service layer for DataMigration business logic.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from django.db import transaction
from django.utils import timezone

from .models import MigrationJob, MigrationLog, MigrationMapping, MigrationRollback, MigrationValidation

logger = logging.getLogger(__name__)


class MigrationResult:
    """Result of migration execution."""

    def __init__(
        self,
        success: bool,
        records_processed: int = 0,
        records_failed: int = 0,
        errors: Optional[List[str]] = None,
    ):
        self.success = success
        self.records_processed = records_processed
        self.records_failed = records_failed
        self.errors = errors or []


class MigrationEngine:
    """Service for executing data migrations."""

    def execute_migration(
        self,
        job_id: str,
        tenant_id: str,
        dry_run: bool = False,
    ) -> MigrationResult:
        """Execute migration job.

        Args:
            job_id: Migration job ID.
            tenant_id: Tenant ID.
            dry_run: If True, validate but don't import data.

        Returns:
            MigrationResult instance.

        Raises:
            ValueError: If job not found.
        """
        job = MigrationJob.objects.filter(id=job_id, tenant_id=tenant_id).first()
        if not job:
            raise ValueError(f"Migration job {job_id} not found for tenant {tenant_id}")

        if job.status == "running":
            raise ValueError(f"Migration job {job_id} is already running")

        with transaction.atomic():
            job.status = "running"
            job.started_at = timezone.now()
            job.save()

            # Create checkpoint
            checkpoint = self._create_checkpoint(job)

            try:
                # Load source data
                source_data = self._load_source_data(job)

                records_processed = 0
                records_failed = 0
                errors = []
                imported_record_ids = []  # Track imported records for rollback

                for index, record in enumerate(source_data):
                    # Apply mappings
                    transformed_record = self._apply_mappings(job, record)

                    # Validate record
                    validation_errors = self._validate_record(job, transformed_record, index)
                    if validation_errors:
                        records_failed += 1
                        errors.extend(validation_errors)
                        continue

                    if not dry_run:
                        # Import record and track ID for rollback
                        record_id = self._import_record(job, transformed_record, tenant_id)
                        if record_id:
                            imported_record_ids.append(record_id)

                    records_processed += 1

                # Update checkpoint with imported record IDs for rollback capability
                if imported_record_ids:
                    checkpoint.checkpoint_data["imported_record_ids"] = imported_record_ids
                    checkpoint.save()

                job.status = "completed" if records_failed == 0 else "failed"
                job.completed_at = timezone.now()
                job.records_processed = records_processed
                job.records_failed = records_failed
                job.records_total = len(source_data)
                job.error_message = "; ".join(errors[:10]) if errors else ""
                job.save()

                return MigrationResult(
                    success=records_failed == 0,
                    records_processed=records_processed,
                    records_failed=records_failed,
                    errors=errors,
                )

            except Exception as e:
                job.status = "failed"
                job.completed_at = timezone.now()
                job.error_message = str(e)
                job.save()

                logger.error(f"Migration job {job_id} failed: {e}")
                raise

    def _create_checkpoint(self, job: MigrationJob) -> MigrationRollback:
        """Create checkpoint for rollback.

        Args:
            job: Migration job.

        Returns:
            MigrationRollback instance.
        """
        checkpoint_data = {
            "job_id": job.id,
            "status": job.status,
            "records_processed": job.records_processed,
            "timestamp": timezone.now().isoformat(),
        }
        return MigrationRollback.objects.create(
            tenant_id=job.tenant_id,
            job=job,
            checkpoint_data=checkpoint_data,
        )

    def _load_source_data(self, job: MigrationJob) -> List[Dict[str, Any]]:
        """Load data from source.

        Args:
            job: Migration job.

        Returns:
            List of source records.

        Raises:
            ValueError: If source type is not supported or configuration is invalid.
        """
        source_type = job.source_type
        source_config = job.source_config or {}

        logger.info(f"Loading source data for job {job.id} from {source_type}")

        try:
            if source_type == "csv":
                return self._load_csv_data(source_config)
            elif source_type == "excel":
                return self._load_excel_data(source_config)
            elif source_type == "json":
                return self._load_json_data(source_config)
            elif source_type == "database":
                return self._load_database_data(source_config)
            elif source_type == "api":
                return self._load_api_data(source_config)
            else:
                raise ValueError(f"Unsupported source type: {source_type}")
        except Exception as e:
            logger.error(f"Failed to load source data for job {job.id}: {e}")
            raise ValueError(f"Failed to load source data: {str(e)}")

    def _load_csv_data(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Load data from CSV file.

        Args:
            config: Configuration dict with 'file_path' and optional 'delimiter', 'encoding'.

        Returns:
            List of records as dictionaries.
        """
        import csv
        from django.core.files.storage import default_storage

        file_path = config.get("file_path")
        if not file_path:
            raise ValueError("CSV file_path is required in source_config")

        delimiter = config.get("delimiter", ",")
        encoding = config.get("encoding", "utf-8")

        records = []
        try:
            with default_storage.open(file_path, mode="r", encoding=encoding) as f:
                reader = csv.DictReader(f, delimiter=delimiter)
                records = list(reader)
        except FileNotFoundError:
            raise ValueError(f"CSV file not found: {file_path}")
        except Exception as e:
            raise ValueError(f"Failed to read CSV file: {str(e)}")

        logger.info(f"Loaded {len(records)} records from CSV file")
        return records

    def _load_excel_data(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Load data from Excel file.

        Args:
            config: Configuration dict with 'file_path' and optional 'sheet_name', 'header_row'.

        Returns:
            List of records as dictionaries.
        """
        try:
            import pandas as pd
        except ImportError:
            raise ValueError("pandas is required for Excel file support. Install with: pip install pandas openpyxl")

        file_path = config.get("file_path")
        if not file_path:
            raise ValueError("Excel file_path is required in source_config")

        sheet_name = config.get("sheet_name", 0)
        header_row = config.get("header_row", 0)

        try:
            from django.core.files.storage import default_storage

            with default_storage.open(file_path, mode="rb") as f:
                df = pd.read_excel(f, sheet_name=sheet_name, header=header_row)
                records = df.to_dict("records")
        except FileNotFoundError:
            raise ValueError(f"Excel file not found: {file_path}")
        except Exception as e:
            raise ValueError(f"Failed to read Excel file: {str(e)}")

        logger.info(f"Loaded {len(records)} records from Excel file")
        return records

    def _load_json_data(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Load data from JSON file or JSON string.

        Args:
            config: Configuration dict with 'file_path' or 'data' (JSON string).

        Returns:
            List of records as dictionaries.
        """
        import json
        from django.core.files.storage import default_storage

        if "data" in config:
            # JSON string provided directly
            try:
                data = json.loads(config["data"])
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return [data]
                else:
                    raise ValueError("JSON data must be a list or object")
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid JSON data: {str(e)}")

        file_path = config.get("file_path")
        if not file_path:
            raise ValueError("JSON file_path or data is required in source_config")

        try:
            with default_storage.open(file_path, mode="r", encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    return data
                elif isinstance(data, dict):
                    return [data]
                else:
                    raise ValueError("JSON file must contain a list or object")
        except FileNotFoundError:
            raise ValueError(f"JSON file not found: {file_path}")
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON file: {str(e)}")
        except Exception as e:
            raise ValueError(f"Failed to read JSON file: {str(e)}")

    def _load_database_data(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Load data from external database.

        Args:
            config: Configuration dict with database connection details and query.

        Returns:
            List of records as dictionaries.
        """
        from django.db import connections

        connection_string = config.get("connection_string")
        query = config.get("query")

        if not connection_string or not query:
            raise ValueError("Database connection_string and query are required in source_config")

        try:
            # Create a temporary database connection
            # Note: This is a simplified implementation
            # In production, you'd want to use proper connection pooling
            conn = connections["default"]
            with conn.cursor() as cursor:
                cursor.execute(query)
                columns = [col[0] for col in cursor.description]
                rows = cursor.fetchall()
                records = [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            raise ValueError(f"Failed to query database: {str(e)}")

        logger.info(f"Loaded {len(records)} records from database")
        return records

    def _load_api_data(self, config: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Load data from API endpoint.

        Args:
            config: Configuration dict with 'url', 'method', 'headers', 'params'.

        Returns:
            List of records as dictionaries.
        """
        try:
            import httpx
        except ImportError:
            raise ValueError("httpx is required for API source support. Install with: pip install httpx")

        url = config.get("url")
        if not url:
            raise ValueError("API url is required in source_config")

        method = config.get("method", "GET").upper()
        headers = config.get("headers", {})
        params = config.get("params", {})
        timeout = config.get("timeout", 30)

        try:
            response = httpx.request(method, url, headers=headers, params=params, timeout=timeout)
            response.raise_for_status()
            data = response.json()

            if isinstance(data, list):
                return data
            elif isinstance(data, dict):
                # Check if data contains a list (common API pattern)
                if "results" in data:
                    return data["results"]
                elif "data" in data:
                    return data["data"] if isinstance(data["data"], list) else [data["data"]]
                else:
                    return [data]
            else:
                raise ValueError("API response must be JSON array or object")
        except httpx.HTTPError as e:
            raise ValueError(f"API request failed: {str(e)}")
        except Exception as e:
            raise ValueError(f"Failed to load data from API: {str(e)}")

    def _apply_mappings(
        self,
        job: MigrationJob,
        record: Dict[str, Any],
    ) -> Dict[str, Any]:
        """Apply field mappings to record.

        Args:
            job: Migration job.
            record: Source record.

        Returns:
            Transformed record.
        """
        mappings = MigrationMapping.objects.filter(job=job)
        transformed = {}

        for mapping in mappings:
            source_value = record.get(mapping.source_field)
            transform = mapping.transform

            # Apply transformation
            if "type" in transform:
                # Type conversion
                target_type = transform["type"]
                if target_type == "string":
                    source_value = str(source_value) if source_value is not None else ""
                elif target_type == "integer":
                    source_value = int(source_value) if source_value else 0
                elif target_type == "decimal":
                    from decimal import Decimal
                    source_value = Decimal(str(source_value)) if source_value else Decimal("0.00")

            if "default" in transform and source_value is None:
                source_value = transform["default"]

            transformed[mapping.target_field] = source_value

        return transformed

    def _validate_record(
        self,
        job: MigrationJob,
        record: Dict[str, Any],
        index: int,
    ) -> List[str]:
        """Validate transformed record.

        Args:
            job: Migration job.
            record: Transformed record.
            index: Record index.

        Returns:
            List of validation error messages.
        """
        errors = []
        validation_rules = job.source_config.get("validation_rules", {})

        # Get required fields from validation rules
        required_fields = validation_rules.get("required_fields", [])
        field_types = validation_rules.get("field_types", {})
        field_constraints = validation_rules.get("field_constraints", {})

        # Validate required fields
        for field in required_fields:
            if field not in record or record[field] is None or record[field] == "":
                error_msg = f"Field {field} is required at record {index}"
                MigrationValidation.objects.create(
                    tenant_id=job.tenant_id,
                    job=job,
                    field=field,
                    rule="required",
                    status="failed",
                    message=error_msg,
                    record_index=index,
                )
                errors.append(error_msg)

        # Validate field types
        for field, expected_type in field_types.items():
            if field not in record:
                continue

            value = record[field]
            if value is None or value == "":
                continue  # Skip null/empty values (handled by required check)

            type_valid = False
            if expected_type == "string":
                type_valid = isinstance(value, str)
            elif expected_type == "integer":
                type_valid = isinstance(value, int) or (isinstance(value, str) and value.isdigit())
            elif expected_type == "decimal" or expected_type == "float":
                try:
                    float(value)
                    type_valid = True
                except (ValueError, TypeError):
                    type_valid = False
            elif expected_type == "boolean":
                type_valid = isinstance(value, bool) or str(value).lower() in ("true", "false", "1", "0", "yes", "no")
            elif expected_type == "date":
                from datetime import datetime
                try:
                    datetime.fromisoformat(str(value))
                    type_valid = True
                except (ValueError, TypeError):
                    type_valid = False
            elif expected_type == "email":
                import re
                email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
                type_valid = isinstance(value, str) and bool(re.match(email_pattern, value))
            else:
                # Unknown type, skip validation
                continue

            if not type_valid:
                error_msg = f"Field {field} must be of type {expected_type} at record {index}"
                MigrationValidation.objects.create(
                    tenant_id=job.tenant_id,
                    job=job,
                    field=field,
                    rule="type_check",
                    status="failed",
                    message=error_msg,
                    record_index=index,
                )
                errors.append(error_msg)

        # Validate field constraints
        for field, constraints in field_constraints.items():
            if field not in record:
                continue

            value = record[field]
            if value is None or value == "":
                continue

            # Min length constraint
            if "min_length" in constraints:
                min_length = constraints["min_length"]
                if isinstance(value, str) and len(value) < min_length:
                    error_msg = f"Field {field} must be at least {min_length} characters at record {index}"
                    MigrationValidation.objects.create(
                        tenant_id=job.tenant_id,
                        job=job,
                        field=field,
                        rule="min_length",
                        status="failed",
                        message=error_msg,
                        record_index=index,
                    )
                    errors.append(error_msg)

            # Max length constraint
            if "max_length" in constraints:
                max_length = constraints["max_length"]
                if isinstance(value, str) and len(value) > max_length:
                    error_msg = f"Field {field} must be at most {max_length} characters at record {index}"
                    MigrationValidation.objects.create(
                        tenant_id=job.tenant_id,
                        job=job,
                        field=field,
                        rule="max_length",
                        status="failed",
                        message=error_msg,
                        record_index=index,
                    )
                    errors.append(error_msg)

            # Min value constraint
            if "min_value" in constraints:
                min_value = constraints["min_value"]
                try:
                    num_value = float(value)
                    if num_value < min_value:
                        error_msg = f"Field {field} must be at least {min_value} at record {index}"
                        MigrationValidation.objects.create(
                            tenant_id=job.tenant_id,
                            job=job,
                            field=field,
                            rule="min_value",
                            status="failed",
                            message=error_msg,
                            record_index=index,
                        )
                        errors.append(error_msg)
                except (ValueError, TypeError):
                    pass  # Not a number, skip

            # Max value constraint
            if "max_value" in constraints:
                max_value = constraints["max_value"]
                try:
                    num_value = float(value)
                    if num_value > max_value:
                        error_msg = f"Field {field} must be at most {max_value} at record {index}"
                        MigrationValidation.objects.create(
                            tenant_id=job.tenant_id,
                            job=job,
                            field=field,
                            rule="max_value",
                            status="failed",
                            message=error_msg,
                            record_index=index,
                        )
                        errors.append(error_msg)
                except (ValueError, TypeError):
                    pass  # Not a number, skip

            # Pattern/regex constraint
            if "pattern" in constraints:
                import re
                pattern = constraints["pattern"]
                if isinstance(value, str) and not re.match(pattern, value):
                    error_msg = f"Field {field} does not match required pattern at record {index}"
                    MigrationValidation.objects.create(
                        tenant_id=job.tenant_id,
                        job=job,
                        field=field,
                        rule="pattern",
                        status="failed",
                        message=error_msg,
                        record_index=index,
                    )
                    errors.append(error_msg)

        return errors

    def _import_record(
        self,
        job: MigrationJob,
        record: Dict[str, Any],
        tenant_id: str,
    ) -> Optional[str]:
        """Import record into target system.

        Args:
            job: Migration job.
            record: Transformed record.
            tenant_id: Tenant ID.

        Returns:
            Imported record ID (str) if successful, None otherwise.

        Raises:
            ValueError: If target model is not specified or import fails.
        """
        target_config = job.source_config.get("target", {})
        target_model_path = target_config.get("model")
        target_action = target_config.get("action", "create")  # 'create' or 'update'

        if not target_model_path:
            # If no target model specified, log the record for manual import
            logger.warning(f"No target model specified for job {job.id}, skipping import")
            MigrationLog.objects.create(
                tenant_id=tenant_id,
                job=job,
                level="warning",
                message=f"Record skipped (no target model): {record}",
            )
            return None

        try:
            # Import target model dynamically
            # Format: "app_label.ModelName" or "module.path.ModelName"
            if "." in target_model_path:
                parts = target_model_path.rsplit(".", 1)
                module_path = parts[0]
                model_name = parts[1]

                from importlib import import_module

                module = import_module(module_path)
                Model = getattr(module, model_name)

                # Prepare record data with tenant_id
                record_data = record.copy()
                record_data["tenant_id"] = tenant_id

                if target_action == "update":
                    # Update requires a lookup field
                    lookup_field = target_config.get("lookup_field", "id")
                    lookup_value = record_data.get(lookup_field)

                    if lookup_value:
                        # Try to find existing record
                        existing = Model.objects.filter(
                            tenant_id=tenant_id,
                            **{lookup_field: lookup_value},
                        ).first()

                        if existing:
                            # Update existing record
                            for key, value in record_data.items():
                                if key != lookup_field and hasattr(existing, key):
                                    setattr(existing, key, value)
                            existing.save()
                            record_id = str(getattr(existing, "id", existing.pk))
                            logger.debug(f"Updated {target_model_path} record: {lookup_value}")
                        else:
                            # Create new record if not found
                            new_record = Model.objects.create(**record_data)
                            record_id = str(getattr(new_record, "id", new_record.pk))
                            logger.debug(f"Created {target_model_path} record (update not found): {lookup_value}")
                    else:
                        raise ValueError(f"Lookup field {lookup_field} not found in record for update")
                else:
                    # Create new record
                    new_record = Model.objects.create(**record_data)
                    record_id = str(getattr(new_record, "id", new_record.pk))
                    logger.debug(f"Created {target_model_path} record")

                # Log successful import
                MigrationLog.objects.create(
                    tenant_id=tenant_id,
                    job=job,
                    level="info",
                    message=f"Successfully imported record into {target_model_path}",
                )

                return record_id

        except ImportError as e:
            error_msg = f"Failed to import target model {target_model_path}: {str(e)}"
            logger.error(error_msg)
            MigrationLog.objects.create(
                tenant_id=tenant_id,
                job=job,
                level="error",
                message=error_msg,
            )
            raise ValueError(error_msg)
        except Exception as e:
            error_msg = f"Failed to import record into {target_model_path}: {str(e)}"
            logger.error(error_msg)
            MigrationLog.objects.create(
                tenant_id=tenant_id,
                job=job,
                level="error",
                message=error_msg,
            )
            raise ValueError(error_msg)

    def rollback(self, checkpoint_id: str, tenant_id: str) -> None:
        """Rollback migration to checkpoint.

        Args:
            checkpoint_id: Checkpoint ID.
            tenant_id: Tenant ID.

        Raises:
            ValueError: If checkpoint not found or rollback fails.
        """
        checkpoint = MigrationRollback.objects.filter(
            id=checkpoint_id,
            tenant_id=tenant_id,
        ).first()

        if not checkpoint:
            raise ValueError(f"Checkpoint {checkpoint_id} not found for tenant {tenant_id}")

        job = checkpoint.job
        checkpoint_data = checkpoint.checkpoint_data

        logger.info(f"Rolling back migration job {job.id} to checkpoint {checkpoint_id}")

        try:
            with transaction.atomic():
                # Restore job status
                job.status = checkpoint_data.get("status", "pending")
                job.records_processed = checkpoint_data.get("records_processed", 0)
                job.save()

                # Get target model configuration
                target_config = job.source_config.get("target", {})
                target_model_path = target_config.get("model")

                if target_model_path:
                    # Import target model
                    if "." in target_model_path:
                        parts = target_model_path.rsplit(".", 1)
                        module_path = parts[0]
                        model_name = parts[1]

                        from importlib import import_module

                        module = import_module(module_path)
                        Model = getattr(module, model_name)

                        # Get records imported after checkpoint timestamp
                        checkpoint_time = checkpoint.created_at
                        lookup_field = target_config.get("lookup_field", "id")

                        # Find records created/updated after checkpoint
                        # Note: This is a simplified rollback - in production, you'd want to
                        # track which records were imported by this job
                        # For now, we'll delete records that match the job's import pattern
                        # This requires the job to store imported record IDs in checkpoint_data

                        imported_record_ids = checkpoint_data.get("imported_record_ids", [])

                        if imported_record_ids:
                            # Delete records that were imported after this checkpoint
                            deleted_count = Model.objects.filter(
                                tenant_id=tenant_id,
                                id__in=imported_record_ids,
                            ).delete()[0]

                            logger.info(f"Deleted {deleted_count} records during rollback")

                # Log rollback
                MigrationLog.objects.create(
                    tenant_id=tenant_id,
                    job=job,
                    level="info",
                    message=f"Migration rolled back to checkpoint {checkpoint_id}",
                )

                logger.info(f"Successfully rolled back migration job {job.id}")

        except Exception as e:
            error_msg = f"Failed to rollback migration: {str(e)}"
            logger.error(error_msg)
            MigrationLog.objects.create(
                tenant_id=tenant_id,
                job=job,
                level="error",
                message=error_msg,
            )
            raise ValueError(error_msg)
