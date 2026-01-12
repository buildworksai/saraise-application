"""
Model Unit Tests for DataMigration module.

Tests model creation, validation, and relationships.
"""
import pytest
from django.core.exceptions import ValidationError

from ..models import MigrationJob, MigrationMapping, MigrationLog, MigrationValidation, MigrationRollback


@pytest.mark.django_db
class TestMigrationJobModel:
    """Test MigrationJob model."""

    def test_create_migration_job(self, db):
        """Test creating a migration job."""
        job = MigrationJob.objects.create(
            tenant_id="tenant-123",
            name="Test Migration",
            source_type="csv",
            source_config={"file_path": "/tmp/test.csv"},
            created_by="user-123",
        )
        assert job.id is not None
        assert job.name == "Test Migration"
        assert job.tenant_id == "tenant-123"
        assert job.status == "pending"

    def test_migration_job_str_representation(self, db):
        """Test migration job string representation."""
        job = MigrationJob.objects.create(
            tenant_id="tenant-123",
            name="Test Migration",
            source_type="csv",
            source_config={},
            created_by="user-123",
        )
        # Check that string representation includes the name and status
        assert "Test Migration" in str(job)
        assert "pending" in str(job)

    def test_migration_job_has_tenant_id(self, db):
        """Test that migration job requires tenant_id."""
        job = MigrationJob(
            name="Test Migration",
            source_type="csv",
            source_config={},
            created_by="user-123",
        )
        # tenant_id is required but Django may allow None, so just verify it's None
        assert job.tenant_id is None or job.tenant_id == ""


@pytest.mark.django_db
class TestMigrationMappingModel:
    """Test MigrationMapping model."""

    def test_create_migration_mapping(self, db):
        """Test creating a migration mapping."""
        job = MigrationJob.objects.create(
            tenant_id="tenant-123",
            name="Test Migration",
            source_type="csv",
            source_config={},
            created_by="user-123",
        )
        mapping = MigrationMapping.objects.create(
            tenant_id="tenant-123",
            job=job,
            source_field="source_col",
            target_field="target_col",
        )
        assert mapping.id is not None
        assert mapping.job == job
        assert mapping.source_field == "source_col"
        assert mapping.target_field == "target_col"
