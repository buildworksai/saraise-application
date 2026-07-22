"""Convert the applied legacy policy/requirement schema without data loss."""

from __future__ import annotations

import hashlib
import uuid
from datetime import timedelta

from django.db import migrations, models


LEGACY_MARKER = "legacy_compliance_0001"
LEGACY_VERSION_SUMMARY = "Imported from the legacy compliance policy record."
LEGACY_REVIEW_DAYS = 365


def _normalise_regulation(value):
    if not isinstance(value, str) or not value.strip():
        raise RuntimeError("Legacy regulation_type must be a nonblank string.")
    return " ".join(value.split()).casefold()


def _validate_uuid(value, label):
    try:
        return uuid.UUID(str(value))
    except (TypeError, ValueError, AttributeError) as exc:
        raise RuntimeError(f"Malformed {label}: {value!r}.") from exc


def forwards(apps, schema_editor):
    Policy = apps.get_model("compliance_management", "CompliancePolicy")
    Requirement = apps.get_model("compliance_management", "ComplianceRequirement")
    Framework = apps.get_model("compliance_management", "ComplianceFramework")
    Version = apps.get_model("compliance_management", "CompliancePolicyVersion")
    Mapping = apps.get_model("compliance_management", "RequirementPolicyMapping")
    Assessment = apps.get_model("compliance_management", "ComplianceAssessment")
    Configuration = apps.get_model("compliance_management", "ComplianceConfigurationRevision")

    valid_statuses = {"pending", "compliant", "non_compliant"}
    frameworks = {}
    categories_by_tenant = {}

    for policy in Policy.objects.order_by("tenant_id", "regulation_type", "id"):
        tenant_id = _validate_uuid(policy.tenant_id, "policy tenant_id")
        normalised = _normalise_regulation(policy.regulation_type)
        categories_by_tenant.setdefault(tenant_id, set()).add(normalised)
        key = (tenant_id, normalised)
        framework = frameworks.get(key)
        if framework is None:
            digest = hashlib.sha256(normalised.encode("utf-8")).hexdigest()[:16].upper()
            framework = Framework.objects.create(
                tenant_id=tenant_id,
                code=f"LEGACY-{digest}",
                name=" ".join(policy.regulation_type.split()),
                version="legacy-1",
                category=normalised[:50],
                description="Framework reconstructed from legacy compliance policy data.",
                source_kind="imported",
                source_package="legacy/compliance-management/0001",
                source_version="0001",
                status="active",
                transition_history=[
                    {
                        "migration": LEGACY_MARKER,
                        "original_regulation_type": policy.regulation_type,
                    }
                ],
            )
            frameworks[key] = framework

        content = policy.description or ""
        lifecycle_status = "published" if policy.is_active else "archived"
        policy.code = policy.policy_code
        policy.title = policy.policy_name
        policy.summary = content
        policy.category = normalised[:50]
        policy.review_frequency_days = LEGACY_REVIEW_DAYS
        policy.next_review_date = (
            policy.effective_date + timedelta(days=LEGACY_REVIEW_DAYS)
            if policy.effective_date is not None and policy.is_active
            else None
        )
        policy.lifecycle_status = lifecycle_status
        policy.current_version = 1
        policy.transition_history = [
            {
                "migration": LEGACY_MARKER,
                "framework_id": str(framework.id),
                "original_regulation_type": policy.regulation_type,
                "original_is_active": policy.is_active,
            }
        ]
        policy.save(
            update_fields=(
                "code",
                "title",
                "summary",
                "category",
                "review_frequency_days",
                "next_review_date",
                "lifecycle_status",
                "current_version",
                "transition_history",
            )
        )
        version = Version.objects.create(
            tenant_id=tenant_id,
            policy_id=policy.id,
            version=1,
            content=content,
            content_sha256=hashlib.sha256(content.encode("utf-8")).hexdigest(),
            change_summary=LEGACY_VERSION_SUMMARY,
            approved_at=policy.created_at if policy.is_active else None,
            published_at=policy.created_at if policy.is_active else None,
        )
        Version.objects.filter(pk=version.pk).update(created_at=policy.created_at)

    seen_requirement_codes = set()
    for requirement in Requirement.objects.select_related("policy").order_by("tenant_id", "id"):
        tenant_id = _validate_uuid(requirement.tenant_id, "requirement tenant_id")
        if requirement.policy_id is None:
            raise RuntimeError(f"Legacy requirement {requirement.id} has no policy.")
        if requirement.policy.tenant_id != tenant_id:
            raise RuntimeError(f"Legacy requirement {requirement.id} references a foreign-tenant policy.")
        if requirement.status not in valid_statuses:
            raise RuntimeError(f"Unknown legacy requirement status {requirement.status!r}.")
        normalised = _normalise_regulation(requirement.policy.regulation_type)
        framework = frameworks.get((tenant_id, normalised))
        if framework is None:
            raise RuntimeError(f"Legacy requirement {requirement.id} references an orphan policy.")
        uniqueness_key = (tenant_id, framework.id, requirement.requirement_code)
        if uniqueness_key in seen_requirement_codes:
            raise RuntimeError(
                f"Duplicate requirement code {requirement.requirement_code!r} in migrated framework {framework.id}."
            )
        seen_requirement_codes.add(uniqueness_key)
        legacy_status = requirement.status
        legacy_policy_id = requirement.policy_id
        requirement.framework_id = framework.id
        requirement.code = requirement.requirement_code
        requirement.title = requirement.requirement_name
        requirement.lifecycle_status = "active"
        requirement.transition_history = [
            {
                "migration": LEGACY_MARKER,
                "legacy_policy_id": str(legacy_policy_id),
                "legacy_status": legacy_status,
            }
        ]
        requirement.save(
            update_fields=("framework", "code", "title", "lifecycle_status", "transition_history")
        )
        coverage = "full" if legacy_status == "compliant" else "none"
        mapping = Mapping.objects.create(
            tenant_id=tenant_id,
            requirement_id=requirement.id,
            policy_id=legacy_policy_id,
            policy_version_id=None,
            coverage=coverage,
            rationale=f"Migrated from legacy requirement status: {legacy_status}.",
            mapped_at=requirement.updated_at,
        )
        Mapping.objects.filter(pk=mapping.pk).update(
            created_at=requirement.created_at,
            updated_at=requirement.updated_at,
        )
        if legacy_status in {"compliant", "non_compliant"}:
            assessment = Assessment.objects.create(
                tenant_id=tenant_id,
                requirement_id=requirement.id,
                mapping_id=mapping.id,
                status=legacy_status,
                assessed_at=requirement.updated_at,
                notes=("" if legacy_status == "compliant" else "Imported legacy non-compliant status."),
                source="import",
            )
            Assessment.objects.filter(pk=assessment.pk).update(created_at=requirement.created_at)

    # Seed runtime-editable defaults for all environments. These are initial
    # data, not permanent behavior: activation, versioning, export, and rollback
    # operate on the same rows immediately after migration.
    for tenant_id, categories in categories_by_tenant.items():
        category_values = sorted(categories) or ["general"]
        for environment in ("development", "staging", "production"):
            Configuration.objects.create(
                tenant_id=tenant_id,
                environment=environment,
                version=1,
                status="active",
                policy_code_prefix="POL",
                default_review_frequency_days=LEGACY_REVIEW_DAYS,
                expiry_warning_days=30,
                evidence_warning_days=30,
                minimum_assessment_note_length=1,
                allow_external_evidence_urls=False,
                bulk_import_row_limit=1000,
                regulation_categories=category_values,
                rollout={},
                transition_history=[{"migration": LEGACY_MARKER, "command": "bootstrap"}],
            )


