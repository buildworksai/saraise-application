#!/usr/bin/env python3
"""
Surgical migration splitter for ai_agent_management/migrations/0001_initial.py

Splits 2,205-line migration into separate migrations (one per model or small groups).
Each migration file will be ≤200 lines per SARAISE standards.

Strategy: 21 models → ~21-24 model migrations + 4-5 index migrations
"""
import re
from pathlib import Path

# Paths
BACKEND_DIR = Path(__file__).parent.parent
MIGRATIONS_DIR = BACKEND_DIR / "src/modules/ai_agent_management/migrations"
ORIGINAL_FILE = BACKEND_DIR / "migration-backups-2026-01-09/ai_agent_0001_initial_BACKUP.py"

# Each model gets its own migration (or small groups for very small models)
MODEL_SEQUENCE = [
    ("agent", ["Agent"]),
    ("agent_execution", ["AgentExecution"]),
    ("agent_scheduler_task", ["AgentSchedulerTask"]),
    ("tool", ["Tool"]),
    ("tool_invocation", ["ToolInvocation"]),
    ("approval_request", ["ApprovalRequest"]),
    ("sod_policy", ["SoDPolicy"]),
    ("sod_violation", ["SoDViolation"]),
    ("tenant_quota", ["TenantQuota"]),
    ("quota_usage", ["QuotaUsage"]),
    ("cost_record", ["CostRecord"]),
    ("cost_summary", ["CostSummary"]),
    ("token_usage", ["TokenUsage"]),
    ("audit_event", ["AuditEvent"]),
    ("audit_trail", ["AuditTrail"]),
    ("egress_request", ["EgressRequest"]),
    ("egress_rule", ["EgressRule"]),
    ("secret", ["Secret"]),
    ("secret_access", ["SecretAccess"]),
    ("kill_switch", ["KillSwitch"]),
    ("shard_saturation", ["ShardSaturation"]),
]


def read_original_migration():
    """Read the original migration file."""
    with open(ORIGINAL_FILE, 'r') as f:
        return f.read()


def extract_model_operation(content, model_name):
    """Extract a single CreateModel operation for a model."""
    pattern = rf'migrations\.CreateModel\(\s*name="{model_name}"'
    match = re.search(pattern, content)
    if not match:
        return None

    start_pos = match.start()
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

    # Add proper indentation
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
    pattern = r'migrations\.AddIndex\([^)]+\),'
    matches = re.finditer(pattern, content, re.DOTALL)

    operations = []
    for match in matches:
        operation = match.group(0)
        lines = operation.split('\n')
        indented_lines = []
        for line in lines:
            if line.strip():
                indented_lines.append(' ' * 8 + line.strip())
            else:
                indented_lines.append('')
        operations.append('\n'.join(indented_lines))

    return operations


def get_import_for_model(model_name):
    """Get the correct import statement for a model."""
    imports = "from django.db import migrations, models"

    # Map model names to their import modules
    model_imports = {
        "Agent": "import src.modules.ai_agent_management.models",
        "AgentExecution": "import src.modules.ai_agent_management.models",
        "AgentSchedulerTask": "import src.modules.ai_agent_management.models",
        "Tool": "import src.modules.ai_agent_management.tool_models",
        "ToolInvocation": "import src.modules.ai_agent_management.tool_models",
        "ApprovalRequest": "import src.modules.ai_agent_management.approval_models",
        "SoDPolicy": "import src.modules.ai_agent_management.models",
        "SoDViolation": "import src.modules.ai_agent_management.models",
        "TenantQuota": "import src.modules.ai_agent_management.quota_models",
        "QuotaUsage": "import src.modules.ai_agent_management.quota_models",
        "CostRecord": "import src.modules.ai_agent_management.models",
        "CostSummary": "import src.modules.ai_agent_management.models",
        "TokenUsage": "import src.modules.ai_agent_management.token_models",
        "AuditEvent": "import src.modules.ai_agent_management.audit_models",
        "AuditTrail": "import src.modules.ai_agent_management.audit_models",
        "EgressRequest": "import src.modules.ai_agent_management.egress_models",
        "EgressRule": "import src.modules.ai_agent_management.egress_models",
        "Secret": "import src.modules.ai_agent_management.models",
        "SecretAccess": "import src.modules.ai_agent_management.models",
        "KillSwitch": "import src.modules.ai_agent_management.models",
        "ShardSaturation": "import src.modules.ai_agent_management.models",
    }

    for model in model_imports:
        if model in model_name:
            imports += f"\n{model_imports[model]}"
            break

    return imports


