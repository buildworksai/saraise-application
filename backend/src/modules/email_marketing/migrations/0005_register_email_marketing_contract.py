"""Idempotently register the canonical email-marketing v2 contract."""

import hashlib
import json

from django.db import migrations

MODULE_NAME = "email_marketing"
MODULE_VERSION = "2.0.0"
MIGRATION_MARKER = "email_marketing.0005_register_email_marketing_contract"

PERMISSIONS = [
    "email_marketing.campaign:read",
    "email_marketing.campaign:create",
    "email_marketing.campaign:update",
    "email_marketing.campaign:delete",
    "email_marketing.campaign:resolve_audience",
    "email_marketing.campaign:schedule",
    "email_marketing.campaign:send",
    "email_marketing.campaign:pause",
    "email_marketing.campaign:cancel",
    "email_marketing.analytics:read",
    "email_marketing.template:read",
    "email_marketing.template:create",
    "email_marketing.template:update",
    "email_marketing.template:delete",
    "email_marketing.template:activate",
    "email_marketing.recipient:read",
    "email_marketing.recipient:retry",
    "email_marketing.delivery:read",
    "email_marketing.suppression:read",
    "email_marketing.suppression:manage",
    "email_marketing.consent:read",
    "email_marketing.consent:record",
    "email_marketing.consent:revoke",
    "email_marketing.health:read",
    "email_marketing.provider_event:ingest",
]

QUOTA_RESOURCES = [
    {"name": "email_marketing.api_reads", "cost": 1, "open_source_monthly_default": 100000},
    {"name": "email_marketing.api_writes", "cost": 1, "open_source_monthly_default": 10000},
    {"name": "email_marketing.audience_resolutions", "cost": 1, "open_source_monthly_default": 1000},
    {
        "name": "email_marketing.monthly_recipients",
        "cost_projection": "eligible_recipient",
        "open_source_monthly_default": 10000,
    },
]

MANIFEST = {
    "name": MODULE_NAME,
    "version": MODULE_VERSION,
    "description": (
        "Tenant-isolated, consent-aware email campaign authoring, durable delivery, "
        "suppression management, provider event processing, and analytics."
    ),
    "type": "domain",
    "lifecycle": "managed",
    "dependencies": [],
    "permissions": PERMISSIONS,
    "sod_actions": ["email_marketing.campaign:send", "email_marketing.suppression:manage"],
    "search_indexes": [
        "email_campaigns",
        "email_templates",
        "email_campaign_recipients",
        "email_suppression_entries",
    ],
    "ai_tools": [],
    "metadata": {
        "entitlement": "email_marketing",
        "api_version": "v2",
        "canonical_prefix": "/api/v2/email-marketing/",
        "quota_resources": QUOTA_RESOURCES,
        "state_machines": [
            "email_marketing.campaign",
            "email_marketing.template",
            "email_marketing.recipient",
        ],
        "durable_jobs": [
            "email_marketing.resolve_audience",
            "email_marketing.send_campaign",
            "email_marketing.send_recipient",
            "email_marketing.reconcile_delivery",
            "email_marketing.process_provider_event",
        ],
    },
}


def register_contract(apps, schema_editor):
    del schema_editor
    ModuleRegistryEntry = apps.get_model("core", "ModuleRegistryEntry")
    manifest_content = json.dumps(MANIFEST, sort_keys=True, separators=(",", ":"))
    metadata = dict(MANIFEST["metadata"], migration_marker=MIGRATION_MARKER)
    entry, created = ModuleRegistryEntry.objects.get_or_create(
        name=MODULE_NAME,
        version=MODULE_VERSION,
        defaults={
            "description": MANIFEST["description"],
            "module_type": MANIFEST["type"],
            "lifecycle": MANIFEST["lifecycle"],
            "manifest_content": manifest_content,
            "manifest_hash": hashlib.sha256(manifest_content.encode("utf-8")).hexdigest(),
            "dependencies": MANIFEST["dependencies"],
            "permissions": PERMISSIONS,
            "sod_actions": MANIFEST["sod_actions"],
            "search_indexes": MANIFEST["search_indexes"],
            "ai_tools": [],
            "metadata": metadata,
            "is_active": True,
        },
    )
    if not created and entry.metadata.get("migration_marker") != MIGRATION_MARKER:
        raise RuntimeError("Conflicting email-marketing v2 module registration already exists")


def unregister_contract(apps, schema_editor):
    del schema_editor
    ModuleRegistryEntry = apps.get_model("core", "ModuleRegistryEntry")
    for entry in ModuleRegistryEntry.objects.filter(name=MODULE_NAME, version=MODULE_VERSION):
        if entry.metadata.get("migration_marker") == MIGRATION_MARKER:
            entry.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_apply_typed_rls_to_notifications"),
        ("email_marketing", "0004_constraints_indexes_and_rls"),
    ]

    operations = [migrations.RunPython(register_contract, unregister_contract)]
