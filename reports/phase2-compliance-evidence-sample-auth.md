# Phase 2 Compliance Evidence: Sample Implementation — saraise-auth

This file provides reference implementations for compliance evidence emission in **saraise-auth**. Other services should follow similar patterns.

---

## Overview
Emit auditable events for auth operations (login, logout, rotate, errors) with schema validation and exportability.

---

## Event Schema Definition

### File: `src/audit_schemas.py` (new)

```python
from dataclasses import dataclass, asdict
from datetime import datetime
from enum import Enum
from typing import Optional
import json

class AuthEventType(Enum):
    """Auth event types for compliance audit trail."""
    LOGIN_SUCCESS = 'auth.login.success'
    LOGIN_FAILURE = 'auth.login.failure'
    LOGOUT = 'auth.logout'
    SESSION_ROTATE = 'auth.session.rotate'
    SESSION_VALIDATION_FAILURE = 'auth.validation.failure'
    STORE_ERROR = 'auth.store.error'

@dataclass
class AuthAuditEvent:
    """Auditable auth event with required fields for compliance."""
    timestamp: str  # ISO 8601 timestamp
    event_type: str  # AuthEventType value
    user_id: Optional[str]  # None if login failed
    tenant_id: str  # Always present
    action: str  # 'login', 'logout', 'rotate', etc.
    result: str  # 'success', 'validation_error', 'store_error', 'invalid_credentials'
    policy_version: Optional[str]  # Current policy version at time of event
    error_reason: Optional[str]  # If result != 'success'
    
    def to_json(self) -> str:
        """Serialize to JSON for audit trail export."""
        return json.dumps(asdict(self))
    
    @classmethod
    def from_dict(cls, data: dict) -> 'AuthAuditEvent':
        """Deserialize from dict."""
        return cls(**data)


def validate_auth_event_schema(event: AuthAuditEvent) -> bool:
    """Validate event has all required fields."""
    required = ['timestamp', 'event_type', 'tenant_id', 'action', 'result']
    event_dict = asdict(event)
    
    for field in required:
        if field not in event_dict or event_dict[field] is None:
            return False
    
    # Validate event_type is valid enum value
    valid_types = [e.value for e in AuthEventType]
    if event_dict['event_type'] not in valid_types:
        return False
    
    return True
```

---

## Event Emission Implementation

### File: `src/audit_logger.py` (new)

```python
import json
from datetime import datetime, timezone
from typing import Optional
from src.audit_schemas import AuthAuditEvent, AuthEventType, validate_auth_event_schema
import logging

# Separate audit logger
audit_logger = logging.getLogger('auth.audit')

class AuditEventEmitter:
    """Emit compliance audit events for auth operations."""
    
    @staticmethod
    def emit_login_success(user_id: str, tenant_id: str, policy_version: str):
        """Emit login success event."""
        event = AuthAuditEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=AuthEventType.LOGIN_SUCCESS.value,
            user_id=user_id,
            tenant_id=tenant_id,
            action='login',
            result='success',
            policy_version=policy_version,
            error_reason=None
        )
        
        assert validate_auth_event_schema(event), 'Invalid event schema'
        audit_logger.info(event.to_json())
        return event
    
    @staticmethod
    def emit_login_failure(tenant_id: str, reason: str):
        """Emit login failure event (no user_id since auth failed)."""
        event = AuthAuditEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=AuthEventType.LOGIN_FAILURE.value,
            user_id=None,  # Not authenticated
            tenant_id=tenant_id,
            action='login',
            result='validation_error',  # or 'invalid_credentials'
            policy_version=None,
            error_reason=reason
        )
        
        assert validate_auth_event_schema(event), 'Invalid event schema'
        audit_logger.warning(event.to_json())
        return event
    
    @staticmethod
    def emit_logout(user_id: str, tenant_id: str):
        """Emit logout event."""
        event = AuthAuditEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=AuthEventType.LOGOUT.value,
            user_id=user_id,
            tenant_id=tenant_id,
            action='logout',
            result='success',
            policy_version=None,
            error_reason=None
        )
        
        assert validate_auth_event_schema(event), 'Invalid event schema'
        audit_logger.info(event.to_json())
        return event
    
    @staticmethod
    def emit_session_rotate(user_id: str, tenant_id: str, policy_version: str):
        """Emit session rotation event."""
        event = AuthAuditEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=AuthEventType.SESSION_ROTATE.value,
            user_id=user_id,
            tenant_id=tenant_id,
            action='rotate',
            result='success',
            policy_version=policy_version,
            error_reason=None
        )
        
        assert validate_auth_event_schema(event), 'Invalid event schema'
        audit_logger.info(event.to_json())
        return event
    
    @staticmethod
    def emit_store_error(tenant_id: str, operation: str, error_msg: str):
        """Emit session store error event."""
        event = AuthAuditEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            event_type=AuthEventType.STORE_ERROR.value,
            user_id=None,
            tenant_id=tenant_id,
            action=f'store_{operation}',
            result='store_error',
            policy_version=None,
            error_reason=error_msg
        )
        
        assert validate_auth_event_schema(event), 'Invalid event schema'
        audit_logger.error(event.to_json())
        return event


# Global instance
emitter = AuditEventEmitter()
```

