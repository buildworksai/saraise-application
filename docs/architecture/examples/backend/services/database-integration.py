# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: Database Operations with Django ORM
# backend/src/core/database.py
# Reference: docs/architecture/operational-runbooks.md § 2.0 (Infrastructure)
# CRITICAL: SARAISE uses Django ORM exclusively
# - Django manages connection pooling automatically via DATABASES setting
# - Use Django's transaction.atomic() for transactions
# - Use Model.objects for all database queries

from django.db import transaction, connection
from django.conf import settings
from typing import Generator

def get_db_connection():
    """Get Django database connection.
    
    CRITICAL: Django ORM manages connection pooling automatically.
    Connection settings configured in settings.DATABASES.
    See docs/architecture/operational-runbooks.md § 2.0.
    
    Django handles:
    - Connection pooling (via DATABASES['default']['CONN_MAX_AGE'])
    - Connection reuse
    - Automatic connection management
    """
    return connection


def get_db():
    """Get database connection for dependency injection.
    
    Django ORM pattern: Use Model.objects directly, or connection for raw SQL.
    For DRF views, use Model.objects.filter() - no session needed.
    
    Example:
        from src.models.user import User
        users = User.objects.filter(tenant_id=tenant_id)
    """
    return connection


# ✅ CORRECT: Django transaction pattern
@transaction.atomic
def execute_with_transaction(func):
    """Execute function within Django transaction.
    
    Django ORM uses @transaction.atomic decorator for transaction management.
    """
    return func()

