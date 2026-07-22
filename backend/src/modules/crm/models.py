"""Canonical, tenant-owned persistence for the CRM domain.

The UUID relationship columns are deliberately logical references.  CRM may be
installed without optional modules and must not couple its schema to a user,
campaign, product, or order table.  Same-tenant CRM relationships are validated
here and are also protected by PostgreSQL triggers installed by migration 0007.
"""

from __future__ import annotations

import re
import uuid
from collections.abc import Iterable
from typing import Any

from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator, URLValidator
from django.db import models, transaction
from django.db.models.functions import Lower
from django.utils import timezone
from jsonschema import Draft202012Validator

from src.core.tenancy import TenantScopedModel, TimestampedModel


def generate_uuid() -> str:
    """Retain the callable imported by immutable legacy migrations."""

    return str(uuid.uuid4())


ISO_3166_ALPHA_2 = frozenset(
    "AD AE AF AG AI AL AM AO AQ AR AS AT AU AW AX AZ BA BB BD BE BF BG BH BI BJ BL BM BN BO BQ BR BS BT BV "
    "BW BY BZ CA CC CD CF CG CH CI CK CL CM CN CO CR CU CV CW CX CY CZ DE DJ DK DM DO DZ EC EE EG EH ER ES ET "
    "FI FJ FK FM FO FR GA GB GD GE GF GG GH GI GL GM GN GP GQ GR GS GT GU GW GY HK HM HN HR HT HU ID IE IL IM "
    "IN IO IQ IR IS IT JE JM JO JP KE KG KH KI KM KN KP KR KW KY KZ LA LB LC LI LK LR LS LT LU LV LY MA MC MD ME "
    "MF MG MH MK ML MM MN MO MP MQ MR MS MT MU MV MW MX MY MZ NA NC NE NF NG NI NL NO NP NR NU NZ OM PA PE PF "
    "PG PH PK PL PM PN PR PS PT PW PY QA RE RO RS RU RW SA SB SC SD SE SG SH SI SJ SK SL SM SN SO SR SS ST SV SX "
    "SY SZ TC TD TF TG TH TJ TK TL TM TN TO TR TT TV TW TZ UA UG UM US UY UZ VA VC VE VG VI VN VU WF WS YE YT "
    "ZA ZM ZW".split()
)

# Active and fund ISO-4217 codes.  Explicit membership prevents plausible but
# nonexistent three-letter strings from entering financial aggregates.
ISO_4217_CODES = frozenset(
    "AED AFN ALL AMD ANG AOA ARS AUD AWG AZN BAM BBD BDT BGN BHD BIF BMD BND BOB BOV BRL BSD BTN BWP BYN BZD "
    "CAD CDF CHE CHF CHW CLF CLP CNY COP COU CRC CUC CUP CVE CZK DJF DKK DOP DZD EGP ERN ETB EUR FJD FKP GBP GEL "
    "GHS GIP GMD GNF GTQ GYD HKD HNL HTG HUF IDR ILS INR IQD IRR ISK JMD JOD JPY KES KGS KHR KMF KPW KRW KWD "
    "KYD KZT LAK LBP LKR LRD LSL LYD MAD MDL MGA MKD MMK MNT MOP MRU MUR MVR MWK MXN MXV MYR MZN NAD NGN NIO "
    "NOK NPR NZD OMR PAB PEN PGK PHP PKR PLN PYG QAR RON RSD RUB RWF SAR SBD SCR SDG SEK SGD SHP SLE SLL SOS SRD "
    "SSP STN SVC SYP SZL THB TJS TMT TND TOP TRY TTD TWD TZS UAH UGX USD USN UYI UYU UYW UZS VED VES VND VUV "
    "WST XAF XAG XAU XBA XBB XBC XBD XCD XDR XOF XPD XPF XPT XSU XTS XUA XXX YER ZAR ZMW ZWL".split()
)