def create_model_migration(file_name, models, operations, migration_num, prev_migration=None):
    """Create a migration file for model(s)."""
    # Get imports for all models
    imports = "from django.db import migrations, models"
    added_imports = set()

    for model in models:
        model_import = get_import_for_model(model).split('\n')[-1]
        if model_import and model_import not in added_imports:
            imports += f"\n{model_import}"
            added_imports.add(model_import)

    # Check if we need django deletion
    operations_str = '\n'.join(operations)
    if "django.db.models.deletion" in operations_str:
        imports += "\nimport django.db.models.deletion"

    # Determine dependency
    if migration_num == 1:
        dependency = 'dependencies = []'
        is_initial = True
    else:
        dependency = f'dependencies = [\n        ("ai_agent_management", "{prev_migration}"),\n    ]'
        is_initial = False

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

    return content


def create_index_migration(file_name, index_ops, migration_num, prev_migration):
    """Create a migration file for indexes."""
    operations_str = '\n'.join(index_ops)

    content = f'''# Generated by Django 4.2.27 on 2026-01-09 (split from 0001)

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ai_agent_management", "{prev_migration}"),
    ]

    operations = [
{operations_str}
    ]
'''

    return content


def main():
    print("🔪 Surgical Migration Splitter: AI Agent Management (v2)")
    print("=" * 70)
    print(f"Original file: {ORIGINAL_FILE}")
    print(f"Models: {len(MODEL_SEQUENCE)}")
    print()

    # Read original migration
    print("📖 Reading original migration...")
    content = read_original_migration()
    print(f"   Original size: {len(content)} chars, {len(content.splitlines())} lines")

    # Split models
    print("\n✂️  Splitting model migrations...")
    created_files = []
    prev_migration = None

    for i, (name, models) in enumerate(MODEL_SEQUENCE, start=1):
        print(f"\n   [{i}/{len(MODEL_SEQUENCE)}] Processing {name}...")

        operations = []
        for model_name in models:
            operation = extract_model_operation(content, model_name)
            if not operation:
                print(f"      ⚠️  Could not extract operation for {model_name}")
                continue
            operations.append(operation)

        if not operations:
            print(f"      ❌ No operations extracted")
            continue

        file_name = f"{i:04d}_create_{name}.py"
        file_content = create_model_migration(file_name, models, operations, i, prev_migration)

        output_path = MIGRATIONS_DIR / file_name
        with open(output_path, 'w') as f:
            f.write(file_content)

        lines = len(file_content.splitlines())
        print(f"      ✅ Created: {file_name} ({lines} lines)")
        created_files.append((file_name, lines))

        prev_migration = file_name.replace('.py', '')

    # Extract and split indexes
    print(f"\n✂️  Splitting index migrations...")
    index_operations = extract_add_index_operations(content)
    print(f"   Found {len(index_operations)} AddIndex operations")

    # Split indexes into batches of 15 (each batch ~170 lines)
    batch_size = 15
    index_batches = [index_operations[i:i + batch_size] for i in range(0, len(index_operations), batch_size)]

    current_migration_num = len(MODEL_SEQUENCE) + 1

    for batch_num, batch in enumerate(index_batches, start=1):
        print(f"\n   Index batch {batch_num}/{len(index_batches)} ({len(batch)} indexes)...")

        file_name = f"{current_migration_num:04d}_add_indexes_batch_{batch_num}.py"
        file_content = create_index_migration(file_name, batch, current_migration_num, prev_migration)

        output_path = MIGRATIONS_DIR / file_name
        with open(output_path, 'w') as f:
            f.write(file_content)

        lines = len(file_content.splitlines())
        print(f"      ✅ Created: {file_name} ({lines} lines)")
        created_files.append((file_name, lines))

        prev_migration = file_name.replace('.py', '')
        current_migration_num += 1

    print("\n" + "=" * 70)
    print("📊 Summary:")
    print(f"   Total migrations created: {len(created_files)}")
    print(f"   Average lines per migration: {sum(l for _, l in created_files) / len(created_files):.1f}")
    print(f"   Max lines: {max(l for _, l in created_files)}")
    print(f"   Min lines: {min(l for _, l in created_files)}")
    print(f"   All files ≤200 lines: {'✅ YES' if all(l <= 200 for _, l in created_files) else '❌ NO'}")

    if any(l > 200 for _, l in created_files):
        print("\n⚠️  Files exceeding 200 lines:")
        for fname, lines in created_files:
            if lines > 200:
                print(f"      - {fname}: {lines} lines")

    print("\n✅ Migration splitting complete!")
    print("\n⚠️  IMPORTANT: Original 0001 file preserved for reference.")
    print("   Archive it after verification.")


if __name__ == "__main__":
    main()
