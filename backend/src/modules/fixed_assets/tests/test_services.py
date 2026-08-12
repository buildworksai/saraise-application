"""Lifecycle, calculation, posting, and idempotency service coverage."""

from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from django.core.exceptions import ObjectDoesNotExist
from django.test import TestCase

from src.core.async_jobs.models import JobStatus
from src.core.async_jobs.services import JobExecutionError, execute
from src.core.state_machine import (
    IdempotencyConflictError,
    IllegalTransitionError,
    StateMachine,
    TerminalStateError,
    Transition,
    TransitionRecord,
    UnknownCommandError,
)
from src.modules.fixed_assets.integrations import (
    AccountingPostingResult,
    CapabilityUnavailable,
    DefaultAccountingAdapter,
    extension_registry,
)
from src.modules.fixed_assets.models import AssetCategory, AssetTransaction, DepreciationLine, FixedAsset
from src.modules.fixed_assets.services import (
    AssetCategoryService,
    AssetTransactionService,
    DepreciationService,
    FixedAssetService,
    FixedAssetServiceError,
    StaleVersionError,
    _add_months,
    _canonical,
    _category_accounts,
    _correlation,
    _fingerprint,
    _periods,
    _required,
    _tenant,
    _transition,
    _version,
)

ACCOUNT_FIELDS = (
    "asset_account_id",
    "accumulated_depreciation_account_id",
    "depreciation_expense_account_id",
    "impairment_loss_account_id",
    "disposal_gain_account_id",
    "disposal_loss_account_id",
)


class FakeAccounting:
    schema_version = "1.0"

    def __init__(self, *, failure: bool = False) -> None:
        self.failure = failure
        self.requests = []

    def validate_accounts(self, tenant_id: uuid.UUID, account_ids: tuple[uuid.UUID, ...]) -> None:
        if self.failure:
            raise CapabilityUnavailable("accounting unavailable")
        if len(account_ids) != 6:
            raise AssertionError("six mapped accounts required")

    def post_journal(self, request: object) -> AccountingPostingResult:
        if self.failure:
            raise CapabilityUnavailable("accounting unavailable")
        self.requests.append(request)
        return AccountingPostingResult("1.0", uuid.uuid4(), "2026-07-22T00:00:00Z")


