"""
Django settings for SARAISE backend.

Supports three operating modes:
- development: All modules enabled, no license checks
- self-hosted: Single-tenant, built-in auth, license validation
- saas: Multi-tenant, delegated auth to platform

Reference: saraise-documentation/AGENTS.md
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
SARAISE_MODE: Literal['development', 'self-hosted', 'saas'] = os.getenv(
    'SARAISE_MODE', 'self-hosted'  # Default to self-hosted for production readiness
)

# Self-hosted license mode (only applicable when SARAISE_MODE='self-hosted')
# - 'connected': Validates against license.saraise.com
# - 'isolated': Uses offline license keys
SARAISE_LICENSE_MODE: Literal['connected', 'isolated'] = os.getenv(
    'SARAISE_LICENSE_MODE', 'connected'
)

# Platform URL for SaaS mode (auth delegation and policy engine)
SARAISE_PLATFORM_URL: str = os.getenv(
    'SARAISE_PLATFORM_URL', 'http://localhost:18000'
)

# License server URL for self-hosted connected mode
SARAISE_LICENSE_SERVER_URL: str = os.getenv(
    'SARAISE_LICENSE_SERVER_URL', 'https://license.saraise.com'
)

# License public key for offline validation (PEM format)
# Set this in production for isolated mode license validation
SARAISE_LICENSE_PUBLIC_KEY: str = os.getenv(
    'SARAISE_LICENSE_PUBLIC_KEY', ''
)

# Module registry URL for downloading industry modules
SARAISE_REGISTRY_URL: str = os.getenv(
    'SARAISE_REGISTRY_URL', 'https://registry.saraise.com'
)

# =============================================================================
# MODE-AWARE CONFIGURATION
# =============================================================================
# Determine tenant behavior based on mode
SARAISE_MULTI_TENANT: bool = SARAISE_MODE == 'saas'
SARAISE_SINGLE_TENANT: bool = SARAISE_MODE in ('development', 'self-hosted')

# License validation settings
SARAISE_LICENSE_VALIDATION_ENABLED: bool = SARAISE_MODE == 'self-hosted'
SARAISE_LICENSE_GRACE_PERIOD_DAYS: int = 30

# Trial period for new self-hosted installations
SARAISE_TRIAL_PERIOD_DAYS: int = 14

# SECURITY WARNING: keep the secret key used in production secret!
SECRET_KEY = 'django-insecure-test-key-only-for-testing-do-not-use-in-production'

# SECURITY WARNING: don't run with debug turned on in production!
DEBUG = True

ALLOWED_HOSTS = ['*']

# Application definition
INSTALLED_APPS = [
    'django.contrib.admin',
    'django.contrib.contenttypes',
    'django.contrib.auth',
    'django.contrib.sessions',  # Session support
    'django.contrib.messages',
    'django.contrib.staticfiles',
    'corsheaders',  # CORS support
    'rest_framework',
    'drf_spectacular',  # OpenAPI schema generation
    # SARAISE core
    'src.core',
    # SARAISE modules
    'src.modules.ai_agent_management',
    'src.modules.platform_management',
    'src.modules.tenant_management',
    'src.modules.security_access_control',
]

MIDDLEWARE = [
    'django.middleware.security.SecurityMiddleware',
    'corsheaders.middleware.CorsMiddleware',  # CORS middleware (should be early)
    'django.contrib.sessions.middleware.SessionMiddleware',  # Session middleware
    'django.middleware.common.CommonMiddleware',
    'django.middleware.csrf.CsrfViewMiddleware',  # CSRF protection (MANDATORY per auth spec)
    'django.contrib.auth.middleware.AuthenticationMiddleware',  # Authentication
    'django.contrib.messages.middleware.MessageMiddleware',
    'src.core.middleware.api_tracking.APITrackingMiddleware',  # API call tracking for metrics
    # Phase 7.5: License validation middleware (only active in self-hosted mode)
    'src.core.licensing.middleware.LicenseValidationMiddleware',
]

ROOT_URLCONF = 'saraise_backend.urls'

TEMPLATES = [
    {
        'BACKEND': 'django.template.backends.django.DjangoTemplates',
        'DIRS': [],
        'APP_DIRS': True,
        'OPTIONS': {
            'context_processors': [
                'django.template.context_processors.debug',
                'django.template.context_processors.request',
                'django.contrib.auth.context_processors.auth',
                'django.contrib.messages.context_processors.messages',
            ],
        },
    },
]

WSGI_APPLICATION = 'saraise_backend.wsgi.application'

# Database
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.postgresql',
        'NAME': os.getenv('DB_NAME', 'saraise'),
        'USER': os.getenv('DB_USER', 'postgres'),
        'PASSWORD': os.getenv('DB_PASSWORD', 'postgres'),
        'HOST': os.getenv('DB_HOST', 'localhost'),
        'PORT': os.getenv('DB_PORT', '5432'),
    }
}

# For tests, use SQLite if DATABASE_URL not set
if 'test' in os.sys.argv:
    DATABASES['default'] = {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',
    }

# Redis configuration
REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')

# Session configuration
SESSION_ENGINE = 'django.contrib.sessions.backends.db'
SESSION_COOKIE_NAME = 'saraise_sessionid'
SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SECURE = False  # Set to True in production with HTTPS
# CRITICAL: For cross-origin requests (different ports on localhost), we need None
# Modern browsers allow SameSite=None with Secure=False for localhost in development
# In production with HTTPS, this should be 'None' with Secure=True
# CRITICAL: Use 'Lax' now that frontend uses Vite proxy (same-origin requests)
# The Vite dev server proxies /api/* to backend, making requests same-origin
SESSION_COOKIE_SAMESITE = 'Lax'  # Works with Vite proxy (same-origin)
SESSION_COOKIE_AGE = 86400  # 24 hours
# CRITICAL: Don't set SESSION_COOKIE_DOMAIN for localhost (allows cross-port cookies)
SESSION_COOKIE_DOMAIN = None

# CORS configuration
# Application frontend: 25173 (2xxxx port convention)
# Platform frontend: 17000 (1xxxx port convention)
# Also allow standard Vite dev server port for local development
CORS_ALLOWED_ORIGINS = [
    'http://localhost:25173',  # Application frontend (Runtime Plane)
    'http://localhost:17000',  # Platform frontend (Control Plane UI)
    'http://localhost:15173',  # Legacy/alternative port
    'http://localhost:5173',   # Standard Vite dev server port
    'http://127.0.0.1:25173',
    'http://127.0.0.1:17000',
    'http://127.0.0.1:15173',
    'http://127.0.0.1:5173',
]

CORS_ALLOW_CREDENTIALS = True
CORS_ALLOW_HEADERS = [
    'accept',
    'accept-encoding',
    'authorization',
    'content-type',
    'dnt',
    'origin',
    'user-agent',
    'x-csrftoken',
    'x-requested-with',
]

# CSRF configuration
CSRF_TRUSTED_ORIGINS = [
    'http://localhost:25173',  # Application frontend (Runtime Plane)
    'http://localhost:17000',  # Platform frontend (Control Plane UI)
    'http://localhost:15173',  # Legacy/alternative port
    'http://localhost:5173',   # Standard Vite dev server port
    'http://127.0.0.1:25173',
    'http://127.0.0.1:17000',
    'http://127.0.0.1:15173',
    'http://127.0.0.1:5173',
]
CSRF_COOKIE_NAME = 'saraise_csrftoken'
CSRF_COOKIE_HTTPONLY = False  # Must be False for JavaScript access
CSRF_COOKIE_SECURE = False  # Set to True in production with HTTPS
CSRF_COOKIE_SAMESITE = 'Lax'

# Internationalization
LANGUAGE_CODE = 'en-us'
TIME_ZONE = 'UTC'
USE_I18N = True
USE_TZ = True

# Static files (CSS, JavaScript, Images)
STATIC_URL = 'static/'
STATIC_ROOT = BASE_DIR / 'staticfiles'

# Default primary key field type
DEFAULT_AUTO_FIELD = 'django.db.models.BigAutoField'

# REST Framework
REST_FRAMEWORK = {
    'DEFAULT_RENDERER_CLASSES': [
        'rest_framework.renderers.JSONRenderer',
    ],
    'DEFAULT_PARSER_CLASSES': [
        'rest_framework.parsers.JSONParser',
    ],
    'DEFAULT_SCHEMA_CLASS': 'drf_spectacular.openapi.AutoSchema',
    'DEFAULT_AUTHENTICATION_CLASSES': [
        'src.core.authentication.RelaxedCsrfSessionAuthentication',  # GET requests don't need CSRF
    ],
    'DEFAULT_PERMISSION_CLASSES': [
        'rest_framework.permissions.IsAuthenticated',
    ],
}

# DRF Spectacular (OpenAPI) Configuration
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

# Logging
LOGGING = {
    'version': 1,
    'disable_existing_loggers': False,
    'formatters': {
        'verbose': {
            'format': '{levelname} {asctime} [{name}] {message}',
            'style': '{',
        },
    },
    'handlers': {
        'console': {
            'class': 'logging.StreamHandler',
            'formatter': 'verbose',
        },
    },
    'root': {
        'handlers': ['console'],
        'level': 'DEBUG' if SARAISE_MODE == 'development' else 'INFO',
    },
    'loggers': {
        'saraise': {
            'handlers': ['console'],
            'level': 'DEBUG' if SARAISE_MODE == 'development' else 'INFO',
            'propagate': False,
        },
        'saraise.licensing': {
            'handlers': ['console'],
            'level': 'INFO',
            'propagate': False,
        },
    },
}

# Test settings
TEST_RUNNER = 'django.test.runner.DiscoverRunner'

# =============================================================================
# MODE-SPECIFIC STARTUP BANNER
# =============================================================================
if SARAISE_MODE == 'development':
    import logging
    _logger = logging.getLogger('saraise')
    _logger.info("=" * 60)
    _logger.info("SARAISE running in DEVELOPMENT mode")
    _logger.info("  - All modules enabled")
    _logger.info("  - License validation DISABLED")
    _logger.info("  - Debug logging ENABLED")
    _logger.info("=" * 60)
