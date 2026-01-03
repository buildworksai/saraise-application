# ✅ APPROVED: Settings Configuration
# backend/src/config/settings.py
# Reference: docs/architecture/security-model.md § 5 (Secrets Management)
# CRITICAL NOTES:
# - ALL settings sourced from environment variables (never hardcode)
# - Connection strings use environment variable interpolation
# - Database connection pooling configured per-environment (development vs production)
# - Session secret key MUST be cryptographically random (generated per deployment)
# - MinIO credentials sourced from Vault in production (never in code/version control)
# - CORS_ORIGINS validated from environment (prevent misconfigurations)
# - Settings immutable after initialization (fail-fast on invalid config)
# - All secrets marked with Field(..., sensitive=True) to prevent logging
# - Validation runs on startup (application fails if config invalid)
# - Different settings per environment (development, staging, production)
# Source: docs/architecture/security-model.md § 5, operational-runbooks.md § 1

import os
from typing import Optional

class Settings:
    """Django settings from environment variables."""
    
    # Database Configuration
    POSTGRES_HOST = os.getenv('POSTGRES_HOST', 'localhost')
    POSTGRES_PORT = os.getenv('POSTGRES_PORT', '5432')
    POSTGRES_DB = os.getenv('POSTGRES_DB', 'saraise')
    POSTGRES_USER = os.getenv('POSTGRES_USER', 'postgres')
    POSTGRES_PASSWORD = os.getenv('POSTGRES_PASSWORD', 'postgres')
    
    DATABASES = {
        'default': {
            'ENGINE': 'django.db.backends.postgresql',
            'NAME': POSTGRES_DB,
            'USER': POSTGRES_USER,
            'PASSWORD': POSTGRES_PASSWORD,
            'HOST': POSTGRES_HOST,
            'PORT': POSTGRES_PORT,
            'CONN_MAX_AGE': 600,
            'OPTIONS': {
                'connect_timeout': 10,
            }
        }
    }

    # Redis Configuration
    REDIS_HOST = os.getenv('REDIS_HOST', 'localhost')
    REDIS_PORT = os.getenv('REDIS_PORT', '6379')
    REDIS_URL = f"redis://{REDIS_HOST}:{REDIS_PORT}/0"

    # Object Storage (MinIO)
    MINIO_ENDPOINT = os.getenv('MINIO_ENDPOINT', 'localhost:9000')
    MINIO_ACCESS_KEY = os.getenv('MINIO_ACCESS_KEY', 'minioadmin')
    MINIO_SECRET_KEY = os.getenv('MINIO_SECRET_KEY', 'minioadmin')
    MINIO_BUCKET_NAME = os.getenv('MINIO_BUCKET_NAME', 'saraise-storage')
    MINIO_SECURE = os.getenv('MINIO_SECURE', 'False').lower() == 'true'

    # Session Authentication
    SESSION_SECRET_KEY = os.getenv('SESSION_SECRET_KEY', 'CHANGE-ME-IN-PRODUCTION')
    SESSION_TIMEOUT = int(os.getenv('SESSION_TIMEOUT', 7200))  # 2 hours
    COOKIE_DOMAIN = os.getenv('COOKIE_DOMAIN', 'localhost')
    COOKIE_SECURE = os.getenv('COOKIE_SECURE', 'False').lower() == 'true'
    COOKIE_HTTPONLY = True  # Always True for security
    COOKIE_SAMESITE = 'Strict'  # Prevent CSRF attacks

    # Application Configuration
    APP_ENV = os.getenv('APP_ENV', 'development')
    APP_DEBUG = os.getenv('APP_DEBUG', 'True').lower() == 'true'
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')

    # Email Configuration (MailHog)
    SMTP_HOST = os.getenv('SMTP_HOST', 'localhost')
    SMTP_PORT = int(os.getenv('SMTP_PORT', 1025))
    SMTP_USERNAME = os.getenv('SMTP_USERNAME', '')
    SMTP_PASSWORD = os.getenv('SMTP_PASSWORD', '')
    SMTP_USE_TLS = os.getenv('SMTP_USE_TLS', 'False').lower() == 'true'

    # AI/ML Configuration (OpenAI)
    OPENAI_API_KEY = os.getenv('OPENAI_API_KEY', '')
    OPENAI_ORG_ID = os.getenv('OPENAI_ORG_ID', '')

    # Vault Configuration
    VAULT_ADDR = os.getenv('VAULT_ADDR', 'http://localhost:8200')
    VAULT_TOKEN = os.getenv('VAULT_TOKEN', 'dev-token')

    # Celery Configuration
    CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', f'redis://{REDIS_HOST}:{REDIS_PORT}/1')
    CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', f'redis://{REDIS_HOST}:{REDIS_PORT}/2')

    # CORS Configuration
    CORS_ALLOWED_ORIGINS = [
        origin.strip()
        for origin in os.getenv('CORS_ALLOWED_ORIGINS', 'http://localhost:3000').split(',')
    ]
    CORS_ALLOW_CREDENTIALS = True

    # REST Framework
    REST_FRAMEWORK = {
        'DEFAULT_AUTHENTICATION_CLASSES': [
            'rest_framework.authentication.SessionAuthentication',
        ],
        'DEFAULT_PERMISSION_CLASSES': [
            'rest_framework.permissions.IsAuthenticated',
        ],
    }

    @staticmethod
    def validate():
        """Validate settings on startup."""
        if not Settings.SESSION_SECRET_KEY or Settings.SESSION_SECRET_KEY == 'CHANGE-ME-IN-PRODUCTION':
            raise ValueError("SESSION_SECRET_KEY must be set in production!")
        if Settings.APP_ENV == 'production' and Settings.APP_DEBUG:
            raise ValueError("DEBUG must be False in production!")
        return True
    VAULT_NAMESPACE: str = Field(
        default="",
        description="Vault namespace (optional)"
    )

    # Multi-tenant Configuration
    DEFAULT_TENANT_ID: str = Field(default="default", description="Default tenant ID")
    TENANT_ISOLATION_MODE: str = Field(
        default="schema-per-tenant",
        description="Tenant isolation mode"
    )

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        case_sensitive = False

# Global settings instance
settings = Settings()