class FixedAssetServiceTests(TestCase):
    def setUp(self) -> None:
        self.tenant = uuid.uuid4()
        self.actor = "service-tester"
        self.accounting = FakeAccounting()
        extension_registry.set_accounting_port(self.accounting)
        self.category_data = {
            "code": "it",
            "name": "Information technology",
            "default_depreciation_method": "straight_line",
            "default_useful_life_months": 12,
            **{field: uuid.uuid4() for field in ACCOUNT_FIELDS},
        }

    def tearDown(self) -> None:
        extension_registry.set_accounting_port(DefaultAccountingAdapter())

    def create_category(self, key: str = "category-1"):
        return AssetCategoryService.create_category(self.tenant, self.actor, self.category_data, key)

    def create_asset(self, *, key: str = "asset-1", cost: str = "1200.00"):
        category = AssetCategory.objects.filter(tenant_id=self.tenant, code="IT").first()
        if category is None:
            category = self.create_category(f"{key}:category")
        return FixedAssetService.create_asset(
            self.tenant,
            self.actor,
            {
                "asset_code": key,
                "asset_name": "Test asset",
                "category_id": category.id,
                "purchase_date": date(2026, 1, 1),
                "purchase_cost": Decimal(cost),
                "currency": "usd",
            },
            key,
        )

    def capitalize(self, asset, key: str = "capitalize-1"):
        return FixedAssetService.capitalize(
            self.tenant,
            asset.id,
            self.actor,
            date(2026, 1, 1),
            key,
            expected_version=asset.version,
        )

    def test_create_idempotency_and_payload_conflict(self) -> None:
        category = self.create_category()
        duplicate = self.create_category()
        self.assertEqual(duplicate.id, category.id)
        changed = dict(self.category_data, name="Different")
        with self.assertRaises(IdempotencyConflictError):
            AssetCategoryService.create_category(self.tenant, self.actor, changed, "category-1")

        asset = self.create_asset()
        duplicate_asset = FixedAssetService.create_asset(
            self.tenant,
            self.actor,
            {
                "asset_code": "asset-1",
                "asset_name": "Test asset",
                "category_id": asset.category_id,
                "purchase_date": date(2026, 1, 1),
                "purchase_cost": Decimal("1200.00"),
                "currency": "usd",
            },
            "asset-1",
        )
        self.assertEqual(duplicate_asset.id, asset.id)

    def test_draft_version_and_cross_tenant_guards(self) -> None:
        asset = self.create_asset()
        with self.assertRaises(StaleVersionError):
            FixedAssetService.update_draft(self.tenant, asset.id, self.actor, {"asset_name": "Changed"}, 999)
        with self.assertRaises(ObjectDoesNotExist):
            FixedAssetService.update_draft(uuid.uuid4(), asset.id, self.actor, {"asset_name": "Changed"}, 1)

    def test_category_and_ledger_guards_stop_cross_tenant_inactive_and_external_writes(self) -> None:
        category = self.create_category()
        asset = self.create_asset()

        with self.assertRaisesMessage(FixedAssetServiceError, "Category was not found"):
            AssetCategoryService.validate_account_mapping(uuid.uuid4(), category)

        with self.assertRaisesMessage(FixedAssetServiceError, "Draft assets require an active category"):
            AssetCategoryService.deactivate_category(self.tenant, category.id, self.actor)

        updated = AssetCategoryService.update_category(
            self.tenant,
            category.id,
            self.actor,
            {"name": "Updated category", "unknown": "ignored"},
            category.version,
        )
        self.assertEqual(updated.name, "Updated category")
        self.assertEqual(updated.version, category.version + 1)

        with self.assertRaisesMessage(FixedAssetServiceError, "Transactions can only be appended"):
            AssetTransactionService.append_transaction(tenant_id=self.tenant, idempotency_key="external")

        with self.assertRaises(ObjectDoesNotExist):
            AssetTransactionService.get_asset_history(self.tenant, uuid.uuid4())
        self.assertEqual(list(AssetTransactionService.get_asset_history(self.tenant, asset.id)), [])

    def test_capitalize_transfer_impair_and_dispose_are_idempotent(self) -> None:
        asset = self.capitalize(self.create_asset())
        self.assertEqual(asset.status, "active")
        self.assertEqual(asset.depreciation_start_date, date(2026, 1, 1))

        asset = FixedAssetService.transfer(
            self.tenant,
            asset.id,
            self.actor,
            date(2026, 2, 1),
            "HQ-2",
            "CC-2",
            "transfer-1",
        )
        self.assertEqual(asset.location, "HQ-2")
        asset = FixedAssetService.record_impairment(
            self.tenant,
            asset.id,
            self.actor,
            date(2026, 3, 1),
            Decimal("900.00"),
            "Damage",
            "impair-1",
        )
        self.assertEqual(asset.accumulated_impairment, Decimal("300.00"))
        asset = FixedAssetService.dispose(
            self.tenant,
            asset.id,
            self.actor,
            date(2026, 4, 1),
            Decimal("950.00"),
            "Sold",
            "dispose-1",
        )
        self.assertEqual(asset.status, "disposed")
        self.assertEqual(asset.disposal_gain_loss, Decimal("50.00"))
        duplicate = FixedAssetService.dispose(
            self.tenant,
            asset.id,
            self.actor,
            date(2026, 4, 1),
            Decimal("950.00"),
            "Sold",
            "dispose-1",
        )
        self.assertEqual(duplicate.id, asset.id)
        self.assertEqual(AssetTransaction.objects.filter(asset=asset).count(), 4)

    def test_lifecycle_rejects_invalid_dates_amounts_states_and_idempotency_reuse(self) -> None:
        draft = self.create_asset(key="guarded")
        with self.assertRaisesRegex(FixedAssetServiceError, "Capitalization cannot precede purchase"):
            FixedAssetService.capitalize(
                self.tenant,
                draft.id,
                self.actor,
                date(2025, 12, 31),
                "bad-cap-date",
                expected_version=draft.version,
            )
        with self.assertRaisesRegex(FixedAssetServiceError, "Depreciation cannot precede capitalization"):
            FixedAssetService.capitalize(
                self.tenant,
                draft.id,
                self.actor,
                date(2026, 1, 2),
                "bad-dep-date",
                depreciation_start_date=date(2026, 1, 1),
                expected_version=draft.version,
            )
        with self.assertRaisesRegex(FixedAssetServiceError, "Only capitalized assets can be transferred"):
            FixedAssetService.transfer(
                self.tenant, draft.id, self.actor, date(2026, 1, 1), "HQ", "CC", "draft-transfer"
            )
        with self.assertRaisesRegex(FixedAssetServiceError, "Only active assets can be impaired"):
            FixedAssetService.record_impairment(
                self.tenant, draft.id, self.actor, date(2026, 1, 1), Decimal("10.00"), "draft", "draft-impair"
            )

        active = self.capitalize(draft, "valid-cap")
        with self.assertRaisesRegex(FixedAssetServiceError, "Transfer must change"):
            FixedAssetService.transfer(
                self.tenant,
                active.id,
                self.actor,
                date(2026, 1, 2),
                active.location,
                active.cost_center,
                "same-transfer",
            )
        with self.assertRaisesRegex(FixedAssetServiceError, "Recoverable amount must be below book value"):
            FixedAssetService.record_impairment(
                self.tenant,
                active.id,
                self.actor,
                date(2026, 1, 3),
                active.net_book_value,
                "no loss",
                "bad-impair",
            )
        with self.assertRaises(IdempotencyConflictError):
            FixedAssetService.transfer(
                self.tenant,
                active.id,
                self.actor,
                date(2026, 1, 4),
                "HQ-2",
                "CC-2",
                "valid-cap",
            )

    def test_straight_line_partial_period_reconciles_exactly(self) -> None:
        asset = self.create_asset(cost="1200.00")
        asset = FixedAssetService.capitalize(
            self.tenant,
            asset.id,
            self.actor,
            date(2026, 1, 15),
            "cap-partial",
            depreciation_start_date=date(2026, 1, 15),
            expected_version=asset.version,
        )
        schedule = DepreciationService.create_schedule_draft(self.tenant, asset.id, self.actor, {}, "schedule-partial")
        schedule = DepreciationService.calculate_schedule(self.tenant, schedule.id, self.actor, {}, "calculate-partial")
        lines = list(schedule.lines.order_by("sequence"))
        self.assertEqual(len(lines), 13)
        self.assertLess(lines[0].depreciation_amount, Decimal("100.00"))
        self.assertEqual(
            sum((line.depreciation_amount for line in lines), Decimal("0.00")),
            schedule.depreciable_amount,
        )
        self.assertEqual(lines[-1].closing_net_book_value, schedule.residual_value)

    def test_units_schedule_requires_complete_reconciled_input(self) -> None:
        asset = self.create_asset(cost="1000.00")
        asset.depreciation_method = "units_of_production"
        asset.expected_total_units = Decimal("100.0000")
        asset.save()
        asset = self.capitalize(asset, "cap-units")
        schedule = DepreciationService.create_schedule_draft(
            self.tenant,
            asset.id,
            self.actor,
            {"start_date": date(2026, 1, 1), "end_date": date(2026, 2, 28)},
            "schedule-units",
        )
        with self.assertRaises(FixedAssetServiceError):
            DepreciationService.calculate_schedule(self.tenant, schedule.id, self.actor, {}, "calculate-units-missing")
        schedule = DepreciationService.calculate_schedule(
            self.tenant,
            schedule.id,
            self.actor,
            {"2026-01-01": Decimal("40"), "2026-02-01": Decimal("60")},
            "calculate-units",
        )
        self.assertEqual(schedule.lines.count(), 2)
        self.assertEqual(schedule.total_planned_depreciation, Decimal("1000.00"))

    def test_posting_worker_updates_line_asset_ledger_and_job(self) -> None:
        asset = self.capitalize(self.create_asset())
        schedule = DepreciationService.create_schedule_draft(self.tenant, asset.id, self.actor, {}, "schedule-post")
        schedule = DepreciationService.calculate_schedule(self.tenant, schedule.id, self.actor, {}, "calculate-post")
        schedule = DepreciationService.activate_schedule(self.tenant, schedule.id, self.actor, "activate-post")
        line = schedule.lines.order_by("sequence").first()
        job = DepreciationService.enqueue_line_posting(self.tenant, line.id, self.actor, "post-line-1", "corr-post")
        completed = execute(job.id, self.tenant)
        line.refresh_from_db()
        asset.refresh_from_db()
        self.assertEqual(completed.status, JobStatus.SUCCEEDED)
        self.assertEqual(line.status, "posted")
        self.assertIsNotNone(line.journal_entry_id)
        self.assertEqual(asset.net_book_value, Decimal("1100.00"))
        self.assertEqual(
            AssetTransaction.objects.filter(asset=asset, transaction_type="depreciation").count(),
            1,
        )

    def test_accounting_failure_marks_line_and_job_without_balance_change(self) -> None:
        asset = self.capitalize(self.create_asset())
        schedule = DepreciationService.create_schedule_draft(self.tenant, asset.id, self.actor, {}, "schedule-fail")
        schedule = DepreciationService.calculate_schedule(self.tenant, schedule.id, self.actor, {}, "calculate-fail")
        schedule = DepreciationService.activate_schedule(self.tenant, schedule.id, self.actor, "activate-fail")
        line: DepreciationLine = schedule.lines.order_by("sequence").first()
        job = DepreciationService.enqueue_line_posting(self.tenant, line.id, self.actor, "post-fail", "corr-fail")
        extension_registry.set_accounting_port(FakeAccounting(failure=True))
        with self.assertRaises(JobExecutionError):
            execute(job.id, self.tenant)
        line.refresh_from_db()
        asset.refresh_from_db()
        job.refresh_from_db()
        self.assertEqual(line.status, "failed")
        self.assertEqual(line.posting_error_code, "CAPABILITY_UNAVAILABLE")
        self.assertEqual(job.status, JobStatus.FAILED)
        self.assertEqual(asset.net_book_value, Decimal("1200.00"))

    def test_delete_draft_is_tenant_scoped_and_rejects_asset_history(self) -> None:
        deletable = self.create_asset(key="draft-delete")
        FixedAssetService.delete_draft(self.tenant, deletable.id, self.actor)
        self.assertFalse(FixedAsset.objects.filter(pk=deletable.id, tenant_id=self.tenant).exists())

        guarded = self.create_asset(key="draft-history")
        AssetTransaction.objects.create(
            tenant_id=self.tenant,
            asset=guarded,
            transaction_type="transfer",
            effective_date=date(2026, 1, 2),
            amount=Decimal("0.00"),
            currency=guarded.currency,
            opening_net_book_value=guarded.net_book_value,
            closing_net_book_value=guarded.net_book_value,
            actor_id=self.actor,
            correlation_id="history-delete-correlation",
            source_type="asset",
            source_id=guarded.id,
            idempotency_key="draft-history-transaction",
            request_fingerprint="h" * 64,
        )

        with self.assertRaisesRegex(FixedAssetServiceError, "history prevents deletion"):
            FixedAssetService.delete_draft(self.tenant, guarded.id, self.actor)
        with self.assertRaises(ObjectDoesNotExist):
            FixedAssetService.delete_draft(uuid.uuid4(), guarded.id, self.actor)

    def test_legacy_adapter_creates_active_default_category_with_derived_life(self) -> None:
        asset = FixedAssetService.create_fixed_asset(
            self.tenant,
            "legacy-service-1",
            "Legacy service asset",
            date(2026, 1, 1),
            Decimal("2400.00"),
            asset_category="vehicles",
            useful_life_years=2,
            depreciation_method="straight_line",
            idempotency_key="legacy-service-asset",
            actor_id=self.actor,
        )

        self.assertEqual(asset.asset_code, "LEGACY-SERVICE-1")
        self.assertEqual(asset.useful_life_months, 24)
        self.assertEqual(asset.category.code, "VEHICLES")
        self.assertTrue(asset.category.is_active)
        self.assertEqual(
            FixedAssetService.create_fixed_asset(
                self.tenant,
                "legacy-service-1",
                "Legacy service asset",
                date(2026, 1, 1),
                Decimal("2400.00"),
                asset_category="vehicles",
                useful_life_years=2,
                depreciation_method="straight_line",
                idempotency_key="legacy-service-asset",
                actor_id=self.actor,
            ).id,
            asset.id,
        )

    def test_fully_depreciated_transition_requires_residual_balance_and_is_idempotent(self) -> None:
        asset = self.capitalize(self.create_asset(key="fully-depreciated", cost="1200.00"), "cap-fully")
        with self.assertRaisesRegex(FixedAssetServiceError, "residual value"):
            FixedAssetService.mark_fully_depreciated(self.tenant, asset.id, self.actor, "fully-before-residual")

        asset.accumulated_depreciation = Decimal("1200.00")
        asset.net_book_value = Decimal("0.00")
        asset.save(update_fields={"accumulated_depreciation", "net_book_value", "updated_at"})
        transitioned = FixedAssetService.mark_fully_depreciated(self.tenant, asset.id, self.actor, "fully-once")

        self.assertEqual(transitioned.status, "fully_depreciated")
        version = transitioned.version
        replay = FixedAssetService.mark_fully_depreciated(self.tenant, transitioned.id, self.actor, "fully-once")
        self.assertEqual(replay.status, "fully_depreciated")
        self.assertEqual(replay.version, version)

    def test_lifecycle_previews_surface_blockers_without_mutating_asset(self) -> None:
        category = AssetCategory.objects.create(
            tenant_id=self.tenant,
            code="PREVIEW",
            name="Preview category",
            default_depreciation_method="straight_line",
            default_useful_life_months=12,
        )
        asset = FixedAsset.objects.create(
            tenant_id=self.tenant,
            asset_code="PREVIEW-1",
            asset_name="Preview asset",
            category=category,
            purchase_date=date(2026, 1, 1),
            purchase_cost=Decimal("1200.00"),
            currency="USD",
            residual_value=Decimal("0.00"),
            depreciation_method="straight_line",
            useful_life_months=12,
            net_book_value=Decimal("1200.00"),
            created_by=self.actor,
            updated_by=self.actor,
        )

        capitalization = FixedAssetService.preview_capitalization(self.tenant, asset.id, date(2026, 1, 1))
        transfer = FixedAssetService.preview_transfer(
            self.tenant,
            asset.id,
            date(2026, 1, 2),
            to_location=asset.location,
            to_cost_center=asset.cost_center,
        )
        impairment = FixedAssetService.preview_impairment(
            self.tenant,
            asset.id,
            date(2026, 1, 3),
            recoverable_amount=Decimal("1200.00"),
        )
        disposal = FixedAssetService.preview_disposal(self.tenant, asset.id, date(2026, 1, 4))

        self.assertEqual(capitalization["journal_effect"]["status"], "unavailable")
        self.assertIn(
            {"code": "ACCOUNT_MAPPING_INCOMPLETE", "message": "Complete category account mapping."},
            capitalization["blockers"],
        )
        self.assertEqual(transfer["journal_effect"]["status"], "unavailable")
        self.assertIn({"code": "NO_TRANSFER_CHANGE", "message": "Destination must change."}, transfer["blockers"])
        self.assertIn(
            {"code": "INVALID_RECOVERABLE_AMOUNT", "message": "Recoverable amount is outside the allowed range."},
            impairment["blockers"],
        )
        self.assertIn({"code": "DISPOSAL_NOT_ALLOWED", "message": "Asset is not disposable."}, disposal["blockers"])
        asset.refresh_from_db()
        self.assertEqual(asset.status, "draft")


