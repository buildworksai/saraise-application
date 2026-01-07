"""
License Service for SARAISE.

Business logic for license validation and management.

Phase 7.5: Licensing Subsystem
Reference: saraise-documentation/planning/phases/phase-7.5-licensing.md
"""

import json
import base64
import hashlib
import socket
import logging
from datetime import timedelta, datetime
from typing import Optional, Tuple
from django.conf import settings
from django.utils import timezone
import requests
from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding

from .models import License, LicenseStatus, Organization, LicenseValidationLog

logger = logging.getLogger('saraise.licensing')


class LicenseService:
    """Service for license validation and management."""
    
    TRIAL_DURATION_DAYS = 14
    GRACE_PERIOD_DAYS = 30
    LICENSE_SERVER_URL = "https://license.saraise.com"
    
    @classmethod
    def initialize_trial(cls, organization: Organization) -> License:
        """Initialize 14-day trial for new organization."""
        now = timezone.now()
        trial_ends = now + timedelta(days=cls.TRIAL_DURATION_DAYS)
        
        license = License.objects.create(
            organization=organization,
            status=LicenseStatus.TRIAL,
            core_tier='free',
            max_companies=1,
            max_users=-1,
            trial_started_at=now,
            trial_ends_at=trial_ends,
        )
        
        cls._log_validation(license, 'trial_start', True)
        return license
    
    @classmethod
    def validate_license(cls, license: License) -> Tuple[bool, str]:
        """
        Validate license based on mode.
        
        Returns:
            Tuple of (is_valid, message)
        """
        mode = getattr(settings, 'SARAISE_MODE', 'development')
        license_mode = getattr(settings, 'SARAISE_LICENSE_MODE', 'connected')
        
        # Development mode - skip validation
        if mode == 'development':
            return True, "Development mode - validation skipped"
        
        # SaaS mode - skip (handled by platform billing)
        if mode == 'saas':
            return True, "SaaS mode - handled by platform billing"
        
        # Self-hosted mode
        if mode == 'self-hosted':
            if license_mode == 'connected':
                return cls._validate_connected(license)
            else:
                return cls._validate_isolated(license)
        
        return False, f"Unknown mode: {mode}"
    
    @classmethod
    def _validate_connected(cls, license: License) -> Tuple[bool, str]:
        """Validate license via license server."""
        try:
            response = requests.post(
                f"{cls.LICENSE_SERVER_URL}/api/v1/validate",
                json={
                    'organization_id': str(license.organization_id),
                    'license_key': license.license_key,
                    'instance_id': cls._get_instance_id(),
                },
                timeout=10,
            )
            
            if response.status_code == 200:
                data = response.json()
                if data.get('valid'):
                    cls._update_from_server(license, data)
                    cls._log_validation(license, 'connected', True, server_response=data)
                    return True, "License valid"
                else:
                    cls._handle_invalid(license, data.get('error', 'unknown'))
                    cls._log_validation(
                        license, 
                        'connected', 
                        False, 
                        data.get('message', ''), 
                        data
                    )
                    return False, data.get('message', 'License invalid')
            else:
                # Server error - enter grace period if not already
                return cls._handle_server_unreachable(license)
                
        except requests.RequestException as e:
            logger.warning(f"License server request failed: {e}")
            return cls._handle_server_unreachable(license)
    
    @classmethod
    def _validate_isolated(cls, license: License) -> Tuple[bool, str]:
        """Validate offline license key."""
        if not license.license_key:
            return False, "No license key configured"
        
        try:
            # Decode and verify key
            payload, signature = cls._decode_license_key(license.license_key)
            
            # Verify signature
            if not cls._verify_signature(payload, signature):
                cls._log_validation(license, 'isolated', False, "Invalid signature")
                return False, "Invalid license key signature"
            
            # Parse payload
            data = json.loads(payload)
            
            # Verify organization
            if data.get('organization_id') != str(license.organization_id):
                cls._log_validation(license, 'isolated', False, "Organization mismatch")
                return False, "License key does not match organization"
            
            # Check expiry
            expires_at_str = data.get('expires_at', '')
            if expires_at_str:
                expires_at = datetime.fromisoformat(expires_at_str.replace('Z', '+00:00'))
                expires_at = timezone.make_aware(expires_at) if timezone.is_naive(expires_at) else expires_at
                if timezone.now() > expires_at:
                    cls._handle_expired(license)
                    cls._log_validation(license, 'isolated', False, "License expired")
                    return False, "License has expired"
                license.license_expires_at = expires_at
            
            # Update license from key data
            license.core_tier = data.get('core_tier', 'free')
            license.max_companies = data.get('core_limits', {}).get('max_companies', 1)
            license.industry_modules = data.get('industry_modules', [])
            license.status = LicenseStatus.ACTIVE
            license.last_validated_at = timezone.now()
            license.save()
            
            cls._log_validation(license, 'isolated', True)
            return True, "License valid"
            
        except Exception as e:
            logger.error(f"License validation error: {e}", exc_info=True)
            cls._log_validation(license, 'isolated', False, str(e))
            return False, f"License validation error: {e}"
    
    @classmethod
    def _handle_server_unreachable(cls, license: License) -> Tuple[bool, str]:
        """Handle case when license server is unreachable."""
        license.validation_failures += 1
        
        if license.status == LicenseStatus.ACTIVE:
            # Enter grace period
            license.status = LicenseStatus.GRACE
            license.grace_ends_at = timezone.now() + timedelta(days=cls.GRACE_PERIOD_DAYS)
            license.save()
            cls._log_validation(
                license, 
                'connected', 
                False, 
                "Server unreachable - entering grace period"
            )
            return True, (
                f"License server unreachable. "
                f"Grace period active until {license.grace_ends_at.date()}"
            )
        
        elif license.status == LicenseStatus.GRACE:
            if license.grace_ends_at and timezone.now() > license.grace_ends_at:
                # Grace period expired
                license.status = LicenseStatus.LOCKED
                license.save()
                cls._log_validation(license, 'connected', False, "Grace period expired")
                return False, (
                    "Grace period expired. "
                    "Please restore connectivity to license server."
                )
            else:
                days_left = (license.grace_ends_at - timezone.now()).days
                license.save()
                return True, f"Grace period active. {days_left} days remaining."
        
        license.save()
        return False, "License validation failed"
    
    @classmethod
    def _handle_invalid(cls, license: License, error: str) -> None:
        """Handle invalid license response."""
        if error == 'license_expired':
            cls._handle_expired(license)
        else:
            license.status = LicenseStatus.LOCKED
            license.save()
    
    @classmethod
    def _handle_expired(cls, license: License) -> None:
        """Handle expired license - soft lock."""
        license.status = LicenseStatus.EXPIRED
        license.save()
    
    @classmethod
    def _update_from_server(cls, license: License, data: dict) -> None:
        """Update license from server response."""
        license.status = LicenseStatus.ACTIVE
        license.core_tier = data.get('license', {}).get('tier', 'free')
        license.max_companies = data.get('core', {}).get('limits', {}).get('max_companies', 1)
        license.industry_modules = data.get('modules', {}).get('allowed', [])
        license.last_validated_at = timezone.now()
        license.validation_failures = 0
        license.save()
    
    @classmethod
    def _decode_license_key(cls, key: str) -> Tuple[str, bytes]:
        """Decode license key into payload and signature."""
        parts = key.split('.')
        if len(parts) != 2:
            raise ValueError("Invalid license key format")
        payload = base64.urlsafe_b64decode(parts[0] + '==').decode('utf-8')
        signature = base64.urlsafe_b64decode(parts[1] + '==')
        return payload, signature
    
    @classmethod
    def _verify_signature(cls, payload: str, signature: bytes) -> bool:
        """Verify RSA signature."""
        try:
            # TODO: Load actual public key from settings or key file
            # For now, this is a placeholder
            # In production, the public key should be stored securely
            public_key_pem = getattr(
                settings, 
                'SARAISE_LICENSE_PUBLIC_KEY', 
                None
            )
            
            if not public_key_pem:
                logger.warning("License public key not configured - signature verification skipped")
                # In development, allow unsigned keys
                if getattr(settings, 'SARAISE_MODE', 'development') == 'development':
                    return True
                return False
            
            public_key = serialization.load_pem_public_key(public_key_pem.encode())
            public_key.verify(
                signature,
                payload.encode(),
                padding.PKCS1v15(),
                hashes.SHA256()
            )
            return True
        except Exception as e:
            logger.error(f"Signature verification failed: {e}")
            return False
    
    @classmethod
    def _get_instance_id(cls) -> str:
        """Generate unique instance ID."""
        import uuid as uuid_mod
        data = f"{socket.gethostname()}-{uuid_mod.getnode()}"
        return hashlib.sha256(data.encode()).hexdigest()[:32]
    
    @classmethod
    def _log_validation(
        cls,
        license: License,
        validation_type: str,
        success: bool,
        error_message: str = '',
        server_response: dict = None
    ) -> None:
        """Log validation attempt."""
        LicenseValidationLog.objects.create(
            license=license,
            validation_type=validation_type,
            success=success,
            error_message=error_message,
            server_response=server_response,
        )


