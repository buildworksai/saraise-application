"""Add the normalized compliance domain alongside the applied legacy schema."""

import uuid

import django.core.validators
import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models

import src.modules.compliance_management.models


USER = settings.AUTH_USER_MODEL


def actor_fk(*, related_name="+"):
    return models.ForeignKey(
        blank=True,
        null=True,
        on_delete=django.db.models.deletion.SET_NULL,
        related_name=related_name,
        to=USER,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_apply_typed_rls_to_notifications"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ("compliance_management", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="ComplianceFramework",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("code", models.CharField(max_length=50)),
                ("name", models.CharField(max_length=255)),
                ("version", models.CharField(max_length=50)),
                ("category", models.CharField(max_length=50)),
                ("description", models.TextField(blank=True)),
                ("source_kind", models.CharField(choices=[("custom", "Custom"), ("imported", "Imported"), ("extension", "Extension")], max_length=20)),
                ("source_package", models.CharField(blank=True, max_length=255)),
                ("source_version", models.CharField(blank=True, max_length=50)),
                ("status", models.CharField(choices=[("draft", "Draft"), ("active", "Active"), ("archived", "Archived")], default="draft", max_length=20)),
                ("transition_history", models.JSONField(blank=True, default=list)),
                ("created_by", actor_fk()),
                ("deleted_by", actor_fk()),
                ("updated_by", actor_fk()),
            ],
            options={
                "db_table": "compliance_frameworks",
                "indexes": [
                    models.Index(fields=["tenant_id", "status", "name"], name="cmp_fw_tenant_status_name_ix"),
                    models.Index(fields=["tenant_id", "category", "status"], name="cmp_fw_tenant_cat_status_ix"),
                    models.Index(fields=["tenant_id", "deleted_at"], name="cmp_fw_tenant_deleted_ix"),
                ],
                "constraints": [
                    models.UniqueConstraint(condition=models.Q(("deleted_at__isnull", True)), fields=("tenant_id", "code", "version"), name="cmp_fw_tenant_code_ver_uq"),
                    models.CheckConstraint(condition=models.Q(("source_kind", "extension"), _negated=True) | models.Q(("source_package", ""), _negated=True), name="cmp_fw_extension_package_ck"),
                ],
            },
        ),
        # New policy columns remain nullable until the legacy converter succeeds.
        migrations.AddField("compliancepolicy", "created_by", actor_fk()),
        migrations.AddField("compliancepolicy", "updated_by", actor_fk()),
        migrations.AddField("compliancepolicy", "deleted_by", actor_fk()),
        migrations.AddField("compliancepolicy", "deleted_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("compliancepolicy", "code", models.CharField(max_length=100, null=True)),
        migrations.AddField("compliancepolicy", "title", models.CharField(max_length=500, null=True)),
        migrations.AddField("compliancepolicy", "summary", models.TextField(blank=True)),
        migrations.AddField("compliancepolicy", "category", models.CharField(max_length=50, null=True)),
        migrations.AddField("compliancepolicy", "owner", actor_fk(related_name="owned_compliance_policies")),
        migrations.AddField("compliancepolicy", "review_frequency_days", models.PositiveSmallIntegerField(null=True)),
        migrations.AddField("compliancepolicy", "next_review_date", models.DateField(blank=True, null=True)),
        migrations.AddField("compliancepolicy", "lifecycle_status", models.CharField(choices=[("draft", "Draft"), ("in_review", "In review"), ("approved", "Approved"), ("published", "Published"), ("archived", "Archived")], max_length=20, null=True)),
        migrations.AddField("compliancepolicy", "current_version", models.PositiveIntegerField(default=0)),
        migrations.AddField("compliancepolicy", "transition_history", models.JSONField(blank=True, default=list)),
        migrations.AlterField("compliancepolicy", "effective_date", models.DateField(blank=True, db_index=True, null=True)),
        # New requirement columns likewise coexist with the legacy policy/status fields.
        migrations.AddField("compliancerequirement", "created_by", actor_fk()),
        migrations.AddField("compliancerequirement", "updated_by", actor_fk()),
        migrations.AddField("compliancerequirement", "deleted_by", actor_fk()),
        migrations.AddField("compliancerequirement", "deleted_at", models.DateTimeField(blank=True, null=True)),
        migrations.AddField("compliancerequirement", "framework", models.ForeignKey(null=True, on_delete=django.db.models.deletion.PROTECT, related_name="requirements", to="compliance_management.complianceframework")),
        migrations.AddField("compliancerequirement", "code", models.CharField(max_length=100, null=True)),
        migrations.AddField("compliancerequirement", "title", models.CharField(max_length=500, null=True)),
        migrations.AddField("compliancerequirement", "section", models.CharField(blank=True, max_length=255)),
        migrations.AddField("compliancerequirement", "guidance", models.TextField(blank=True)),
        migrations.AddField("compliancerequirement", "applicability", models.CharField(choices=[("applicable", "Applicable"), ("not_applicable", "Not applicable")], default="applicable", max_length=20)),
        migrations.AddField("compliancerequirement", "applicability_rationale", models.TextField(blank=True)),
        migrations.AddField("compliancerequirement", "lifecycle_status", models.CharField(choices=[("active", "Active"), ("archived", "Archived")], default="active", max_length=20)),
        migrations.AddField("compliancerequirement", "sort_order", models.PositiveIntegerField(default=0)),
        migrations.AddField("compliancerequirement", "tags", models.JSONField(blank=True, default=list, validators=[src.modules.compliance_management.models.validate_tags])),
        migrations.AddField("compliancerequirement", "transition_history", models.JSONField(blank=True, default=list)),
        migrations.CreateModel(
            name="CompliancePolicyVersion",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("version", models.PositiveIntegerField()),
                ("content", models.TextField()),
                ("content_sha256", models.CharField(max_length=64, validators=[src.modules.compliance_management.models.validate_sha256])),
                ("change_summary", models.TextField()),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("approved_at", models.DateTimeField(blank=True, null=True)),
                ("published_at", models.DateTimeField(blank=True, null=True)),
                ("approved_by", actor_fk()),
                ("created_by", actor_fk()),
                ("published_by", actor_fk()),
                ("policy", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="versions", to="compliance_management.compliancepolicy")),
            ],
            options={
                "db_table": "compliance_policy_versions",
                "indexes": [models.Index(fields=["tenant_id", "policy", "-version"], name="cmp_pol_ver_tenant_pol_ix")],
                "constraints": [
                    models.UniqueConstraint(fields=("tenant_id", "policy", "version"), name="cmp_pol_ver_number_uq"),
                    models.UniqueConstraint(fields=("tenant_id", "policy", "content_sha256"), name="cmp_pol_ver_content_uq"),
                    models.CheckConstraint(condition=models.Q(("content_sha256__regex", "^[0-9a-f]{64}$")), name="cmp_pol_ver_sha256_ck"),
                ],
            },
        ),
        migrations.CreateModel(
            name="RequirementPolicyMapping",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("coverage", models.CharField(choices=[("none", "None"), ("partial", "Partial"), ("full", "Full"), ("not_applicable", "Not applicable")], max_length=20)),
                ("rationale", models.TextField(blank=True)),
                ("mapped_at", models.DateTimeField()),
                ("created_by", actor_fk()),
                ("deleted_by", actor_fk()),
                ("updated_by", actor_fk()),
                ("policy", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="requirement_mappings", to="compliance_management.compliancepolicy")),
                ("policy_version", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="requirement_mappings", to="compliance_management.compliancepolicyversion")),
                ("requirement", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="policy_mappings", to="compliance_management.compliancerequirement")),
            ],
            options={
                "db_table": "compliance_requirement_policy_mappings",
                "indexes": [
                    models.Index(fields=["tenant_id", "requirement", "coverage"], name="cmp_map_tenant_req_cov_ix"),
                    models.Index(fields=["tenant_id", "policy", "coverage"], name="cmp_map_tenant_pol_cov_ix"),
                    models.Index(fields=["tenant_id", "deleted_at"], name="cmp_map_tenant_deleted_ix"),
                ],
                "constraints": [
                    models.UniqueConstraint(condition=models.Q(("deleted_at__isnull", True)), fields=("tenant_id", "requirement", "policy"), name="cmp_map_tenant_req_pol_uq"),
                    models.CheckConstraint(condition=models.Q(("coverage", "full")) | models.Q(("rationale", ""), _negated=True), name="cmp_map_rationale_ck"),
                ],
            },
        ),
        migrations.CreateModel(
            name="ComplianceAssessment",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("status", models.CharField(choices=[("not_assessed", "Not assessed"), ("in_progress", "In progress"), ("compliant", "Compliant"), ("partial", "Partial"), ("non_compliant", "Non-compliant"), ("not_applicable", "Not applicable")], max_length=20)),
                ("assessed_at", models.DateTimeField()),
                ("due_date", models.DateField(blank=True, null=True)),
                ("notes", models.TextField(blank=True)),
                ("source", models.CharField(choices=[("manual", "Manual"), ("import", "Import"), ("extension", "Extension")], max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("assessor", actor_fk(related_name="compliance_assessments")),
                ("mapping", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.PROTECT, related_name="assessments", to="compliance_management.requirementpolicymapping")),
                ("requirement", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="assessments", to="compliance_management.compliancerequirement")),
            ],
            options={
                "db_table": "compliance_assessments",
                "indexes": [
                    models.Index(fields=["tenant_id", "requirement", "-assessed_at"], name="cmp_assess_tenant_req_ix"),
                    models.Index(fields=["tenant_id", "status", "due_date"], name="cmp_assess_tenant_due_ix"),
                ],
                "constraints": [models.CheckConstraint(condition=models.Q(("status__in", ("not_assessed", "in_progress", "compliant"))) | models.Q(("notes", ""), _negated=True), name="cmp_assessment_notes_ck")],
            },
        ),
        migrations.CreateModel(
            name="ComplianceEvidence",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("deleted_at", models.DateTimeField(blank=True, null=True)),
                ("name", models.CharField(max_length=500)),
                ("description", models.TextField(blank=True)),
                ("evidence_type", models.CharField(choices=[("document", "Document"), ("report", "Report"), ("screenshot", "Screenshot"), ("log", "Log"), ("attestation", "Attestation"), ("external_reference", "External reference")], max_length=30)),
                ("reference_kind", models.CharField(choices=[("dms_document", "DMS document"), ("external_url", "External URL"), ("text_reference", "Text reference")], max_length=20)),
                ("document_id", models.UUIDField(blank=True, null=True)),
                ("external_uri", models.URLField(blank=True, max_length=200)),
                ("text_reference", models.CharField(blank=True, max_length=1000)),
                ("sha256", models.CharField(blank=True, max_length=64, validators=[src.modules.compliance_management.models.validate_optional_sha256])),
                ("classification", models.CharField(choices=[("public", "Public"), ("internal", "Internal"), ("confidential", "Confidential"), ("restricted", "Restricted")], max_length=20)),
                ("collection_method", models.CharField(choices=[("manual", "Manual"), ("import", "Import"), ("extension", "Extension")], max_length=20)),
                ("valid_from", models.DateTimeField(blank=True, null=True)),
                ("valid_until", models.DateTimeField(blank=True, null=True)),
                ("collected_at", models.DateTimeField()),
                ("collected_by", actor_fk(related_name="collected_compliance_evidence")),
                ("created_by", actor_fk()),
                ("deleted_by", actor_fk()),
                ("updated_by", actor_fk()),
            ],
            options={
                "db_table": "compliance_evidence",
                "indexes": [
                    models.Index(fields=["tenant_id", "classification", "collected_at"], name="cmp_evid_tenant_class_ix"),
                    models.Index(fields=["tenant_id", "valid_until", "deleted_at"], name="cmp_evid_tenant_valid_ix"),
                    models.Index(fields=["tenant_id", "document_id"], name="cmp_evid_tenant_doc_ix"),
                    models.Index(fields=["tenant_id", "deleted_at"], name="cmp_evid_tenant_deleted_ix"),
                ],
                "constraints": [
                    models.CheckConstraint(condition=((models.Q(reference_kind="dms_document") & models.Q(document_id__isnull=False) & models.Q(external_uri="") & models.Q(text_reference="")) | (models.Q(reference_kind="external_url") & models.Q(document_id__isnull=True) & ~models.Q(external_uri="") & models.Q(text_reference="")) | (models.Q(reference_kind="text_reference") & models.Q(document_id__isnull=True) & models.Q(external_uri="") & ~models.Q(text_reference=""))), name="cmp_evidence_reference_ck"),
                    models.CheckConstraint(condition=models.Q(("valid_until__isnull", True)) | models.Q(("valid_from__isnull", False), ("valid_until__gt", models.F("valid_from"))), name="cmp_evidence_validity_ck"),
                    models.CheckConstraint(condition=models.Q(("sha256", "")) | models.Q(("sha256__regex", "^[0-9a-f]{64}$")), name="cmp_evidence_sha256_ck"),
                ],
            },
        ),
        migrations.CreateModel(
            name="EvidenceRequirementLink",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("relevance", models.CharField(choices=[("supporting", "Supporting"), ("primary", "Primary"), ("contradicting", "Contradicting")], max_length=20)),
                ("notes", models.TextField(blank=True)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("created_by", actor_fk()),
                ("evidence", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="requirement_links", to="compliance_management.complianceevidence")),
                ("requirement", models.ForeignKey(on_delete=django.db.models.deletion.PROTECT, related_name="evidence_links", to="compliance_management.compliancerequirement")),
            ],
            options={
                "db_table": "compliance_evidence_requirement_links",
                "indexes": [
                    models.Index(fields=["tenant_id", "requirement", "relevance"], name="cmp_evid_link_req_rel_ix"),
                    models.Index(fields=["tenant_id", "evidence"], name="cmp_evid_link_evidence_ix"),
                ],
                "constraints": [models.UniqueConstraint(fields=("tenant_id", "evidence", "requirement"), name="cmp_evid_link_tenant_uq")],
            },
        ),
        migrations.CreateModel(
            name="ComplianceConfigurationRevision",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("environment", models.CharField(choices=[("development", "Development"), ("staging", "Staging"), ("production", "Production")], max_length=20)),
                ("version", models.PositiveIntegerField()),
                ("status", models.CharField(choices=[("draft", "Draft"), ("active", "Active"), ("superseded", "Superseded")], default="draft", max_length=20)),
                ("policy_code_prefix", models.CharField(max_length=10)),
                ("default_review_frequency_days", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(3650)])),
                ("expiry_warning_days", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(365)])),
                ("evidence_warning_days", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(365)])),
                ("minimum_assessment_note_length", models.PositiveSmallIntegerField(validators=[django.core.validators.MinValueValidator(0), django.core.validators.MaxValueValidator(2000)])),
                ("allow_external_evidence_urls", models.BooleanField()),
                ("bulk_import_row_limit", models.PositiveIntegerField(validators=[django.core.validators.MinValueValidator(1), django.core.validators.MaxValueValidator(10000)])),
                ("regulation_categories", models.JSONField(default=list, validators=[src.modules.compliance_management.models.validate_regulation_categories])),
                ("rollout", models.JSONField(blank=True, default=dict, validators=[src.modules.compliance_management.models.validate_rollout])),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("activated_at", models.DateTimeField(blank=True, null=True)),
                ("activated_by", actor_fk()),
                ("created_by", actor_fk()),
                ("transition_history", models.JSONField(blank=True, default=list)),
            ],
            options={
                "db_table": "compliance_configuration_revisions",
                "indexes": [models.Index(fields=["tenant_id", "environment", "status", "-version"], name="cmp_cfg_tenant_env_status_ix")],
                "constraints": [
                    models.UniqueConstraint(fields=("tenant_id", "environment", "version"), name="cmp_cfg_tenant_env_version_uq"),
                    models.UniqueConstraint(condition=models.Q(("status", "active")), fields=("tenant_id", "environment"), name="cmp_cfg_one_active_uq"),
                    models.CheckConstraint(condition=models.Q(("default_review_frequency_days__range", (1, 3650))), name="cmp_cfg_review_range_ck"),
                    models.CheckConstraint(condition=models.Q(("expiry_warning_days__range", (0, 365))), name="cmp_cfg_expiry_range_ck"),
                    models.CheckConstraint(condition=models.Q(("evidence_warning_days__range", (0, 365))), name="cmp_cfg_evidence_range_ck"),
                    models.CheckConstraint(condition=models.Q(("minimum_assessment_note_length__range", (0, 2000))), name="cmp_cfg_note_range_ck"),
                    models.CheckConstraint(condition=models.Q(("bulk_import_row_limit__range", (1, 10000))), name="cmp_cfg_import_range_ck"),
                ],
            },
        ),
        migrations.CreateModel(
            name="ComplianceActivity",
            fields=[
                ("tenant_id", models.UUIDField(db_index=True)),
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("entity_type", models.CharField(choices=[("framework", "Framework"), ("requirement", "Requirement"), ("policy", "Policy"), ("policy_version", "Policy version"), ("mapping", "Mapping"), ("assessment", "Assessment"), ("evidence", "Evidence"), ("evidence_link", "Evidence link"), ("configuration", "Configuration")], max_length=30)),
                ("entity_id", models.UUIDField()),
                ("action", models.CharField(max_length=100)),
                ("correlation_id", models.UUIDField()),
                ("before", models.JSONField(blank=True, default=dict)),
                ("after", models.JSONField(blank=True, default=dict)),
                ("reason", models.TextField(blank=True)),
                ("occurred_at", models.DateTimeField(auto_now_add=True)),
                ("actor", actor_fk(related_name="compliance_activity")),
            ],
            options={
                "db_table": "compliance_activity",
                "indexes": [
                    models.Index(fields=["tenant_id", "-occurred_at"], name="cmp_act_tenant_time_ix"),
                    models.Index(fields=["tenant_id", "entity_type", "entity_id", "-occurred_at"], name="cmp_act_tenant_entity_ix"),
                    models.Index(fields=["tenant_id", "correlation_id"], name="cmp_act_tenant_corr_ix"),
                ],
            },
        ),
    ]
