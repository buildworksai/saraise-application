"""Harden Asset Management persistence without rewriting financial data."""

from decimal import Decimal

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models
from django.db.models import Count, F, Q


def validate_legacy_financial_data(apps, schema_editor):
    """Stop the migration when legacy rows cannot satisfy governed invariants.

    Financial values and useful lives cannot be guessed safely. Operators must
    correct invalid legacy records explicitly before retrying the migration.
    """

    del schema_editor
    Asset = apps.get_model("asset_management", "Asset")
    Entry = apps.get_model("asset_management", "DepreciationEntry")
    invalid_assets = Asset.objects.filter(
        Q(purchase_cost__lte=0)
        | Q(current_value__lt=0)
        | Q(current_value__gt=F("purchase_cost"))
        | (~Q(depreciation_method="none") & Q(useful_life_years__isnull=True))
    )
    if invalid_assets.exists():
        raise RuntimeError(
            "Asset Management migration blocked: correct non-positive costs, "
            "invalid book values, and missing useful lives in legacy assets."
        )
    cross_tenant_entries = Entry.objects.exclude(tenant_id=F("asset__tenant_id"))
    if cross_tenant_entries.exists():
        raise RuntimeError(
            "Asset Management migration blocked: depreciation entries reference " "assets owned by another tenant."
        )
    duplicate_dates = (
        Entry.objects.values("tenant_id", "asset_id", "entry_date")
        .annotate(row_count=Count("id"))
        .filter(row_count__gt=1)
    )
    if duplicate_dates.exists():
        raise RuntimeError(
            "Asset Management migration blocked: duplicate depreciation dates "
            "must be reconciled before enforcing immutable history."
        )


