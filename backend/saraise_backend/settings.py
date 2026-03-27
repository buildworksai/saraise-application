"""
Django settings for SARAISE backend.

Supports three operating modes:
- development: All modules enabled, no license checks
- self-hosted: Single-tenant, built-in auth, license validation
- saas: Multi-tenant, delegated auth to platform

Reference: https://docs.saraise.com (architecture and configuration)
"""

import os
from pathlib import Path
from typing import Literal

# Build paths inside the project
BASE_DIR = Path(__file__).resolve().parent.parent

# =============================================================================
# SARAISE MODE CONFIGURATION
# =============================================================================
# Mode determines authentication, tenant handling, and license behavior
# Valid values: 'development', 'self-hosted', 'saas'
_VALID_MODES = ("development", "self-hosted", "saas")
_raw_mode = os.getenv("SARAISE_MODE", "self-hosted")
if _raw_mode not in _VALID_MODES:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(f"SARAISE_MODE must be one of {_VALID_MODES}, got: {_raw_mode!r}")
SARAISE_MODE: Literal["development", "self-hosted", "saas"] = _raw_mode

# Self-hosted license mode (only applicable when SARAISE_MODE='self-hosted')
# - 'connected': Validates against license.saraise.com
# - 'isolated': Uses offline license keys
SARAISE_LICENSE_MODE: Literal["connected", "isolated"] = os.getenv("SARAISE_LICENSE_MODE", "connected")

# Platform URL for SaaS mode (auth delegation and policy engine)
# Required when SARAISE_MODE=saas (Phase 7.6)
SARAISE_PLATFORM_URL: str = os.getenv("SARAISE_PLATFORM_URL", "http://localhost:18000")
if SARAISE_MODE == "saas" and not (SARAISE_PLATFORM_URL or "").strip():
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured("SARAISE_PLATFORM_URL must be set when SARAISE_MODE=saas")

# Control Plane API URL (platform settings, feature flags) — distinct from SARAISE_PLATFORM_URL
# Docker: http://control-plane:8004 | Local: http://localhost:18004
SARAISE_CONTROL_PLANE_URL: str = os.getenv(
    "SARAISE_CONTROL_PLANE_URL",
    "http://localhost:18004",
)

# Policy Engine URL for SaaS mode authorization evaluation
# Docker: http://policy-engine:8003 | Local: http://localhost:18003
SARAISE_POLICY_ENGINE_URL: str = os.getenv(
    "SARAISE_POLICY_ENGINE_URL",
    "http://localhost:18003",
)

# License server URL for self-hosted connected mode
SARAISE_LICENSE_SERVER_URL: str = os.getenv("SARAISE_LICENSE_SERVER_URL", "https://license.saraise.com")

# License public key for offline validation (PEM format)
# Set via env in production. Falls back to embedded dev key when unset.
_license_public_key_env = os.getenv("SARAISE_LICENSE_PUBLIC_KEY", "")
if _license_public_key_env:
    SARAISE_LICENSE_PUBLIC_KEY = _license_public_key_env
else:
    _license_key_path = BASE_DIR / "src" / "core" / "licensing" / "saraise_public_key.pem"
    SARAISE_LICENSE_PUBLIC_KEY = _license_key_path.read_text() if _license_key_path.exists() else ""

# Application version for license server validation requests
SARAISE_VERSION = os.getenv("SARAISE_VERSION", "1.0.0")

# Module registry URL for downloading industry modules
SARAISE_REGISTRY_URL: str = os.getenv("SARAISE_REGISTRY_URL", "https://registry.saraise.com")

# =============================================================================
# MODE-AWARE CONFIGURATION
# =============================================================================
# Determine tenant behavior based on mode
SARAISE_MULTI_TENANT: bool = SARAISE_MODE == "saas"
SARAISE_SINGLE_TENANT: bool = SARAISE_MODE in ("development", "self-hosted")

# License validation settings
SARAISE_LICENSE_VALIDATION_ENABLED: bool = SARAISE_MODE == "self-hosted"
SARAISE_LICENSE_GRACE_PERIOD_DAYS: int = 30

# Trial period for new self-hosted installations
SARAISE_TRIAL_PERIOD_DAYS: int = 14

