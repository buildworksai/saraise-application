# Phase 2 Security Hardening: Sample Implementation — saraise-auth

This file provides reference implementations for security hardening tests in **saraise-auth**. Other services should follow similar patterns.

---

## Overview
Test session lifecycle security invariants: token tamper detection, graceful store outage handling, and input validation.

---

## Test Suite 1: Session Tamper Detection

### File: `tests/test_auth_session_tamper.py` (new)

```python
import pytest
from src.auth_service import validate_session_token, SessionError
from unittest.mock import patch

class TestSessionTamper:
    """Verify sessions reject tampering attempts."""
    
    def test_session_token_modification_rejected(self):
        """Modified session token must be rejected."""
        # Create valid session
        token = 'valid_token_abc123'
        
        # Store has valid session
        with patch('src.auth_service.store') as mock_store:
            mock_store.read.return_value = {
                'user_id': 'user-1',
                'tenant_id': 'tenant-1',
                'policy_version': 'v1.0',
                'issued_at': 1234567890
            }
            
            # Validate succeeds
            identity = validate_session_token(token)
            assert identity.user_id == 'user-1'
        
        # Tampered token (modify last 4 chars)
        tampered_token = token[:-4] + 'xxxx'
        
        # Store.read raises for tampered token
        with patch('src.auth_service.store') as mock_store:
            mock_store.read.side_effect = ValueError('Session not found or invalid')
            
            # Validation must fail
            with pytest.raises(SessionError) as exc:
                validate_session_token(tampered_token)
            
            assert 'invalid' in str(exc.value).lower()
    
    def test_session_rotation_changes_token(self):
        """Token must change after rotation."""
        original_token = 'token_original'
        
        with patch('src.auth_service.store') as mock_store:
            # Initial session
            mock_store.read.return_value = {
                'user_id': 'user-1',
                'tenant_id': 'tenant-1',
                'policy_version': 'v1.0',
                'issued_at': 1234567890
            }
            mock_store.write.return_value = 'token_rotated'
            
            from src.auth_service import rotate
            new_token = rotate(original_token, 'tenant-1')
            
            # Token must change
            assert new_token != original_token
            assert new_token == 'token_rotated'
            
            # Old token deleted
            mock_store.delete.assert_called_once_with(original_token)
    
    def test_session_signature_validation(self):
        """Session must include cryptographic signature."""
        # Token structure: {base64(payload)}.{signature}
        token = 'eyJhIjogMX0=.invalid_signature'
        
        with patch('src.auth_service.store'):
            from src.auth_service import validate_session_token
            
            with pytest.raises(SessionError) as exc:
                validate_session_token(token)
            
            assert 'signature' in str(exc.value).lower() or 'invalid' in str(exc.value).lower()
```

---

## Test Suite 2: Session Store Outage Resilience

### File: `tests/test_auth_store_outage.py` (new)

```python
import pytest
from src.auth_service import login, SessionError, SessionStoreUnavailableError
from src.observability import session_store_errors_total
from unittest.mock import patch, MagicMock

class TestSessionStoreOutage:
    """Verify auth fails closed when session store is unavailable."""
    
    def test_login_fails_when_store_unavailable(self):
        """Login must fail explicitly when store is down."""
        with patch('src.auth_service.validate_credentials') as mock_validate:
            mock_validate.return_value = {'user_id': 'user-1', 'policy_version': 'v1.0'}
            
            with patch('src.auth_service.store') as mock_store:
                # Store connection fails
                mock_store.write.side_effect = ConnectionError('Redis unreachable')
                
                # Login must raise and not succeed silently
                with pytest.raises(SessionStoreUnavailableError) as exc:
                    login('user', 'pass', 'tenant-1')
                
                assert 'unavailable' in str(exc.value).lower()
    
    def test_validate_fails_when_store_unavailable(self):
        """Token validation must fail when store is down."""
        with patch('src.auth_service.store') as mock_store:
            # Store read fails
            mock_store.read.side_effect = ConnectionError('Redis unreachable')
            
            from src.auth_service import validate_session_token
            
            with pytest.raises(SessionStoreUnavailableError):
                validate_session_token('any_token')
    
    def test_store_error_metrics_recorded(self):
        """Store errors must be recorded in metrics."""
        with patch('src.auth_service.validate_credentials') as mock_validate:
            mock_validate.return_value = {'user_id': 'user-1'}
            
            with patch('src.auth_service.store') as mock_store:
                mock_store.write.side_effect = TimeoutError('Store timeout')
                
                with pytest.raises(SessionStoreUnavailableError):
                    login('user', 'pass', 'tenant-1')
        
        # Verify error metric incremented
        # Note: This requires mocking prometheus_client or using in-memory registry
        from prometheus_client import REGISTRY
        # Assert that session_store_errors_total counter was incremented
        assert session_store_errors_total._metrics[('write',)]._value.get() > 0
    
    def test_store_latency_tracked(self):
        """Store latency must be tracked as metric."""
        import time
        
        with patch('src.auth_service.validate_credentials') as mock_validate:
            mock_validate.return_value = {'user_id': 'user-1'}
            
            with patch('src.auth_service.store') as mock_store:
                # Simulate slow store
                def slow_write(*args, **kwargs):
                    time.sleep(0.1)  # 100ms
                    return 'token'
                
                mock_store.write.side_effect = slow_write
                
                login('user', 'pass', 'tenant-1')
        
        # Verify histogram recorded latency >= 100ms
        from src.observability import session_store_latency_ms
        histogram = session_store_latency_ms.labels(operation='write')
        # Observation should include ~100ms
        assert histogram._sum._value.get() >= 100
```

