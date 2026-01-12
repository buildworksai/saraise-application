from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from django.contrib.auth import get_user_model
from src.core.licensing.models import License, LicenseStatus

User = get_user_model()


class LicenseViewSetTests(APITestCase):
    def setUp(self):
        # Create a user
        self.user = User.objects.create_user(username="testuser", password="password")
        self.admin = User.objects.create_superuser(username="admin", password="password", email="admin@example.com")

    def test_status_endpoint_authenticated(self):
        """
        Ensure status endpoint is accessible to authenticated users.
        """
        self.client.force_authenticate(user=self.user)
        url = reverse("licensing-status")
        # Since we use a DefaultRouter with basename='licensing', the detail=False action is 'licensing-status'
        # Wait, if basename='licensing', standard actions are licensing-list.
        # But this is a ViewSet (not ModelViewSet) with custom action 'status'.
        # The URL name is typically {basename}-{action_name}.

        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertIn("organization_name", response.data)
        self.assertIn("tier", response.data)

    def test_status_endpoint_unauthenticated(self):
        """
        Ensure status endpoint is protected.
        """
        url = reverse("licensing-status")
        response = self.client.get(url)
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_activate_endpoint_admin_only(self):
        """
        Ensure activation is admin-only.
        """
        self.client.force_authenticate(user=self.user)
        url = reverse("licensing-activate")

        data = {"license_key": "valid_key"}
        response = self.client.post(url, data)
        # Should be forbidden for non-admin
        self.assertEqual(response.status_code, status.HTTP_403_FORBIDDEN)

    def test_activate_endpoint_admin_success(self):
        """
        Ensure activation works for admin.
        """
        self.client.force_authenticate(user=self.admin)
        url = reverse("licensing-activate")

        data = {"license_key": "new_license_key"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, status.HTTP_200_OK)

        # Verify DB update
        license_obj = License.objects.first()
        self.assertIsNotNone(license_obj)
        self.assertEqual(license_obj.license_key, "new_license_key")
        self.assertEqual(license_obj.status, LicenseStatus.ACTIVE)
