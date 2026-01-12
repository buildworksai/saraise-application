"""
DRF Serializers for CRM module.

Provides request/response validation for all models.
"""

from datetime import date

from django.utils import timezone
from rest_framework import serializers

from .models import (
    Account,
    AccountType,
    Activity,
    ActivityType,
    Contact,
    Lead,
    LeadStatus,
    Opportunity,
    OpportunityStage,
    OpportunityStatus,
    RelatedToType,
)


# ===== Lead Serializers =====


class LeadSerializer(serializers.ModelSerializer):
    """Lead serializer for read operations."""

    class Meta:
        model = Lead
        fields = [
            "id",
            "tenant_id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "company",
            "title",
            "score",
            "grade",
            "source",
            "campaign_id",
            "owner_id",
            "status",
            "converted_at",
            "converted_to_opportunity_id",
            "metadata",
            "created_at",
            "updated_at",
            "created_by",
        ]
        read_only_fields = [
            "id",
            "tenant_id",
            "score",
            "grade",
            "converted_at",
            "converted_to_opportunity_id",
            "created_at",
            "updated_at",
            "created_by",
        ]


class LeadCreateSerializer(serializers.ModelSerializer):
    """Lead serializer for create operations."""

    class Meta:
        model = Lead
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "company",
            "title",
            "source",
            "campaign_id",
            "owner_id",
            "status",
            "metadata",
        ]

    def validate_email(self, value):
        """Validate email format."""
        if value and "@" not in value:
            raise serializers.ValidationError("Invalid email format")
        return value


class LeadUpdateSerializer(serializers.ModelSerializer):
    """Lead serializer for update operations."""

    class Meta:
        model = Lead
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "company",
            "title",
            "source",
            "campaign_id",
            "owner_id",
            "status",
            "metadata",
        ]


class LeadScoringResponseSerializer(serializers.Serializer):
    """Response serializer for lead scoring."""

    score = serializers.IntegerField(min_value=0, max_value=100)
    grade = serializers.CharField(max_length=2)
    bant_qualification = serializers.DictField(required=False)


# ===== Account Serializers =====


class AccountSerializer(serializers.ModelSerializer):
    """Account serializer for read operations."""

    class Meta:
        model = Account
        fields = [
            "id",
            "tenant_id",
            "name",
            "website",
            "industry",
            "employees",
            "annual_revenue",
            "parent_account_id",
            "billing_street",
            "billing_city",
            "billing_state",
            "billing_postal_code",
            "billing_country",
            "owner_id",
            "account_type",
            "metadata",
            "created_at",
            "updated_at",
            "created_by",
        ]
        read_only_fields = [
            "id",
            "tenant_id",
            "created_at",
            "updated_at",
            "created_by",
        ]


class AccountCreateSerializer(serializers.ModelSerializer):
    """Account serializer for create operations."""

    class Meta:
        model = Account
        fields = [
            "name",
            "website",
            "industry",
            "employees",
            "annual_revenue",
            "parent_account_id",
            "billing_street",
            "billing_city",
            "billing_state",
            "billing_postal_code",
            "billing_country",
            "owner_id",
            "account_type",
            "metadata",
        ]

    def validate(self, data):
        """Validate account data."""
        # Account name is required
        if not data.get("name"):
            raise serializers.ValidationError({"name": "Account name is required"})
        return data


class AccountUpdateSerializer(serializers.ModelSerializer):
    """Account serializer for update operations."""

    class Meta:
        model = Account
        fields = [
            "name",
            "website",
            "industry",
            "employees",
            "annual_revenue",
            "parent_account_id",
            "billing_street",
            "billing_city",
            "billing_state",
            "billing_postal_code",
            "billing_country",
            "owner_id",
            "account_type",
            "metadata",
        ]


class AccountHierarchySerializer(serializers.Serializer):
    """Serializer for account hierarchy tree."""

    id = serializers.UUIDField()
    name = serializers.CharField()
    account_type = serializers.CharField()
    children = serializers.ListField(child=serializers.DictField(), required=False)


# ===== Contact Serializers =====


