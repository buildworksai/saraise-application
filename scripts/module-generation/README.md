# Module Generation Scripts

Automates SARAISE module creation from AI Agent Management template.

## Overview

The module generation script creates a complete module structure including:
- Backend (models, API, serializers, URLs, health checks)
- Frontend (pages, components, services)
- Documentation (README, API docs, user guide)

Reduces implementation time by ~70% by automating boilerplate code.

## Usage

### Generate a Foundation Module

```bash
python scripts/module-generation/generate_module.py \
    --name platform-management \
    --category foundation \
    --description "Platform administration and configuration"
```

### Generate a Core Module

```bash
python scripts/module-generation/generate_module.py \
    --name inventory-management \
    --category core \
    --description "Real-time stock tracking and warehouse management"
```

### Generate an Industry Module

```bash
python scripts/module-generation/generate_module.py \
    --name manufacturing-mrp \
    --category industry \
    --description "Manufacturing resource planning and production scheduling"
```

## Parameters

- `--name`: Module name in kebab-case (e.g., `platform-management`)
- `--category`: Module category (`foundation`, `core`, `industry`)
- `--description`: Brief module description

## What Gets Generated

### Backend (`backend/src/modules/{module_name}/`)

- `__init__.py` - Python package initialization
- `models.py` - Django models (copied from template)
- `api.py` - DRF ViewSets
- `serializers.py` - DRF serializers
- `urls.py` - URL routing
- `services.py` - Business logic (copied from template)
- `permissions.py` - Permission classes (copied from template)
- `policies.py` - Policy definitions (copied from template)
- `health.py` - Health check endpoint
- `manifest.yaml` - Module contract
- `migrations/` - Django migrations directory
- `tests/` - Test directory

### Frontend (`frontend/src/modules/{module_name}/`)

- `pages/ListPage.tsx` - List view
- `pages/DetailPage.tsx` - Detail view
- `components/` - Reusable components directory
- `services/{module_name}-service.ts` - API client
- `types/` - TypeScript types directory
- `tests/` - Frontend tests directory

### Documentation (`docs/modules/{category}/{module-name}/`)

- `README.md` - Module overview
- `API.md` - API documentation placeholder
- `USER-GUIDE.md` - User guide placeholder

## Post-Generation Steps

After running the script, follow these steps:

1. **Update models** - Define domain models in `models.py`
2. **Create migrations** - Run `python manage.py makemigrations {module_name}`
3. **Update serializers** - Add validation in `serializers.py`
4. **Update ViewSets** - Add custom actions in `api.py`
5. **Register routes** - Add to `backend/saraise_backend/urls.py`
6. **Implement frontend** - Complete pages and components
7. **Write tests** - Backend + frontend tests (≥90% coverage)
8. **Update documentation** - API docs and user guide

See script output for detailed next steps.

## Template Module

The script uses `backend/src/modules/ai_agent_management/` as the template.

All new modules follow this structure for consistency.

## License

Apache-2.0

