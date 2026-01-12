"""
Permissions Tests for DataMigration module.

Tests permission declarations and SoD actions.
"""
import pytest
from ..permissions import PERMISSIONS, SOD_ACTIONS


class TestDataMigrationPermissions:
    """Test DataMigration permission declarations."""

    def test_permissions_list_exists(self):
        """Test that PERMISSIONS list exists and is not empty."""
        assert PERMISSIONS is not None
        assert isinstance(PERMISSIONS, list)
        assert len(PERMISSIONS) > 0

    def test_permissions_format(self):
        """Test that permissions follow the correct format."""
        for perm in PERMISSIONS:
            assert isinstance(perm, str)
            assert "data_migration" in perm
            assert ":" in perm
            # Format: module.resource:action
            parts = perm.split(":")
            assert len(parts) == 2
            assert parts[1] in ["create", "read", "update", "delete", "activate", "deactivate"]

    def test_sod_actions_list_exists(self):
        """Test that SOD_ACTIONS list exists."""
        assert SOD_ACTIONS is not None
        assert isinstance(SOD_ACTIONS, list)

    def test_sod_actions_are_subset_of_permissions(self):
        """Test that SOD_ACTIONS are a subset of PERMISSIONS."""
        for sod_action in SOD_ACTIONS:
            assert sod_action in PERMISSIONS

    def test_sod_actions_include_critical_operations(self):
        """Test that SOD_ACTIONS include critical operations."""
        assert "data_migration.resource:create" in SOD_ACTIONS
        assert "data_migration.resource:delete" in SOD_ACTIONS
