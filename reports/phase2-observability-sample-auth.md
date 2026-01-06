# Phase 2 Observability: Sample Implementation — saraise-auth

This file provides a reference implementation pattern for observability instrumentation in **saraise-auth**. Other services should follow the same pattern.

---

## Overview
Wire metrics, structured logging, and tracing for session lifecycle events (login, logout, rotate) and session store interactions.

---

## Pattern 1: Metrics Instrumentation

### File: `src/observability.py` (new)

```python
from prometheus_client import Counter, Histogram
import time

# Counters
session_issue_total = Counter(
    'session_issue_total',
    'Total sessions issued',
    ['tenant_id', 'result']  # result: success, store_error, validation_error
)

session_rotate_total = Counter(
    'session_rotate_total',
    'Total sessions rotated',
    ['tenant_id', 'result']
)

session_invalid_total = Counter(
    'session_invalid_total',
    'Total sessions invalidated',
    ['tenant_id', 'result']
)

session_store_errors_total = Counter(
    'session_store_errors_total',
    'Total session store errors',
    ['operation']  # operation: write, read, delete
)

# Histograms
session_store_latency_ms = Histogram(
    'session_store_latency_ms',
    'Session store operation latency',
    ['operation'],
    buckets=(1, 5, 10, 25, 50, 100, 250, 500, 1000)
)


class MetricsContext:
    """Context manager for recording metric operations."""
    def __init__(self, operation: str):
        self.operation = operation
        self.start = None

    def __enter__(self):
        self.start = time.time()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration_ms = (time.time() - self.start) * 1000
        session_store_latency_ms.labels(operation=self.operation).observe(duration_ms)
        if exc_type:
            session_store_errors_total.labels(operation=self.operation).inc()
```

### File: `src/auth_service.py` (instrumentation additions)

```python
from .observability import (
    session_issue_total, session_rotate_total, session_store_latency_ms,
    MetricsContext
)

def login(username: str, password: str, tenant_id: str) -> SessionToken:
    """Issue a session token."""
    try:
        # Validate credentials...
        identity = validate_credentials(username, password, tenant_id)
        
        # Store session
        with MetricsContext('write'):
            session_token = store.write(identity)
        
        # Record metric
        session_issue_total.labels(tenant_id=tenant_id, result='success').inc()
        return session_token
    
    except StoreError as e:
        session_issue_total.labels(tenant_id=tenant_id, result='store_error').inc()
        raise
    except ValidationError as e:
        session_issue_total.labels(tenant_id=tenant_id, result='validation_error').inc()
        raise


def rotate(session_token: SessionToken, tenant_id: str) -> SessionToken:
    """Rotate a session token."""
    try:
        # Fetch old session
        with MetricsContext('read'):
            old_session = store.read(session_token)
        
        # Create new session with bumped identity
        new_identity = old_session.identity.with_rotated_timestamp()
        
        # Write new, delete old
        with MetricsContext('write'):
            new_token = store.write(new_identity)
        with MetricsContext('delete'):
            store.delete(session_token)
        
        session_rotate_total.labels(tenant_id=tenant_id, result='success').inc()
        return new_token
    
    except StoreError:
        session_rotate_total.labels(tenant_id=tenant_id, result='store_error').inc()
        raise
```

---

## Pattern 2: Structured Logging

### File: `src/logging_config.py` (new)

```python
import json
import logging
from dataclasses import asdict
from typing import Optional

class StructuredJsonFormatter(logging.Formatter):
    """Format logs as structured JSON."""
    def format(self, record):
        log_data = {
            'timestamp': self.formatTime(record),
            'level': record.levelname,
            'message': record.getMessage(),
            'logger': record.name,
        }
        if hasattr(record, 'tenant_id'):
            log_data['tenant_id'] = record.tenant_id
        if hasattr(record, 'action'):
            log_data['action'] = record.action
        if hasattr(record, 'result'):
            log_data['result'] = record.result
        if record.exc_info:
            log_data['exception'] = self.formatException(record.exc_info)
        return json.dumps(log_data)

# Configure logger
logger = logging.getLogger('auth')
handler = logging.StreamHandler()
handler.setFormatter(StructuredJsonFormatter())
logger.addHandler(handler)
logger.setLevel(logging.INFO)
```

### File: `src/auth_service.py` (logging additions)

```python
from .logging_config import logger

def login(username: str, password: str, tenant_id: str) -> SessionToken:
    """Issue a session token."""
    try:
        identity = validate_credentials(username, password, tenant_id)
        session_token = store.write(identity)
        
        # Structured log
        logger.info('login_success', extra={
            'tenant_id': tenant_id,
            'action': 'login',
            'result': 'success'
        })
        
        session_issue_total.labels(tenant_id=tenant_id, result='success').inc()
        return session_token
    
    except ValidationError as e:
        logger.warning('login_validation_failed', extra={
            'tenant_id': tenant_id,
            'action': 'login',
            'result': 'validation_error',
            'error': str(e)
        })
        session_issue_total.labels(tenant_id=tenant_id, result='validation_error').inc()
        raise
    
    except StoreError as e:
        logger.error('login_store_error', extra={
            'tenant_id': tenant_id,
            'action': 'login',
            'result': 'store_error',
            'error': str(e)
        })
        session_issue_total.labels(tenant_id=tenant_id, result='store_error').inc()
        raise
```