---

## Test Suite 3: Input Validation & Hardening

### File: `tests/test_auth_input_validation.py` (new)

```python
import pytest
from src.auth_service import login, ValidationError

class TestAuthInputValidation:
    """Verify auth endpoints reject malformed/oversized inputs."""
    
    def test_login_rejects_empty_username(self):
        """Login must reject empty username."""
        with pytest.raises(ValidationError) as exc:
            login('', 'password', 'tenant-1')
        
        assert 'username' in str(exc.value).lower()
    
    def test_login_rejects_empty_password(self):
        """Login must reject empty password."""
        with pytest.raises(ValidationError) as exc:
            login('user', '', 'tenant-1')
        
        assert 'password' in str(exc.value).lower()
    
    def test_login_rejects_oversized_username(self):
        """Login must reject oversized username (e.g., > 255 chars)."""
        oversized_username = 'a' * 10000
        
        with pytest.raises(ValidationError) as exc:
            login(oversized_username, 'password', 'tenant-1')
        
        assert 'length' in str(exc.value).lower() or 'size' in str(exc.value).lower()
    
    def test_login_rejects_invalid_tenant_id(self):
        """Login must validate tenant_id format."""
        # Empty tenant
        with pytest.raises(ValidationError):
            login('user', 'pass', '')
        
        # Invalid format (e.g., contains special chars)
        with pytest.raises(ValidationError):
            login('user', 'pass', 'tenant@invalid')
    
    def test_login_rejects_null_bytes(self):
        """Login must reject payloads with null bytes (injection vector)."""
        with pytest.raises(ValidationError):
            login('user\x00admin', 'pass', 'tenant-1')
    
    def test_login_rejects_sql_injection_attempts(self):
        """Login must safely handle SQL-like injection attempts."""
        injection_attempts = [
            "admin' or '1'='1",
            "'; DROP TABLE users; --",
            "admin%' or %'%'='%",
        ]
        
        for payload in injection_attempts:
            with pytest.raises(ValidationError):
                login(payload, 'pass', 'tenant-1')
    
    def test_password_not_logged(self):
        """Password must never be logged (security)."""
        import logging
        from io import StringIO
        
        # Capture logs
        log_capture = StringIO()
        handler = logging.StreamHandler(log_capture)
        logger = logging.getLogger('auth')
        logger.addHandler(handler)
        
        from unittest.mock import patch
        with patch('src.auth_service.validate_credentials') as mock_validate:
            mock_validate.return_value = {'user_id': 'user-1'}
            with patch('src.auth_service.store') as mock_store:
                mock_store.write.return_value = 'token'
                
                login('user', 'my_secret_password', 'tenant-1')
        
        # Verify password not in logs
        log_output = log_capture.getvalue()
        assert 'my_secret_password' not in log_output
```

---

## Checklist: Apply to saraise-auth

- [ ] Create `tests/test_auth_session_tamper.py` with tamper detection tests.
- [ ] Create `tests/test_auth_store_outage.py` with outage resilience tests.
- [ ] Create `tests/test_auth_input_validation.py` with input validation tests.
- [ ] Run `pytest tests/test_auth_*.py -v` and verify all pass.
- [ ] Update CI to enforce these hardening tests (add to quality-guardrails).
- [ ] Merge PR with required status checks passing.

---

## Pattern: Apply Same Structure to Other Services

**saraise-runtime** hardening tests should cover:
- Policy eval guarantee (verify policy_engine invoked on every request)
- Stale policy handling (requests with old policy_version denied)
- Path traversal / module injection attempts rejected

**saraise-policy-engine** hardening tests should cover:
- Deny-by-default (missing/invalid policies → deny)
- Stale vs current bundle handling
- SoD/JIT enforcement (restricted actions denied without grant)

Use the same test organization pattern: separate files by concern (lifecycle, outage, validation), clear test names, explicit assertions.