# =============================================================================
# SECURITY CONFIGURATION
# =============================================================================
# SARAISE-26001: All secrets MUST come from environment variables in production.
# Development mode permits insecure defaults for local development ONLY.

_secret_key_env = os.getenv("SECRET_KEY", "")
if not _secret_key_env and SARAISE_MODE != "development":
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        "SECRET_KEY environment variable is REQUIRED in non-development modes. "
        "Generate one with: python -c 'from django.core.management.utils import "
        "get_random_secret_key; print(get_random_secret_key())'"
    )
SECRET_KEY = _secret_key_env or "django-insecure-dev-only-not-for-production"  # pragma: allowlist secret

DEBUG = os.getenv("DEBUG", "false").lower() == "true" if SARAISE_MODE != "development" else True

_allowed_hosts_env = os.getenv("ALLOWED_HOSTS", "")
if SARAISE_MODE == "development":
    ALLOWED_HOSTS = ["localhost", "127.0.0.1", "0.0.0.0"]
elif _allowed_hosts_env:
    ALLOWED_HOSTS = [h.strip() for h in _allowed_hosts_env.split(",") if h.strip()]
else:
    from django.core.exceptions import ImproperlyConfigured

    raise ImproperlyConfigured(
        "ALLOWED_HOSTS environment variable is REQUIRED in non-development modes. "
        "Example: ALLOWED_HOSTS=app.saraise.com,api.saraise.com"
    )

# Application definition
INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "django.contrib.sessions",  # Session support
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "corsheaders",  # CORS support
    "rest_framework",
    "drf_spectacular",  # OpenAPI schema generation
    # SARAISE core
    "src.core",
    # SARAISE modules
    "src.modules.ai_agent_management",
    "src.modules.platform_management",  # Mode-aware: Full CRUD in self-hosted, read-only in SaaS
    "src.modules.tenant_management",
    "src.modules.security_access_control",
    "src.modules.workflow_automation",
    "src.modules.api_management",
    "src.modules.integration_platform",
    "src.modules.customization_framework",
    "src.modules.ai_provider_configuration",
    "src.modules.automation_orchestration",
    "src.modules.process_mining",
    "src.modules.document_intelligence",
    "src.modules.dms",
    "src.modules.data_migration",
    "src.modules.metadata_modeling",
    "src.modules.blockchain_traceability",
    "src.modules.billing_subscriptions",
    "src.modules.backup_disaster_recovery",
    "src.modules.backup_recovery",
    "src.modules.performance_monitoring",
    "src.modules.localization",
    "src.modules.regional",
    "src.modules.crm",
    # ===== Core Business Modules =====
    "src.modules.accounting_finance",
    "src.modules.inventory_management",
    # ===== Manufacturing Industry Modules =====
    "src.modules.human_resources",
    "src.modules.purchase_management",
    "src.modules.sales_management",
    "src.modules.project_management",
    "src.modules.master_data_management",
    "src.modules.multi_company",
    "src.modules.asset_management",
    "src.modules.bank_reconciliation",
    "src.modules.budget_management",
    "src.modules.business_intelligence",
    "src.modules.compliance_management",
    "src.modules.compliance_risk_management",
    "src.modules.email_marketing",
    "src.modules.fixed_assets",
    # ===== Foundation Modules =====
    "src.modules.communication_hub",
    "src.modules.notifications",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "src.core.middleware.correlation.CorrelationIdMiddleware",  # SARAISE-17007: Correlation ID tracing
    "corsheaders.middleware.CorsMiddleware",  # CORS middleware (should be early)
    "django.contrib.sessions.middleware.SessionMiddleware",  # Session middleware
    "src.core.auth.middleware.ModeAwareSessionMiddleware",  # Phase 7.6: Mode-aware session validation
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",  # CSRF protection (MANDATORY per auth spec)
    "django.contrib.auth.middleware.AuthenticationMiddleware",  # Authentication
    "src.core.middleware.tenant_context.TenantContextMiddleware",  # SARAISE-33001: PostgreSQL RLS context
    "src.core.auth.mode_auth_middleware.ModeAuthMiddleware",  # Phase 7.6: SaaS 401/redirect
    "django.contrib.messages.middleware.MessageMiddleware",
    "src.core.middleware.api_tracking.APITrackingMiddleware",  # API call tracking for metrics
    # Phase 7.5: License validation middleware (only active in self-hosted mode)
    "src.core.licensing.middleware.LicenseValidationMiddleware",
]

