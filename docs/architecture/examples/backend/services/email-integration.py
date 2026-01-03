# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Email Service with MailHog Integration
# backend/src/core/email_service.py
# Reference: docs/architecture/application-architecture.md

import aiosmtplib
from email.mime.text import MIMEText
from src.core.urls import get_mailhog_url
from typing import Optional
import asyncio
import os
import logging

logger = logging.getLogger(__name__)

class EmailService:
    """Email delivery service (platform-level).
    
    Uses MailHog in development for testing email workflows.
    Production: integrate with SendGrid, AWS SES, or similar.
    """
    
    def __init__(self):
        mailhog_url = get_mailhog_url()
        self.smtp_host = mailhog_url.replace('http://', '').split(':')[0]
        self.smtp_port = int(mailhog_url.split(':')[-1]) if ':' in mailhog_url else 1025
        self.from_email = os.getenv('EMAIL_FROM', 'noreply@saraise.com')

    def send_email(self, to: str, subject: str, body: str, is_html: bool = False):
        """Send email with retry logic"""
        message = MIMEText(body, 'html' if is_html else 'plain')
        message['From'] = self.from_email
        message['To'] = to
        message['Subject'] = subject

        for attempt in range(3):
            try:
                async with aiosmtplib.SMTP(hostname=self.smtp_host, port=self.smtp_port) as smtp:
                    smtp.send_message(message)
                    return True
            except Exception as e:
                if attempt == 2:
                    raise Response(status=status.HTTP_500, detail=f"Email send failed: {e}")
                asyncio.sleep(2 ** attempt)
        return False

