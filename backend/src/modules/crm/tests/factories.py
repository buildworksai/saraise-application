"""Deterministic tenant-safe factories shared by CRM contract tests."""

import uuid
from datetime import timedelta
from decimal import Decimal

import factory
from django.utils import timezone

from ..models import Account, Activity, Contact, Lead, Opportunity


class CRMFactory(factory.django.DjangoModelFactory):
    tenant_id = factory.LazyFunction(uuid.uuid4)
    created_by = factory.Sequence(lambda value: f"crm-test-actor-{value}")
    updated_by = factory.SelfAttribute("created_by")

    class Meta:
        abstract = True


class LeadFactory(CRMFactory):
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    email = factory.Sequence(lambda value: f"lead-{value}@example.test")
    company = factory.Faker("company")

    class Meta:
        model = Lead


class AccountFactory(CRMFactory):
    name = factory.Sequence(lambda value: f"Account {value}")

    class Meta:
        model = Account


class ContactFactory(CRMFactory):
    account = factory.SubFactory(AccountFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    account_id = factory.SelfAttribute("account.id")
    first_name = factory.Faker("first_name")
    last_name = factory.Faker("last_name")
    email = factory.Sequence(lambda value: f"contact-{value}@example.test")

    class Meta:
        model = Contact
        exclude = ("account",)


class OpportunityFactory(CRMFactory):
    account = factory.SubFactory(AccountFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    account_id = factory.SelfAttribute("account.id")
    name = factory.Sequence(lambda value: f"Opportunity {value}")
    amount = Decimal("1000.00")
    close_date = factory.LazyFunction(lambda: timezone.localdate() + timedelta(days=30))

    class Meta:
        model = Opportunity
        exclude = ("account",)


class ActivityFactory(CRMFactory):
    related = factory.SubFactory(LeadFactory, tenant_id=factory.SelfAttribute("..tenant_id"))
    related_to_type = "Lead"
    related_to_id = factory.SelfAttribute("related.id")
    activity_type = "call"
    subject = factory.Sequence(lambda value: f"Activity {value}")

    class Meta:
        model = Activity
        exclude = ("related",)
