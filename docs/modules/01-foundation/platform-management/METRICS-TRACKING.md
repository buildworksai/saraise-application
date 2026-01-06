# Platform Metrics Tracking

**SPDX-License-Identifier: Apache-2.0**

## Overview

The Platform Management module includes comprehensive metrics tracking and visualization capabilities. This document describes how metrics are collected, stored, and displayed.

## Architecture

### Data Flow

1. **Real-time Collection**: API calls are tracked via `APITrackingMiddleware`
2. **Periodic Aggregation**: Metrics are saved to database via `save_platform_metrics` command
3. **Time-Series Retrieval**: Charts fetch historical data via `/api/v1/platform/metrics/timeseries/`
4. **Visualization**: Frontend displays charts with export capabilities

### Components

#### Backend

- **`APITrackingMiddleware`**: Tracks API calls in Redis cache
  - Records: total calls, response times, error rates, endpoint usage
  - Storage: Redis with 24-hour TTL
  - Location: `backend/src/core/middleware/api_tracking.py`

- **`AnalyticsService`**: Aggregates metrics from multiple sources
  - Sources: Database queries, Redis cache, system metrics
  - Methods: `get_api_metrics()`, `get_tenant_metrics()`, `get_user_metrics()`, etc.
  - Location: `backend/src/modules/platform_management/services.py`

- **`save_platform_metrics` Command**: Saves current metrics snapshot
  - Usage: `python manage.py save_platform_metrics --metric-type=complete --time-range=30d`
  - Frequency: Recommended hourly via cron
  - Location: `backend/src/modules/platform_management/management/commands/save_platform_metrics.py`

#### Frontend

- **Chart Components**: Reusable chart components with export
  - Components: `AreaChart`, `LineChart`, `BarChart`, `PieChart`
  - Export: CSV download via `exportTimeseriesToCSV()`
  - Location: `frontend/src/components/charts/`

- **Export Utilities**: CSV export functions
  - Functions: `exportToCSV()`, `exportTimeseriesToCSV()`
  - Location: `frontend/src/utils/export.ts`

## Usage

### Saving Metrics

**Manual Save:**
```bash
docker compose -f docker-compose.dev.yml exec backend python manage.py save_platform_metrics
```

**Scheduled Save (Cron):**
```bash
# Add to crontab (runs every hour)
0 * * * * /path/to/saraise/scripts/cron/save-platform-metrics.sh
```

**Generate Historical Data:**
```bash
# Creates 30 days of historical data
./scripts/generate-historical-metrics.sh
```

### API Endpoints

**Get Current Metrics:**
```
GET /api/v1/platform/metrics/current/?time_range=30d&metric_type=complete
```

**Get Time-Series Data:**
```
GET /api/v1/platform/metrics/timeseries/?metric_type=complete&time_range=30d&interval=day
```

**Save Metrics:**
```
POST /api/v1/platform/metrics/save/
{
  "metric_type": "complete",
  "time_range": "30d"
}
```

### Frontend Export

All charts include an "Export CSV" button that downloads the time-series data:
- Date column
- Timestamp column
- Value column

## Metrics Collected

### API Metrics
- Total API calls (30d)
- Average response time (ms)
- P95/P99 response times (ms)
- Error rate (%)
- Top endpoints (future)

### Tenant Metrics
- Total tenants
- Active tenants (30d)
- New tenants (this month)
- Churned tenants (this month)
- Growth rate

### User Metrics
- Total users
- Active users (7d, 30d)
- New users (this month)

### Revenue Metrics
- Monthly Recurring Revenue (MRR)
- Annual Recurring Revenue (ARR)
- Average revenue per tenant
- Customer Lifetime Value (CLV)
- Customer Acquisition Cost (CAC)

## Configuration

### Middleware

The API tracking middleware is enabled by default in `settings.py`:

```python
MIDDLEWARE = [
    # ... other middleware ...
    'src.core.middleware.api_tracking.APITrackingMiddleware',
]
```

### Redis Cache

Metrics are stored in Redis with keys:
- `api_metrics:{date}:total` - Total calls per day
- `api_metrics:{date}:response_times` - List of response times
- `api_metrics:{date}:errors` - Error count
- `api_metrics:{date}:endpoint:{path}` - Per-endpoint counts

All keys expire after 24 hours.

## Troubleshooting

### Charts Show "N/A"

**Cause**: No historical metrics saved yet.

**Solution**: Run `save_platform_metrics` command to create initial data points.

### API Metrics Show Zero

**Cause**: Middleware not tracking or Redis not accessible.

**Solution**: 
1. Verify middleware is in `MIDDLEWARE` list
2. Check Redis connection
3. Make some API calls to generate data

### Export Button Not Visible

**Cause**: No data available for the chart.

**Solution**: Ensure time-series data exists for the selected time range.

## Future Enhancements

1. **Real-time WebSocket Updates**: Push metric updates to frontend
2. **Advanced Aggregations**: Hourly, weekly, monthly rollups
3. **Alert Thresholds**: Configure alerts based on metric values
4. **Custom Dashboards**: User-configurable metric displays
5. **Export Formats**: Excel, PDF, JSON export options