class Migration(migrations.Migration):
    dependencies = [("asset_management", "0001_initial")]

    operations = [
        migrations.AlterField(
            model_name="asset",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AlterField(
            model_name="depreciationentry",
            name="created_at",
            field=models.DateTimeField(auto_now_add=True),
        ),
        migrations.AddField(
            model_name="asset",
            name="residual_value",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=15,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
        migrations.AddField(
            model_name="asset",
            name="declining_balance_rate",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text="Optional annual percentage; double-declining rate is used when omitted.",
                max_digits=7,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(Decimal("0.0001")),
                    django.core.validators.MaxValueValidator(Decimal("100.0000")),
                ],
            ),
        ),
        migrations.AddField(
            model_name="asset",
            name="is_deleted",
            field=models.BooleanField(default=False, editable=False),
        ),
        migrations.AddField(
            model_name="asset",
            name="deleted_at",
            field=models.DateTimeField(blank=True, editable=False, null=True),
        ),
        migrations.AlterField(
            model_name="asset",
            name="asset_code",
            field=models.CharField(max_length=50),
        ),
        migrations.AlterField(
            model_name="asset",
            name="purchase_date",
            field=models.DateField(),
        ),
        migrations.AlterField(
            model_name="asset",
            name="purchase_cost",
            field=models.DecimalField(
                decimal_places=2,
                max_digits=15,
                validators=[django.core.validators.MinValueValidator(Decimal("0.01"))],
            ),
        ),
        migrations.AlterField(
            model_name="asset",
            name="current_value",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=15,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
        migrations.AlterField(
            model_name="asset",
            name="depreciation_method",
            field=models.CharField(
                choices=[
                    ("straight_line", "Straight line"),
                    ("declining_balance", "Declining balance"),
                    ("none", "Not depreciated"),
                ],
                default="none",
                max_length=50,
            ),
        ),
        migrations.AlterField(
            model_name="asset",
            name="useful_life_years",
            field=models.PositiveSmallIntegerField(
                blank=True,
                null=True,
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(100),
                ],
            ),
        ),
        migrations.AlterField(
            model_name="asset",
            name="is_active",
            field=models.BooleanField(default=True),
        ),
        migrations.AlterField(
            model_name="depreciationentry",
            name="entry_date",
            field=models.DateField(),
        ),
        migrations.AlterField(
            model_name="depreciationentry",
            name="accumulated_depreciation",
            field=models.DecimalField(
                decimal_places=2,
                max_digits=15,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
        migrations.AlterField(
            model_name="depreciationentry",
            name="book_value",
            field=models.DecimalField(
                decimal_places=2,
                max_digits=15,
                validators=[django.core.validators.MinValueValidator(Decimal("0.00"))],
            ),
        ),
        migrations.AlterField(
            model_name="depreciationentry",
            name="asset",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.PROTECT,
                related_name="depreciation_entries",
                to="asset_management.asset",
            ),
        ),
        migrations.RunPython(validate_legacy_financial_data, migrations.RunPython.noop),
        migrations.RemoveConstraint(model_name="asset", name="unique_asset_code_per_tenant"),
        migrations.AddConstraint(
            model_name="asset",
            constraint=models.UniqueConstraint(fields=("tenant_id", "asset_code"), name="asset_code_tenant_uniq"),
        ),
        migrations.AddConstraint(
            model_name="asset",
            constraint=models.CheckConstraint(condition=Q(purchase_cost__gt=0), name="asset_purchase_cost_pos"),
        ),
        migrations.AddConstraint(
            model_name="asset",
            constraint=models.CheckConstraint(
                condition=Q(residual_value__gte=0) & Q(residual_value__lte=F("purchase_cost")),
                name="asset_residual_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="asset",
            constraint=models.CheckConstraint(
                condition=Q(current_value__gte=F("residual_value")) & Q(current_value__lte=F("purchase_cost")),
                name="asset_current_value_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="asset",
            constraint=models.CheckConstraint(
                condition=Q(depreciation_method="none") | Q(useful_life_years__isnull=False),
                name="asset_useful_life_required",
            ),
        ),
        migrations.AddConstraint(
            model_name="asset",
            constraint=models.CheckConstraint(
                condition=Q(declining_balance_rate__isnull=True)
                | (Q(declining_balance_rate__gt=0) & Q(declining_balance_rate__lte=100)),
                name="asset_declining_rate_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="asset",
            constraint=models.CheckConstraint(
                condition=Q(is_deleted=False, deleted_at__isnull=True) | Q(is_deleted=True, deleted_at__isnull=False),
                name="asset_delete_state_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="depreciationentry",
            constraint=models.UniqueConstraint(
                fields=("tenant_id", "asset", "entry_date"),
                name="asset_depr_date_uniq",
            ),
        ),
        migrations.AddConstraint(
            model_name="depreciationentry",
            constraint=models.CheckConstraint(
                condition=Q(depreciation_amount__gte=0),
                name="asset_depr_amount_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="depreciationentry",
            constraint=models.CheckConstraint(
                condition=Q(accumulated_depreciation__gte=0),
                name="asset_depr_accum_valid",
            ),
        ),
        migrations.AddConstraint(
            model_name="depreciationentry",
            constraint=models.CheckConstraint(condition=Q(book_value__gte=0), name="asset_depr_book_valid"),
        ),
        migrations.RemoveIndex(model_name="asset", name="asset_asset_tenant__641f1a_idx"),
        migrations.RemoveIndex(model_name="asset", name="asset_asset_tenant__c6d049_idx"),
        migrations.RemoveIndex(model_name="depreciationentry", name="asset_depre_tenant__04779b_idx"),
        migrations.RemoveIndex(model_name="depreciationentry", name="asset_depre_tenant__279fa0_idx"),
        migrations.AddIndex(
            model_name="asset",
            index=models.Index(fields=("tenant_id", "asset_code"), name="asset_tenant_code_idx"),
        ),
        migrations.AddIndex(
            model_name="asset",
            index=models.Index(fields=("tenant_id", "category", "is_deleted"), name="asset_tenant_cat_del_idx"),
        ),
        migrations.AddIndex(
            model_name="asset",
            index=models.Index(fields=("tenant_id", "is_active", "is_deleted"), name="asset_tenant_active_idx"),
        ),
        migrations.AddIndex(
            model_name="asset",
            index=models.Index(fields=("tenant_id", "purchase_date"), name="asset_tenant_date_idx"),
        ),
        migrations.AddIndex(
            model_name="asset",
            index=models.Index(fields=("tenant_id", "created_at"), name="asset_tenant_created_idx"),
        ),
        migrations.AddIndex(
            model_name="depreciationentry",
            index=models.Index(fields=("tenant_id", "asset", "entry_date"), name="asset_depr_asset_date_idx"),
        ),
        migrations.AddIndex(
            model_name="depreciationentry",
            index=models.Index(fields=("tenant_id", "entry_date"), name="asset_depr_date_idx"),
        ),
        migrations.AddIndex(
            model_name="depreciationentry",
            index=models.Index(fields=("tenant_id", "created_at"), name="asset_depr_created_idx"),
        ),
        migrations.AlterModelOptions(name="asset", options={"ordering": ("asset_code",)}),
        migrations.AlterModelOptions(
            name="depreciationentry",
            options={"ordering": ("-entry_date", "-created_at")},
        ),
    ]
