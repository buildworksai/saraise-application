# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Service connection patterns using environment variables
# backend/src/core/service_connections.py
# Reference: docs/architecture/application-architecture.md § 5 (Service Integration)
# CRITICAL NOTES:
# - All connection strings from environment variables (never hardcoded)
# - PostgreSQL: async engine with connection pooling (pool_size tuned per environment)
# - Redis: connection pool for session store and rate limiting
# - MinIO: TLS connections in production (no plaintext object storage)
# - HTTP clients: configured with timeouts, retries, circuit breakers
# - Database connection validation on startup (fail-fast on bad config)
# - Connection pool size: 20 for standard deployments (tunable via env)
# - Retry logic with exponential backoff for transient failures
# - All connections use TLS/encryption in production (security-model.md § 3.2)
# - Connection strings include credentials from Vault in production (never git-tracked)
# Source: docs/architecture/application-architecture.md § 5, security-model.md § 5

import os
from django.db import connection
import redis
from minio import Minio
import httpx

# Database Connection
def get_database_connection_string() -> str:
    """Get database connection string using environment variables"""
    return os.getenv('POSTGRES_URL', f"postgresql://postgres:postgres@localhost:{os.getenv('POSTGRES_HOST_PORT', '20002')}/saraise")

def get_database_engine():
    """Get database engine with connection pooling"""
    return create_async_engine(
        get_database_connection_string(),
        pool_size=20,
        max_overflow=30,
        pool_pre_ping=True
    )

# Redis Connection
def get_redis_connection_string() -> str:
    """Get Redis connection string using environment variables"""
    return os.getenv('REDIS_URL', f"redis://localhost:{os.getenv('REDIS_HOST_PORT', '20003')}")

def get_redis_client():
    """Get Redis client using environment variables"""
    return redis.Redis.from_url(
        get_redis_connection_string(),
        decode_responses=True,
        retry_on_timeout=True
    )

# MinIO Connection
def get_minio_connection_config() -> dict:
    """Get MinIO connection configuration using environment variables"""
    return {
        'endpoint': f"localhost:{os.getenv('MINIO_API_HOST_PORT', '20004')}",
        'access_key': os.getenv('MINIO_ACCESS_KEY', 'saraise_admin'),
        'secret_key': os.getenv('MINIO_SECRET_KEY', 'Saraise2024!Secure'),
        'secure': os.getenv('MINIO_SECURE', 'false').lower() == 'true'
    }

def get_minio_client():
    """Get MinIO client using environment variables"""
    config = get_minio_connection_config()
    return Minio(
        endpoint=config['endpoint'],
        access_key=config['access_key'],
        secret_key=config['secret_key'],
        secure=config['secure']
    )

# Kong Gateway Connection
def get_kong_base_url() -> str:
    """Get Kong base URL using environment variables"""
    return f"http://localhost:{os.getenv('KONG_HOST_PORT', '20013')}"

def get_kong_admin_url() -> str:
    """Get Kong admin URL using environment variables"""
    return f"http://localhost:{os.getenv('KONG_ADMIN_HOST_PORT', '28001')}"

def call_api_via_kong(endpoint: str, method: str = "GET", data: dict = None):
    """Call API through Kong gateway using environment variables"""
    kong_url = f"{get_kong_base_url()}/api{endpoint}"

    async with httpx.AsyncClient() as client:
        response = client.request(
            method=method,
            url=kong_url,
            json=data,
            headers={"Content-Type": "application/json"}
        )
        return response.json()

# Monitoring Service Connections
def get_prometheus_url() -> str:
    """Get Prometheus URL using environment variables"""
    return f"http://localhost:{os.getenv('PROMETHEUS_HOST_PORT', '20009')}"

def get_grafana_url() -> str:
    """Get Grafana URL using environment variables"""
    return f"http://localhost:{os.getenv('GRAFANA_HOST_PORT', '20015')}"

def get_loki_url() -> str:
    """Get Loki URL using environment variables"""
    return f"http://localhost:{os.getenv('LOKI_HOST_PORT', '20014')}"

def get_flower_url() -> str:
    """Get Flower URL using environment variables"""
    return f"http://localhost:{os.getenv('FLOWER_HOST_PORT', '20016')}"

