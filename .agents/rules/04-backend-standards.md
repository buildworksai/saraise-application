---
description: Python coding standards, Django REST Framework development standards, and MyPy type checking for SARAISE backend
globs: backend/src/**/*.py
alwaysApply: true
---

# 🐍 SARAISE Backend Standards (Python + Type Checking)

**Rule IDs**: SARAISE-02001 to SARAISE-02015
**Consolidates**: `04-backend-standards.md`, `04-backend-standards.md`

---

## Python Coding Standards

### SARAISE-02001 Python Version & Environment
- Use Python 3.10+ (as specified in pyproject.toml)
- Use virtual environments for development
- Follow PEP 8 style guidelines
- Use Black 25.1.0 for code formatting
- Use Flake8 7.2.0 for linting

### SARAISE-02002 Django REST Framework (DRF) Standards

See [DRF Standards Example](docs/architecture/examples/backend/services/drf-standards-example.py).

### SARAISE-02003 Django Serializers Standards

See [Django Serializers Standards Example](docs/architecture/examples/backend/models/django-serializers-standards-example.py).

### SARAISE-02004 Django ORM Model Standards

See [Django ORM Model Standards Example](docs/architecture/examples/backend/models/django-orm-standards-example.py). All tenant-scoped models MUST include `tenant_id` field.

### SARAISE-02005 Database Operations

See [Database Operations Example](docs/architecture/examples/backend/services/database-operations-example.py).

### SARAISE-02006 Session-Based Authentication & Security

See [Session-Based Authentication Example](docs/architecture/examples/backend/services/session-auth-example.py).

### SARAISE-02007 Error Handling

See [Error Handling Example](docs/architecture/examples/backend/services/error-handling-example.py).

### SARAISE-02008 AI Agent Development

See [AI Agent Development Example](docs/architecture/examples/backend/services/ai-agent-example.py).

### SARAISE-02009 Testing Standards

See [Python Testing Example](docs/architecture/examples/backend/tests/python-testing-example.py).

### SARAISE-02010 Dependency Management
- All dependencies must be specified in `pyproject.toml`
- Use exact versions for production dependencies
- Use version ranges for development dependencies
- Document any new dependencies via Architecture Change Proposal (ACP) process

### SARAISE-02011 Environment-Aware Input Validation & Security
- **Development Environment:** Relaxed validation for rapid development
- **Staging Environment:** Production-like validation for testing
- **Production Environment:** Maximum validation and security controls

See [Security Validator](docs/architecture/examples/backend/core/security-validator.py).

### SARAISE-02012 Environment-Aware Request Security
- **Development Environment:** Relaxed request limits for development
- **Staging Environment:** Standard request limits for testing
- **Production Environment:** Strict request limits for security

See [Request Security Middleware](docs/architecture/examples/backend/middleware/request-security-middleware.py).

---

## Python Type Checking with MyPy

**Related Documentation:**
- Quality Gates: `02-quality-enforcement.md`
- Automated Enforcement: `06-automated-enforcement.md`

### SARAISE-02013 Baseline + Ratcheting Enforcement

**Current State (as of 2024-12-14):**
- **Baseline**: 4,540 MyPy errors
- **Ratcheting**: No new errors allowed above baseline
- **Target**: Reduce to 3,200 errors by Q3 2025
- **Strategy**: Gradual improvement via baseline ratcheting

**Error Category Breakdown:**
```
1,800 [attr-defined]   - Django model fields, circular imports
1,200 [arg-type]       - Type inference with Django ORM querysets
  900 [call-arg]       - DRF serializer field arguments
  400 [assignment]     - Type mismatches in field assignments
  240 [index]          - Collection indexing issues
```

**Note**: ~70% of errors are framework limitations (Django ORM, DRF), not code quality issues.

**Pre-Commit Hook Configuration:**

```yaml
  - repo: local
    hooks:
      - id: mypy-baseline-check
        name: MyPy Baseline Check (no new errors)
        entry: bash -lc "./scripts/mypy-baseline.sh check"
        language: system
        files: ^backend/src/.*\.py$
        pass_filenames: false
```

**Baseline Management Script:**

Location: `backend/scripts/mypy-baseline.sh`

Commands:
```bash
# Check current errors vs baseline (used in pre-commit)
./scripts/mypy-baseline.sh check

# View progress statistics
./scripts/mypy-baseline.sh stats

# Lock in improvements (reduce baseline)
./scripts/mypy-baseline.sh ratchet 5300

# Full report with categorized errors
./scripts/mypy-baseline.sh report
```

### SARAISE-02014 Suppression Policy

Strategic `# type: ignore` suppressions are allowed **ONLY** for documented framework limitations:

**Approved Suppressions:**

1. **Django ORM QuerySet Type Inference:**
```python
# Django ORM QuerySet[T] vs specific type hints - MyPy limitation
users = User.objects.filter(is_active=True)  # type: ignore[attr-defined]
```

2. **Django Model Field Descriptors:**
```python
# MyPy can't fully infer Django model field types
user = User.objects.get(id=1)  # type: ignore[attr-defined]
user.email  # MyPy doesn't infer EmailField type
```

