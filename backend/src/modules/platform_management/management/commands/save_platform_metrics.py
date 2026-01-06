"""
Django management command to save platform metrics periodically.

This command should be run via cron or scheduler to build historical time-series data.
Usage:
    python manage.py save_platform_metrics [--metric-type=complete] [--time-range=30d]
"""
from django.core.management.base import BaseCommand
from src.modules.platform_management.services import AnalyticsService
from src.modules.platform_management.models import PlatformMetrics


class Command(BaseCommand):
    help = 'Save current platform metrics to database for historical tracking'

    def add_arguments(self, parser):
        parser.add_argument(
            '--metric-type',
            type=str,
            default=PlatformMetrics.MetricType.COMPLETE,
            choices=[
                PlatformMetrics.MetricType.TENANT,
                PlatformMetrics.MetricType.USER,
                PlatformMetrics.MetricType.API,
                PlatformMetrics.MetricType.REVENUE,
                PlatformMetrics.MetricType.COMPLETE,
            ],
            help='Type of metrics to save',
        )
        parser.add_argument(
            '--time-range',
            type=str,
            default='30d',
            help='Time range for metrics (e.g., 7d, 30d, 90d)',
        )

    def handle(self, *args, **options):
        metric_type = options['metric_type']
        time_range = options['time_range']

        self.stdout.write(f'Saving {metric_type} metrics for {time_range}...')

        service = AnalyticsService()
        try:
            metric = service.save_metrics(
                metric_type=metric_type,
                time_range=time_range,
                created_by=None,  # System-initiated
            )
            self.stdout.write(
                self.style.SUCCESS(
                    f'Successfully saved metrics: {metric.id} ({metric.metric_type}, {metric.time_range})'
                )
            )
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(f'Failed to save metrics: {str(e)}')
            )
            raise
