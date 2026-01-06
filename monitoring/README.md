# Monitoring

Purpose: local observability stack assets for SARAISE (Prometheus, Alertmanager, Grafana provisioning, and dashboards).

Contents:
- prometheus/: scrape config and alert rules
- alertmanager/: alert routing configuration
- grafana/: datasources, dashboard provisioning, and dashboard JSON

This folder is wired into `docker-compose.dev.yml` for development and validation.
