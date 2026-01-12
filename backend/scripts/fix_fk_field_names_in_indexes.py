#!/usr/bin/env python3
"""
Fix ForeignKey field names in AddIndex operations.
Django expects model field names (without _id suffix), not database column names.
"""
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent
MIGRATIONS_DIR = BACKEND_DIR / "src/modules/ai_agent_management/migrations"
INDEX_FILE = MIGRATIONS_DIR / "0022_add_all_indexes.py"

# Read the index migration
with open(INDEX_FILE, 'r') as f:
    content = f.read()

# Map of ForeignKey database column names to model field names
# These are extracted from the CreateModel operations
FK_MAPPING = {
    'agent_execution_id': 'agent_execution',
    'tool_id': 'tool',
    'agent_id': 'agent',
    'policy_id': 'policy',
    'agent_execution_id': 'agent_execution',
    'egress_rule_id': 'egress_rule',
}

# Replace all occurrences
original_content = content
for db_col, model_field in FK_MAPPING.items():
    # Replace in fields= arrays
    # Pattern: "field_name_id"  -> "field_name"
    content = re.sub(
        rf'"\b{db_col}\b"',
        f'"{model_field}"',
        content
    )

if content != original_content:
    print("Fixed FK field references:")
    for db_col, model_field in FK_MAPPING.items():
        if db_col in original_content:
            print(f"  - {db_col} → {model_field}")

    # Write back
    with open(INDEX_FILE, 'w') as f:
        f.write(content)

    print(f"\n✅ Updated {INDEX_FILE}")
else:
    print("No changes needed")
