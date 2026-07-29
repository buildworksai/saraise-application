"""Django management command to seed default development users."""

import os
import re
import uuid
from datetime import timedelta
from pathlib import Path

import yaml
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from src.core.user_models import UserProfile

User = get_user_model()
PASSWORD_ENV = "SARAISE_SEED_DEFAULT_PASSWORD"  # pragma: allowlist secret
PERMISSION_CODE_RE = re.compile(
    r"^(?P<module>[a-z][a-z0-9_-]{0,99})\.(?P<resource>[a-z][a-z0-9_-]{0,99}):(?P<action>[a-z][a-z0-9_-]{0,49})$"
)
ACCESS_RESOURCE_RE = re.compile(r"['\"]([a-z][a-z0-9_-]*(?:[.:][a-z][a-z0-9_-]*)*)['\"]")
STANDARD_VIEWSET_ACTIONS = (
    "list",
    "retrieve",
    "create",
    "update",
    "partial_update",
    "destroy",
    "preview",
    "versions",
    "rollback",
    "import_configuration",
    "export_configuration",
    "health",
)
LOCAL_DEVELOPMENT_QUOTA_RESOURCES = (
    "active-schedules",
    "backup-jobs-per-period",
    "backup-recovery.archive",
    "backup-recovery.health",
    "backup-recovery.job",
    "backup-recovery.read",
    "backup-recovery.retention",
    "backup-recovery.schedule",
    "backup-recovery.storage_target",
    "integrity-verifications",
    "provider-probes",
)


