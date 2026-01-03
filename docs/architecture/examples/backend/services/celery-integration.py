# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Celery Task Integration with Error Handling
# backend/src/tasks/email_tasks.py
# Reference: docs/architecture/operational-runbooks.md § 5.1 (Background Jobs)
# CRITICAL: Celery tasks are synchronous. NO async/await patterns.

from celery import Celery
from src.core.celery_config import celery_app
import logging

@celery_app.task(bind=True, max_retries=3, default_retry_delay=60)
def process_email_task(self, email_data: dict):
    """Process email task with retry logic.
    
    CRITICAL: Background jobs operate without session context.
    Authorization for actions must be pre-established by caller.
    See docs/architecture/operational-runbooks.md § 5.1.
    
    Tasks must be synchronous - Django ORM does not support async.
    """
    try:
        from src.services.email_service import EmailService
        email_service = EmailService()

        # CRITICAL: Synchronous call - NO asyncio.run()
        result = email_service.send_email(
            to=email_data['to'],
            subject=email_data['subject'],
            body=email_data['body']
        )

        return {"status": "success", "result": result}
    except Exception as exc:
        logging.error(f"Email task failed: {exc}")
        # Retry with exponential backoff
        raise self.retry(exc=exc, countdown=60 * (2 ** self.request.retries))

