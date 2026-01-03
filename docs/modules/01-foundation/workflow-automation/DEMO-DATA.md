<!-- SPDX-License-Identifier: Apache-2.0 -->
# Workflow Automation Frontend - Demo Data

**Version:** 1.0.0
**Last Updated:** 2025-12-02
**Status:** Demo Data Reference
**Development Agent:** Agent 64

---

This document describes the comprehensive demo data included with the Workflow Automation Frontend module for testing and training purposes.

## Overview

The demo data seed script (`backend/scripts/seed_workflow-automation_demo.py`) creates a fully functional Workflow Automation Frontend setup for the demo tenant `demo@saraise.com` with:

- [Number] [entities] (e.g., 10 customers, 5 products)
- [Number] [entities]
- [Number] [entities]

---

## Sample Data Sets

### Basic Demo (10 records)

**Purpose:** Minimal data for quick demos and initial testing.

**Includes:**
- [Entity type 1]: [Number] records
- [Entity type 2]: [Number] records
- [Entity type 3]: [Number] records

**Usage:**
```bash
python backend/scripts/seed_workflow-automation_demo.py --size basic
```

### Full Demo (100+ records)

**Purpose:** Comprehensive data for thorough testing, training, and demonstrations.

**Includes:**
- [Entity type 1]: [Number] records
- [Entity type 2]: [Number] records
- [Entity type 3]: [Number] records
- [Entity type 4]: [Number] records

**Usage:**
```bash
python backend/scripts/seed_workflow-automation_demo.py --size full
```

---

## Demo Data Structure

### Entity 1: [Name]

**Count:** [Number]
**Purpose:** [What this entity represents]

**Sample Record:**

```json
{
  "id": "[id]",
  "name": "[Name]",
  "field1": "[value]",
  "field2": "[value]"
}
```

**Key Fields:**
| Field | Value | Description |
|-------|-------|-------------|
| [field] | [value] | [description] |

[Repeat for all entity types]

---

## Relationships & Dependencies

The demo data includes realistic relationships between entities:

- **[Entity A]** → **[Entity B]**: [How they relate]
- **[Entity B]** → **[Entity C]**: [How they relate]

### Data Dependency Order

The following order ensures all dependencies are created correctly:

1. [Base entity] (no dependencies)
2. [Dependent entity 1] (depends on step 1)
3. [Dependent entity 2] (depends on steps 1-2)

---

## Data Generation Scripts

### Main Seed Script

**File:** `backend/scripts/seed_workflow-automation_demo.py`

**Usage:**
```bash
# Basic demo
python backend/scripts/seed_workflow-automation_demo.py --size basic --tenant demo@saraise.com

# Full demo
python backend/scripts/seed_workflow-automation_demo.py --size full --tenant demo@saraise.com

# Custom count
python backend/scripts/seed_workflow-automation_demo.py --count 50 --tenant demo@saraise.com
```

**Options:**
- `--size`: `basic` or `full` (default: `basic`)
- `--count`: Custom number of records per entity
- `--tenant`: Tenant ID or email (default: `demo@saraise.com`)
- `--reset`: Clear existing demo data before seeding

### Helper Functions

#### `generate_workflow-automation_data(count)`
**Purpose:** Generate [entity type] records
**Parameters:**
- `count` (int): Number of records to generate

```python
def generate_workflow-automation_data(count: int):
    """Generate demo data"""
    # Implementation
    pass
```

---

## Sample Data Examples

### Example 1: [Entity Name]

**Type:** [Resource Type]
**Description:** [What this example demonstrates]

**Data:**
```json
{
  "name": "Example Record",
  "field1": "value1",
  "field2": "value2"
}
```

**Use Case:** [When to use this example]

[Repeat for key examples]

---

## Reset Instructions

### Clearing Demo Data

**Method 1: Using Script**
```bash
python backend/scripts/seed_workflow-automation_demo.py --reset --tenant demo@saraise.com
```

**Method 2: Manual Deletion**
1. Delete dependent entities first
2. Delete base entities
3. Verify all data cleared

### Verification

After reset, verify:
- [ ] All demo records deleted
- [ ] No orphaned relationships
- [ ] Database constraints satisfied

---

## Testing Scenarios

### Scenario 1: Basic Functionality

**Data Required:** Basic demo set
**Steps:**
1. [Step 1]
2. [Step 2]
3. [Step 3]

### Scenario 2: Advanced Features

**Data Required:** Full demo set
**Steps:**
1. [Step 1]
2. [Step 2]
3. [Step 3]

---

## Data Quality Standards

### Realistic Data
- All data values are realistic and representative
- Relationships follow business logic
- Dates are within valid ranges

### Completeness
- All required fields populated
- No null values in critical fields
- Relationships properly linked

### Consistency
- Naming conventions followed
- Data formats consistent
- Business rules validated

---

## Customization

### Extending Demo Data

To add custom demo data:

1. **Create Custom Seed Function:**
```python
def generate_custom_data():
    """Generate custom demo data"""
    # Your custom logic
    pass
```

2. **Add to Seed Script:**
```python
if __name__ == "__main__":
    # ... existing code ...
    generate_custom_data()
```

3. **Run:**
```bash
python backend/scripts/seed_workflow-automation_demo.py --custom
```

---

**Last Updated:** 2025-12-02
**License:** Apache-2.0