ROOT_URLCONF = "saraise_backend.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "saraise_backend.wsgi.application"

# Database
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.getenv("DB_NAME", "saraise"),
        "USER": os.getenv("DB_USER", "postgres"),
        "PASSWORD": os.getenv("DB_PASSWORD", "postgres"),
        "HOST": os.getenv("DB_HOST", "localhost"),
        "PORT": os.getenv("DB_PORT", "5432"),
    }
}

# For tests, use SQLite (pytest/manage.py test)
_use_sqlite = (
    os.getenv("DJANGO_USE_SQLITE_FOR_TESTS") == "1"
    or "test" in os.sys.argv
    or any("pytest" in arg for arg in os.sys.argv)
)
if _use_sqlite:
    DATABASES["default"] = {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": ":memory:",
    }

# SaaS mode: platform_management tables live in Control Plane DB — no migrations in application
# Skip when running tests (tests need platform_management tables for self-hosted/development coverage)
_in_test = "test" in os.sys.argv or "pytest" in os.sys.argv
if SARAISE_MODE == "saas" and not _in_test:
    MIGRATION_MODULES = {
        "platform_management": "src.modules.platform_management.migrations_saas",
    }

# Redis configuration
REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
# Domain events (Stream A3) — disable in unit tests via env if needed
SARAISE_EVENTS_ENABLED = os.getenv("SARAISE_EVENTS_ENABLED", "true").lower() in ("1", "true", "yes")

# Session configuration
SESSION_ENGINE = "django.contrib.sessions.backends.db"
SESSION_COOKIE_NAME = "saraise_sessionid"
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = not DEBUG  # HTTPS-only cookies in production (SARAISE-26001)
# CRITICAL: For cross-origin requests (different ports on localhost), we need None
# Modern browsers allow SameSite=None with Secure=False for localhost in development
# In production with HTTPS, this should be 'None' with Secure=True
# CRITICAL: Use 'Lax' now that frontend uses Vite proxy (same-origin requests)
# The Vite dev server proxies /api/* to backend, making requests same-origin
SESSION_COOKIE_SAMESITE = "Lax"  # Works with Vite proxy (same-origin)
SESSION_COOKIE_AGE = 86400  # 24 hours
# CRITICAL: Don't set SESSION_COOKIE_DOMAIN for localhost (allows cross-port cookies)
SESSION_COOKIE_DOMAIN = None

# CORS configuration
# Production: set CORS_ALLOWED_ORIGINS env var (comma-separated)
# Development: hardcoded localhost origins for local development
_cors_origins_env = os.getenv("CORS_ALLOWED_ORIGINS", "")
if _cors_origins_env:
    CORS_ALLOWED_ORIGINS = [o.strip() for o in _cors_origins_env.split(",") if o.strip()]
elif SARAISE_MODE == "development":
    CORS_ALLOWED_ORIGINS = [
        "http://localhost:25173",  # Application frontend (Runtime Plane)
        "http://localhost:17000",  # Platform frontend (Control Plane UI)
        "http://localhost:15173",  # Legacy/alternative port
        "http://localhost:5173",  # Standard Vite dev server port
        "http://127.0.0.1:25173",
        "http://127.0.0.1:17000",
        "http://127.0.0.1:15173",
        "http://127.0.0.1:5173",
    ]
else:
    # Non-development mode without explicit CORS origins: deny all cross-origin
    CORS_ALLOWED_ORIGINS = []

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    "accept",
    "accept-encoding",
    "authorization",
    "content-type",
    "dnt",
    "origin",
    "user-agent",
    "x-csrftoken",
    "x-requested-with",
]

# CSRF configuration
# Production: set CSRF_TRUSTED_ORIGINS env var (comma-separated)
_csrf_origins_env = os.getenv("CSRF_TRUSTED_ORIGINS", "")
if _csrf_origins_env:
    CSRF_TRUSTED_ORIGINS = [o.strip() for o in _csrf_origins_env.split(",") if o.strip()]
