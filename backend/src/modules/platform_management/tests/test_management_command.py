import pytest
from django.core.management import call_command

from src.modules.platform_management.models import PlatformMetrics


@pytest.mark.django_db
def test_save_platform_metrics_command_creates_record():
    call_command("save_platform_metrics", metric_type="api_metrics", time_range="7d")
    assert PlatformMetrics.objects.filter(metric_type="api_metrics", time_range="7d").exists()