---

## Integration with Auth Service

### File: `src/auth_service.py` (audit integration additions)

```python
from src.audit_logger import emitter
from src.observability import session_issue_total

def login(username: str, password: str, tenant_id: str) -> SessionToken:
    """Issue a session token with compliance audit."""
    try:
        # Validate credentials
        identity = validate_credentials(username, password, tenant_id)
        
        # Store session
        with MetricsContext('write'):
            session_token = store.write(identity)
        
        # Emit audit event
        emitter.emit_login_success(
            user_id=identity.user_id,
            tenant_id=tenant_id,
            policy_version=identity.policy_version
        )
        
        session_issue_total.labels(tenant_id=tenant_id, result='success').inc()
        return session_token
    
    except ValidationError as e:
        emitter.emit_login_failure(tenant_id, f'validation_error: {str(e)}')
        session_issue_total.labels(tenant_id=tenant_id, result='validation_error').inc()
        raise
    
    except InvalidCredentialsError as e:
        emitter.emit_login_failure(tenant_id, 'invalid_credentials')
        session_issue_total.labels(tenant_id=tenant_id, result='invalid_credentials').inc()
        raise
    
    except StoreError as e:
        emitter.emit_store_error(tenant_id, 'write', str(e))
        session_issue_total.labels(tenant_id=tenant_id, result='store_error').inc()
        raise


def logout(session_token: SessionToken, tenant_id: str):
    """Invalidate session with compliance audit."""
    try:
        identity = validate_session_token(session_token)
        
        # Delete session
        with MetricsContext('delete'):
            store.delete(session_token)
        
        # Emit audit event
        emitter.emit_logout(
            user_id=identity.user_id,
            tenant_id=tenant_id
        )
    
    except Exception as e:
        emitter.emit_store_error(tenant_id, 'delete', str(e))
        raise


def rotate(session_token: SessionToken, tenant_id: str) -> SessionToken:
    """Rotate session with compliance audit."""
    try:
        # Fetch old session
        with MetricsContext('read'):
            old_session = store.read(session_token)
        
        # Create new session
        new_identity = old_session.identity.with_rotated_timestamp()
        
        # Write new, delete old
        with MetricsContext('write'):
            new_token = store.write(new_identity)
        with MetricsContext('delete'):
            store.delete(session_token)
        
        # Emit audit event
        emitter.emit_session_rotate(
            user_id=new_identity.user_id,
            tenant_id=tenant_id,
            policy_version=new_identity.policy_version
        )
        
        return new_token
    
    except Exception as e:
        emitter.emit_store_error(tenant_id, 'rotate', str(e))
        raise
```

---

## Compliance Evidence Export

### File: `src/audit_export.py` (new)

