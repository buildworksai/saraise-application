"""
User profile models for storing tenant_id and roles.

Since Django's default User model doesn't include tenant_id,
we use a UserProfile model to extend user information.
"""

from django.db import models
from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver
from django.core.exceptions import ValidationError


User = get_user_model()


class UserProfile(models.Model):
    """User profile extending Django User with tenant_id and roles."""
    
    user = models.OneToOneField(
        User,
        on_delete=models.CASCADE,
        related_name='profile',
        primary_key=True,
    )
    tenant_id = models.CharField(
        max_length=36,
        null=True,
        blank=True,
        db_index=True,
        help_text='Tenant ID for tenant-scoped users (null for platform users)',
    )
    platform_role = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        db_index=True,
        choices=[
            ('platform_owner', 'Platform Owner'),
            ('platform_operator', 'Platform Operator'),
        ],
        help_text='Platform-level role',
    )
    tenant_role = models.CharField(
        max_length=50,
        null=True,
        blank=True,
        db_index=True,
        choices=[
            ('tenant_admin', 'Tenant Admin'),
            ('tenant_user', 'Tenant User'),
        ],
        help_text='Tenant-level role',
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'user_profiles'
        indexes = [
            models.Index(fields=['tenant_id']),
            models.Index(fields=['platform_role']),
            models.Index(fields=['tenant_role']),
            models.Index(fields=['tenant_id', 'tenant_role']),
        ]

    def __str__(self):
        role_info = []
        if self.platform_role:
            role_info.append(f'Platform: {self.platform_role}')
        if self.tenant_role:
            role_info.append(f'Tenant: {self.tenant_role}')
        roles = ', '.join(role_info) if role_info else 'No roles'
        return f'{self.user.email} ({roles})'

    def clean(self):
        """
        Guardrails (CRITICAL):
        - Platform users MUST NOT be tenant-scoped (tenant_id must be null).
        - Tenant-scoped users MUST reference a real tenant (no orphan tenant_id).
        - Platform role and tenant role MUST NOT be combined (identity is either platform or tenant scoped).
        """
        errors = {}

        # Mutually exclusive roles (strict)
        if self.platform_role and self.tenant_role:
            errors["tenant_role"] = "Tenant role is not allowed for platform-scoped users."
            errors["platform_role"] = "Platform role is not allowed for tenant-scoped users."

        # Platform users cannot have tenant_id
        if self.platform_role and self.tenant_id:
            errors["tenant_id"] = "tenant_id must be null for platform-scoped users."

        # Tenant role requires tenant_id
        if self.tenant_role and not self.tenant_id:
            errors["tenant_id"] = "tenant_id is required for tenant-scoped users."

        # If tenant_id is present, it must reference an existing Tenant row
        if self.tenant_id:
            try:
                from src.modules.tenant_management.models import Tenant  # local import to avoid hard dependency at import time
                if not Tenant.objects.filter(id=self.tenant_id).exists():
                    errors["tenant_id"] = f"tenant_id '{self.tenant_id}' does not reference an existing tenant."
            except Exception as e:
                errors["tenant_id"] = f"Unable to validate tenant_id against tenant registry: {e}"

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        # Enforce invariants on every write.
        self.full_clean()
        return super().save(*args, **kwargs)


@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    """Create UserProfile when User is created."""
    if created:
        UserProfile.objects.get_or_create(user=instance)

