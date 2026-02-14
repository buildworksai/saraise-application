"""
DRF Serializers for Business Intelligence module.
"""

from rest_framework import serializers

from .models import Dashboard, Report


class ReportSerializer(serializers.ModelSerializer):
    """Report serializer."""

    class Meta:
        model = Report
        fields = [
            "id",
            "tenant_id",
            "report_code",
            "report_name",
            "report_type",
            "query",
            "parameters",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]


class DashboardSerializer(serializers.ModelSerializer):
    """Dashboard serializer."""

    class Meta:
        model = Dashboard
        fields = [
            "id",
            "tenant_id",
            "dashboard_code",
            "dashboard_name",
            "layout",
            "is_active",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "created_at", "updated_at"]
