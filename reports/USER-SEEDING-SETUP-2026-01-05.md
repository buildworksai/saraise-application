# User Seeding Setup — Default Development Users

**Date:** January 5, 2026  
**Status:** ✅ COMPLETE

---

## Summary

Created automatic user seeding system that creates default development users on every backend container startup/restart/rebuild.

---

## Default Users Created

### Platform Owner
- **Email:** `admin@saraise.com`
- **Password:** `admin@134`
- **Role:** Platform Owner (`platform_owner`)
- **Tenant:** None (platform-level user)
- **Permissions:** Full platform access, superuser

### Tenant Admin
- **Email:** `admin@buildworks.ai`
- **Password:** `admin@134`
- **Role:** Tenant Admin (`tenant_admin`)
- **Tenant:** Auto-generated UUID (created per seed)
- **Permissions:** Full tenant access

---

## Implementation

### UserProfile Model

Created `UserProfile` model to extend Django's default User model with:
- `tenant_id` - Tenant association (null for platform users)
- `platform_role` - Platform-level role (platform_owner, platform_operator)
- `tenant_role` - Tenant-level role (tenant_admin, tenant_user)

**Location:** `backend/src/core/user_models.py`

### Seeder Command

Created Django management command `seed_default_users`:
- **Location:** `backend/src/core/management/commands/seed_default_users.py`
- **Idempotent:** Won't create duplicate users (use `--force` to update)
- **Automatic:** Runs on every container startup

**Usage:**
```bash
# Manual execution
python manage.py seed_default_users

# Force update existing users
python manage.py seed_default_users --force
```

### Docker Integration

Updated `docker-compose.dev.yml` to automatically run seeder:
```yaml
command: >
  sh -c "
    pip install -r requirements.txt &&
    python manage.py migrate &&
    python manage.py seed_default_users &&
    python manage.py runserver 0.0.0.0:8000
  "
```

**Runs automatically on:**
- Container build
- Container rebuild
- Container restart
- Container start

---

## Database Schema

### UserProfile Table
```sql
CREATE TABLE user_profiles (
    user_id INTEGER PRIMARY KEY REFERENCES auth_user(id),
    tenant_id VARCHAR(36) NULL,
    platform_role VARCHAR(50) NULL,
    tenant_role VARCHAR(50) NULL,
    created_at TIMESTAMP,
    updated_at TIMESTAMP
);

CREATE INDEX idx_user_profiles_tenant_id ON user_profiles(tenant_id);
CREATE INDEX idx_user_profiles_platform_role ON user_profiles(platform_role);
CREATE INDEX idx_user_profiles_tenant_role ON user_profiles(tenant_role);
```

---

## Verification

### Check Users
```bash
# Via Django shell
docker exec saraise-backend python manage.py shell
>>> from django.contrib.auth import get_user_model
>>> from src.core.user_models import UserProfile
>>> User = get_user_model()
>>> u1 = User.objects.get(email='admin@saraise.com')
>>> print(u1.profile.platform_role)  # platform_owner
>>> u2 = User.objects.get(email='admin@buildworks.ai')
>>> print(u2.profile.tenant_role)  # tenant_admin
>>> print(u2.profile.tenant_id)  # UUID
```

### Test Login
```bash
# Test platform owner login
curl -X POST http://localhost:18000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@saraise.com", "password": "admin@134"}'

# Test tenant admin login
curl -X POST http://localhost:18000/api/v1/auth/login/ \
  -H "Content-Type: application/json" \
  -d '{"email": "admin@buildworks.ai", "password": "admin@134"}'
```

---

## Files Created/Modified

### Created
- `backend/src/core/user_models.py` - UserProfile model
- `backend/src/core/apps.py` - Core app configuration
- `backend/src/core/management/__init__.py` - Management package
- `backend/src/core/management/commands/__init__.py` - Commands package
- `backend/src/core/management/commands/seed_default_users.py` - Seeder command

### Modified
- `backend/saraise_backend/settings.py` - Added `src.core` to INSTALLED_APPS
- `docker-compose.dev.yml` - Added seeder to startup command

---

## Migration

Run migrations to create UserProfile table:
```bash
docker exec saraise-backend python manage.py makemigrations core
docker exec saraise-backend python manage.py migrate
```

---

## Usage in Code

### Access User Profile
```python
from django.contrib.auth import get_user_model
from src.core.user_models import UserProfile

User = get_user_model()
user = User.objects.get(email='admin@saraise.com')

# Access profile
profile = user.profile
print(profile.platform_role)  # platform_owner
print(profile.tenant_id)  # None for platform users
```

### Filter by Tenant
```python
# Get all users for a tenant
tenant_users = UserProfile.objects.filter(tenant_id='tenant-uuid')
users = [profile.user for profile in tenant_users]
```

### Check Roles
```python
# Check platform role
if user.profile.platform_role == 'platform_owner':
    # Platform owner logic

# Check tenant role
if user.profile.tenant_role == 'tenant_admin':
    # Tenant admin logic
```

---

## Security Notes

⚠️ **Development Only:** These default credentials are for development/testing only.

**Production Requirements:**
- Remove or disable seeder in production
- Use environment variables for credentials
- Implement proper user provisioning workflow
- Use strong, unique passwords
- Enable MFA for admin accounts

---

## Troubleshooting

### Users Not Created
```bash
# Check if seeder ran
docker logs saraise-backend | grep "Seeding default users"

# Run manually
docker exec saraise-backend python manage.py seed_default_users
```

### Profile Not Found
```bash
# Ensure migrations ran
docker exec saraise-backend python manage.py migrate

# Check if profile exists
docker exec saraise-backend python manage.py shell -c "from src.core.user_models import UserProfile; print(UserProfile.objects.count())"
```

### Force Update Users
```bash
# Update existing users
docker exec saraise-backend python manage.py seed_default_users --force
```

---

**Status:** ✅ COMPLETE

Default users are automatically created on every backend container startup. Developers can immediately login and test the application.

---

**Last Updated:** January 5, 2026

