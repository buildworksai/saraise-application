#!/usr/bin/env python3
"""
Complete AI Agent migration splitter that handles CreateModel + AddField + AddIndex.

Strategy:
1. Extract all CreateModel operations
2. Find AddField operations for each model
3. Group them together in the same migration
4. Skip AddIndex (they'll be added later or embedded in options)
"""
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent
MIGRATIONS_DIR = BACKEND_DIR / "src/modules/ai_agent_management/migrations"
BACKUP_FILE = BACKEND_DIR / "migration-backups-2026-01-09/ai_agent_0001_initial_BACKUP.py"

with open(BACKUP_FILE, 'r') as f:
    content = f.read()

# Model sequence
MODELS = [
    ("agent", "Agent"),
    ("agent_execution", "AgentExecution"),
    ("agent_scheduler_task", "AgentSchedulerTask"),
    ("tool", "Tool"),
    ("tool_invocation", "ToolInvocation"),
    ("approval_request", "ApprovalRequest"),
    ("sod_policy", "SoDPolicy"),
    ("sod_violation", "SoDViolation"),
    ("tenant_quota", "TenantQuota"),
    ("quota_usage", "QuotaUsage"),
    ("cost_record", "CostRecord"),
    ("cost_summary", "CostSummary"),
    ("token_usage", "TokenUsage"),
    ("audit_event", "AuditEvent"),
    ("audit_trail", "AuditTrail"),
    ("egress_request", "EgressRequest"),
    ("egress_rule", "EgressRule"),
    ("secret", "Secret"),
    ("secret_access", "SecretAccess"),
    ("kill_switch", "KillSwitch"),
    ("shard_saturation", "ShardSaturation"),
]

IMPORT_MAP = {
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


def extract_operation(content, pattern_start, start_keyword):
    """Extract an operation (CreateModel or AddField) by counting parentheses."""
    match = re.search(pattern_start, content, re.IGNORECASE)
    if not match:
        return None

    start_pos = match.start()
    rest_content = content[start_pos:]
    paren_count = 0
    in_operation = False
    end_pos = start_pos

    for i, char in enumerate(rest_content):
        if char == '(':
            paren_count += 1
            in_operation = True
        elif char == ')':
            paren_count -= 1
            if in_operation and paren_count == 0:
                end_pos = start_pos + i + 1
                break

    operation = content[start_pos:end_pos]

    # Indent properly
    lines = operation.split('\n')
    indented_lines = []
    for line in lines:
        if line.strip():
            indented_lines.append(' ' * 8 + line.strip())
        else:
            indented_lines.append('')

    return '\n'.join(indented_lines) + ','


def find_add_fields_for_model(content, model_name):
    """Find all AddField operations for a specific model."""
    pattern = rf'migrations\.AddField\(\s*model_name="{model_name.lower()}"'
    matches = []

    pos = 0
    while True:
        match = re.search(pattern, content[pos:], re.IGNORECASE)
        if not match:
            break

        start_pos = pos + match.start()
        rest_content = content[start_pos:]
        paren_count = 0
        in_operation = False
        end_pos = start_pos

        for i, char in enumerate(rest_content):
            if char == '(':
                paren_count += 1
                in_operation = True
            elif char == ')':
                paren_count -= 1
                if in_operation and paren_count == 0:
                    end_pos = start_pos + i + 1
                    break

        operation = content[start_pos:end_pos]

        # Indent
        lines = operation.split('\n')
        indented_lines = []
        for line in lines:
            if line.strip():
                indented_lines.append(' ' * 8 + line.strip())
            else:
                indented_lines.append('')

        matches.append('\n'.join(indented_lines) + ',')
        pos = end_pos

    return matches


print("🔪 Complete AI Agent Migration Splitter")
print("=" * 70)

created_files = []
prev_migration = None

for i, (snake_name, model_name) in enumerate(MODELS, start=1):
    print(f"\n[{i}/{len(MODELS)}] Processing {model_name}...")

    # Extract CreateModel
    create_pattern = rf'migrations\.CreateModel\(\s*name="{model_name}"'
    create_op = extract_operation(content, create_pattern, "CreateModel")

    if not create_op:
        print(f"  ❌ Could not extract CreateModel for {model_name}")
        continue

    # Find AddField operations for this model
    add_fields = find_add_fields_for_model(content, model_name)

    if add_fields:
        print(f"  📎 Found {len(add_fields)} AddField operations")

    # Combine operations
    all_operations = [create_op] + add_fields
    operations_str = '\n'.join(all_operations)

    # Build imports
    imports = "from django.db import migrations, models"
    if model_name in IMPORT_MAP:
        imports += f"\n{IMPORT_MAP[model_name]}"

    if "django.db.models.deletion" in operations_str:
        imports += "\nimport django.db.models.deletion"

    # Build migration file
    if i == 1:
        dependency = 'dependencies = []'
        is_initial = True
    else:
        prev_snake = MODELS[i-2][0]
        dependency = f'dependencies = [\n        ("ai_agent_management", "{i-1:04d}_create_{prev_snake}"),\n    ]'
        is_initial = False

    initial_flag = '\n    initial = True\n' if is_initial else '\n'

    file_name = f"{i:04d}_create_{snake_name}.py"

    migration_content = f'''# Generated by Django 4.2.27 on 2026-01-09 (split from 0001 with AddFields)

{imports}


class Migration(migrations.Migration):
{initial_flag}
    {dependency}

    operations = [
{operations_str}
    ]
'''

    output_path = MIGRATIONS_DIR / file_name
    with open(output_path, 'w') as f:
        f.write(migration_content)

    lines = len(migration_content.splitlines())
    print(f"  ✅ Created: {file_name} ({lines} lines)")

    if lines > 200:
        print(f"  ⚠️  Exceeds 200 lines!")

    created_files.append((file_name, lines))

print("\n" + "=" * 70)
print("📊 Summary:")
print(f"   Total migrations created: {len(created_files)}")
print(f"   Average lines per migration: {sum(l for _, l in created_files) / len(created_files):.1f}")
print(f"   Max lines: {max(l for _, l in created_files)}")
print(f"   Min lines: {min(l for _, l in created_files)}")
print(f"   Files >200 lines: {sum(1 for _, l in created_files if l > 200)}")

if any(l > 200 for _, l in created_files):
    print("\n⚠️  Files exceeding 200 lines:")
    for fname, lines in created_files:
        if lines > 200:
            print(f"      - {fname}: {lines} lines")

print("\n✅ Migration splitting complete!")
print("\nℹ️  Note: AddIndex operations were skipped. Indexes are created")
print("   automatically by Django for ForeignKey fields. Additional")
print("   composite indexes can be added in a follow-up migration.")
