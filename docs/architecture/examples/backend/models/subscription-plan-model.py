# ---------------------------------------------------------------------------------------------
#  Copyright (c) BuildWorks.AI. All rights reserved.
#  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
# ---------------------------------------------------------------------------------------------

# ✅ REQUIRED: Subscription plan model structure
# backend/src/modules/billing/models.py
from django.db.models import String, BooleanField(), DateTime, Numeric, IntegerField(), JSON
from django.db import models, relationship
from src.models.base import Base
from decimal import Decimal
from typing import Optional, Dict, Any, List
from datetime import datetime
from django.db.models import F

class SubscriptionPlan(Base):
    """Subscription plan model"""
    class Meta:
        db_table = "subscription_plans"

    id: str] = models.String, primary_key=True)
    name: str] = models.CharField(max_length=255), nullable=False, unique=True, index=True)
    description: Optional[str]] = models.CharField(max_length=1000))
    tier: str] = models.CharField(max_length=50), nullable=False, index=True)  # free, basic, professional, enterprise
    price: Decimal] = models.Numeric(10, 2), nullable=False)
    currency: str] = models.CharField(max_length=3), default="USD")
    billing_cycle_days: int] = models.IntegerField(), default=30)  # 30 for monthly, 365 for annual
    features: Dict[str, Any]] = models.JSON)  # Feature flags and limits
    max_users: int] = models.IntegerField(), default=10)
    max_storage_gb: int] = models.IntegerField(), default=10)
    max_api_calls_per_month: int] = models.IntegerField(), default=10000)
    is_active: bool] = models.BooleanField(), default=True, index=True)
    is_public: bool] = models.BooleanField(), default=True, index=True)
    created_at: datetime] = models.DateTimeField(timezone=True), server_default=func.now())
    updated_at: datetime] = models.DateTimeField(timezone=True), onupdate=func.now())

    # Relationships
    subscriptions: List["Subscription"]] = # Django ORM relationships via ForeignKey"Subscription", back_populates="plan")

