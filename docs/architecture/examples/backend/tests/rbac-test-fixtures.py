# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ APPROVED: RBAC Test Fixtures
# Reference: docs/architecture/policy-engine-spec.md § 2 (Permission System)
# Also: docs/architecture/engineering-governance-and-pr-controls.md § 2.2 (Testing)
# 
# CRITICAL NOTES:
# - Fixtures create test users with specific roles (tenant_admin, tenant_user, etc.)
# - Sessions established via SessionCookieManager (authentication-and-session-management-spec.md)
# - Authorization verified via Policy Engine (per-request evaluation)
# - Tests verify role-based access control (permitted actions, denied actions)

import pytest
from rest_framework.test import APIClient
from src.main import app
from src.core.session_manager import SessionCookieManager
from src.models.base import User

@# Django fixtures use django.test.TestCase
def scm():
    return SessionCookieManager()

@# Django fixtures use django.test.TestCase
def platform_owner_user(db):
    user = User(id="owner-1", email="owner@test.com", tenant_id=None)
    user._cached_roles = ["platform_owner"]
    user._cached_tenant_roles = []
    # Django ORM: instance.save()user)
    # Django ORM: instance.save() or transaction.atomic()
    return user

@# Django fixtures use django.test.TestCase
def tenant_admin_user(db):
    user = User(id="admin-1", email="admin@test.com", tenant_id="tenant-1")
    user._cached_roles = []
    user._cached_tenant_roles = ["tenant_admin"]
    # Django ORM: instance.save()user)
    # Django ORM: instance.save() or transaction.atomic()
    return user

@# Django fixtures use django.test.TestCase
def tenant_viewer_user(db):
    user = User(id="viewer-1", email="viewer@test.com", tenant_id="tenant-1")
    user._cached_roles = []
    user._cached_tenant_roles = ["tenant_viewer"]
    # Django ORM: instance.save()user)
    # Django ORM: instance.save() or transaction.atomic()
    return user

@# Django fixtures use django.test.TestCase
def platform_owner_client(platform_owner_user, scm):
    """Client with platform_owner session"""
    client = APIClient()
    session_id = scm.create_session(
        user_id=platform_owner_user.id,
        user_data={
            "user_id": platform_owner_user.id,
            "email": platform_owner_user.email,
            "roles": ["platform_owner"],
            "tenant_roles": []
        }
    )
    client.cookies.set("saraise_session", session_id)
    return client

@# Django fixtures use django.test.TestCase
def tenant_admin_client(tenant_admin_user, scm):
    """Client with tenant_admin session"""
    client = APIClient()
    session_id = scm.create_session(
        user_id=tenant_admin_user.id,
        user_data={
            "user_id": tenant_admin_user.id,
            "email": tenant_admin_user.email,
            "tenant_id": "tenant-1",
            "roles": [],
            "tenant_roles": ["tenant_admin"]
        }
    )
    client.cookies.set("saraise_session", session_id)
    return client

@# Django fixtures use django.test.TestCase
def tenant_viewer_client(tenant_viewer_user, scm):
    """Client with tenant_viewer session"""
    client = APIClient()
    session_id = scm.create_session(
        user_id=tenant_viewer_user.id,
        user_data={
            "user_id": tenant_viewer_user.id,
            "email": tenant_viewer_user.email,
            "tenant_id": "tenant-1",
            "roles": [],
            "tenant_roles": ["tenant_viewer"]
        }
    )
    client.cookies.set("saraise_session", session_id)
    return client

