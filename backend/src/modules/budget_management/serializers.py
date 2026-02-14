"""
DRF Serializers for Budget Management module.
"""

from rest_framework import serializers

from .models import Budget, BudgetLine


class BudgetSerializer(serializers.ModelSerializer):
    """Budget serializer."""

    class Meta:
        model = Budget
        fields = [
            "id",
            "tenant_id",
            "budget_code",
            "budget_name",
            "fiscal_year",
            "start_date",
            "end_date",
            "status",
            "currency",
            "total_budget",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "total_budget", "created_at", "updated_at"]


class BudgetLineSerializer(serializers.ModelSerializer):
    """BudgetLine serializer."""

    budget_code = serializers.CharField(source="budget.budget_code", read_only=True)

    class Meta:
        model = BudgetLine
        fields = [
            "id",
            "tenant_id",
            "budget",
            "budget_code",
            "account_id",
            "account_code",
            "budget_amount",
            "actual_amount",
            "variance",
            "created_at",
            "updated_at",
        ]
        read_only_fields = ["id", "tenant_id", "variance", "created_at", "updated_at"]