---

## Pattern 3: Distributed Tracing

### File: `src/tracing_config.py` (new)

```python
from opentelemetry import trace, context as otel_context
from opentelemetry.exporter.jaeger.thrift import JaegerExporter
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor

# Configure Jaeger exporter (or your tracing backend)
jaeger_exporter = JaegerExporter(
    agent_host_name='localhost',
    agent_port=6831,
)

trace.set_tracer_provider(TracerProvider())
trace.get_tracer_provider().add_span_processor(
    BatchSpanProcessor(jaeger_exporter)
)

tracer = trace.get_tracer(__name__)
```

### File: `src/auth_service.py` (tracing additions)

```python
from .tracing_config import tracer
from opentelemetry import context as otel_context

def login(username: str, password: str, tenant_id: str) -> SessionToken:
    """Issue a session token."""
    with tracer.start_as_current_span('login') as span:
        span.set_attribute('tenant_id', tenant_id)
        span.set_attribute('username', username)
        
        try:
            identity = validate_credentials(username, password, tenant_id)
            
            # Nested span for store operation
            with tracer.start_as_current_span('session_store_write') as store_span:
                store_span.set_attribute('tenant_id', tenant_id)
                session_token = store.write(identity)
            
            span.set_attribute('result', 'success')
            span.set_attribute('policy_version', identity.policy_version)
            
            return session_token
        
        except Exception as e:
            span.set_attribute('result', 'error')
            span.set_attribute('error_type', type(e).__name__)
            raise
```

---

## Pattern 4: Testing Observability

### File: `tests/test_auth_observability.py` (new)

```python
import pytest
from prometheus_client import REGISTRY
from unittest.mock import patch
from src.auth_service import login
from src.observability import session_issue_total

def test_login_emits_metrics():
    """Verify login emits session_issue_total metric."""
    # Clear registry
    REGISTRY._names_to_collectors.clear()
    
    # Mock store
    with patch('src.auth_service.store') as mock_store:
        mock_store.write.return_value = 'mock_token'
        
        # Login
        login('user', 'pass', 'tenant-1')
    
    # Assert metric was recorded
    assert session_issue_total.labels(tenant_id='tenant-1', result='success')._value.get() == 1


def test_login_logs_structured_json(caplog):
    """Verify login emits structured JSON log."""
    import json
    from src.logging_config import logger
    
    with patch('src.auth_service.store') as mock_store:
        mock_store.write.return_value = 'mock_token'
        
        # Login
        login('user', 'pass', 'tenant-1')
    
    # Assert structured log was emitted
    log_records = [r for r in caplog.records if 'login' in r.getMessage()]
    assert len(log_records) > 0
    
    # Verify structure
    log_json = json.loads(log_records[0].getMessage())
    assert log_json['tenant_id'] == 'tenant-1'
    assert log_json['action'] == 'login'
    assert log_json['result'] == 'success'


def test_login_traces_session_operations(mock_tracer):
    """Verify login creates traces with policy_version."""
    with patch('src.auth_service.store') as mock_store:
        mock_store.write.return_value = 'mock_token'
        
        # Login
        login('user', 'pass', 'tenant-1')
    
    # Assert spans were created
    assert len(mock_tracer.spans) >= 2  # login + session_store_write
    assert mock_tracer.spans[0].name == 'login'
    assert mock_tracer.spans[0].attributes['tenant_id'] == 'tenant-1'
    assert 'policy_version' in mock_tracer.spans[0].attributes
```

---

## Checklist: Apply This Pattern to saraise-auth

- [ ] Create `src/observability.py` with metrics definitions.
- [ ] Create `src/logging_config.py` with structured JSON formatter.
- [ ] Create `src/tracing_config.py` with Jaeger/tracing setup.
- [ ] Instrument auth_service.py functions (login, logout, rotate) with metrics/logs/traces.
- [ ] Add tests in `tests/test_auth_observability.py`.
- [ ] Verify metrics emitted: `prometheus_client` / dashboard query.
- [ ] Verify logs produced: structured JSON with tenant_id, action, result.
- [ ] Verify traces created: distributed trace in Jaeger/your backend with policy_version context.
- [ ] Merge PR with required status checks passing.

---

## Next: Apply Same Pattern to Other Services

Once saraise-auth PR is merged, apply the same pattern to:
- saraise-runtime (request metrics, policy_eval latency, deny reasons)
- saraise-policy-engine (policy_eval_total, bundle_version, stale denies)
- saraise-control-plane (tenant lifecycle, shard latency, policy bump tracing)
