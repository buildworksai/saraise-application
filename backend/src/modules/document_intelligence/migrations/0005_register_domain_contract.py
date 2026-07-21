"""Register the v2 domain/search contract in the additive module registry."""

import hashlib
import json

from django.db import migrations

MODULE_NAME = "document-intelligence"
MODULE_VERSION = "2.0.0"
MIGRATION_MARKER = "document_intelligence.0005_register_domain_contract"

PERMISSIONS = [
    "document_intelligence.extraction:read",
    "document_intelligence.extraction:create",
    "document_intelligence.extraction:cancel",
    "document_intelligence.extraction:retry",
    "document_intelligence.extraction:delete",
    "document_intelligence.classification:read",
    "document_intelligence.classification:create",
    "document_intelligence.classification:review",
    "document_intelligence.classification:cancel",
    "document_intelligence.classification:retry",
    "document_intelligence.classification:delete",
    "document_intelligence.template:read",
    "document_intelligence.template:create",
    "document_intelligence.template:update",
    "document_intelligence.template:delete",
    "document_intelligence.template:activate",
    "document_intelligence.training:read",
    "document_intelligence.training:create",
    "document_intelligence.training:cancel",
    "document_intelligence.training:retry",
    "document_intelligence.model:read",
    "document_intelligence.model:activate",
    "document_intelligence.model:rollback",
    "document_intelligence.health:read",
]

SEARCH_INDEXES = [
    "document_intelligence_extractions",
    "document_intelligence_classifications",
    "document_intelligence_extraction_templates",
    "document_intelligence_classifier_training_jobs",
    "document_intelligence_classifier_model_versions",
]

AI_TOOLS = [
    "document_intelligence.extract",
    "document_intelligence.classify",
    "document_intelligence.train_classifier",
]

MANIFEST = {
    "name": MODULE_NAME,
    "version": MODULE_VERSION,
    "description": "Tenant-safe OCR, extraction, classification, human review, training, and template management",
    "type": "foundation",
    "lifecycle": "core",
    "dependencies": [
        "core-identity >=1.0.0",
        "ai-agent-management >=1.0.0",
        "dms >=1.0.0",
    ],
    "permissions": PERMISSIONS,
    "sod_actions": [],
    "search_indexes": SEARCH_INDEXES,
    "ai_tools": AI_TOOLS,
    "metadata": {
        "api_version": "v2",
        "extension_surface": "registered-adapters-and-category-schemas",
        "quota_resources": [
            "document_intelligence.api_reads",
            "document_intelligence.api_writes",
            "document_intelligence.processing_requests",
            "document_intelligence.pages_processed",
            "document_intelligence.training_documents",
        ],
    },
}


def register_contract(apps, schema_editor):
    """Create the immutable v2 registry row, rejecting natural-key conflicts."""
    ModuleRegistryEntry = apps.get_model("core", "ModuleRegistryEntry")
    manifest_content = json.dumps(MANIFEST, sort_keys=True, separators=(",", ":"))
    metadata = dict(MANIFEST["metadata"], migration_marker=MIGRATION_MARKER)
    _entry, created = ModuleRegistryEntry.objects.get_or_create(
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
            "sod_actions": [],
            "search_indexes": SEARCH_INDEXES,
            "ai_tools": AI_TOOLS,
            "metadata": metadata,
            "is_active": True,
        },
    )
    if not created and _entry.metadata.get("migration_marker") != MIGRATION_MARKER:
        raise RuntimeError("Conflicting document-intelligence v2 module registration already exists")


def unregister_contract(apps, schema_editor):
    """Delete only the registry row demonstrably created by this migration."""
    ModuleRegistryEntry = apps.get_model("core", "ModuleRegistryEntry")
    for entry in ModuleRegistryEntry.objects.filter(name=MODULE_NAME, version=MODULE_VERSION):
        if entry.metadata.get("migration_marker") == MIGRATION_MARKER:
            entry.delete()


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0011_apply_typed_rls_to_notifications"),
        ("document_intelligence", "0004_domain_rls"),
    ]

    operations = [migrations.RunPython(register_contract, unregister_contract)]