class ContactSerializer(serializers.ModelSerializer):
    """Contact serializer for read operations."""

    class Meta:
        model = Contact
        fields = [
            "id",
            "tenant_id",
            "account_id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "mobile",
            "title",
            "department",
            "linkedin",
            "twitter",
            "last_contacted_at",
            "engagement_score",
            "owner_id",
            "metadata",
            "created_at",
            "updated_at",
            "created_by",
        ]
        read_only_fields = [
            "id",
            "tenant_id",
            "last_contacted_at",
            "engagement_score",
            "created_at",
            "updated_at",
            "created_by",
        ]


class ContactCreateSerializer(serializers.ModelSerializer):
    """Contact serializer for create operations."""

    class Meta:
        model = Contact
        fields = [
            "account_id",
            "first_name",
            "last_name",
            "email",
            "phone",
            "mobile",
            "title",
            "department",
            "linkedin",
            "twitter",
            "owner_id",
            "metadata",
        ]

    def validate(self, data):
        """Validate contact data."""
        # Account ID is required
        if not data.get("account_id"):
            raise serializers.ValidationError({"account_id": "Contact must have account_id"})

        # Last name is required
        if not data.get("last_name"):
            raise serializers.ValidationError({"last_name": "Last name is required"})

        return data


class ContactUpdateSerializer(serializers.ModelSerializer):
    """Contact serializer for update operations."""

    class Meta:
        model = Contact
        fields = [
            "first_name",
            "last_name",
            "email",
            "phone",
            "mobile",
            "title",
            "department",
            "linkedin",
            "twitter",
            "owner_id",
            "metadata",
        ]


# ===== Opportunity Serializers =====


class OpportunitySerializer(serializers.ModelSerializer):
    """Opportunity serializer for read operations."""

    class Meta:
        model = Opportunity
        fields = [
            "id",
            "tenant_id",
            "account_id",
            "primary_contact_id",
            "name",
            "description",
            "amount",
            "currency",
            "probability",
            "stage",
            "close_date",
            "product_ids",
            "competitors",
            "owner_id",
            "status",
            "closed_at",
            "loss_reason",
            "converted_to_order_id",
            "metadata",
            "created_at",
            "updated_at",
            "created_by",
            "last_activity_at",
        ]
        read_only_fields = [
            "id",
            "tenant_id",
            "status",
            "closed_at",
            "converted_to_order_id",
            "created_at",
            "updated_at",
            "created_by",
            "last_activity_at",
        ]


class OpportunityCreateSerializer(serializers.ModelSerializer):
    """Opportunity serializer for create operations."""

    class Meta:
        model = Opportunity
        fields = [
            "account_id",
            "primary_contact_id",
            "name",
            "description",
            "amount",
            "currency",
            "probability",
            "stage",
            "close_date",
            "product_ids",
            "competitors",
            "owner_id",
            "metadata",
        ]

    def validate(self, data):
        """Validate opportunity data."""
        # Account ID is required
        if not data.get("account_id"):
            raise serializers.ValidationError({"account_id": "Opportunity must have account_id"})

        # Amount must be positive
        amount = data.get("amount")
        if amount and amount <= 0:
            raise serializers.ValidationError({"amount": "Opportunity amount must be positive"})

        # Probability must be 0-100
        probability = data.get("probability", 0)
        if probability < 0 or probability > 100:
            raise serializers.ValidationError({"probability": "Probability must be between 0 and 100"})

        # Close date must be future or today
        close_date = data.get("close_date")
        if close_date and close_date < date.today():
            raise serializers.ValidationError({"close_date": "Close date must be today or in the future"})

        return data


class OpportunityUpdateSerializer(serializers.ModelSerializer):
    """Opportunity serializer for update operations."""

    class Meta:
        model = Opportunity
        fields = [
            "name",
            "description",
            "amount",
            "currency",
            "probability",
            "stage",
            "close_date",
            "product_ids",
            "competitors",
            "owner_id",
            "metadata",
        ]

    def validate(self, data):
        """Validate opportunity update data."""
        # Amount must be positive
        amount = data.get("amount")
        if amount is not None and amount <= 0:
            raise serializers.ValidationError({"amount": "Opportunity amount must be positive"})

        # Probability must be 0-100
        probability = data.get("probability")
        if probability is not None and (probability < 0 or probability > 100):
            raise serializers.ValidationError({"probability": "Probability must be between 0 and 100"})

        return data


