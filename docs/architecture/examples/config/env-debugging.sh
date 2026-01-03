# ✅ APPROVED: Debugging Commands Reference
# Reference: docs/architecture/operational-runbooks.md § 7 (Troubleshooting)

# CRITICAL: Debugging commands for development use only
# NO sensitive data should be logged in debugging output
# See docs/architecture/operational-runbooks.md § 7

# Check environment variables
printenv | grep -E "(POSTGRES|REDIS|SESSION)"

# Validate Python configuration
python -c "from src.config.settings import settings; print(settings.model_dump())"

# Test frontend configuration
npm run validate:config

# Check Docker environment
docker exec -it container_name printenv

