"""Append-only correction evidence for attendance facts."""

from __future__ import annotations

from decimal import Decimal
from uuid import uuid4

import pytest
from django.core.exceptions import ValidationError as DjangoValidationError

from ..models import Attendance, AttendanceRevision
from ..serializers import AttendanceDetailSerializer
from ..services import AttendanceService
from .factories import AttendanceFactory

pytestmark = pytest.mark.django_db


def test_attendance_corrections_create_reconstructable_immutable_revisions() -> None:
    tenant_id = uuid4()
    attendance = AttendanceFactory(
        tenant_id=tenant_id,
        hours_worked=Decimal("8.00"),
        notes="Original evidence",
    )

    effective_attendance = AttendanceService.update_attendance(
        tenant_id,
        attendance.id,
        changes={
            "hours_worked": Decimal("7.50"),
            "notes": "First correction",
            "correction_reason": "Payroll evidence reconciliation",
        },
        actor_id="attendance-auditor",
        correlation_id="attendance-correlation-1",
    )
    assert effective_attendance.hours_worked == Decimal("7.50")
    assert effective_attendance.notes == "First correction"
    attendance.refresh_from_db()
    assert attendance.hours_worked == Decimal("8.00")
    assert attendance.notes == "Original evidence"

    first_revision = AttendanceRevision.objects.for_tenant(tenant_id).get(
        attendance=attendance,
        revision=1,
    )
    assert first_revision.before_values["hours_worked"] == "8.00"
    assert first_revision.before_values["notes"] == "Original evidence"
    assert first_revision.after_values["hours_worked"] == "7.50"
    assert first_revision.after_values["notes"] == "First correction"
    assert first_revision.reason == "Payroll evidence reconciliation"
    assert first_revision.actor_id == "attendance-auditor"
    assert first_revision.correlation_id == "attendance-correlation-1"

    second_effective_attendance = AttendanceService.update_attendance(
        tenant_id,
        attendance.id,
        changes={
            "hours_worked": Decimal("7.75"),
            "notes": "Second correction",
            "correction_reason": "Final approval",
        },
        actor_id="attendance-approver",
        correlation_id="attendance-correlation-2",
    )
    assert second_effective_attendance.hours_worked == Decimal("7.75")
    assert second_effective_attendance.notes == "Second correction"
    attendance.refresh_from_db()
    assert attendance.hours_worked == Decimal("8.00")
    assert attendance.notes == "Original evidence"
    second_revision = AttendanceRevision.objects.for_tenant(tenant_id).get(
        attendance=attendance,
        revision=2,
    )
    assert second_revision.before_values == first_revision.after_values
    assert second_revision.after_values["hours_worked"] == "7.75"
    assert second_revision.after_values["notes"] == "Second correction"
    assert second_revision.reason == "Final approval"
    assert second_revision.actor_id == "attendance-approver"
    assert second_revision.correlation_id == "attendance-correlation-2"
    representation = AttendanceDetailSerializer(attendance).data
    assert representation["hours_worked"] == "7.75"
    assert representation["notes"] == "Second correction"

    first_revision.reason = "tampered"
    with pytest.raises(DjangoValidationError, match="immutable"):
        first_revision.save()
    with pytest.raises(DjangoValidationError, match="immutable"):
        first_revision.delete()
    first_revision.refresh_from_db()
    assert first_revision.reason == "Payroll evidence reconciliation"


def test_attendance_revision_queries_are_tenant_isolated_and_soft_archive_preserves_evidence() -> None:
    owner_tenant = uuid4()
    foreign_tenant = uuid4()
    attendance = AttendanceFactory(tenant_id=owner_tenant)

    AttendanceService.update_attendance(
        owner_tenant,
        attendance.id,
        changes={"notes": "Audited correction", "correction_reason": "Verified source document"},
        actor_id="attendance-auditor",
        correlation_id="attendance-isolation-correlation",
    )

    assert AttendanceRevision.objects.for_tenant(owner_tenant).filter(attendance=attendance).count() == 1
    assert not AttendanceRevision.objects.for_tenant(foreign_tenant).filter(attendance=attendance).exists()

    AttendanceService.delete_attendance(
        owner_tenant,
        attendance.id,
        actor_id="attendance-auditor",
        correlation_id="attendance-delete-correlation",
    )
    assert not Attendance.objects.for_tenant(owner_tenant).filter(pk=attendance.pk).exists()
    archived = Attendance.all_objects.for_tenant(owner_tenant).get(pk=attendance.pk)
    assert archived.deleted_at is not None
    assert archived.deleted_by == "attendance-auditor"
    revision = AttendanceRevision.objects.for_tenant(owner_tenant).get(attendance=archived)
    assert revision.before_values["notes"] == ""
    assert revision.after_values["notes"] == "Audited correction"
