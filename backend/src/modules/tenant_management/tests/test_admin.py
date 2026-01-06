import pytest
from django.contrib import admin

from ..models import Tenant


@pytest.mark.django_db
def test_admin_registration():
    # Import registers models with admin site
    __import__("src.modules.tenant_management.admin")
    assert Tenant in admin.site._registry