elif SARAISE_MODE == "development":
    CSRF_TRUSTED_ORIGINS = [
        "http://localhost:25173",  # Application frontend (Runtime Plane)
        "http://localhost:17000",  # Platform frontend (Control Plane UI)
        "http://localhost:15173",  # Legacy/alternative port
        "http://localhost:5173",  # Standard Vite dev server port
        "http://127.0.0.1:25173",
        "http://127.0.0.1:17000",
        "http://127.0.0.1:15173",
        "http://127.0.0.1:5173",
    ]
else:
    CSRF_TRUSTED_ORIGINS = []
CSRF_COOKIE_NAME = "saraise_csrftoken"
CSRF_COOKIE_HTTPONLY = False  # Must be False for JavaScript access
CSRF_COOKIE_SECURE = not DEBUG  # HTTPS-only cookies in production (SARAISE-26001)
CSRF_COOKIE_SAMESITE = "Lax"

# =============================================================================
# SECURITY HEADERS (SARAISE-26001, OWASP)
# =============================================================================
# HSTS: Force HTTPS for all subsequent requests (production only)
SECURE_HSTS_SECONDS = 31536000 if not DEBUG else 0  # 1 year in production
SECURE_HSTS_INCLUDE_SUBDOMAINS = not DEBUG
SECURE_HSTS_PRELOAD = not DEBUG

# X-Frame-Options: Prevent clickjacking
X_FRAME_OPTIONS = "DENY"

# X-Content-Type-Options: Prevent MIME type sniffing
SECURE_CONTENT_TYPE_NOSNIFF = True

# Redirect HTTP to HTTPS in production
SECURE_SSL_REDIRECT = not DEBUG

# Content Security Policy (enforced via middleware in production)
# CSP_DEFAULT_SRC is processed by django-csp if installed
SECURE_REFERRER_POLICY = "strict-origin-when-cross-origin"

# Internationalization
LANGUAGE_CODE = "en-us"
TIME_ZONE = "UTC"
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

# Default primary key field type
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# REST Framework
REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_PARSER_CLASSES": [
        "rest_framework.parsers.JSONParser",
    ],
    "DEFAULT_SCHEMA_CLASS": "drf_spectacular.openapi.AutoSchema",
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "src.core.authentication.RelaxedCsrfSessionAuthentication",  # GET requests don't need CSRF
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
        "src.core.auth.policy_permissions.PolicyRequiredPermission",
    ],
}

# DRF Spectacular (OpenAPI) Configuration
SPECTACULAR_SETTINGS = {
    "TITLE": "SARAISE API",
    "DESCRIPTION": "SARAISE Multi-Tenant SaaS Platform API",
    "VERSION": "1.0.0",
    "SERVE_INCLUDE_SCHEMA": False,
    "COMPONENT_SPLIT_REQUEST": True,
    "COMPONENT_NO_READ_ONLY_REQUIRED": True,
    "SCHEMA_PATH_PREFIX": "/api/v1",
    "TAGS": [
        {"name": "AI Agent Management", "description": "AI agent lifecycle and execution management"},
    ],
}

# Logging
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "correlation_id": {
            "()": "src.core.middleware.correlation.CorrelationIdFilter",
        },
    },
    "formatters": {
        "verbose": {
            "format": "{levelname} {asctime} [{name}] [cid:{correlation_id}] {message}",
            "style": "{",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "verbose",
            "filters": ["correlation_id"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": "DEBUG" if SARAISE_MODE == "development" else "INFO",
    },
    "loggers": {
        "saraise": {
            "handlers": ["console"],
            "level": "DEBUG" if SARAISE_MODE == "development" else "INFO",
            "propagate": False,
        },
        "saraise.licensing": {
            "handlers": ["console"],
            "level": "INFO",
            "propagate": False,
        },
    },
}

# Test settings
TEST_RUNNER = "django.test.runner.DiscoverRunner"

# =============================================================================
# MODE-SPECIFIC STARTUP BANNER
# =============================================================================
if SARAISE_MODE == "development":
    import logging

    _logger = logging.getLogger("saraise")
    _logger.info("=" * 60)
    _logger.info("SARAISE running in DEVELOPMENT mode")
    _logger.info("  - All modules enabled")
    _logger.info("  - License validation DISABLED")
    _logger.info("  - Debug logging ENABLED")
    _logger.info("=" * 60)
