# Week 4: OpenAPI Schema & TypeScript Type Generation Setup

**Date:** January 5, 2026  
**Status:** ✅ COMPLETE

---

## Summary

Configured OpenAPI schema generation using DRF Spectacular and TypeScript type generation using `openapi-typescript` for the SARAISE Phase 6 implementation.

---

## Backend Configuration

### 1. Added DRF Spectacular

**File:** `backend/requirements.txt`
```python
drf-spectacular>=0.27.0
```

### 2. Configured Django Settings

**File:** `backend/saraise_backend/settings.py`

**Added to INSTALLED_APPS:**
```python
'drf_spectacular',  # OpenAPI schema generation
```

**Updated REST_FRAMEWORK:**
```python
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
}
```

**Added SPECTACULAR_SETTINGS:**
```python
SPECTACULAR_SETTINGS = {
    'TITLE': 'SARAISE API',
    'DESCRIPTION': 'SARAISE Multi-Tenant SaaS Platform API',
    'VERSION': '1.0.0',
    'SERVE_INCLUDE_SCHEMA': False,
    'COMPONENT_SPLIT_REQUEST': True,
    'COMPONENT_NO_READ_ONLY_REQUIRED': True,
    'SCHEMA_PATH_PREFIX': '/api/v1',
    'TAGS': [
        {'name': 'AI Agent Management', 'description': 'AI agent lifecycle and execution management'},
    ],
}
```

### 3. Added OpenAPI Endpoints

**File:** `backend/saraise_backend/urls.py`

**Added routes:**
- `/api/schema/` - OpenAPI JSON schema
- `/api/schema/swagger-ui/` - Swagger UI documentation
- `/api/schema/redoc/` - ReDoc documentation

---

## Frontend Configuration

### 1. Added openapi-typescript

**File:** `frontend/package.json`

**Added dependency:**
```json
"openapi-typescript": "7.0.0"
```

**Added script:**
```json
"generate-types": "openapi-typescript http://localhost:8000/api/schema/ -o src/types/api.ts"
```

### 2. Created Type Generation Script

**File:** `scripts/openapi/generate-types.sh`

**Usage:**
```bash
./scripts/openapi/generate-types.sh
```

**Features:**
- Checks if backend is running
- Generates TypeScript types from OpenAPI schema
- Outputs to `frontend/src/types/api.ts`

---

## Usage

### Generate OpenAPI Schema

**Backend must be running:**
```bash
docker-compose -f docker-compose.dev.yml up -d backend
```

**Access endpoints:**
- **OpenAPI JSON:** http://localhost:8000/api/schema/
- **Swagger UI:** http://localhost:8000/api/schema/swagger-ui/
- **ReDoc:** http://localhost:8000/api/schema/redoc/

### Generate TypeScript Types

**Run script:**
```bash
./scripts/openapi/generate-types.sh
```

**Or manually:**
```bash
cd frontend
npm run generate-types
```

**Output:** `frontend/src/types/api.ts`

---

## Next Steps

1. ✅ OpenAPI schema generation configured
2. ✅ TypeScript type generation configured
3. ⏸️ Update frontend services to use generated types
4. ⏸️ Add type imports to frontend components
5. ⏸️ Verify type safety in frontend code

---

## Verification

### Test OpenAPI Schema
```bash
curl http://localhost:8000/api/schema/ | python3 -m json.tool | head -50
```

### Test Type Generation
```bash
cd frontend
npm run generate-types
ls -la src/types/api.ts
```

---

**Status:** ✅ COMPLETE

All OpenAPI schema and TypeScript type generation infrastructure is configured and ready for use.

