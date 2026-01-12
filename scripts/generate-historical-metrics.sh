#!/bin/bash
#
# SPDX-License-Identifier: Apache-2.0
#
# Generate historical metrics data for testing charts
#
# This script creates multiple metric records with different timestamps
# to simulate historical data over the past 30 days.

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

echo "Generating historical metrics data..."

cd "$PROJECT_ROOT"

# Generate metrics for the past 30 days (one per day)
for i in {0..29}; do
    DAYS_AGO=$i
    echo "Creating metrics for $DAYS_AGO days ago..."

    # Use Docker exec to run the command with a custom timestamp
    docker compose -f docker-compose.dev.yml exec -T backend python -c "
import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'saraise_backend.settings')
django.setup()

from django.utils import timezone
from datetime import timedelta
from src.modules.platform_management.services import AnalyticsService
from src.modules.platform_management.models import PlatformMetrics

# Calculate timestamp
target_date = timezone.now() - timedelta(days=$DAYS_AGO)

# Save metrics
service = AnalyticsService()
metric = service.save_metrics(
    metric_type='complete',
    time_range='30d',
    updated_by=None,
)

# Update the recorded_at timestamp to simulate historical data
metric.recorded_at = target_date
metric.save()

print(f'Created metric {metric.id} for {target_date}')
"

    # Small delay to avoid overwhelming the database
    sleep 0.5
done

echo "Historical metrics generation complete!"