```python
import json
from typing import List, Optional
from datetime import datetime, timezone, timedelta
from src.audit_schemas import AuthAuditEvent

class AuditEventStore:
    """In-memory or persistent store for audit events (for export/compliance)."""
    
    def __init__(self, backend='memory'):
        self.backend = backend
        self.events: List[AuthAuditEvent] = []
    
    def store_event(self, event: AuthAuditEvent):
        """Store event for later export."""
        self.events.append(event)
    
    def export_events(
        self,
        tenant_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> str:
        """Export events as JSONL (JSON Lines) for compliance audit."""
        if start_time is None:
            start_time = datetime.now(timezone.utc) - timedelta(days=365)
        if end_time is None:
            end_time = datetime.now(timezone.utc)
        
        filtered = [
            e for e in self.events
            if e.tenant_id == tenant_id
            and datetime.fromisoformat(e.timestamp) >= start_time
            and datetime.fromisoformat(e.timestamp) <= end_time
        ]
        
        # Export as JSONL (one JSON per line)
        lines = [e.to_json() for e in filtered]
        return '\n'.join(lines)
    
    def export_events_csv(
        self,
        tenant_id: str,
        start_time: Optional[datetime] = None,
        end_time: Optional[datetime] = None
    ) -> str:
        """Export events as CSV for spreadsheet/compliance review."""
        import csv
        from io import StringIO
        
        if start_time is None:
            start_time = datetime.now(timezone.utc) - timedelta(days=365)
        if end_time is None:
            end_time = datetime.now(timezone.utc)
        
        filtered = [
            e for e in self.events
            if e.tenant_id == tenant_id
            and datetime.fromisoformat(e.timestamp) >= start_time
            and datetime.fromisoformat(e.timestamp) <= end_time
        ]
        
        output = StringIO()
        writer = csv.DictWriter(output, fieldnames=[
            'timestamp', 'event_type', 'user_id', 'tenant_id', 'action', 'result', 'policy_version', 'error_reason'
        ])
        writer.writeheader()
        
        for event in filtered:
            writer.writerow({
                'timestamp': event.timestamp,
                'event_type': event.event_type,
                'user_id': event.user_id or '',
                'tenant_id': event.tenant_id,
                'action': event.action,
                'result': event.result,
                'policy_version': event.policy_version or '',
                'error_reason': event.error_reason or ''
            })
        
        return output.getvalue()


# Global export store
audit_store = AuditEventStore()
```

---

## Testing Compliance Evidence

### File: `tests/test_auth_compliance_evidence.py` (new)