3. **Pydantic Circular Imports:**
```python
if TYPE_CHECKING:
    from module import Model

# Forward reference required for Pydantic
field: Optional["Model"] = None  # type: ignore[name-defined]
```

4. **Pydantic Response Schema Inheritance:**
```python
class ResponseSchema(BaseSchema):
    # Override child list type - Pydantic inheritance pattern
    items: List[ItemResponse] = None  # type: ignore[assignment]
```

**Suppression Requirements:**

All `# type: ignore` comments MUST:
1. Include the specific error code: `# type: ignore[attr-defined]`
2. Include justification: `# type: ignore[arg-type]  # Django ORM field limitation`
3. Be reviewed in code review
4. Be documented if it's a new pattern

**Forbidden Suppressions:**

❌ Never suppress these without extreme justification:
- `# type: ignore` (bare, no error code)
- `# type: ignore[misc]` (too broad)
- Suppressions in new code for issues that can be fixed
- Suppressions to avoid writing proper type hints

### SARAISE-02015 New Code Requirements

All **NEW** Python files created after 2024-12-14 MUST:

1. **Function signatures have type hints:**
```python
# ✅ Good
def process_user(user_id: str, tenant_id: str) -> Optional[User]:
    pass

# ❌ Bad
def process_user(user_id, tenant_id):
    pass
```

2. **Collections have generic types:**
```python
# ✅ Good
users: list[User] = []
config: dict[str, Any] = {}

# ❌ Bad
users = []  # MyPy infers list[Any]
config = {}  # MyPy infers dict[Any, Any]
```

3. **No bare `Any` without justification:**
```python
# ✅ Good - justified
data: Any  # External API returns unstructured data

# ❌ Bad
def process(data: Any) -> Any:  # Lazy typing
    pass
```

4. **Pass `mypy --strict` on new files:**
```bash
# New file must pass strict mode
mypy --strict backend/src/modules/new_module/service.py
```

### SQL Injection Prevention (Environment-Aware)
- **ALL ENVIRONMENTS:** Use parameterized queries exclusively
- **ALL ENVIRONMENTS:** No dynamic SQL construction
- **Production:** Additional input sanitization and validation

See [Secure Database Operations](docs/architecture/examples/backend/core/secure-database-operations.py).

---

## Legacy Code Improvement Strategy

**Module-by-Module Cleanup:**

1. **Pick 1 module per sprint** for type safety improvement
2. **Goal**: Reduce module's MyPy errors to zero OR document why suppressed
3. **Mark as "type-safe"** in module's `manifest.yaml`
4. **Prioritize**: New modules > Small modules > High-value modules

**Example Workflow:**
```bash
# 1. Check module's current errors
mypy backend/src/modules/billing/ --show-error-codes

# 2. Fix errors by category (easiest first)
#    - var-annotated (add type hints)
#    - name-defined (add imports)
#    - assignment (fix type mismatches)
#    - Add strategic suppressions for framework issues

# 3. Verify improvement
mypy backend/src/modules/billing/ --show-error-codes

# 4. Update baseline if reduced
./scripts/mypy-baseline.sh ratchet 5200
```

## CI/CD Integration

**GitHub Actions Workflow:**

```yaml
- name: MyPy Type Check (Baseline + Ratcheting)
  run: |
    cd backend
    ./scripts/mypy-baseline.sh check
```

**CI Failure Conditions:**
1. MyPy errors > baseline (new errors introduced)
2. New files fail `mypy --strict`
3. `# type: ignore` without error code or justification

## Progress Tracking

**Weekly Report:**
```bash
./scripts/mypy-baseline.sh stats

# Output:
# MyPy Error Tracking:
#   Baseline: 5,378
#   Current:  5,350
#   Delta:    -28
#   Progress: 0.5%
#   Target:   3,200 (2,150 remaining)
```

**Quarterly Goals:**
- Q1 2025: 5,378 → 4,500 (reduce by 878)
- Q2 2025: 4,500 → 3,800 (reduce by 700)
- Q3 2025: 3,800 → 3,200 (reduce by 600, reach target)

## Type Checking Configuration

**mypy.ini** (already exists):
```ini
[mypy]
python_version = 3.10
warn_return_any = True
warn_unused_configs = True
warn_redundant_casts = True
warn_unused_ignores = True
strict_optional = True
check_untyped_defs = True

# Exclude test files from type checking
[mypy-tests.*]
ignore_errors = True

# Known problematic third-party libraries
[mypy-django.*]
ignore_missing_imports = True

[mypy-rest_framework.*]
ignore_missing_imports = True
```

## Best Practices

1. **Fix errors by category** - easier to batch similar issues
2. **Start with low-hanging fruit** - var-annotated, name-defined
3. **Document complex suppressions** - help future developers
4. **Test after fixing** - ensure types match runtime behavior
5. **Commit frequently** - small batches reduce merge conflicts

## Enforcement Summary

✅ **Pre-commit**: Blocks commits with new MyPy errors
✅ **CI/CD**: Fails builds with errors above baseline
✅ **Code Review**: Reviewers check type hint quality
✅ **Ratcheting**: Baseline reduces as errors fixed
✅ **Progress**: Weekly tracking toward 3,200 target

**No more accumulation of type errors - discipline enforced.**

---

**Audit**: Version 7.0.0; Consolidated 2025-12-23
