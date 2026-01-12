#!/usr/bin/env python3
"""
Split ai_agent_management migration with indexes EMBEDDED in CreateModel operations.
This avoids the AddIndex state management issue.
"""
import re
from pathlib import Path

BACKEND_DIR = Path(__file__).parent.parent
MIGRATIONS_DIR = BACKEND_DIR / "src/modules/ai_agent_management/migrations"
BACKUP_FILE = BACKEND_DIR / "migration-backups-2026-01-09/ai_agent_0001_initial_BACKUP.py"

# Read backup
with open(BACKUP_FILE, 'r') as f:
    content = f.read()

# Extract all AddIndex operations and map to models
lines = content.split('\n')
model_indexes = {}  # model_name -> list of index operations

i = 0
while i < len(lines):
    line = lines[i]
    if 'migrations.AddIndex(' in line:
        # Extract model_name
        model_match = re.search(r'model_name="(\w+)"', lines[i+1] if i+1 < len(lines) else '')
        if model_match:
            model_name = model_match.group(1).lower()

            # Extract the index definition
            index_start = i
            paren_count = line.count('(') - line.count(')')
            i += 1

            while i < len(lines) and paren_count > 0:
                paren_count += lines[i].count('(') - lines[i].count(')')
                i += 1

            # Get the index definition between "index=" and the closing paren
            index_lines = lines[index_start:i]
            index_str = '\n'.join(index_lines)

            # Extract just the models.Index(...) part
            index_match = re.search(r'index=(models\.Index\([^)]+\))', index_str, re.DOTALL)
            if index_match:
                index_def = index_match.group(1)
                if model_name not in model_indexes:
                    model_indexes[model_name] = []
                model_indexes[model_name].append(index_def)
        else:
            i += 1
    else:
        i += 1

print(f"Extracted indexes for {len(model_indexes)} models")
for model, indexes in model_indexes.items():
    print(f"  {model}: {len(indexes)} indexes")

# Now extract CreateModel operations and inject indexes
def extract_create_model_with_indexes(content, model_name):
    """Extract CreateModel and add indexes to its options."""
    pattern = rf'migrations\.CreateModel\(\s*name="{model_name}"'
    match = re.search(pattern, content, re.IGNORECASE)
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

    # Check if this model has indexes to add
    model_lower = model_name.lower()
    if model_lower in model_indexes:
        # Find the options section or create one
        if 'options={' in operation:
            # Has options, add indexes to it
            options_match = re.search(r'(options=\{[^}]+)\}', operation, re.DOTALL)
            if options_match:
                options_content = options_match.group(1)

                # Check if already has indexes
                if '"indexes"' in options_content or "'indexes'" in options_content:
                    print(f"  ⚠️  {model_name} already has indexes in options, skipping")
                else:
                    # Add indexes to options
                    indexes_str = ",\n".join([f"                {idx}" for idx in model_indexes[model_lower]])
                    new_options = f'{options_content},\n            "indexes": [\n{indexes_str}\n            ]\n        }}'
                    operation = operation.replace(options_match.group(0), new_options)
        else:
            # No options, create options block with indexes
            indexes_str = ",\n".join([f"                {idx}" for idx in model_indexes[model_lower]])
            # Find where to insert (before the closing paren and comma of CreateModel)
            operation = operation.rstrip(',)')
            operation += f''',
        options={{
            "indexes": [
{indexes_str}
            ]
        }}
    ),'''

    # Add proper indentation
    lines = operation.split('\n')
    indented_lines = []
    for line in lines:
        if line.strip():
            indented_lines.append(' ' * 8 + line.strip())
        else:
            indented_lines.append('')

    return '\n'.join(indented_lines) + ','


# Model sequence (21 models)
MODELS = [
    "Agent", "AgentExecution", "AgentSchedulerTask", "Tool", "ToolInvocation",
    "ApprovalRequest", "SoDPolicy", "SoDViolation", "TenantQuota", "QuotaUsage",
    "CostRecord", "CostSummary", "TokenUsage", "AuditEvent", "AuditTrail",
    "EgressRequest", "EgressRule", "Secret", "SecretAccess", "KillSwitch",
    "ShardSaturation"
]

# Import mapping
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

# Generate migrations
created_files = []
prev_migration = None

for i, model_name in enumerate(MODELS, start=1):
    print(f"\n[{i}/{len(MODELS)}] Processing {model_name}...")

    operation = extract_create_model_with_indexes(content, model_name)
    if not operation:
        print(f"  ❌ Could not extract {model_name}")
        continue

    # Get imports
    imports = "from django.db import migrations, models"
    if model_name in IMPORT_MAP:
        imports += f"\n{IMPORT_MAP[model_name]}"

    # Check if needs django.db.models.deletion
    if "django.db.models.deletion" in operation:
        imports += "\nimport django.db.models.deletion"

    # Create migration
    if i == 1:
        dependency = 'dependencies = []'
        is_initial = True
    else:
        prev_name = MODELS[i-2].lower().replace('sod', 'sod_')
        prev_name = re.sub(r'([a-z])([A-Z])', r'\1_\2', MODELS[i-2]).lower()
        dependency = f'dependencies = [\n        ("ai_agent_management", "{i-1:04d}_create_{prev_name}"),\n    ]'
        is_initial = False

    initial_flag = '\n    initial = True\n' if is_initial else '\n'

    file_name = f"{i:04d}_create_{re.sub(r'([a-z])([A-Z])', r'\\1_\\2', model_name).lower()}.py"

    content_str = f'''# Generated by Django 4.2.27 on 2026-01-09 (split from 0001)

{imports}


class Migration(migrations.Migration):
{initial_flag}
    {dependency}

    operations = [
{operation}
    ]
'''

    output_path = MIGRATIONS_DIR / file_name
    with open(output_path, 'w') as f:
        f.write(content_str)

    lines = len(content_str.splitlines())
    print(f"  ✅ Created: {file_name} ({lines} lines)")
    created_files.append((file_name, lines))

    prev_migration = file_name.replace('.py', '')

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

print("\n✅ Migration splitting complete with embedded indexes!")