```python
import pytest
from src.audit_schemas import AuthAuditEvent, AuthEventType, validate_auth_event_schema
from src.audit_logger import emitter
from src.audit_export import audit_store
from datetime import datetime, timezone
from unittest.mock import patch

class TestAuthComplianceEvidence:
    """Verify compliance audit events are emitted and exported correctly."""
    
    def test_login_success_event_emitted(self):
        """Verify login success emits properly formatted audit event."""
        event = emitter.emit_login_success(
            user_id='user-123',
            tenant_id='tenant-1',
            policy_version='v1.0'
        )
        
        # Validate schema
        assert validate_auth_event_schema(event)
        assert event.event_type == AuthEventType.LOGIN_SUCCESS.value
        assert event.user_id == 'user-123'
        assert event.tenant_id == 'tenant-1'
        assert event.result == 'success'
        assert event.policy_version == 'v1.0'
        assert event.error_reason is None
    
    def test_login_failure_event_emitted(self):
        """Verify login failure emits properly formatted audit event (no user_id)."""
        event = emitter.emit_login_failure(
            tenant_id='tenant-1',
            reason='invalid_credentials'
        )
        
        assert validate_auth_event_schema(event)
        assert event.event_type == AuthEventType.LOGIN_FAILURE.value
        assert event.user_id is None  # Not authenticated
        assert event.tenant_id == 'tenant-1'
        assert event.result == 'validation_error'
        assert event.error_reason == 'invalid_credentials'
    
    def test_session_rotate_event_emitted(self):
        """Verify session rotation emits audit event."""
        event = emitter.emit_session_rotate(
            user_id='user-123',
            tenant_id='tenant-1',
            policy_version='v1.0'
        )
        
        assert validate_auth_event_schema(event)
        assert event.event_type == AuthEventType.SESSION_ROTATE.value
        assert event.action == 'rotate'
        assert event.result == 'success'
    
    def test_store_error_event_emitted(self):
        """Verify session store errors are recorded in audit trail."""
        event = emitter.emit_store_error(
            tenant_id='tenant-1',
            operation='write',
            error_msg='Redis connection timeout'
        )
        
        assert validate_auth_event_schema(event)
        assert event.event_type == AuthEventType.STORE_ERROR.value
        assert event.result == 'store_error'
        assert 'Redis' in event.error_reason
    
    def test_events_exportable_as_jsonl(self):
        """Verify audit events can be exported as JSONL for compliance."""
        # Emit several events
        emitter.emit_login_success('user-1', 'tenant-1', 'v1.0')
        emitter.emit_logout('user-1', 'tenant-1')
        emitter.emit_login_failure('tenant-1', 'invalid_creds')
        
        # Export
        jsonl = audit_store.export_events('tenant-1')
        
        lines = jsonl.strip().split('\n')
        assert len(lines) >= 3
        
        # Validate each line is valid JSON
        for line in lines:
            obj = json.loads(line)
            assert 'timestamp' in obj
            assert 'event_type' in obj
            assert 'tenant_id' in obj
    
    def test_events_exportable_as_csv(self):
        """Verify audit events can be exported as CSV for spreadsheet review."""
        emitter.emit_login_success('user-1', 'tenant-1', 'v1.0')
        emitter.emit_logout('user-1', 'tenant-1')
        
        csv = audit_store.export_events_csv('tenant-1')
        
        lines = csv.strip().split('\n')
        assert len(lines) >= 3  # header + 2 events
        
        # Validate CSV format
        assert 'timestamp,event_type,user_id' in lines[0]  # header
    
    def test_events_filtered_by_tenant(self):
        """Verify export respects tenant isolation."""
        emitter.emit_login_success('user-1', 'tenant-1', 'v1.0')
        emitter.emit_login_success('user-2', 'tenant-2', 'v1.0')
        
        # Export only tenant-1
        jsonl_t1 = audit_store.export_events('tenant-1')
        jsonl_t2 = audit_store.export_events('tenant-2')
        
        lines_t1 = jsonl_t1.strip().split('\n')
        lines_t2 = jsonl_t2.strip().split('\n')
        
        # Ensure no cross-tenant leakage
        for line in lines_t1:
            obj = json.loads(line)
            assert obj['tenant_id'] == 'tenant-1'
        
        for line in lines_t2:
            obj = json.loads(line)
            assert obj['tenant_id'] == 'tenant-2'
    
    def test_events_immutable_once_emitted(self):
        """Verify audit events cannot be modified after emission."""
        # Events are stored as immutable dataclasses
        event = emitter.emit_login_success('user-1', 'tenant-1', 'v1.0')
        
        # Attempt to modify should raise
        with pytest.raises(AttributeError):  # dataclass is frozen
            event.user_id = 'user-2'
```

---

## Checklist: Apply to saraise-auth

- [ ] Create `src/audit_schemas.py` with AuthAuditEvent and validation.
- [ ] Create `src/audit_logger.py` with AuditEventEmitter.
- [ ] Create `src/audit_export.py` with audit export (JSONL/CSV).
- [ ] Integrate audit emission into `src/auth_service.py` (login, logout, rotate).
- [ ] Create `tests/test_auth_compliance_evidence.py` with full test coverage.
- [ ] Run `pytest tests/test_auth_compliance_evidence.py -v` and verify all pass.
- [ ] Verify events are emitted in logs (structured JSON audit format).
- [ ] Merge PR with required status checks passing.

---

## Pattern: Apply to Other Services

**saraise-runtime** compliance evidence should emit:
- policy_decision events (policy_version, decision_reason, module, jit_grant_id, sod_conflict)
- request outcome events

**saraise-policy-engine** compliance evidence should emit:
- evaluation events (bundle_version, decision, rule_hit, stale_reason, jit_check, sod_check)

**saraise-control-plane** compliance evidence should emit:
- tenant lifecycle events (create, suspend, delete, policy_bump)
- shard assignment events

Use the same pattern: schema definitions, emitter class, tests, export functions.
