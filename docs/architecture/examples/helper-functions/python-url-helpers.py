# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: URL Construction Helper Functions
# backend/src/helpers/url_helpers.py
# Reference: docs/architecture/application-architecture.md § 6 (Deployment)

import os

def get_frontend_url() -> str:
    """Get frontend URL using environment variables.
    
    CRITICAL: All URLs must be environment-configured.
    No hardcoded URLs in code - use environment variables.
    """
    return os.getenv('FRONTEND_BASE_URL', f"http://localhost:{os.getenv('FRONTEND_HOST_PORT', '20000')}")

def get_api_url() -> str:
    """Get API URL using environment variables"""
    return os.getenv('API_BASE_URL', f"http://localhost:{os.getenv('API_HOST_PORT', '20001')}")

def get_database_url() -> str:
    """Get database connection URL using environment variables"""
    return os.getenv('POSTGRES_URL', f"postgresql://postgres:postgres@localhost:{os.getenv('POSTGRES_HOST_PORT', '20002')}/saraise")

def get_redis_url() -> str:
    """Get Redis connection URL using environment variables"""
    return os.getenv('REDIS_URL', f"redis://localhost:{os.getenv('REDIS_HOST_PORT', '20003')}")

def get_minio_url() -> str:
    """Get MinIO URL using environment variables"""
    return os.getenv('MINIO_URL', f"http://localhost:{os.getenv('MINIO_API_HOST_PORT', '20004')}")

def get_mailhog_url() -> str:
    """Get MailHog URL using environment variables"""
    return os.getenv('DEV_MAILHOG_URL', f"http://localhost:{os.getenv('MAILHOG_UI_HOST_PORT', '20007')}")

def get_vault_url() -> str:
    """Get Vault URL using environment variables"""
    return os.getenv('DEV_VAULT_URL', f"http://localhost:{os.getenv('VAULT_HOST_PORT', '20008')}")

def get_kong_url() -> str:
    """Get Kong URL using environment variables"""
    return f"http://localhost:{os.getenv('KONG_HOST_PORT', '20013')}"

def get_loki_url() -> str:
    """Get Loki URL using environment variables"""
    return f"http://localhost:{os.getenv('LOKI_HOST_PORT', '20014')}"

def get_prometheus_url() -> str:
    """Get Prometheus URL using environment variables"""
    return f"http://localhost:{os.getenv('PROMETHEUS_HOST_PORT', '20009')}"

def get_grafana_url() -> str:
    """Get Grafana URL using environment variables"""
    return f"http://localhost:{os.getenv('GRAFANA_HOST_PORT', '20015')}"

def get_flower_url() -> str:
    """Get Flower URL using environment variables"""
    return f"http://localhost:{os.getenv('FLOWER_HOST_PORT', '20016')}"

def get_cors_origins() -> list:
    """Get CORS origins using environment variables"""
    frontend_port = os.getenv('FRONTEND_HOST_PORT', '20000')
    api_port = os.getenv('API_HOST_PORT', '20001')
    return [
        f"http://localhost:{frontend_port}",
        f"http://127.0.0.1:{frontend_port}",
        f"http://localhost:{api_port}",
        f"http://127.0.0.1:{api_port}"
    ]

def get_environment_urls() -> dict:
    """Get all environment-specific URLs"""
    return {
        'development': {
            'frontend': get_frontend_url(),
            'api': get_api_url(),
            'mailhog': get_mailhog_url(),
            'vault': get_vault_url(),
            'kong': get_kong_url(),
            'loki': get_loki_url(),
            'prometheus': get_prometheus_url(),
            'grafana': get_grafana_url(),
            'flower': get_flower_url()
        },
        'staging': {
            'base': os.getenv('STAGING_BASE_URL', 'https://staging.saraise.com'),
            'api': os.getenv('API_BASE_URL', 'https://api.saraise.com')
        },
        'production': {
            'base': os.getenv('PRODUCTION_BASE_URL', 'https://saraise.com'),
            'api': os.getenv('API_PRODUCTION_URL', 'https://api.saraise.com')
        }
    }