def backwards(apps, schema_editor):
    Policy = apps.get_model("compliance_management", "CompliancePolicy")
    Requirement = apps.get_model("compliance_management", "ComplianceRequirement")
    Version = apps.get_model("compliance_management", "CompliancePolicyVersion")
    Mapping = apps.get_model("compliance_management", "RequirementPolicyMapping")

    for policy in Policy.objects.order_by("id"):
        markers = [
            item
            for item in (policy.transition_history or [])
            if isinstance(item, dict) and item.get("migration") == LEGACY_MARKER
        ]
        if len(markers) != 1:
            raise RuntimeError(f"Cannot reverse policy {policy.id}: legacy provenance is ambiguous.")
        versions = list(Version.objects.filter(policy_id=policy.id).order_by("version"))
        if len(versions) != 1 or versions[0].version != 1:
            raise RuntimeError(f"Cannot reverse policy {policy.id}: immutable versions are ambiguous.")
        marker = markers[0]
        policy.policy_code = policy.code
        policy.policy_name = policy.title
        policy.regulation_type = marker["original_regulation_type"]
        policy.description = versions[0].content
        policy.is_active = bool(marker["original_is_active"])
        policy.save(
            update_fields=(
                "policy_code",
                "policy_name",
                "regulation_type",
                "description",
                "is_active",
            )
        )

    for requirement in Requirement.objects.order_by("id"):
        markers = [
            item
            for item in (requirement.transition_history or [])
            if isinstance(item, dict) and item.get("migration") == LEGACY_MARKER
        ]
        if len(markers) != 1:
            raise RuntimeError(f"Cannot reverse requirement {requirement.id}: legacy provenance is ambiguous.")
        marker = markers[0]
        mappings = list(Mapping.objects.filter(requirement_id=requirement.id, deleted_at__isnull=True))
        if len(mappings) != 1 or str(mappings[0].policy_id) != marker["legacy_policy_id"]:
            raise RuntimeError(f"Cannot reverse requirement {requirement.id}: former policy mapping is ambiguous.")
        requirement.policy_id = marker["legacy_policy_id"]
        requirement.requirement_code = requirement.code
        requirement.requirement_name = requirement.title
        requirement.status = marker["legacy_status"]
        requirement.save(update_fields=("policy", "requirement_code", "requirement_name", "status"))