class ModuleAccessService:
    """Service for checking module access based on license."""
    
    FOUNDATION_MODULES = [
        'platform_management', 'tenant_management', 'security_access_control',
        'ai_agent_management', 'workflow_automation', 'metadata_modeling',
        'document_management', 'integration_platform', 'api_management',
        'ai_provider_configuration', 'automation_orchestration', 'document_intelligence',
        'process_mining', 'backup_disaster_recovery', 'performance_monitoring',
        'localization', 'regional_compliance', 'blockchain_traceability',
        'billing_subscriptions', 'data_migration', 'customization_framework',
        'backup_recovery',
    ]
    
    CORE_MODULES = [
        'crm', 'accounting_finance', 'sales_management', 'purchase_management',
        'inventory_management', 'human_resources', 'project_management',
        'business_intelligence', 'communication_hub', 'bank_reconciliation',
        'budget_management', 'asset_management', 'fixed_assets', 'sales_operations',
        'purchase_operations', 'compliance_risk_management', 'master_data_management',
        'multi_company', 'compliance_management', 'email_marketing', 'dms_business',
    ]
    
    @classmethod
    def can_access_module(cls, license: License, module_name: str) -> Tuple[bool, str]:
        """
        Check if license allows access to a module.
        
        Returns:
            Tuple of (can_access, reason)
        """
        # Foundation modules - always free
        if module_name in cls.FOUNDATION_MODULES:
            return True, "Foundation module - always available"
        
        # Core modules - free for single company
        if module_name in cls.CORE_MODULES:
            if license.status in [LicenseStatus.TRIAL, LicenseStatus.ACTIVE]:
                return True, "Core module - available"
            elif license.status in [LicenseStatus.EXPIRED, LicenseStatus.GRACE]:
                # Soft lock - read only
                return True, "Core module - read-only mode"
            else:
                return False, "License required for Core modules"
        
        # Industry modules - require purchase
        if license.has_module(module_name):
            return True, "Industry module - licensed"
        
        return False, f"Industry module '{module_name}' not in license"
    
    @classmethod
    def can_write_module(cls, license: License, module_name: str) -> bool:
        """Check if writes are allowed for a module."""
        # Foundation - always writable
        if module_name in cls.FOUNDATION_MODULES:
            return True
        
        # Check license status for write permission
        return license.can_write()