class Command(BaseCommand):
    help = "Seed default users for development (platform and tenant users)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force recreate users even if they exist",
        )
        parser.add_argument(
            "--password",
            default=None,
            help=f"Password for seeded users. Defaults to {PASSWORD_ENV}.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        force = options.get("force", False)
        common_password = options.get("password") or os.environ.get(PASSWORD_ENV)
        if not common_password:
            raise CommandError(f"Provide --password or set {PASSWORD_ENV}; seeded users must not use a source default.")

        self.stdout.write(self.style.SUCCESS("🌱 Seeding default users..."))

        # Clean up orphaned profiles (profiles referencing non-existent users)
        self._cleanup_orphaned_profiles()

        # ===== Platform Users =====

        # Platform Owner
        platform_owner_email = "admin@saraise.com"
        platform_owner_user, created = self._create_or_update_user(
            email=platform_owner_email,
            password=common_password,
            username=platform_owner_email,
            is_staff=True,
            is_superuser=True,
            platform_role="platform_owner",
            tenant_id=None,
            tenant_role=None,
            force=force,
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f"✅ Created platform owner: {platform_owner_email}"))
        else:
            self.stdout.write(self.style.WARNING(f"ℹ️  Platform owner already exists: {platform_owner_email}"))

        # Platform Operator
        platform_operator_email = "operator@saraise.com"
        platform_operator_user, created = self._create_or_update_user(
            email=platform_operator_email,
            password=common_password,
            username=platform_operator_email,
            is_staff=True,
            is_superuser=False,
            platform_role="platform_operator",
            tenant_id=None,
            tenant_role=None,
            force=force,
        )

        if created:
            self.stdout.write(self.style.SUCCESS(f"✅ Created platform operator: {platform_operator_email}"))
        else:
            self.stdout.write(self.style.WARNING(f"ℹ️  Platform operator already exists: {platform_operator_email}"))

        # ===== Tenant Users =====

        # Ensure real organization/tenant records exist for the configured runtime.
        #
        # UserProfile.clean is mode-aware: development/self-hosted identities are
        # bound to licensing.Organization, while SaaS identities are bound to
        # tenant_management.Tenant. Keep both records available for local module
        # data, but bind seeded users to the authority required by the guardrail.
        tenant_id = None
        tenant_slug = "buildworks"
        try:
            from src.core.licensing.models import License, LicenseStatus, Organization
            from src.modules.tenant_management.models import Tenant  # type: ignore

            organization, organization_created = Organization.objects.get_or_create(
                domain="buildworks.ai",
                defaults={"name": "BuildWorks AI"},
            )
            License.objects.get_or_create(
                organization=organization,
                defaults={
                    "status": LicenseStatus.ACTIVE,
                    "core_tier": "enterprise",
                    "max_companies": -1,
                    "max_users": -1,
                },
            )
            if organization_created:
                self.stdout.write(
                    self.style.SUCCESS(f"✅ Created default organization: {organization.name} ({organization.id})")
                )
            else:
                self.stdout.write(self.style.WARNING(f"ℹ️  Default organization already exists: {organization.name}"))

            # Idempotent: ensure stable dev tenant exists
            tenant_obj, tenant_created = Tenant.objects.get_or_create(
                slug=tenant_slug,
                defaults={
                    "name": "BuildWorks AI",
                    "subdomain": tenant_slug,
                    "status": Tenant.TenantStatus.ACTIVE,
                    "primary_contact_name": "BuildWorks Admin",
                    "primary_contact_email": "admin@buildworks.ai",
                    "billing_email": "admin@buildworks.ai",
                    "technical_email": "admin@buildworks.ai",
                    "timezone": "UTC",
                    "default_language": "en",
                    "default_currency": "USD",
                    "max_users": 50,
                    "max_storage_gb": 10,
                    "max_api_calls_per_day": 10000,
                    "created_by": None,
                },
            )
            mode = getattr(settings, "SARAISE_MODE", "development")
            tenant_id = str(organization.id if mode in {"development", "self-hosted"} else tenant_obj.id)
            if tenant_created:
                self.stdout.write(
                    self.style.SUCCESS(f"✅ Created default tenant: {tenant_obj.name} ({tenant_obj.slug})")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"ℹ️  Default tenant already exists: {tenant_obj.name} ({tenant_obj.slug})")
                )
            self.stdout.write(self.style.SUCCESS(f"✅ Binding tenant users to {mode} identity scope: {tenant_id}"))
        except Exception as e:
            # Keep seeding users functional even if tenant module isn't available for some reason
            self.stdout.write(self.style.ERROR(f"⚠️  Could not create default identity scope: {e}"))
            self.stdout.write(self.style.WARNING("⚠️  Tenant users will not be created without a valid tenant."))

        if tenant_id:
            # Define tenant users to create
            # Note: UserProfile.tenant_role only supports 'tenant_admin' and 'tenant_user'
            # Other functional roles (developer, operator, billing_manager, auditor, viewer)
            # are managed through the Role model in security_access_control module
            tenant_users = [
                {
                    "email": "admin@buildworks.ai",
                    "role": "tenant_admin",
                    "description": "Tenant Admin",
                },
                {
                    "email": "user@buildworks.ai",
                    "role": "tenant_user",
                    "description": "Tenant User",
                },
                {
                    "email": "developer@buildworks.ai",
                    "role": "tenant_user",  # Functional roles managed via Role model
                    "description": "Tenant User (Developer)",
                },
                {
                    "email": "operator@buildworks.ai",
                    "role": "tenant_user",  # Functional roles managed via Role model
                    "description": "Tenant User (Operator)",
                },
                {
                    "email": "billing@buildworks.ai",
                    "role": "tenant_user",  # Functional roles managed via Role model
                    "description": "Tenant User (Billing Manager)",
                },
                {
                    "email": "auditor@buildworks.ai",
                    "role": "tenant_user",  # Functional roles managed via Role model
                    "description": "Tenant User (Auditor)",
                },
                {
                    "email": "viewer@buildworks.ai",
                    "role": "tenant_user",  # Functional roles managed via Role model
                    "description": "Tenant User (Viewer)",
                },
            ]

            for user_config in tenant_users:
                user_email = user_config["email"]
                user_role = user_config["role"]
                user_description = user_config["description"]

                user, created = self._create_or_update_user(
                    email=user_email,
                    password=common_password,
                    username=user_email,
                    is_staff=False,
                    is_superuser=False,
                    platform_role=None,
                    tenant_id=tenant_id,
                    tenant_role=user_role,
                    force=force,
                )

                if created:
                    self.stdout.write(
                        self.style.SUCCESS(f"✅ Created {user_description}: {user_email} (tenant: {tenant_id})")
                    )
                else:
                    self.stdout.write(self.style.WARNING(f"ℹ️  {user_description} already exists: {user_email}"))

            if getattr(settings, "SARAISE_MODE", "development") in {"development", "self-hosted"}:
                local_users = list(
                    User.objects.filter(  # nosemgrep: semgrep.tenant-id-required-in-queries
                        email__in=[str(user_config["email"]) for user_config in tenant_users]
                    )
                )
                self._bootstrap_local_access(tenant_id, local_users)
                self._bootstrap_local_procurement_configuration(tenant_id, local_users)

        # Summary
        self.stdout.write(self.style.SUCCESS("\n✅ Default users seeded successfully!"))
        self.stdout.write("\n📋 Created Users:")
        self.stdout.write("\n   Platform Users:")
        self.stdout.write(f"     - {platform_owner_email} (Platform Owner)")
        self.stdout.write(f"     - {platform_operator_email} (Platform Operator)")
        if tenant_id:
            self.stdout.write("\n   Tenant Users (buildworks.ai):")
            self.stdout.write("     - admin@buildworks.ai (Tenant Admin)")
            self.stdout.write("     - user@buildworks.ai (Tenant User)")
            self.stdout.write("     - developer@buildworks.ai (Tenant User)")
            self.stdout.write("     - operator@buildworks.ai (Tenant User)")
            self.stdout.write("     - billing@buildworks.ai (Tenant User)")
            self.stdout.write("     - auditor@buildworks.ai (Tenant User)")
            self.stdout.write("     - viewer@buildworks.ai (Tenant User)")
            self.stdout.write("\n   Note: Functional roles (developer, operator, billing, auditor, viewer)")
            self.stdout.write("         are managed via Role model in security_access_control module.")

    def _bootstrap_local_access(self, tenant_id: str, tenant_users) -> None:
        """Create explicit local access state for every seeded tenant UAT identity."""

        try:
            from src.core.access.entitlements import Entitlement, Quota
            from src.modules.security_access_control.models import (
                Permission,
                PermissionSet,
                PermissionSetPermission,
                UserPermissionSet,
            )
            from src.modules.security_access_control.services import ConfigurationService
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"⚠️  Could not bootstrap local access state: {exc}"))
            return

        tenant_uuid = uuid.UUID(str(tenant_id))
        users = tuple(tenant_users)
        actor_email = users[0].email if users else "local-access"
        actor_id = uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:seed:{actor_email}")
        correlation_id = "seed-default-users-local-access"
        ConfigurationService.current(tenant_uuid, actor_id=actor_id, correlation_id=correlation_id)

        permissions, resources, capabilities = self._collect_local_access_contracts()
        created_permissions = []
        for code in sorted(permissions):
            match = PERMISSION_CODE_RE.fullmatch(code)
            if match is None:
                continue
            item, _ = Permission.objects.get_or_create(
                **match.groupdict(),
                defaults={
                    "name": code,
                    "description": "Seeded local development permission",
                    "risk_level": Permission.RiskLevel.MEDIUM,
                },
            )
            created_permissions.append(item)

        permission_set, _ = PermissionSet.objects.get_or_create(
            tenant_id=tenant_uuid,
            name="Local development administrator",
            defaults={
                "description": "Explicit seeded grant for local end-to-end UAT.",
                "default_duration_days": 365,
                "is_active": True,
                "created_by": actor_id,
                "updated_by": actor_id,
            },
        )
        if not permission_set.is_active or permission_set.is_deleted:
            permission_set.is_active = True
            permission_set.is_deleted = False
            permission_set.deleted_at = None
            permission_set.updated_by = actor_id
            permission_set.save(update_fields=("is_active", "is_deleted", "deleted_at", "updated_by", "updated_at"))

        existing_members = set(
            PermissionSetPermission.objects.for_tenant(tenant_uuid)
            .filter(permission_set=permission_set, removed_at__isnull=True)
            .values_list("permission_id", flat=True)
        )
        for permission in created_permissions:
            if permission.id not in existing_members:
                PermissionSetPermission.objects.create(
                    tenant_id=tenant_uuid,
                    permission_set=permission_set,
                    permission=permission,
                    added_by=actor_id,
                )

        expiry = timezone.now() + timedelta(days=365)
        for user in users:
            grant = (
                UserPermissionSet.objects.for_tenant(tenant_uuid)
                .filter(user=user, permission_set=permission_set, revoked_at__isnull=True)
                .first()
            )
            if grant is None:
                UserPermissionSet.objects.create(
                    tenant_id=tenant_uuid,
                    user=user,
                    permission_set=permission_set,
                    expires_at=expiry,
                    granted_by=actor_id,
                    reason="Seeded local development UAT access",
                )
            elif grant.expires_at <= expiry:
                grant.expires_at = expiry
                grant.reason = "Seeded local development UAT access"
                grant.save(update_fields=("expires_at", "reason", "updated_at"))

        for capability in sorted(capabilities | permissions):
            Entitlement.objects.update_or_create(
                tenant_id=tenant_uuid,
                capability=capability,
                defaults={"enabled": True, "starts_at": None, "expires_at": None},
            )
        for resource in sorted(resources | permissions):
            Quota.objects.update_or_create(
                tenant_id=tenant_uuid,
                resource=resource,
                defaults={"limit": 1_000_000, "remaining": 1_000_000, "reset_at": None},
            )

        self.stdout.write(
            self.style.SUCCESS(
                "✅ Bootstrapped local access: "
                f"{len(created_permissions)} permissions, {len(capabilities | permissions)} entitlements, "
                f"{len(resources | permissions)} quotas"
            )
        )

    def _bootstrap_local_procurement_configuration(self, tenant_id: str, tenant_users) -> None:
        """Ensure local purchase-management settings have an active tenant policy."""

        try:
            from src.modules.purchase_management.models import (
                ConfigurationEnvironment,
                ConfigurationStatus,
                ProcurementConfiguration,
            )
        except Exception as exc:
            self.stdout.write(self.style.WARNING(f"⚠️  Could not bootstrap procurement configuration: {exc}"))
            return

        tenant_uuid = uuid.UUID(str(tenant_id))
        users = tuple(tenant_users)
        actor_email = users[0].email if users else "local-procurement-configuration"
        actor_id = uuid.uuid5(uuid.NAMESPACE_URL, f"saraise:seed:{actor_email}")
        now = timezone.now()
        defaults = {
            "default_currency": "USD",
            "default_payment_terms": "Net 30",
            "supplier_code_prefix": "SUP",
            "requisition_prefix": "PR",
            "rfq_prefix": "RFQ",
            "po_prefix": "PO",
            "receipt_prefix": "GRN",
            "approval_rules": [],
            "receipt_tolerance_percent": "5.00",
            "minimum_rfq_suppliers": 3,
            "quote_scoring_weights": {"price": 55, "delivery": 20, "quality": 15, "service": 10},
            "inventory_integration_enabled": False,
            "accounting_integration_enabled": False,
            "supplier_delivery_enabled": False,
            "rollout": {"roles": [], "cohorts": [], "percentage": 100},
            "created_by": actor_id,
            "updated_by": actor_id,
            "activated_at": now,
            "activated_by": actor_id,
        }
        created = 0
        for environment in ConfigurationEnvironment.values:
            active_exists = (
                ProcurementConfiguration.objects.for_tenant(tenant_uuid)
                .filter(
                    environment=environment,
                    status=ConfigurationStatus.ACTIVE,
                )
                .exists()
            )
            if active_exists:
                continue
            next_version = (
                ProcurementConfiguration.objects.for_tenant(tenant_uuid)
                .filter(environment=environment)
                .order_by("-version")
                .values_list("version", flat=True)
                .first()
                or 0
            ) + 1
            ProcurementConfiguration.objects.create(
                tenant_id=tenant_uuid,
                environment=environment,
                version=next_version,
                status=ConfigurationStatus.ACTIVE,
                **defaults,
            )
            created += 1
        if created:
            self.stdout.write(
                self.style.SUCCESS(f"✅ Bootstrapped local procurement configuration: {created} active environments")
            )

    def _collect_local_access_contracts(self) -> tuple[set[str], set[str], set[str]]:
        permissions: set[str] = set()
        resources: set[str] = set()
        capabilities: set[str] = set()
        backend_root = Path(settings.BASE_DIR) / "src" / "modules"

        for manifest in backend_root.glob("*/manifest.yaml"):
            module_name = manifest.parent.name
            capabilities.add(module_name)
            capabilities.add(f"module.{module_name}")
            try:
                document = yaml.safe_load(manifest.read_text(encoding="utf-8")) or {}
            except (OSError, yaml.YAMLError):
                continue
            self._collect_manifest_access_values(document, permissions, resources, capabilities)

        for permissions_file in backend_root.glob("*/*.py"):
            if permissions_file.parent.name in {"migrations", "tests"} or permissions_file.name.startswith("test_"):
                continue
            try:
                text = permissions_file.read_text(encoding="utf-8")
            except OSError:
                continue
            for token in ACCESS_RESOURCE_RE.findall(text):
                if PERMISSION_CODE_RE.fullmatch(token):
                    permissions.add(token)
                    capabilities.add(token.split(".", maxsplit=1)[0])
                elif token.startswith("module."):
                    capabilities.add(token)
                elif "." in token:
                    resources.add(token)
                    capabilities.add(token.split(".", maxsplit=1)[0])
                elif "-" in token:
                    resources.add(token)
                    if token.endswith("-recovery") or "_" in token:
                        capabilities.add(token)

        module_capabilities = {capability for capability in capabilities if "." not in capability}
        resources.update(LOCAL_DEVELOPMENT_QUOTA_RESOURCES)
        for capability in tuple(capabilities):
            for action in ("get", "post", "put", "patch", "delete", "list", "retrieve", "create", "update"):
                resources.add(f"{capability}.{action}")
                resources.add(f"{capability}.api.{action}")
        for module_name in module_capabilities:
            for action in STANDARD_VIEWSET_ACTIONS:
                resources.add(f"{module_name}.api.{action}")
        for permission in tuple(permissions):
            resources.add(f"{permission}:read")

        return permissions, resources, capabilities

    def _collect_manifest_access_values(
        self,
        value: object,
        permissions: set[str],
        resources: set[str],
        capabilities: set[str],
        *,
        key: str | None = None,
    ) -> None:
        if isinstance(value, dict):
            for child_key, child_value in value.items():
                self._collect_manifest_access_values(
                    child_value,
                    permissions,
                    resources,
                    capabilities,
                    key=str(child_key),
                )
            return
        if isinstance(value, list):
            for item in value:
                self._collect_manifest_access_values(item, permissions, resources, capabilities, key=key)
            return
        if not isinstance(value, str):
            return

        if key in {"permission", "permissions"} and PERMISSION_CODE_RE.fullmatch(value):
            permissions.add(value)
            capabilities.add(value.split(".", maxsplit=1)[0])
        elif key in {"entitlement", "entitlements"}:
            capabilities.add(value)
        elif key in {"quota_resource", "quota_resources"}:
            resources.add(value)

    def _create_or_update_user(
        self,
        email: str,
        password: str,
        username: str,
        is_staff: bool,
        is_superuser: bool,
        platform_role: str | None = None,
        tenant_id: str | None = None,
        tenant_role: str | None = None,
        force: bool = False,
    ):
        """Create or update a user with profile."""
        try:
            # Get user and refresh from database to ensure it's not stale
            user = User.objects.get(email=email)  # nosemgrep: semgrep.tenant-id-required-in-queries
            # Refresh user from database to ensure it exists
            user.refresh_from_db()
            created = False

            if force:
                # Update existing user
                user.username = username
                user.is_staff = is_staff
                user.is_superuser = is_superuser
                validate_password(password, user=user)
                user.set_password(password)
                user.save()

            # Get or create user profile (handle race conditions and duplicates gracefully)
            # Filter by primary key (user_id) directly to avoid issues with orphaned users
            try:
                # Since user is the primary key, filter by pk directly
                profile = UserProfile.objects.get(pk=user.pk)  # nosemgrep: semgrep.tenant-id-required-in-queries
            except UserProfile.DoesNotExist:
                profile = None
            except UserProfile.MultipleObjectsReturned:
                # Handle duplicates - keep first, delete rest (shouldn't happen with pk, but be safe)
                profiles = UserProfile.objects.filter(pk=user.pk)  # nosemgrep: semgrep.tenant-id-required-in-queries
                profile = profiles.first()
                for dup in profiles[1:]:
                    dup.delete()

            # Verify profile's user exists (handle orphaned profiles)
            if profile is not None:
                try:
                    # Verify the user referenced by the profile actually exists
                    if not User.objects.filter(  # nosemgrep: semgrep.tenant-id-required-in-queries
                        pk=profile.user_id
                    ).exists():
                        # Orphaned profile - delete it
                        profile.delete()
                        profile = None
                except Exception:
                    # If we can't verify, delete to be safe
                    if profile is not None:
                        profile.delete()
                    profile = None

            if profile is None:
                # Verify user still exists before creating profile
                if not User.objects.filter(pk=user.pk).exists():  # nosemgrep: semgrep.tenant-id-required-in-queries
                    # User was deleted - refresh from database
                    user = User.objects.get(email=email)  # nosemgrep: semgrep.tenant-id-required-in-queries
                # Check if profile exists by pk (might be orphaned)
                # Delete any orphaned profile first
                try:
                    orphaned = UserProfile.objects.get(pk=user.pk)  # nosemgrep: semgrep.tenant-id-required-in-queries
                    # If we got here, profile exists - verify user exists
                    if not User.objects.filter(pk=user.pk).exists():  # nosemgrep: semgrep.tenant-id-required-in-queries
                        # Orphaned profile - delete it
                        orphaned.delete()
                    else:
                        # Profile exists and user exists - use it
                        profile = orphaned
                except UserProfile.DoesNotExist:
                    pass  # Profile doesn't exist, we'll create it

                # Create profile if it doesn't exist
                if profile is None:
                    profile = UserProfile.objects.create(
                        user=user,
                        tenant_id=tenant_id,
                        platform_role=platform_role,
                        tenant_role=tenant_role,
                    )

            # Always reconcile provided values (idempotent, and enforces guardrails)
            if tenant_id is not None or platform_role or tenant_role or force:
                # Update tenant_id explicitly when provided (including None for platform users)
                profile.tenant_id = tenant_id
                profile.platform_role = platform_role
                profile.tenant_role = tenant_role
                # Try to save, but handle orphaned profile errors
                try:
                    profile.save()
                except Exception as e:
                    # If save fails due to orphaned user, delete and recreate
                    if "does not exist" in str(e).lower():
                        profile.delete()
                        profile = UserProfile.objects.create(
                            user=user,
                            tenant_id=tenant_id,
                            platform_role=platform_role,
                            tenant_role=tenant_role,
                        )
                    else:
                        # Re-raise if it's a different error
                        raise

            return user, created

        except User.DoesNotExist:
            # Create new user
            user = User.objects.create_user(
                username=username,
                email=email,
                password=password,
                is_staff=is_staff,
                is_superuser=is_superuser,
            )

            # Create user profile
            # Get or create user profile (handle race conditions and duplicates gracefully)
            # Filter by primary key (user_id) directly to avoid issues with orphaned users
            try:
                # Since user is the primary key, filter by pk directly
                profile = UserProfile.objects.get(pk=user.pk)  # nosemgrep: semgrep.tenant-id-required-in-queries
            except UserProfile.DoesNotExist:
                profile = None
            except UserProfile.MultipleObjectsReturned:
                # Handle duplicates - keep first, delete rest (shouldn't happen with pk, but be safe)
                profiles = UserProfile.objects.filter(pk=user.pk)  # nosemgrep: semgrep.tenant-id-required-in-queries
                profile = profiles.first()
                for dup in profiles[1:]:
                    dup.delete()

            # Verify profile's user exists (handle orphaned profiles)
            if profile is not None:
                try:
                    # Verify the user referenced by the profile actually exists
                    if not User.objects.filter(  # nosemgrep: semgrep.tenant-id-required-in-queries
                        pk=profile.user_id
                    ).exists():
                        # Orphaned profile - delete it
                        profile.delete()
                        profile = None
                except Exception:
                    # If we can't verify, delete to be safe
                    if profile is not None:
                        profile.delete()
                    profile = None

            if profile is None:
                # Verify user still exists before creating profile
                if not User.objects.filter(pk=user.pk).exists():  # nosemgrep: semgrep.tenant-id-required-in-queries
                    # User was deleted - this shouldn't happen for new users, but handle it
                    raise ValueError(f"User {user.email} (id={user.pk}) does not exist in database")
                # Check if profile exists by pk (might be orphaned)
                # Delete any orphaned profile first
                try:
                    orphaned = UserProfile.objects.get(pk=user.pk)  # nosemgrep: semgrep.tenant-id-required-in-queries
                    # If we got here, profile exists - verify user exists
                    if not User.objects.filter(pk=user.pk).exists():  # nosemgrep: semgrep.tenant-id-required-in-queries
                        # Orphaned profile - delete it
                        orphaned.delete()
                    else:
                        # Profile exists and user exists - use it
                        profile = orphaned
                except UserProfile.DoesNotExist:
                    pass  # Profile doesn't exist, we'll create it

                # Create profile if it doesn't exist
                if profile is None:
                    profile = UserProfile.objects.create(
                        user=user,
                        tenant_id=tenant_id,
                        platform_role=platform_role,
                        tenant_role=tenant_role,
                    )

            # Update profile deterministically (enforces guardrails)
            profile.tenant_id = tenant_id
            profile.platform_role = platform_role
            profile.tenant_role = tenant_role
            # Try to save, but handle orphaned profile errors
            try:
                profile.save()
            except Exception as e:
                # If save fails due to orphaned user, delete and recreate
                if "does not exist" in str(e).lower():
                    profile.delete()
                    profile = UserProfile.objects.create(
                        user=user,
                        tenant_id=tenant_id,
                        platform_role=platform_role,
                        tenant_role=tenant_role,
                    )
                else:
                    # Re-raise if it's a different error
                    raise

            return user, True

    def _cleanup_orphaned_profiles(self):
        """Remove any UserProfile records that reference non-existent users."""
        try:
            # Get all user IDs that exist
            existing_user_ids = set(User.objects.values_list("id", flat=True))

            # Find profiles that reference non-existent users
            # Since user is the primary key, profile.pk is the user_id
            orphaned_profiles = []
            for profile in UserProfile.objects.all():
                # profile.pk is the user_id (OneToOneField with primary_key=True)
                if profile.pk not in existing_user_ids:
                    orphaned_profiles.append(profile)

            # Delete orphaned profiles
            orphaned_count = len(orphaned_profiles)
            if orphaned_count > 0:
                for profile in orphaned_profiles:
                    try:
                        profile.delete()
                    except Exception:
                        # If delete fails, try to delete by pk directly
                        UserProfile.objects.filter(  # nosemgrep: semgrep.tenant-id-required-in-queries
                            pk=profile.pk
                        ).delete()
                self.stdout.write(self.style.WARNING(f"🧹 Cleaned up {orphaned_count} orphaned user profile(s)"))
        except Exception as e:
            # Don't fail the entire command if cleanup fails
            self.stdout.write(self.style.ERROR(f"⚠️  Warning: Could not clean up orphaned profiles: {e}"))