class Migration(migrations.Migration):
    dependencies = [("compliance_management", "0002_open_source_compliance_core")]

    operations = [
        # Nullable staging is essential for a data-preserving reverse: Django
        # recreates removed columns before calling ``backwards``. The reverse
        # of these operations tightens them only after reconstruction.
        migrations.AlterField("compliancepolicy", "policy_code", models.CharField(db_index=True, max_length=50, null=True)),
        migrations.AlterField("compliancepolicy", "policy_name", models.CharField(max_length=255, null=True)),
        migrations.AlterField("compliancepolicy", "regulation_type", models.CharField(db_index=True, max_length=100, null=True)),
        migrations.AlterField("compliancepolicy", "description", models.TextField(blank=True, null=True)),
        migrations.AlterField("compliancerequirement", "policy", models.ForeignKey(null=True, on_delete=models.CASCADE, related_name="requirements", to="compliance_management.compliancepolicy")),
        migrations.AlterField("compliancerequirement", "requirement_code", models.CharField(db_index=True, max_length=50, null=True)),
        migrations.AlterField("compliancerequirement", "requirement_name", models.CharField(max_length=255, null=True)),
        migrations.AlterField("compliancerequirement", "description", models.TextField(blank=True, null=True)),
        migrations.AlterField("compliancerequirement", "status", models.CharField(db_index=True, default="pending", max_length=50, null=True)),
        migrations.RunPython(forwards, backwards),
        migrations.RemoveConstraint("compliancepolicy", "unique_policy_code_per_tenant"),
        migrations.RemoveIndex("compliancepolicy", "compliance__tenant__bf0bc5_idx"),
        migrations.RemoveIndex("compliancepolicy", "compliance__tenant__03d2d3_idx"),
        migrations.RemoveIndex("compliancerequirement", "compliance__tenant__014cf5_idx"),
        migrations.RemoveIndex("compliancerequirement", "compliance__tenant__3cc0e2_idx"),
        migrations.RemoveIndex("compliancerequirement", "compliance__tenant__b09a98_idx"),
        migrations.RemoveField("compliancepolicy", "policy_code"),
        migrations.RemoveField("compliancepolicy", "policy_name"),
        migrations.RemoveField("compliancepolicy", "regulation_type"),
        migrations.RemoveField("compliancepolicy", "description"),
        migrations.RemoveField("compliancepolicy", "is_active"),
        migrations.RemoveField("compliancerequirement", "policy"),
        migrations.RemoveField("compliancerequirement", "requirement_code"),
        migrations.RemoveField("compliancerequirement", "requirement_name"),
        migrations.RemoveField("compliancerequirement", "status"),
        migrations.RenameField("compliancepolicy", "lifecycle_status", "status"),
        migrations.RenameField("compliancerequirement", "lifecycle_status", "status"),
        migrations.AlterField("compliancepolicy", "status", models.CharField(choices=[("draft", "Draft"), ("in_review", "In review"), ("approved", "Approved"), ("published", "Published"), ("archived", "Archived")], default="draft", max_length=20)),
        migrations.AlterField("compliancepolicy", "code", models.CharField(max_length=100)),
        migrations.AlterField("compliancepolicy", "title", models.CharField(max_length=500)),
        migrations.AlterField("compliancepolicy", "category", models.CharField(max_length=50)),
        migrations.AlterField("compliancepolicy", "review_frequency_days", models.PositiveSmallIntegerField()),
        migrations.AlterField("compliancepolicy", "effective_date", models.DateField(blank=True, null=True)),
        migrations.AlterField("compliancepolicy", "created_at", models.DateTimeField(auto_now_add=True)),
        migrations.AlterField("compliancerequirement", "framework", models.ForeignKey(on_delete=models.PROTECT, related_name="requirements", to="compliance_management.complianceframework")),
        migrations.AlterField("compliancerequirement", "code", models.CharField(max_length=100)),
        migrations.AlterField("compliancerequirement", "title", models.CharField(max_length=500)),
        migrations.AlterField("compliancerequirement", "description", models.TextField()),
        migrations.AlterField("compliancerequirement", "created_at", models.DateTimeField(auto_now_add=True)),
        migrations.AddIndex("compliancepolicy", models.Index(fields=["tenant_id", "status", "title"], name="cmp_pol_tenant_status_title_ix")),
        migrations.AddIndex("compliancepolicy", models.Index(fields=["tenant_id", "owner", "status"], name="cmp_pol_tenant_owner_status_ix")),
        migrations.AddIndex("compliancepolicy", models.Index(fields=["tenant_id", "next_review_date", "status"], name="cmp_pol_tenant_review_ix")),
        migrations.AddIndex("compliancepolicy", models.Index(fields=["tenant_id", "expiry_date", "status"], name="cmp_pol_tenant_exp_status_ix")),
        migrations.AddIndex("compliancepolicy", models.Index(fields=["tenant_id", "deleted_at"], name="cmp_pol_tenant_deleted_ix")),
        migrations.AddConstraint("compliancepolicy", models.UniqueConstraint(condition=models.Q(("deleted_at__isnull", True)), fields=("tenant_id", "code"), name="cmp_policy_tenant_code_uq")),
        migrations.AddConstraint("compliancepolicy", models.CheckConstraint(condition=models.Q(("expiry_date__isnull", True)) | models.Q(("effective_date__isnull", True)) | models.Q(("expiry_date__gt", models.F("effective_date"))), name="cmp_policy_expiry_after_eff_ck")),
        migrations.AddConstraint("compliancepolicy", models.CheckConstraint(condition=models.Q(("current_version__gte", 0)), name="cmp_policy_version_nonneg_ck")),
        migrations.AddConstraint("compliancepolicy", models.CheckConstraint(condition=~models.Q(status="published") | (models.Q(current_version__gt=0) & models.Q(effective_date__isnull=False)), name="cmp_policy_published_ready_ck")),
        migrations.AddIndex("compliancerequirement", models.Index(fields=["tenant_id", "framework", "status", "sort_order"], name="cmp_req_tenant_fw_status_ix")),
        migrations.AddIndex("compliancerequirement", models.Index(fields=["tenant_id", "applicability", "status"], name="cmp_req_tenant_app_status_ix")),
        migrations.AddIndex("compliancerequirement", models.Index(fields=["tenant_id", "deleted_at"], name="cmp_req_tenant_deleted_ix")),
        migrations.AddConstraint("compliancerequirement", models.UniqueConstraint(condition=models.Q(("deleted_at__isnull", True)), fields=("tenant_id", "framework", "code"), name="cmp_req_tenant_fw_code_uq")),
        migrations.AddConstraint("compliancerequirement", models.CheckConstraint(condition=~models.Q(applicability="not_applicable") | ~models.Q(applicability_rationale=""), name="cmp_req_na_rationale_ck")),
    ]
