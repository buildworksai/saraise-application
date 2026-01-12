#!/usr/bin/env python3
"""
Surgical migration splitter for ai_agent_management/migrations/0001_initial.py

Splits 2,205-line migration with 21 models + 86 indexes into 11 separate migrations.
Each migration file will be ≤200 lines per SARAISE standards.

Usage:
    python scripts/split_migration_ai_agent_0001.py
"""
import os
import re
from pathlib import Path

# Paths
BACKEND_DIR = Path(__file__).parent.parent
MIGRATIONS_DIR = BACKEND_DIR / "src/modules/ai_agent_management/migrations"
ORIGINAL_FILE = MIGRATIONS_DIR / "0001_initial.py"

# Model groupings (strategic grouping to keep related models together)
MODEL_GROUPS = [
    {
        "name": "agent_core",
        "models": ["Agent", "AgentExecution", "AgentSchedulerTask"],
        "migration_num": 1,
        "description": "Core agent models"
    },
    {
        "name": "tool",
        "models": ["Tool", "ToolInvocation"],
        "migration_num": 2,
        "description": "Tool models"
    },
    {
        "name": "approval",
        "models": ["ApprovalRequest"],
        "migration_num": 3,
        "description": "Approval models"
    },
    {
        "name": "sod",
        "models": ["SoDPolicy", "SoDViolation"],
        "migration_num": 4,
        "description": "Segregation of Duties models"
    },
    {
        "name": "quota",
        "models": ["TenantQuota", "QuotaUsage"],
        "migration_num": 5,
        "description": "Quota models"
    },
    {
        "name": "cost",
        "models": ["CostRecord", "CostSummary", "TokenUsage"],
        "migration_num": 6,
        "description": "Cost tracking models"
    },
    {
        "name": "audit",
        "models": ["AuditEvent", "AuditTrail"],
        "migration_num": 7,
        "description": "Audit models"
    },
    {
        "name": "egress",
        "models": ["EgressRequest", "EgressRule"],
        "migration_num": 8,
        "description": "Egress control models"
    },
    {
        "name": "secret",
        "models": ["Secret", "SecretAccess"],
        "migration_num": 9,
        "description": "Secret management models"
    },
    {
        "name": "control",
        "models": ["KillSwitch", "ShardSaturation"],
        "migration_num": 10,
        "description": "Control plane models"
    },
]


def read_original_migration():
    """Read the original migration file."""
    with open(ORIGINAL_FILE, 'r') as f:
        return f.read()


def extract_imports(content):
    """Extract import statements from migration."""
    lines = content.split('\n')
    imports = []
    for line in lines:
        if line.startswith('import ') or line.startswith('from '):
            imports.append(line)
        elif line.startswith('class Migration'):
            break
    return '\n'.join(imports)


def extract_model_operation(content, model_name):
    """Extract a single CreateModel operation for a model."""
    # Find the start of this model's CreateModel
    pattern = rf'migrations\.CreateModel\(\s*name="{model_name}"'
    match = re.search(pattern, content)
    if not match:
        return None

    start_pos = match.start()

    # Find the end by counting parentheses
    rest_content = content[start_pos:]
    paren_count = 0
    in_create_model = False
    end_pos = start_pos

    for i, char in enumerate(rest_content):
        if char == '(':
            paren_count += 1
            in_create_model = True
        elif char == ')':
            paren_count -= 1
            if in_create_model and paren_count == 0:
                end_pos = start_pos + i + 1
                break

    operation = content[start_pos:end_pos]

    # Add proper indentation (8 spaces for operations list)
    lines = operation.split('\n')
    indented_lines = []
    for line in lines:
        if line.strip():
            indented_lines.append(' ' * 8 + line.strip())
        else:
            indented_lines.append('')

    return '\n'.join(indented_lines) + ','


def extract_add_index_operations(content):
    """Extract all AddIndex operations."""
    # Find all AddIndex operations
    pattern = r'migrations\.AddIndex\([^)]+\),'
    matches = re.finditer(pattern, content, re.DOTALL)

    operations = []
    for match in matches:
        operation = match.group(0)
        # Add proper indentation
        lines = operation.split('\n')
        indented_lines = []
        for line in lines:
            if line.strip():
                indented_lines.append(' ' * 8 + line.strip())
            else:
                indented_lines.append('')
        operations.append('\n'.join(indented_lines))

    return operations


