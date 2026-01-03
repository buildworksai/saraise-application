# ✅ APPROVED: Environment Variables for Tech Stack
# Reference: docs/architecture/application-architecture.md § 5
# Reference: .agents/rules/03-tech-stack.md (SARAISE-12000, SARAISE-12001)

# CRITICAL: Version numbers must match docs/architecture/application-architecture.md § 5
# and .agents/rules/03-tech-stack.md (SARAISE-12001)
#
# NON-NEGOTIABLE VERSION PINNING RULES (SARAISE-12000):
# - BANNED: "latest", "stable", "*", ">=", "+", caret (^) ranges, tilde (~) ranges
# - REQUIRED: Exact versions for all dependencies
# - All references to major-only versions (e.g. "18", "5", "x") are forbidden
# - Exact patch versions are mandatory

# Backend Framework
DJANGO_VERSION=5.0.6
DJANGORESTFRAMEWORK_VERSION=3.15.1
GUNICORN_VERSION=23.0.0
PYTHON_VERSION=3.10.14

# Database
POSTGRES_VERSION=17.2
POSTGRES_IMAGE=postgres:17.2-alpine
PSYCOPG_VERSION=3.2.1

# Authentication & Security (Session-based only, NO JWT for interactive users)
BCRYPT_VERSION=4.3.0
DJANGO_REDIS_VERSION=5.4.0
REDIS_VERSION=7.2
REDIS_IMAGE=redis:7.2-alpine

# MFA (TOTP only - RFC 6238)
DJANGO_OTP_VERSION=1.3.0
DJANGO_OTP_TOTP_VERSION=1.1.2

# Validation
DJANGO_ENVIRON_VERSION=0.11.2

# Frontend
VITE_VERSION=5.1.4
VITEST_VERSION=1.3.1
REACT_VERSION=18.2.0
TYPESCRIPT_VERSION=5.3.3
TAILWIND_VERSION=3.4.17
NODE_VERSION=18.19.1

# Frontend State Management (SARAISE-12001: Redux BANNED, Zustand only)
ZUSTAND_VERSION=4.5.0
TANSTACK_QUERY_VERSION=5.17.0

# UI Components
RADIX_UI_VERSION=1.0.0
LUCIDE_REACT_VERSION=0.454.0

# Forms & Validation
REACT_HOOK_FORM_VERSION=7.54.1
ZOD_VERSION=3.24.1

# Routing (React Router, NOT Next.js)
REACT_ROUTER_DOM_VERSION=6.22.0

# Testing & Quality
PYTEST_VERSION=8.3.5
PYTEST_COV_VERSION=6.1.1
PYTEST_DJANGO_VERSION=4.8.0
BLACK_VERSION=25.1.0
FLAKE8_VERSION=7.2.0
ESLINT_VERSION=9.34.0
DJANGO_STUBS_VERSION=5.0.2

# Task Queue & Monitoring
CELERY_VERSION=5.3.4
FLOWER_VERSION=2.0.1

# Observability
OPENTELEMETRY_SDK_VERSION=1.33.0
OTLP_EXPORTER_VERSION=1.33.0

# HTTP Client
HTTPX_VERSION=0.28.1
HTTPX_SSE_VERSION=0.4.0

# API Documentation
DRF_SPECTACULAR_VERSION=0.27.2

# CORS
DJANGO_CORS_HEADERS_VERSION=4.3.1

# Infrastructure (Exact versions - NO "latest" tags allowed)
VAULT_IMAGE=hashicorp/vault:1.15.2
MINIO_IMAGE=minio/minio:RELEASE.2024-01-18T22-51-28Z
MAILHOG_IMAGE=mailhog/mailhog:v1.0.1
PROMETHEUS_IMAGE=prom/prometheus:v2.48.0
KONG_IMAGE=kong/kong:3.4-alpine
LOKI_IMAGE=grafana/loki:2.9.0
GRAFANA_IMAGE=grafana/grafana:10.2.0

# Search (OpenSearch - Apache 2.0 licensed, NOT Elasticsearch)
OPENSEARCH_VERSION=2.11.1

# MCP
MCP_VERSION=1.9.0

# ============================================================================
# AI/ML Dependencies (PHASE 4+ ONLY - SARAISE-12005)
# These are OPTIONAL and phase-gated
# DO NOT enable until Phase 4 begins
# ============================================================================
# OPENAI_SDK_VERSION=1.12.0
# LANGCHAIN_VERSION=0.1.0
# LANGGRAPH_VERSION=0.0.47
# CREWAI_VERSION=0.120.1
# ============================================================================
