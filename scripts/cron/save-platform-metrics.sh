#!/bin/bash
#
# SPDX-License-Identifier: Apache-2.0
#
# Cron script to save platform metrics periodically
#
# This script should be added to crontab to run every hour:
# 0 * * * * /path/to/saraise/scripts/cron/save-platform-metrics.sh
#
# Or use Docker exec:
# docker compose -f docker-compose.dev.yml exec backend python manage.py save_platform_metrics

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

# Default to Docker exec if docker-compose.yml exists
if [ -f "$PROJECT_ROOT/docker-compose.dev.yml" ]; then
    echo "Running via Docker..."
    cd "$PROJECT_ROOT"
    docker compose -f docker-compose.dev.yml exec -T backend python manage.py save_platform_metrics --metric-type=complete --time-range=30d
else
    # Fallback to direct Python execution
    echo "Running directly..."
    cd "$PROJECT_ROOT/backend"
    python manage.py save_platform_metrics --metric-type=complete --time-range=30d
fi

echo "Platform metrics saved successfully at $(date)"

