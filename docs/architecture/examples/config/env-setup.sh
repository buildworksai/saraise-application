# ✅ APPROVED: Environment Setup Process
# Reference: docs/architecture/security-model.md § 5 (Secrets Management)
#            docs/architecture/operational-runbooks.md § 1 (Setup)

# CRITICAL: Never commit actual .env files - only commit .example files
# See docs/architecture/security-model.md § 5

# Step 1: Create Environment Files
# Copy example files to create actual environment files
cp .env.example .env
cp .env.development.example .env.development
cp .env.production.example .env.production
cp frontend/.env.local.example frontend/.env.local

# Step 2: Configure Environment Variables
# Update .env with your local configuration
# Database
POSTGRES_CONNECTION_STRING=postgresql://postgres:postgres@localhost:25432/saraise
REDIS_URL=redis://localhost:26379

# Session Authentication
SESSION_SECRET_KEY=your-session-secret-key-generate-a-strong-one
SESSION_TIMEOUT=7200
COOKIE_DOMAIN=localhost

# Step 3: Validate Configuration
# Run environment validation
python -c "from src.config.validation import validate_environment; validate_environment()"

# Test frontend configuration
npm run validate:config

# Step 4: Clean Up Backup Files
# Remove any backup files
rm -f .env.backup .env.backup.before_fix frontend/.env.local.backup