class FixedAssetHelperBoundaryTests(TestCase):
    def test_value_helpers_fail_closed_and_normalize_domain_values(self) -> None:
        tenant = uuid.uuid4()
        self.assertEqual(_tenant(str(tenant)), tenant)
        with self.assertRaisesRegex(FixedAssetServiceError, "tenant_id"):
            _tenant("not-a-uuid")

        self.assertEqual(_required("  asset-code  ", "asset_code"), "asset-code")
        with self.assertRaisesRegex(FixedAssetServiceError, "asset_code"):
            _required("", "asset_code")
        with self.assertRaisesRegex(FixedAssetServiceError, "asset_code"):
            _required("x" * 31, "asset_code", 30)

        nested = {
            "uuid": tenant,
            "date": date(2026, 7, 1),
            "decimal": Decimal("12.30"),
            "list": (Decimal("1.00"), date(2026, 7, 2)),
            "model": AssetCategory(id=tenant),
        }
        canonical = _canonical(nested)
        self.assertEqual(canonical["uuid"], str(tenant))
        self.assertEqual(canonical["date"], "2026-07-01")
        self.assertEqual(canonical["decimal"], "12.30")
        self.assertEqual(canonical["list"], ["1.00", "2026-07-02"])
        self.assertEqual(canonical["model"], str(tenant))
        self.assertEqual(_fingerprint({"b": 2, "a": 1}), _fingerprint({"a": 1, "b": 2}))

    def test_correlation_version_and_account_helpers_cover_guardrails(self) -> None:
        self.assertTrue(_correlation("fixed-asset-test").startswith("cmd-"))

        instance = type("Versioned", (), {"version": 3})()
        _version(instance, 3)
        for expected in (False, 0, 4):
            with self.assertRaises(StaleVersionError):
                _version(instance, expected)

        category = AssetCategory(
            asset_account_id=uuid.uuid4(),
            accumulated_depreciation_account_id=uuid.uuid4(),
            depreciation_expense_account_id=uuid.uuid4(),
            impairment_loss_account_id=uuid.uuid4(),
            disposal_gain_account_id=uuid.uuid4(),
            disposal_loss_account_id=uuid.uuid4(),
        )
        self.assertEqual(len(_category_accounts(category)), 6)
        category.disposal_loss_account_id = None
        with self.assertRaisesRegex(FixedAssetServiceError, "account mapping"):
            _category_accounts(category)

    def test_transition_helper_is_idempotent_and_rejects_illegal_commands(self) -> None:
        class Recorder:
            def __init__(self) -> None:
                self.records: dict[str, TransitionRecord] = {}

            def find(self, aggregate, transition_key: str):
                del aggregate
                return self.records.get(transition_key)

            def record(self, aggregate, record: TransitionRecord) -> None:
                del aggregate
                self.records[record.transition_key] = record

            def aggregate_update_fields(self):
                return ("transition_history",)

        aggregate = type("Aggregate", (), {"status": "draft"})()
        recorder = Recorder()
        machine = StateMachine(
            states=("draft", "active", "disposed"),
            transitions=(Transition("activate", "draft", "active"), Transition("dispose", "active", "disposed")),
            terminal_states=("disposed",),
            recorder=recorder,
            name="asset-test",
        )

        self.assertTrue(_transition(machine, aggregate, "activate", "activate-1", "actor", "corr"))
        self.assertEqual(aggregate.status, "active")
        self.assertFalse(_transition(machine, aggregate, "activate", "activate-1", "actor", "corr"))
        with self.assertRaises(IdempotencyConflictError):
            _transition(machine, aggregate, "dispose", "activate-1", "actor", "corr")
        with self.assertRaises(UnknownCommandError):
            _transition(machine, aggregate, "missing", "missing-1", "actor", "corr")
        with self.assertRaises(IllegalTransitionError):
            _transition(machine, aggregate, "activate", "activate-2", "actor", "corr")
        self.assertTrue(_transition(machine, aggregate, "dispose", "dispose-1", "actor", "corr"))
        with self.assertRaises(TerminalStateError):
            _transition(machine, aggregate, "dispose", "dispose-2", "actor", "corr")

    def test_period_helpers_handle_month_end_and_partial_ranges(self) -> None:
        self.assertEqual(_add_months(date(2024, 1, 31), 1), date(2024, 2, 29))
        self.assertEqual(_add_months(date(2025, 10, 31), 4), date(2026, 2, 28))

        assert _periods(date(2026, 1, 15), date(2026, 3, 10)) == [
            (date(2026, 1, 15), date(2026, 1, 31)),
            (date(2026, 2, 1), date(2026, 2, 28)),
            (date(2026, 3, 1), date(2026, 3, 10)),
        ]
        assert _periods(date(2026, 4, 2), date(2026, 4, 1)) == []