class CloseWonRequestSerializer(serializers.Serializer):
    """Request serializer for closing opportunity as won."""

    pass  # No additional fields needed


class CloseLostRequestSerializer(serializers.Serializer):
    """Request serializer for closing opportunity as lost."""

    loss_reason = serializers.CharField(required=True, allow_blank=False)


# ===== Activity Serializers =====


class ActivitySerializer(serializers.ModelSerializer):
    """Activity serializer for read operations."""

    class Meta:
        model = Activity
        fields = [
            "id",
            "tenant_id",
            "activity_type",
            "related_to_type",
            "related_to_id",
            "subject",
            "description",
            "outcome",
            "due_date",
            "completed",
            "completed_at",
            "owner_id",
            "external_id",
            "metadata",
            "created_at",
            "updated_at",
            "created_by",
        ]
        read_only_fields = [
            "id",
            "tenant_id",
            "completed_at",
            "created_at",
            "updated_at",
            "created_by",
        ]


class ActivityCreateSerializer(serializers.ModelSerializer):
    """Activity serializer for create operations."""

    class Meta:
        model = Activity
        fields = [
            "activity_type",
            "related_to_type",
            "related_to_id",
            "subject",
            "description",
            "outcome",
            "due_date",
            "owner_id",
            "external_id",
            "metadata",
        ]

    def validate(self, data):
        """Validate activity data."""
        # Related entity is required
        if not data.get("related_to_type") or not data.get("related_to_id"):
            raise serializers.ValidationError(
                {"related_to": "Activity must have related_to_type and related_to_id"}
            )

        # Subject is required
        if not data.get("subject"):
            raise serializers.ValidationError({"subject": "Activity subject is required"})

        # Due date must be future for tasks
        due_date = data.get("due_date")
        activity_type = data.get("activity_type")
        if activity_type == ActivityType.TASK and due_date:
            if due_date <= timezone.now():
                raise serializers.ValidationError({"due_date": "Task due date must be in the future"})

        return data


class ActivityUpdateSerializer(serializers.ModelSerializer):
    """Activity serializer for update operations."""

    class Meta:
        model = Activity
        fields = [
            "subject",
            "description",
            "outcome",
            "due_date",
            "owner_id",
            "metadata",
        ]


# ===== Forecasting Serializers =====


class ForecastSerializer(serializers.Serializer):
    """Serializer for pipeline forecast response."""

    total_pipeline_value = serializers.FloatField()
    weighted_pipeline_value = serializers.FloatField()
    opportunity_count = serializers.IntegerField()
    period_days = serializers.IntegerField()


class WinRateSerializer(serializers.Serializer):
    """Serializer for win rate response."""

    win_rate = serializers.FloatField()
    won_count = serializers.IntegerField()
    lost_count = serializers.IntegerField()
    total_closed = serializers.IntegerField()
    period_days = serializers.IntegerField()


class AIPredictionSerializer(serializers.Serializer):
    """Serializer for AI prediction response."""

    predicted_revenue = serializers.FloatField()
    confidence = serializers.FloatField()
    factors = serializers.ListField(child=serializers.CharField())
    period_days = serializers.IntegerField()


# ===== Lead Conversion Serializers =====


class OpportunityCreateFromLeadSerializer(serializers.Serializer):
    """Serializer for creating opportunity from lead conversion."""

    name = serializers.CharField(required=False)
    amount = serializers.DecimalField(max_digits=15, decimal_places=2, required=True)
    close_date = serializers.DateField(required=False)
    stage = serializers.CharField(required=False)
    probability = serializers.IntegerField(required=False, min_value=0, max_value=100)
    account_id = serializers.UUIDField(required=False)  # Optional: use existing account
    create_new_account = serializers.BooleanField(default=True)

    def validate_amount(self, value):
        """Validate amount is positive."""
        if value <= 0:
            raise serializers.ValidationError("Amount must be positive")
        return value

    def validate_close_date(self, value):
        """Validate close date is future or today."""
        if value < date.today():
            raise serializers.ValidationError("Close date must be today or in the future")
        return value
