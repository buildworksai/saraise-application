"""
Django management command to seed default users for development.

Creates:
- admin@saraise.com / admin@134 - Platform Owner
- operator@saraise.com / admin@134 - Platform Operator
- admin@buildworks.ai / admin@134 - Tenant Admin
- user@buildworks.ai / admin@134 - Tenant User

This command is idempotent - it will not create duplicate users.
All passwords are set to 'admin@134' for developer ease.
"""

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand
from django.db import transaction

from src.core.user_models import UserProfile

User = get_user_model()

# Common password for all users (developer ease)
COMMON_PASSWORD = "admin@134"


class Command(BaseCommand):
    help = "Seed default users for development (platform and tenant users)"

    def add_arguments(self, parser):
        parser.add_argument(
            "--force",
            action="store_true",
            help="Force recreate users even if they exist",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        force = options.get("force", False)

        self.stdout.write(self.style.SUCCESS("🌱 Seeding default users..."))

        # Clean up orphaned profiles (profiles referencing non-existent users)
        self._cleanup_orphaned_profiles()

        # ===== Platform Users =====

        # Platform Owner
        platform_owner_email = "admin@saraise.com"
        platform_owner_user, created = self._create_or_update_user(
            email=platform_owner_email,
            password=COMMON_PASSWORD,
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
            password=COMMON_PASSWORD,
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

        # Ensure a real Tenant exists (Tenant Management module)
        tenant_id = None
        tenant_slug = "buildworks"
        try:
            from src.modules.tenant_management.models import Tenant  # type: ignore

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
            tenant_id = str(tenant_obj.id)  # Ensure string format
            if tenant_created:
                self.stdout.write(
                    self.style.SUCCESS(f"✅ Created default tenant: {tenant_obj.name} ({tenant_obj.slug})")
                )
            else:
                self.stdout.write(
                    self.style.WARNING(f"ℹ️  Default tenant already exists: {tenant_obj.name} ({tenant_obj.slug})")
                )
        except Exception as e:
            # Keep seeding users functional even if tenant module isn't available for some reason
            self.stdout.write(self.style.ERROR(f"⚠️  Could not create default tenant (Tenant Management): {e}"))
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
                    password=COMMON_PASSWORD,
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

    def _create_or_update_user(
        self,
        email: str,
        password: str,
        username: str,
        is_staff: bool,
        is_superuser: bool,
        platform_role: str = None,
        tenant_id: str = None,
        tenant_role: str = None,
        force: bool = False,
    ):
        """Create or update a user with profile."""
        try:
            # Get user and refresh from database to ensure it's not stale
            user = User.objects.get(email=email)
            # Refresh user from database to ensure it exists
            user.refresh_from_db()
            created = False

            if force:
                # Update existing user
                user.username = username
                user.is_staff = is_staff
                user.is_superuser = is_superuser
                user.set_password(password)
                user.save()

            # Get or create user profile (handle race conditions and duplicates gracefully)
            # Filter by primary key (user_id) directly to avoid issues with orphaned users
            try:
                # Since user is the primary key, filter by pk directly
                profile = UserProfile.objects.get(pk=user.pk)
            except UserProfile.DoesNotExist:
                profile = None
            except UserProfile.MultipleObjectsReturned:
                # Handle duplicates - keep first, delete rest (shouldn't happen with pk, but be safe)
                profiles = UserProfile.objects.filter(pk=user.pk)
                profile = profiles.first()
                for dup in profiles[1:]:
                    dup.delete()

            # Verify profile's user exists (handle orphaned profiles)
            if profile is not None:
                try:
                    # Verify the user referenced by the profile actually exists
                    if not User.objects.filter(pk=profile.user_id).exists():
                        # Orphaned profile - delete it
                        profile.delete()
                        profile = None
                except Exception:
                    # If we can't verify, delete to be safe
                    profile.delete()
                    profile = None

            if profile is None:
                # Verify user still exists before creating profile
                if not User.objects.filter(pk=user.pk).exists():
                    # User was deleted - refresh from database
                    user = User.objects.get(email=email)
                # Check if profile exists by pk (might be orphaned)
                # Delete any orphaned profile first
                try:
                    orphaned = UserProfile.objects.get(pk=user.pk)
                    # If we got here, profile exists - verify user exists
                    if not User.objects.filter(pk=user.pk).exists():
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
                profile = UserProfile.objects.get(pk=user.pk)
            except UserProfile.DoesNotExist:
                profile = None
            except UserProfile.MultipleObjectsReturned:
                # Handle duplicates - keep first, delete rest (shouldn't happen with pk, but be safe)
                profiles = UserProfile.objects.filter(pk=user.pk)
                profile = profiles.first()
                for dup in profiles[1:]:
                    dup.delete()

            # Verify profile's user exists (handle orphaned profiles)
            if profile is not None:
                try:
                    # Verify the user referenced by the profile actually exists
                    if not User.objects.filter(pk=profile.user_id).exists():
                        # Orphaned profile - delete it
                        profile.delete()
                        profile = None
                except Exception:
                    # If we can't verify, delete to be safe
                    profile.delete()
                    profile = None

            if profile is None:
                # Verify user still exists before creating profile
                if not User.objects.filter(pk=user.pk).exists():
                    # User was deleted - this shouldn't happen for new users, but handle it
                    raise ValueError(f"User {user.email} (id={user.pk}) does not exist in database")
                # Check if profile exists by pk (might be orphaned)
                # Delete any orphaned profile first
                try:
                    orphaned = UserProfile.objects.get(pk=user.pk)
                    # If we got here, profile exists - verify user exists
                    if not User.objects.filter(pk=user.pk).exists():
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
                        UserProfile.objects.filter(pk=profile.pk).delete()
                self.stdout.write(self.style.WARNING(f"🧹 Cleaned up {orphaned_count} orphaned user profile(s)"))
        except Exception as e:
            # Don't fail the entire command if cleanup fails
            self.stdout.write(self.style.ERROR(f"⚠️  Warning: Could not clean up orphaned profiles: {e}"))
