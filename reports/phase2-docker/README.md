# Phase 2 Docker Infrastructure

This directory contains Docker configuration for Phase 2 containerized development, testing, and observability validation.

## Structure

- `Dockerfiles/` — Service-specific Dockerfiles for each Tier-0 repo
- `docker-compose.phase2.yml` — Orchestration for Phase 2 stack (auth, runtime, policy, control-plane, platform-core)
- `docker-compose.observability.yml` — Prometheus, Jaeger, Grafana for metrics/tracing
- `scripts/` — Helper scripts for Docker operations

## Quick Start

```bash
# Build all Phase 2 services
docker-compose -f docker-compose.phase2.yml build

# Start Phase 2 stack with observability
docker-compose -f docker-compose.phase2.yml -f docker-compose.observability.yml up

# Run tests in containers
docker-compose -f docker-compose.phase2.yml run --rm saraise-auth pytest tests/

# View metrics
open http://localhost:9090  # Prometheus
open http://localhost:3000  # Grafana
open http://localhost:16686  # Jaeger
```

## Phase 2 Validation

All Phase 2 work (observability, hardening, compliance evidence, chaos drills) runs in Docker:

- Tests execute in isolated containers
- Metrics scraped by Prometheus
- Traces sent to Jaeger
- Logs aggregated and structured
- Chaos drills simulate container/network failures

## Services

- `saraise-auth`: Port 8001
- `saraise-runtime`: Port 8002
- `saraise-policy-engine`: Port 8003
- `saraise-control-plane`: Port 8004
- `redis`: Port 6379 (session store)
- `prometheus`: Port 9090 (metrics)
- `jaeger`: Port 16686 (tracing UI)
- `grafana`: Port 3000 (dashboards)
