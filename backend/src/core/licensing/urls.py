from rest_framework.routers import DefaultRouter
from .api import LicenseViewSet

router = DefaultRouter()
router.register(r"licensing", LicenseViewSet, basename="licensing")

urlpatterns = router.urls