def create_migration_file(group, operations, migration_number, dependency_number):
    """Create a new migration file for a group of models."""
    file_name = f"{migration_number:04d}_create_{group['name']}.py"

    # Get imports
    imports = "from django.db import migrations, models"

    # Add specific imports based on group
    if group['name'] == 'agent_core':
        imports += "\nimport src.modules.ai_agent_management.models"
    elif group['name'] == 'tool':
        imports += "\nimport src.modules.ai_agent_management.tool_models"
    elif group['name'] == 'approval':
        imports += "\nimport src.modules.ai_agent_management.approval_models"
    elif group['name'] == 'quota':
        imports += "\nimport src.modules.ai_agent_management.quota_models"
    elif group['name'] == 'cost':
        imports += "\nimport src.modules.ai_agent_management.models"
    elif group['name'] == 'audit':
        imports += "\nimport src.modules.ai_agent_management.audit_models"
    elif group['name'] == 'egress':
        imports += "\nimport src.modules.ai_agent_management.egress_models"
    elif group['name'] == 'secret':
        imports += "\nimport src.modules.ai_agent_management.models"
    elif group['name'] == 'control':
        imports += "\nimport src.modules.ai_agent_management.models"
    elif group['name'] == 'sod':
        imports += "\nimport src.modules.ai_agent_management.models"

    # Check if foreign keys exist
    operations_str = '\n'.join(operations)
    if "django.db.models.deletion" in operations_str:
        imports += "\nimport django.db.models.deletion"

    # Determine dependency
    if migration_number == 1:
        dependency = 'dependencies = []'
        is_initial = True
    else:
        prev_group = MODEL_GROUPS[migration_number - 2]
        dependency = f'dependencies = [\n        ("ai_agent_management", "{dependency_number:04d}_create_{prev_group["name"]}"),\n    ]'
        is_initial = False

    # Create migration content
    initial_flag = '\n    initial = True\n' if is_initial else '\n'

    content = f'''# Generated by Django 4.2.27 on 2026-01-09 (split from 0001)

{imports}


class Migration(migrations.Migration):
{initial_flag}
    {dependency}

    operations = [
{operations_str}
    ]
'''

    return file_name, content


def create_index_migration(index_operations, migration_number):
    """Create migration file for all AddIndex operations."""
    file_name = f"{migration_number:04d}_add_indexes.py"

    # Join all index operations
    operations_str = '\n'.join(index_operations)

    # Get dependency on last model migration
    prev_group = MODEL_GROUPS[-1]

    content = f'''# Generated by Django 4.2.27 on 2026-01-09 (split from 0001)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai_agent_management", "{migration_number - 1:04d}_create_{prev_group["name"]}"),
    ]

    operations = [
{operations_str}
    ]
'''

    return file_name, content


def main():
    print("🔪 Surgical Migration Splitter: AI Agent Management")
    print("=" * 60)
    print(f"Original file: {ORIGINAL_FILE}")
    print(f"Model groups to split: {len(MODEL_GROUPS)}")
    print(f"Plus 1 migration for indexes")
    print()

    # Read original migration
    print("📖 Reading original migration...")
    content = read_original_migration()
    print(f"   Original size: {len(content)} chars, {len(content.splitlines())} lines")

    # Process each model group
    print("\n✂️  Splitting migrations...")
    created_files = []

    for group in MODEL_GROUPS:
        migration_number = group['migration_num']
        dependency_number = migration_number - 1 if migration_number > 1 else 0

        print(f"\n   [{migration_number}/{len(MODEL_GROUPS) + 1}] Processing {group['name']}...")
        print(f"      Models: {', '.join(group['models'])}")

        # Extract operations for all models in group
        operations = []
        for model_name in group['models']:
            operation = extract_model_operation(content, model_name)
            if not operation:
                print(f"      ⚠️  Could not extract operation for {model_name}")
                continue
            operations.append(operation)

        if not operations:
            print(f"      ❌ No operations extracted for group {group['name']}")
            continue

        # Create migration file
        file_name, file_content = create_migration_file(
            group, operations, migration_number, dependency_number
        )

        # Calculate output path
        output_path = MIGRATIONS_DIR / file_name

        # Write file
        with open(output_path, 'w') as f:
            f.write(file_content)

        lines = len(file_content.splitlines())
        print(f"      ✅ Created: {file_name} ({lines} lines)")
        created_files.append((file_name, lines))

    # Extract and create index migration
    print(f"\n   [{len(MODEL_GROUPS) + 1}/{len(MODEL_GROUPS) + 1}] Processing indexes...")
    index_operations = extract_add_index_operations(content)
    print(f"      Found {len(index_operations)} AddIndex operations")

    if index_operations:
        file_name, file_content = create_index_migration(index_operations, len(MODEL_GROUPS) + 1)
        output_path = MIGRATIONS_DIR / file_name

        with open(output_path, 'w') as f:
            f.write(file_content)

        lines = len(file_content.splitlines())
        print(f"      ✅ Created: {file_name} ({lines} lines)")
        created_files.append((file_name, lines))

    print("\n" + "=" * 60)
    print("📊 Summary:")
    print(f"   Total migrations created: {len(created_files)}")
    print(f"   Average lines per migration: {sum(l for _, l in created_files) / len(created_files):.1f}")
    print(f"   Max lines: {max(l for _, l in created_files)}")
    print(f"   All files ≤200 lines: {'✅ YES' if all(l <= 200 for _, l in created_files) else '❌ NO'}")

    print("\n✅ Migration splitting complete!")
    print("\n⚠️  IMPORTANT: Do NOT delete the original 0001 file yet.")
    print("   First verify the split migrations work correctly.")
    print("\n📝 Next steps:")
    print("   1. Review generated migrations")
    print("   2. Test migrations: python manage.py migrate ai_agent_management")
    print("   3. If successful, archive original 0001 file")


if __name__ == "__main__":
    main()
