"""
Django management command to seed default users for development.

Creates:
- admin@saraise.com / admin@134 - Platform Owner
- admin@buildworks.ai / admin@134 - Tenant Admin

This command is idempotent - it will not create duplicate users.
"""

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from django.db import transaction
from src.core.user_models import UserProfile

User = get_user_model()


class Command(BaseCommand):
    help = 'Seed default users for development (platform owner and tenant admin)'

    def add_arguments(self, parser):
        parser.add_argument(
            '--force',
            action='store_true',
            help='Force recreate users even if they exist',
        )

    @transaction.atomic
    def handle(self, *args, **options):
        force = options.get('force', False)
        
        self.stdout.write(self.style.SUCCESS('🌱 Seeding default users...'))

        # Platform Owner User
        platform_email = 'admin@saraise.com'
        platform_password = 'admin@134'
        
        platform_user, created = self._create_or_update_user(
            email=platform_email,
            password=platform_password,
            username=platform_email,
            is_staff=True,
            is_superuser=True,
            platform_role='platform_owner',
            tenant_id=None,  # Platform users don't belong to a tenant
            force=force,
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Created platform owner: {platform_email}'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f'ℹ️  Platform owner already exists: {platform_email}'
                )
            )

        # Tenant Admin User
        tenant_email = 'admin@buildworks.ai'
        tenant_password = 'admin@134'

        # Ensure a real Tenant exists (Tenant Management module)
        tenant_id = None
        try:
            from src.modules.tenant_management.models import Tenant  # type: ignore

            # Idempotent: ensure stable dev tenant exists
            tenant_obj, tenant_created = Tenant.objects.get_or_create(
                slug="buildworks",
                defaults={
                    "name": "BuildWorks AI",
                    "subdomain": "buildworks",
                    "status": Tenant.TenantStatus.ACTIVE,
                    "primary_contact_name": "BuildWorks Admin",
                    "primary_contact_email": tenant_email,
                    "billing_email": tenant_email,
                    "technical_email": tenant_email,
                    "timezone": "UTC",
                    "default_language": "en",
                    "default_currency": "USD",
                    "max_users": 50,
                    "max_storage_gb": 10,
                    "max_api_calls_per_day": 10000,
                    "created_by": None,
                },
            )
            tenant_id = tenant_obj.id
            if tenant_created:
                self.stdout.write(self.style.SUCCESS(f'✅ Created default tenant: {tenant_obj.name} ({tenant_obj.slug})'))
            else:
                self.stdout.write(self.style.WARNING(f'ℹ️  Default tenant already exists: {tenant_obj.name} ({tenant_obj.slug})'))
        except Exception as e:
            # Keep seeding users functional even if tenant module isn't available for some reason
            self.stdout.write(self.style.ERROR(f'⚠️  Could not create default tenant (Tenant Management): {e}'))
        
        tenant_user, created = self._create_or_update_user(
            email=tenant_email,
            password=tenant_password,
            username=tenant_email,
            is_staff=False,
            is_superuser=False,
            platform_role=None,
            tenant_id=tenant_id,
            tenant_role='tenant_admin',
            force=force,
        )
        
        if created:
            self.stdout.write(
                self.style.SUCCESS(
                    f'✅ Created tenant admin: {tenant_email} (tenant: {tenant_id})'
                )
            )
        else:
            self.stdout.write(
                self.style.WARNING(
                    f'ℹ️  Tenant admin already exists: {tenant_email}'
                )
            )

        self.stdout.write(self.style.SUCCESS('\n✅ Default users seeded successfully!'))
        self.stdout.write('\n📋 Login Credentials:')
        self.stdout.write(f'   Platform Owner: {platform_email} / {platform_password}')
        self.stdout.write(f'   Tenant Admin: {tenant_email} / {tenant_password}')

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
            user = User.objects.get(email=email)
            created = False
            
            if force:
                # Update existing user
                user.username = username
                user.is_staff = is_staff
                user.is_superuser = is_superuser
                user.set_password(password)
                user.save()
            
            # Get or create user profile
            profile, profile_created = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'tenant_id': tenant_id,
                    'platform_role': platform_role,
                    'tenant_role': tenant_role,
                }
            )
            
            # Always reconcile provided values (idempotent, and enforces guardrails)
            if tenant_id is not None or platform_role or tenant_role or force:
                # Update tenant_id explicitly when provided (including None for platform users)
                profile.tenant_id = tenant_id
                profile.platform_role = platform_role
                profile.tenant_role = tenant_role
                profile.save()
            
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
            profile, _ = UserProfile.objects.get_or_create(
                user=user,
                defaults={
                    'tenant_id': tenant_id,
                    'platform_role': platform_role,
                    'tenant_role': tenant_role,
                }
            )
            
            # Update profile deterministically (enforces guardrails)
            profile.tenant_id = tenant_id
            profile.platform_role = platform_role
            profile.tenant_role = tenant_role
            profile.save()
            
            return user, True

