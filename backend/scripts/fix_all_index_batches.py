#!/usr/bin/env python3
"""
Fix ForeignKey field names in ALL AddIndex batch migrations.
"""
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent
MIGRATIONS_DIR = BACKEND_DIR / "src/modules/ai_agent_management/migrations"

# FK mapping: database column name -> model field name
FK_MAPPING = {
    'agent_execution_id': 'agent_execution',
    'tool_id': 'tool',
    'agent_id': 'agent',
    'policy_id': 'policy',
    'egress_rule_id': 'egress_rule',
}

# Find all index batch files
index_files = list(MIGRATIONS_DIR.glob("00*_add_indexes_batch_*.py"))

print(f"Found {len(index_files)} index batch files to fix")

for index_file in sorted(index_files):
    print(f"\nProcessing {index_file.name}...")

    with open(index_file, 'r') as f:
        content = f.read()

    original_content = content

    # Replace all FK references
    for db_col, model_field in FK_MAPPING.items():
        pattern = rf'"\b{db_col}\b"'
        replacement = f'"{model_field}"'
        content = re.sub(pattern, replacement, content)

    if content != original_content:
        with open(index_file, 'w') as f:
            f.write(content)
        print(f"  ✅ Fixed {index_file.name}")
    else:
        print(f"  ⏭️  No changes needed for {index_file.name}")

print("\n✅ All index batch files processed!")