def _normalize_email(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = value.strip().lower()
    return normalized or None


def _normalize_phone(value: str) -> str:
    """Normalize unambiguous phone strings while retaining opaque extensions."""

    value = value.strip()
    if not value:
        return ""
    if not re.fullmatch(r"[+()\-.\s0-9]+", value):
        return value
    international = value.startswith("+")
    digits = re.sub(r"\D", "", value)
    if not 7 <= len(digits) <= 15:
        return value
    return f"+{digits}" if international else digits


def _validate_json_value(value: object, *, path: str = "metadata") -> None:
    if value is None or isinstance(value, (str, int, float, bool)):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            _validate_json_value(item, path=f"{path}[{index}]")
        return
    if isinstance(value, dict):
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                raise ValidationError({"metadata": f"{path} keys must be non-empty strings."})
            _validate_json_value(item, path=f"{path}.{key}")
        return
    raise ValidationError({"metadata": f"{path} contains an unsupported value type."})


def validate_metadata(value: object) -> None:
    """Validate the stable JSON-object portion of the customization contract.

    Definitions and typed values remain owned by ``customization_framework``;
    CRM stores only JSON-compatible module extension evidence.  Services apply
    the active per-tenant JSON schemas before persistence.
    """

    if not isinstance(value, dict):
        raise ValidationError("metadata must be a JSON object.", code="invalid_metadata")
    _validate_json_value(value)


def _validate_registered_custom_fields(instance: "CRMModel") -> None:
    """Apply active customization definitions to the reserved value object."""

    custom_fields = instance.metadata.get("custom_fields")
    if custom_fields is None:
        return
    if not isinstance(custom_fields, dict):
        raise ValidationError({"metadata": "metadata.custom_fields must be an object."})
    # Imported lazily so standalone CRM operation has no import-time coupling.
    from src.modules.customization_framework.services import CustomizationRegistry

    schema = CustomizationRegistry.get_active_field_schema(
        instance.tenant_id,
        "crm",
        str(instance._meta.model_name),
    )
    unknown = sorted(set(custom_fields) - set(schema))
    if unknown:
        raise ValidationError(
            {"metadata": f"Unknown CRM custom fields: {', '.join(unknown)}."},
            code="unknown_custom_field",
        )
    errors: dict[str, str] = {}
    for key, value in custom_fields.items():
        first_error = next(Draft202012Validator(schema[key]).iter_errors(value), None)
        if first_error is not None:
            errors[key] = first_error.message
    if errors:
        raise ValidationError({"metadata": errors}, code="invalid_custom_field")


def validate_uuid_string_array(value: object) -> None:
    if not isinstance(value, list):
        raise ValidationError("Expected an array of UUID strings.", code="invalid_uuid_array")
    for item in value:
        if not isinstance(item, str):
            raise ValidationError("Every array item must be a UUID string.", code="invalid_uuid_array")
        try:
            uuid.UUID(item)
        except ValueError as exc:
            raise ValidationError("Every array item must be a UUID string.", code="invalid_uuid_array") from exc


def validate_non_empty_string_array(value: object) -> None:
    if not isinstance(value, list) or any(not isinstance(item, str) or not item.strip() for item in value):
        raise ValidationError("Expected an array of non-empty strings.", code="invalid_string_array")


class CRMModel(TenantScopedModel, TimestampedModel):
    """Common mutable CRM persistence and optimistic-version contract."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_by = models.CharField(max_length=255, null=True, blank=True, db_index=True, editable=False)
    updated_by = models.CharField(max_length=255, null=True, blank=True, db_index=True, editable=False)
    version = models.PositiveBigIntegerField(default=1, editable=False)
    is_deleted = models.BooleanField(default=False, db_index=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    metadata = models.JSONField(default=dict, blank=True, validators=[validate_metadata])

    class Meta:
        abstract = True
        constraints = [
            models.CheckConstraint(
                condition=(models.Q(is_deleted=False, deleted_at__isnull=True))
                | (models.Q(is_deleted=True, deleted_at__isnull=False)),
                name="crm_%(class)s_soft_del_ck",
            )
        ]
        indexes = [
            models.Index(
                fields=["tenant_id", "is_deleted", "-created_at"],
                name="crm_%(class)s_tenant_del_ct",
            )
        ]

    def clean(self) -> None:
        super().clean()
        validate_metadata(self.metadata)
        _validate_registered_custom_fields(self)
        if self.is_deleted != (self.deleted_at is not None):
            raise ValidationError(
                {"deleted_at": "deleted_at must be set if and only if is_deleted is true."},
                code="invalid_soft_delete",
            )

    def save(self, *args: Any, **kwargs: Any) -> None:
        """Validate writes and atomically advance the optimistic version."""

        self.full_clean()
        if self._state.adding:
            super().save(*args, **kwargs)
            return
        using = kwargs.get("using") or self._state.db or "default"
        with transaction.atomic(using=using):
            prior = type(self)._base_manager.using(using).select_for_update().get(pk=self.pk, tenant_id=self.tenant_id)
            # Services may pre-increment after validating expected_version;
            # every persisted mutation still advances by exactly one.
            self.version = prior.version + 1
            update_fields = kwargs.get("update_fields")
            if update_fields is not None:
                kwargs["update_fields"] = set(update_fields) | {"version", "updated_at"}
            super().save(*args, **kwargs)

    def delete(self, *args: Any, **kwargs: Any) -> tuple[int, dict[str, int]]:
        raise ValidationError(
            "CRM records cannot be hard-deleted; use the authorized soft-delete service.",
            code="hard_delete_forbidden",
        )


class LeadStatus(models.TextChoices):
    NEW = "new", "New"
    CONTACTED = "contacted", "Contacted"
    QUALIFIED = "qualified", "Qualified"
    CONVERTED = "converted", "Converted"
    LOST = "lost", "Lost"


class LeadGrade(models.TextChoices):
    A = "A", "A"
    B = "B", "B"
    C = "C", "C"
    D = "D", "D"


class LeadScoreSource(models.TextChoices):
    RULES = "rules", "Rules"
    PROVIDER = "provider", "Provider"


class Lead(CRMModel):
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True)
    company = models.CharField(max_length=255, blank=True)
    title = models.CharField(max_length=100, blank=True)
    score = models.SmallIntegerField(default=0)
    grade = models.CharField(max_length=1, choices=LeadGrade.choices, default=LeadGrade.D)
    score_source = models.CharField(max_length=20, choices=LeadScoreSource.choices, default=LeadScoreSource.RULES)
    score_explanation = models.JSONField(default=dict, blank=True, validators=[validate_metadata])
    source = models.CharField(max_length=100, blank=True)
    campaign_id = models.UUIDField(null=True, blank=True)
    owner_id = models.UUIDField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=20, choices=LeadStatus.choices, default=LeadStatus.NEW)
    converted_at = models.DateTimeField(null=True, blank=True)
    converted_to_opportunity_id = models.UUIDField(null=True, blank=True)
    transition_history = models.JSONField(default=list, blank=True, editable=False)

    class Meta(CRMModel.Meta):
        db_table = "crm_leads"
        constraints = [
            *CRMModel.Meta.constraints,
            models.CheckConstraint(condition=models.Q(score__gte=0, score__lte=100), name="crm_lead_score_range_ck"),
            models.CheckConstraint(
                condition=(models.Q(grade="A", score__gte=80, score__lte=100))
                | (models.Q(grade="B", score__gte=60, score__lte=79))
                | (models.Q(grade="C", score__gte=40, score__lte=59))
                | (models.Q(grade="D", score__gte=0, score__lte=39)),
                name="crm_lead_grade_score_ck",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status=LeadStatus.CONVERTED,
                        converted_at__isnull=False,
                        converted_to_opportunity_id__isnull=False,
                    )
                    | (
                        ~models.Q(status=LeadStatus.CONVERTED)
                        & models.Q(converted_at__isnull=True, converted_to_opportunity_id__isnull=True)
                    )
                ),
                name="crm_lead_conversion_ck",
            ),
            models.UniqueConstraint(
                models.F("tenant_id"),
                Lower("email"),
                condition=models.Q(email__isnull=False, is_deleted=False),
                name="crm_lead_active_email_uniq",
            ),
        ]
        indexes = [
            *CRMModel.Meta.indexes,
            models.Index(fields=["tenant_id", "status", "-created_at"], name="crm_lead_status_ct"),
            models.Index(fields=["tenant_id", "owner_id", "status"], name="crm_lead_owner_status"),
            models.Index(fields=["tenant_id", "-score"], name="crm_lead_score_desc"),
            models.Index(fields=["tenant_id", "source", "-created_at"], name="crm_lead_source_ct"),
            models.Index(fields=["tenant_id", "converted_to_opportunity_id"], name="crm_lead_converted_opp"),
        ]

    def clean(self) -> None:
        self.email = _normalize_email(self.email)
        self.phone = _normalize_phone(self.phone)
        super().clean()
        if not self.last_name.strip():
            raise ValidationError({"last_name": "Last name is required."})
        if self.email:
            EmailValidator()(self.email)
        expected_grade = "A" if self.score >= 80 else "B" if self.score >= 60 else "C" if self.score >= 40 else "D"
        if self.grade != expected_grade:
            raise ValidationError({"grade": f"Grade {expected_grade} is required for score {self.score}."})
        converted = self.status == LeadStatus.CONVERTED
        if converted != (self.converted_at is not None and self.converted_to_opportunity_id is not None):
            raise ValidationError("Conversion fields are valid only for converted leads.", code="invalid_conversion")
        if not converted and (self.converted_at is not None or self.converted_to_opportunity_id is not None):
            raise ValidationError("Non-converted leads cannot contain conversion fields.", code="invalid_conversion")
        if not isinstance(self.transition_history, list):
            raise ValidationError({"transition_history": "Transition history must be an array."})
        validate_metadata(self.score_explanation)

    def __str__(self) -> str:
        name = " ".join(part for part in (self.first_name.strip(), self.last_name.strip()) if part)
        return f"{name} ({self.company.strip()})" if self.company.strip() else name


class AccountType(models.TextChoices):
    PROSPECT = "prospect", "Prospect"
    CUSTOMER = "customer", "Customer"
    PARTNER = "partner", "Partner"


class Account(CRMModel):
    name = models.CharField(max_length=255)
    website = models.URLField(max_length=255, blank=True)
    industry = models.CharField(max_length=100, blank=True)
    employees = models.IntegerField(null=True, blank=True)
    annual_revenue = models.DecimalField(max_digits=15, decimal_places=2, null=True, blank=True)
    parent_account_id = models.UUIDField(null=True, blank=True, db_index=True)
    billing_street = models.TextField(blank=True)
    billing_city = models.CharField(max_length=100, blank=True)
    billing_state = models.CharField(max_length=100, blank=True)
    billing_postal_code = models.CharField(max_length=20, blank=True)
    billing_country = models.CharField(max_length=2, blank=True)
    owner_id = models.UUIDField(null=True, blank=True, db_index=True)
    account_type = models.CharField(max_length=20, choices=AccountType.choices, default=AccountType.PROSPECT)

    class Meta(CRMModel.Meta):
        db_table = "crm_accounts"
        constraints = [
            *CRMModel.Meta.constraints,
            models.UniqueConstraint(
                models.F("tenant_id"),
                Lower("name"),
                condition=models.Q(is_deleted=False),
                name="crm_account_active_name_uniq",
            ),
            models.CheckConstraint(
                condition=models.Q(employees__isnull=True) | models.Q(employees__gte=0),
                name="crm_account_employees_ck",
            ),
            models.CheckConstraint(
                condition=models.Q(annual_revenue__isnull=True) | models.Q(annual_revenue__gte=0),
                name="crm_account_revenue_ck",
            ),
            models.CheckConstraint(
                condition=models.Q(parent_account_id__isnull=True) | ~models.Q(parent_account_id=models.F("id")),
                name="crm_account_not_parent_ck",
            ),
        ]
        indexes = [
            *CRMModel.Meta.indexes,
            models.Index(fields=["tenant_id", "account_type", "name"], name="crm_account_type_name"),
            models.Index(fields=["tenant_id", "owner_id", "account_type"], name="crm_account_owner_type"),
            models.Index(fields=["tenant_id", "parent_account_id", "name"], name="crm_account_parent_name"),
        ]

    def clean(self) -> None:
        self.name = self.name.strip()
        self.website = self.website.strip()
        self.billing_country = self.billing_country.strip().upper()
        super().clean()
        if not self.name:
            raise ValidationError({"name": "Account name is required."})
        if self.website:
            URLValidator()(self.website)
        if self.employees is not None and self.employees < 0:
            raise ValidationError({"employees": "Employees cannot be negative."})
        if self.annual_revenue is not None and self.annual_revenue < 0:
            raise ValidationError({"annual_revenue": "Annual revenue cannot be negative."})
        if self.billing_country and self.billing_country not in ISO_3166_ALPHA_2:
            raise ValidationError({"billing_country": "Use an ISO 3166-1 alpha-2 country code."})
        self._validate_hierarchy()

    def _validate_hierarchy(self) -> None:
        if not self.parent_account_id:
            return
        if self.parent_account_id == self.id:
            raise ValidationError({"parent_account_id": "Account cannot be its own parent."})
        visited = {self.id}
        parent_id = self.parent_account_id
        # Including root, the proposed row may have at most two ancestors.
        ancestors = 0
        while parent_id:
            if parent_id in visited:
                raise ValidationError({"parent_account_id": "Account hierarchy must be acyclic."})
            visited.add(parent_id)
            parent = (
                Account.objects.filter(id=parent_id, tenant_id=self.tenant_id, is_deleted=False)
                .only("id", "parent_account_id")
                .first()
            )
            if parent is None:
                raise ValidationError({"parent_account_id": "Active parent account was not found."})
            ancestors += 1
            if ancestors >= 3:
                raise ValidationError({"parent_account_id": "Account hierarchy cannot exceed three nodes."})
            parent_id = parent.parent_account_id

    def __str__(self) -> str:
        return self.name


class Contact(CRMModel):
    account_id = models.UUIDField(db_index=True)
    first_name = models.CharField(max_length=100, blank=True)
    last_name = models.CharField(max_length=100)
    email = models.EmailField(max_length=255, blank=True, null=True)
    phone = models.CharField(max_length=50, blank=True)
    mobile = models.CharField(max_length=50, blank=True)
    title = models.CharField(max_length=100, blank=True)
    department = models.CharField(max_length=100, blank=True)
    linkedin = models.URLField(max_length=255, blank=True)
    twitter = models.CharField(max_length=100, blank=True)
    last_contacted_at = models.DateTimeField(null=True, blank=True)
    engagement_score = models.SmallIntegerField(default=0)
    owner_id = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta(CRMModel.Meta):
        db_table = "crm_contacts"
        constraints = [
            *CRMModel.Meta.constraints,
            models.CheckConstraint(
                condition=models.Q(engagement_score__gte=0, engagement_score__lte=100),
                name="crm_contact_engagement_ck",
            ),
            models.UniqueConstraint(
                models.F("tenant_id"),
                models.F("account_id"),
                Lower("email"),
                condition=models.Q(email__isnull=False, is_deleted=False),
                name="crm_contact_account_email_uniq",
            ),
        ]
        indexes = [
            *CRMModel.Meta.indexes,
            models.Index(fields=["tenant_id", "account_id", "last_name"], name="crm_contact_account_name"),
            models.Index(fields=["tenant_id", "owner_id", "last_name"], name="crm_contact_owner_name"),
            models.Index(fields=["tenant_id", "-last_contacted_at"], name="crm_contact_last_contact"),
            models.Index(fields=["tenant_id", "-engagement_score"], name="crm_contact_engagement"),
        ]

    @staticmethod
    def _account_email_domain(metadata: dict[str, object]) -> str | None:
        value = metadata.get("email_domain") or metadata.get("crm.email_domain")
        crm = metadata.get("crm")
        if value is None and isinstance(crm, dict):
            value = crm.get("email_domain")
        return str(value).strip().lower() if value else None

    def clean(self) -> None:
        self.email = _normalize_email(self.email)
        self.phone = _normalize_phone(self.phone)
        self.mobile = _normalize_phone(self.mobile)
        super().clean()
        if not self.last_name.strip():
            raise ValidationError({"last_name": "Last name is required."})
        if self.email:
            EmailValidator()(self.email)
        if not 0 <= self.engagement_score <= 100:
            raise ValidationError({"engagement_score": "Engagement score must be between 0 and 100."})
        account = (
            Account.objects.filter(id=self.account_id, tenant_id=self.tenant_id, is_deleted=False)
            .only("id", "metadata")
            .first()
        )
        if account is None:
            raise ValidationError({"account_id": "Active account was not found."})
        required_domain = self._account_email_domain(account.metadata)
        if self.email and required_domain and self.email.rpartition("@")[2] != required_domain:
            override_required = self._state.adding
            if not override_required:
                prior = (
                    Contact.objects.filter(pk=self.pk, tenant_id=self.tenant_id).values("account_id", "email").first()
                )
                override_required = prior is None or prior["account_id"] != self.account_id
                if prior is not None and not override_required:
                    override_required = _normalize_email(prior["email"]) != self.email
            if override_required and not getattr(self, "_allow_domain_override", False):
                raise ValidationError(
                    {"email": "Contact email does not match the account domain."},
                    code="domain_override_required",
                )

    def __str__(self) -> str:
        return " ".join(part for part in (self.first_name.strip(), self.last_name.strip()) if part)


class OpportunityStage(models.TextChoices):
    PROSPECTING = "prospecting", "Prospecting"
    QUALIFICATION = "qualification", "Qualification"
    NEEDS_ANALYSIS = "needs_analysis", "Needs Analysis"
    PROPOSAL = "proposal", "Proposal"
    NEGOTIATION = "negotiation", "Negotiation"
    CLOSED_WON = "closed_won", "Closed Won"
    CLOSED_LOST = "closed_lost", "Closed Lost"


class OpportunityStatus(models.TextChoices):
    OPEN = "open", "Open"
    WON = "won", "Won"
    LOST = "lost", "Lost"


class Opportunity(CRMModel):
    account_id = models.UUIDField(db_index=True)
    primary_contact_id = models.UUIDField(null=True, blank=True, db_index=True)
    name = models.CharField(max_length=255)
    description = models.TextField(blank=True)
    amount = models.DecimalField(max_digits=15, decimal_places=2)
    currency = models.CharField(max_length=3, default="USD")
    probability = models.SmallIntegerField(default=10)
    stage = models.CharField(max_length=30, choices=OpportunityStage.choices, default=OpportunityStage.PROSPECTING)
    close_date = models.DateField(db_index=True)
    product_ids = models.JSONField(default=list, blank=True, validators=[validate_uuid_string_array])
    competitors = models.JSONField(default=list, blank=True, validators=[validate_non_empty_string_array])
    owner_id = models.UUIDField(null=True, blank=True, db_index=True)
    status = models.CharField(max_length=10, choices=OpportunityStatus.choices, default=OpportunityStatus.OPEN)
    closed_at = models.DateTimeField(null=True, blank=True)
    loss_reason = models.TextField(blank=True)
    converted_to_order_id = models.UUIDField(null=True, blank=True)
    last_activity_at = models.DateTimeField(null=True, blank=True, db_index=True)
    transition_history = models.JSONField(default=list, blank=True, editable=False)

    class Meta(CRMModel.Meta):
        db_table = "crm_opportunities"
        constraints = [
            *CRMModel.Meta.constraints,
            models.CheckConstraint(condition=models.Q(amount__gt=0), name="crm_opp_amount_positive_ck"),
            models.CheckConstraint(
                condition=models.Q(probability__gte=0, probability__lte=100), name="crm_opp_probability_ck"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        status=OpportunityStatus.OPEN,
                        stage__in=[
                            OpportunityStage.PROSPECTING,
                            OpportunityStage.QUALIFICATION,
                            OpportunityStage.NEEDS_ANALYSIS,
                            OpportunityStage.PROPOSAL,
                            OpportunityStage.NEGOTIATION,
                        ],
                        closed_at__isnull=True,
                    )
                    | models.Q(
                        status=OpportunityStatus.WON,
                        stage=OpportunityStage.CLOSED_WON,
                        probability=100,
                        closed_at__isnull=False,
                    )
                    | (
                        models.Q(
                            status=OpportunityStatus.LOST,
                            stage=OpportunityStage.CLOSED_LOST,
                            probability=0,
                            closed_at__isnull=False,
                        )
                        & ~models.Q(loss_reason="")
                    )
                ),
                name="crm_opp_state_consistency_ck",
            ),
        ]
        indexes = [
            *CRMModel.Meta.indexes,
            models.Index(fields=["tenant_id", "status", "close_date"], name="crm_opp_status_close"),
            models.Index(fields=["tenant_id", "owner_id", "stage", "close_date"], name="crm_opp_owner_stage_close"),
            models.Index(fields=["tenant_id", "account_id", "status"], name="crm_opp_account_status"),
            models.Index(fields=["tenant_id", "stage", "amount"], name="crm_opp_stage_amount"),
            models.Index(fields=["tenant_id", "last_activity_at"], name="crm_opp_last_activity"),
        ]

    def clean(self) -> None:
        self.name = self.name.strip()
        self.currency = self.currency.strip().upper()
        self.loss_reason = self.loss_reason.strip()
        super().clean()
        if not self.name:
            raise ValidationError({"name": "Opportunity name is required."})
        if self.amount <= 0:
            raise ValidationError({"amount": "Opportunity amount must be positive."})
        if not 0 <= self.probability <= 100:
            raise ValidationError({"probability": "Probability must be between 0 and 100."})
        if self.currency not in ISO_4217_CODES:
            raise ValidationError({"currency": "Use an uppercase ISO 4217 currency code."})
        if self._state.adding and self.close_date < timezone.localdate():
            raise ValidationError({"close_date": "Close date cannot be in the past at creation."})
        account = (
            Account.objects.filter(id=self.account_id, tenant_id=self.tenant_id, is_deleted=False).only("id").first()
        )
        if account is None:
            raise ValidationError({"account_id": "Active account was not found."})
        if (
            self.primary_contact_id
            and not Contact.objects.filter(
                id=self.primary_contact_id,
                account_id=self.account_id,
                tenant_id=self.tenant_id,
                is_deleted=False,
            ).exists()
        ):
            raise ValidationError({"primary_contact_id": "Active contact for this account was not found."})
        if not isinstance(self.transition_history, list):
            raise ValidationError({"transition_history": "Transition history must be an array."})
        self._validate_state()

    def _validate_state(self) -> None:
        open_stages = {
            OpportunityStage.PROSPECTING,
            OpportunityStage.QUALIFICATION,
            OpportunityStage.NEEDS_ANALYSIS,
            OpportunityStage.PROPOSAL,
            OpportunityStage.NEGOTIATION,
        }
        if self.status == OpportunityStatus.OPEN:
            valid = self.stage in open_stages and self.closed_at is None and not self.loss_reason
        elif self.status == OpportunityStatus.WON:
            valid = (
                self.stage == OpportunityStage.CLOSED_WON
                and self.probability == 100
                and self.closed_at is not None
                and not self.loss_reason
            )
        else:
            valid = (
                self.status == OpportunityStatus.LOST
                and self.stage == OpportunityStage.CLOSED_LOST
                and self.probability == 0
                and self.closed_at is not None
                and bool(self.loss_reason)
            )
        if not valid:
            raise ValidationError("Opportunity stage, status, probability, and close fields are inconsistent.")

    def __str__(self) -> str:
        return self.name


class ActivityType(models.TextChoices):
    CALL = "call", "Call"
    EMAIL = "email", "Email"
    MEETING = "meeting", "Meeting"
    TASK = "task", "Task"
    NOTE = "note", "Note"


class RelatedToType(models.TextChoices):
    LEAD = "Lead", "Lead"
    CONTACT = "Contact", "Contact"
    ACCOUNT = "Account", "Account"
    OPPORTUNITY = "Opportunity", "Opportunity"


RELATED_MODELS: dict[str, type[CRMModel]] = {
    RelatedToType.LEAD: Lead,
    RelatedToType.CONTACT: Contact,
    RelatedToType.ACCOUNT: Account,
    RelatedToType.OPPORTUNITY: Opportunity,
}


class Activity(CRMModel):
    activity_type = models.CharField(max_length=20, choices=ActivityType.choices)
    related_to_type = models.CharField(max_length=20, choices=RelatedToType.choices)
    related_to_id = models.UUIDField()
    subject = models.CharField(max_length=500)
    description = models.TextField(blank=True)
    outcome = models.CharField(max_length=100, blank=True)
    due_date = models.DateTimeField(null=True, blank=True)
    completed = models.BooleanField(default=False)
    completed_at = models.DateTimeField(null=True, blank=True)
    owner_id = models.UUIDField(null=True, blank=True, db_index=True)
    external_id = models.CharField(max_length=255, blank=True)

    class Meta(CRMModel.Meta):
        db_table = "crm_activities"
        constraints = [
            *CRMModel.Meta.constraints,
            models.CheckConstraint(
                condition=(models.Q(completed=False, completed_at__isnull=True))
                | models.Q(completed=True, completed_at__isnull=False),
                name="crm_activity_completion_ck",
            ),
            models.UniqueConstraint(
                fields=["tenant_id", "activity_type", "external_id"],
                condition=~models.Q(external_id="") & models.Q(is_deleted=False),
                name="crm_activity_external_uniq",
            ),
        ]
        indexes = [
            *CRMModel.Meta.indexes,
            models.Index(
                fields=["tenant_id", "related_to_type", "related_to_id", "-created_at"],
                name="crm_activity_relation_ct",
            ),
            models.Index(
                fields=["tenant_id", "owner_id", "completed", "due_date"],
                name="crm_activity_owner_due",
            ),
            models.Index(fields=["tenant_id", "activity_type", "-created_at"], name="crm_activity_type_ct"),
            models.Index(fields=["tenant_id", "external_id"], name="crm_activity_external"),
        ]

    def clean(self) -> None:
        self.subject = self.subject.strip()
        self.external_id = self.external_id.strip()
        super().clean()
        if not self.subject:
            raise ValidationError({"subject": "Activity subject is required."})
        related_model = RELATED_MODELS.get(self.related_to_type)
        if related_model is None:
            raise ValidationError({"related_to_type": "Unsupported CRM relation type."})
        related = related_model.objects.filter(
            id=self.related_to_id, tenant_id=self.tenant_id, is_deleted=False
        ).first()
        if related is None:
            raise ValidationError({"related_to_id": "Active related CRM record was not found."})
        if self._state.adding and self.activity_type == ActivityType.TASK and self.due_date:
            if self.due_date <= timezone.now():
                raise ValidationError({"due_date": "A new task due date must be in the future."})
        if self.completed != (self.completed_at is not None):
            raise ValidationError({"completed_at": "completed_at must be set if and only if completed is true."})
        if not self._state.adding:
            self._validate_immutability()

    def _validate_immutability(self) -> None:
        prior = Activity._base_manager.filter(pk=self.pk, tenant_id=self.tenant_id).first()
        if prior is None:
            return
        related_closed = False
        if prior.related_to_type == RelatedToType.OPPORTUNITY:
            related_closed = Opportunity.objects.filter(
                id=prior.related_to_id,
                tenant_id=self.tenant_id,
                status__in=[OpportunityStatus.WON, OpportunityStatus.LOST],
            ).exists()
        if not (prior.completed or related_closed):
            return
        mutable_fields: Iterable[str] = (
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
        )
        changed = any(getattr(prior, field) != getattr(self, field) for field in mutable_fields)
        deleting = not prior.is_deleted and self.is_deleted and self.deleted_at is not None
        if changed or (deleting and not getattr(self, "_allow_admin_delete", False)):
            raise ValidationError(
                "Completed activities and activities on closed opportunities are immutable.",
                code="activity_immutable",
            )

    def __str__(self) -> str:
        return f"{self.activity_type}: {self.subject}"
