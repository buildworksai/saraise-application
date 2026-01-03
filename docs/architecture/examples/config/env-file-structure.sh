# ✅ APPROVED: Environment File Structure
# Reference: docs/architecture/security-model.md § 5 (Secrets Management)

# CRITICAL: Never commit actual .env files to version control
# Only commit .example files for documentation
# See docs/architecture/security-model.md § 5

# ✅ APPROVED (Commit these files)
# Root Directory:
# ├── .env.example           # Backend template (committed)
# └── .gitignore with .env   # Prevents .env commits

# Frontend Directory:
# └── .env.local.example     # Frontend template (committed)

# ❌ FORBIDDEN (NEVER commit these)
# ├── .env                   # Main backend config (gitignored)
# ├── .env.production        # Production config (gitignored)
# ├── .env.development       # Development config (gitignored)
# ├── .env.test              # Test config (gitignored)
# ├── frontend/.env.local    # Frontend config (gitignored)
# ├── .env.backup            # Backup files
# ├── .env.*.backup          # Any backup files
# └── .env.local.backup      # Frontend backup files

