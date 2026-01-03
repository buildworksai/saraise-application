# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Service Integration Examples
# Reference: docs/architecture/operational-runbooks.md § 2.0 (Infrastructure Services)

# MailHog Email Testing
import smtplib
from email.mime.text import MIMEText

def send_test_email(to: str, subject: str, body: str):
    """Send email via MailHog for testing.
    
    CRITICAL: Platform-level infrastructure service for development.
    Not for production - use external SMTP for production email.
    """
    message = MIMEText(body)
    message["From"] = "noreply@saraise.com"
    message["To"] = to
    message["Subject"] = subject

    with smtplib.SMTP(host="mailhog", port=1025) as smtp:
        smtp.send_message(message)

# MinIO Object Storage
from minio import Minio
from minio.error import S3Error
from rest_framework.exceptions import APIException
import os

def get_minio_client():
    """Get MinIO client using environment variables"""
    return Minio(
        endpoint=f"minio:{os.getenv('MINIO_API_CONTAINER_PORT', '9000')}",
        access_key=os.getenv('MINIO_ACCESS_KEY', 'saraise_admin'),
        secret_key=os.getenv('MINIO_SECRET_KEY', 'Saraise2024!Secure'),
        secure=False
    )

def upload_file(bucket: str, object_name: str, file_path: str):
    """Upload file to MinIO"""
    client = get_minio_client()
    try:
        client.fput_object(bucket, object_name, file_path)
        return f"http://localhost:{os.getenv('MINIO_API_HOST_PORT', '19000')}/{bucket}/{object_name}"
    except S3Error as e:
        # ✅ CORRECT: Raise DRF exception (NOT raise Response, NOT HTTPException)
        raise APIException(detail=f"Upload failed: {str(e)}")

# Kong API Gateway
import httpx

def call_api_via_kong(endpoint: str, method: str = "GET", data: dict = None):
    """Call API through Kong gateway"""
    kong_url = f"http://kong:{os.getenv('KONG_CONTAINER_PORT', '8000')}/api{endpoint}"

    with httpx.Client() as client:
        response = client.request(
            method=method,
            url=kong_url,
            json=data,
            headers={"Content-Type": "application/json"}
        )
        return response.json()

# Celery Task Queue
from celery import Celery
from src.core.celery_config import celery_app

@celery_app.task(bind=True, max_retries=3)
def process_background_task(self, task_data: dict):
    """Background task with retry logic"""
    try:
        # Task implementation
        result = perform_task(task_data)
        return {"status": "success", "result": result}
    except Exception as exc:
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

# Redis Caching
import redis
import json

def get_redis_client():
    """Get Redis client using environment variables"""
    return redis.Redis(
        host="redis",
        port=int(os.getenv('REDIS_CONTAINER_PORT', '6379')),
        password=os.getenv('REDIS_PASSWORD', 'Saraise2024!Redis'),
        decode_responses=True
    )

def cache_user_data(user_id: str, data: dict, ttl: int = 3600):
    """Cache user data in Redis"""
    client = get_redis_client()
    key = f"user:{user_id}"
    client.setex(key, ttl, json.dumps(data))

def get_cached_user_data(user_id: str) -> dict:
    """Get cached user data from Redis"""
    client = get_redis_client()
    key = f"user:{user_id}"
    data = client.get(key)
    return json.loads(data) if data else None

