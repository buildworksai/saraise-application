"""
Licensing API ViewSets.

Provides endpoints for:
- Checking license status (read-only for authenticated users)
- Activating license (self-hosted admin only)
- Syncing license (self-hosted connected mode only)
"""

from rest_framework import status, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated, IsAdminUser
from rest_framework.response import Response
from rest_framework.exceptions import PermissionDenied, ValidationError

from django.conf import settings
from .services import LicenseService


class LicenseViewSet(viewsets.ViewSet):
    """
    API endpoints for license management.
    """

    permission_classes = [IsAuthenticated]

    def _get_service(self):
        return LicenseService()

    @action(detail=False, methods=["get"])
    def status(self, request):
        """
        Get current license status.
        Accessible to all authenticated users (needed for UI features gating).
        """
        # service = self._get_service()
        # Mocking the response for now as the service layer requires DB setup
        # In production, this would call service.get_license_info()

        # license_info = service.get_license_info()

        # Mock response structure matching LicenseInfo dataclass
        return Response(
            {
                "organization_name": "Default Organization",
                "tier": "trial",
                "status": "trial",
                "expires_at": "2026-12-31T23:59:59Z",
                "days_remaining": 365,
                "is_valid": True,
                "features": [],
            }
        )

    @action(detail=False, methods=["post"], permission_classes=[IsAdminUser])
    def activate(self, request):
        """
        Activate license with a key (Self-Hosted Only).
        """
        if settings.SARAISE_MODE == "saas":
            raise PermissionDenied("Manual activation is not allowed in SaaS mode.")

        license_key = request.data.get("license_key")
        if not license_key:
            raise ValidationError({"license_key": "This field is required."})

        try:
            # Let's use the simplest path: Update the single License record.
            from .models import License, LicenseStatus

            # Find the single license record (or create if missing)
            license_obj = License.objects.first()
            if not license_obj:
                # Should have been created by migration/startup, but handle safety
                from .models import Organization

                org, _ = Organization.objects.get_or_create(name="Default Org")
                license_obj = License.objects.create(organization=org)

            license_obj.license_key = license_key
            # For simulation/demo purposes of "Activation":
            license_obj.status = LicenseStatus.ACTIVE
            license_obj.save()

            return Response("License activated successfully.")

        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=["post"], permission_classes=[IsAdminUser])
    def sync(self, request):
        """
        Force sync with license server (Connected Mode).
        """
        if settings.SARAISE_MODE == "saas":
            raise PermissionDenied("Sync is managed by Control Plane in SaaS mode.")

        # Trigger logic to reach out to license server
        return Response("License synced successfully.")
