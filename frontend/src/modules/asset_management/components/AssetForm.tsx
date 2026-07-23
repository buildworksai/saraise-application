/* eslint-disable max-lines-per-function */
import { useMemo, useState, type FormEvent } from 'react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import type { Asset, AssetConfigurationDocument, AssetCreate, AssetUpdate, DepreciationMethod } from '../contracts';
import { AssetManagementApiError } from '../services/asset-service';
import { ProblemState, titleCase } from './AssetManagementUI';

type FormErrors = Partial<Record<keyof AssetCreate, string>>;

function today(): string {
  return new Date().toISOString().slice(0, 10);
}

function initialForm(configuration: AssetConfigurationDocument, asset?: Asset): AssetCreate {
  return {
    asset_code: asset?.asset_code ?? '',
    asset_name: asset?.asset_name ?? '',
    category: asset?.category ?? configuration.default_category,
    purchase_date: asset?.purchase_date ?? today(),
    purchase_cost: asset?.purchase_cost ?? '',
    residual_value: asset?.residual_value ?? configuration.default_residual_value,
    depreciation_method: asset?.depreciation_method ?? configuration.default_depreciation_method,
    useful_life_years: asset?.useful_life_years ?? configuration.default_useful_life_years,
    declining_balance_rate: asset?.declining_balance_rate ?? null,
    location: asset?.location ?? '',
  };
}

function validateIdentity(form: AssetCreate, configuration: AssetConfigurationDocument): FormErrors {
  const errors: FormErrors = {};
  if (!form.asset_code.trim()) errors.asset_code = 'Asset code is required.';
  else if (form.asset_code.trim().length > configuration.asset_code_max_length) {
    errors.asset_code = `Asset code cannot exceed ${configuration.asset_code_max_length} characters.`;
  }
  else if (!/^[A-Za-z0-9._-]+$/u.test(form.asset_code)) {
    errors.asset_code = 'Use letters, numbers, periods, underscores, or hyphens.';
  }
  if (!form.asset_name.trim()) errors.asset_name = 'Asset name is required.';
  else if (form.asset_name.trim().length > configuration.asset_name_max_length) {
    errors.asset_name = `Asset name cannot exceed ${configuration.asset_name_max_length} characters.`;
  }
  if (form.location.length > configuration.location_max_length) {
    errors.location = `Location cannot exceed ${configuration.location_max_length} characters.`;
  }
  if (!form.purchase_date) errors.purchase_date = 'Purchase date is required.';
  return errors;
}

function validateMoney(form: AssetCreate, configuration: AssetConfigurationDocument): FormErrors {
  const errors: FormErrors = {};
  const cost = Number(form.purchase_cost);
  const residual = Number(form.residual_value);
  if (!Number.isFinite(cost) || cost < Number(configuration.minimum_purchase_cost)) {
    errors.purchase_cost = `Enter at least ${configuration.minimum_purchase_cost}.`;
  }
  if (!Number.isFinite(residual) || residual < 0) errors.residual_value = 'Enter a non-negative amount.';
  else if (Number.isFinite(cost) && residual > cost) {
    errors.residual_value = 'Residual value cannot exceed purchase cost.';
  }
  return errors;
}

function validateDepreciation(form: AssetCreate, configuration: AssetConfigurationDocument): FormErrors {
  const errors: FormErrors = {};
  const rate = form.declining_balance_rate === null ? null : Number(form.declining_balance_rate);
  if (form.depreciation_method !== 'none'
    && (!form.useful_life_years
      || form.useful_life_years < configuration.useful_life_min_years
      || form.useful_life_years > configuration.useful_life_max_years)) {
    errors.useful_life_years = `Useful life must be ${configuration.useful_life_min_years}-${configuration.useful_life_max_years} years.`;
  }
  if (form.depreciation_method === 'declining_balance'
    && rate !== null
    && (!Number.isFinite(rate) || rate < Number(configuration.declining_rate_min) || rate > Number(configuration.declining_rate_max))) {
    errors.declining_balance_rate = `Enter an annual rate from ${configuration.declining_rate_min} to ${configuration.declining_rate_max}.`;
  }
  return errors;
}

function validate(form: AssetCreate, configuration: AssetConfigurationDocument): FormErrors {
  return {
    ...validateIdentity(form, configuration),
    ...validateMoney(form, configuration),
    ...validateDepreciation(form, configuration),
  };
}

function normalizedForm(form: AssetCreate): AssetCreate {
  return {
    ...form,
    asset_code: form.asset_code.trim().toUpperCase(),
    asset_name: form.asset_name.trim(),
    location: form.location.trim(),
    useful_life_years: form.depreciation_method === 'none' ? null : form.useful_life_years,
    declining_balance_rate: form.depreciation_method === 'declining_balance'
      ? form.declining_balance_rate
      : null,
  };
}

const decimalFields = new Set<keyof AssetCreate>([
  'purchase_cost',
  'residual_value',
  'declining_balance_rate',
]);

function equalField<K extends keyof AssetCreate>(
  key: K,
  left: AssetCreate[K],
  right: AssetCreate[K],
): boolean {
  if (!decimalFields.has(key) || left === null || right === null) return left === right;
  const leftNumber = Number(left);
  const rightNumber = Number(right);
  return Number.isFinite(leftNumber) && Number.isFinite(rightNumber)
    ? leftNumber === rightNumber
    : left === right;
}

/** Emit only changed fields so descriptive edits do not rewrite locked financial policy. */
function changedFields(form: AssetCreate, asset: Asset, configuration: AssetConfigurationDocument): AssetUpdate {
  const initial = initialForm(configuration, asset);
  return (Object.keys(form) as (keyof AssetCreate)[]).reduce<AssetUpdate>((changes, key) => {
    if (!equalField(key, form[key], initial[key])) {
      Object.assign(changes, { [key]: form[key] });
    }
    return changes;
  }, {});
}

export function AssetForm({
  asset,
  configuration,
  pending,
  error,
  onCancel,
  onSubmit,
}: {
  asset?: Asset;
  configuration: AssetConfigurationDocument;
  pending: boolean;
  error: unknown;
  onCancel: () => void;
  onSubmit: (data: AssetCreate | AssetUpdate) => void;
}) {
  const [form, setForm] = useState<AssetCreate>(() => initialForm(configuration, asset));
  const [submitted, setSubmitted] = useState(false);
  const clientErrors = useMemo(() => submitted ? validate(form, configuration) : {}, [configuration, form, submitted]);
  const serverErrors = error instanceof AssetManagementApiError ? error.fieldErrors : {};
  const preparedForm = useMemo(() => normalizedForm(form), [form]);
  const updatePayload = useMemo(
    () => asset ? changedFields(preparedForm, asset, configuration) : preparedForm,
    [asset, configuration, preparedForm],
  );
  const isDirty = !asset || Object.keys(updatePayload).length > 0;
  const hasMappedServerError = (Object.keys(serverErrors) as (keyof AssetCreate)[])
    .some((field) => field in form);

  const update = <K extends keyof AssetCreate>(key: K, value: AssetCreate[K]) => {
    setForm((current) => ({ ...current, [key]: value }));
  };
  const fieldError = (field: keyof AssetCreate) => clientErrors[field] ?? serverErrors[field];
  const submit = (event: FormEvent) => {
    event.preventDefault();
    setSubmitted(true);
    if (Object.keys(validate(form, configuration)).length > 0) return;
    if (!isDirty) return;
    onSubmit(updatePayload);
  };

  return (
    <form className="space-y-6" onSubmit={submit} noValidate aria-busy={pending}>
      {error && !hasMappedServerError
        ? <ProblemState error={error} compact />
        : null}
      <Card className="grid gap-5 p-5 sm:p-6 md:grid-cols-2">
        <Input
          id="asset-code"
          label="Asset code"
          required
          maxLength={configuration.asset_code_max_length}
          autoComplete="off"
          value={form.asset_code}
          error={fieldError('asset_code')}
          onChange={(event) => update('asset_code', event.target.value.toUpperCase())}
        />
        <Input
          id="asset-name"
          label="Asset name"
          required
          maxLength={configuration.asset_name_max_length}
          value={form.asset_name}
          error={fieldError('asset_name')}
          onChange={(event) => update('asset_name', event.target.value)}
        />
        <div>
          <label htmlFor="asset-category" className="mb-1 block text-sm font-medium">Category</label>
          <select
            id="asset-category"
            className="h-10 w-full rounded-md border border-input bg-background px-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            value={form.category}
            onChange={(event) => {
              const category = event.target.value as AssetCreate['category'];
              const nonDepreciable = configuration.non_depreciable_categories.includes(category);
              setForm((current) => nonDepreciable
                ? {
                    ...current,
                    category,
                    depreciation_method: 'none',
                    useful_life_years: null,
                    declining_balance_rate: null,
                  }
                : { ...current, category });
            }}
          >
            {configuration.allowed_categories.map((category) => (
              <option key={category} value={category}>{titleCase(category)}</option>
            ))}
          </select>
        </div>
        <Input
          id="purchase-date"
          label="Purchase date"
          type="date"
          required
          value={form.purchase_date}
          error={fieldError('purchase_date')}
          onChange={(event) => update('purchase_date', event.target.value)}
        />
        <Input
          id="purchase-cost"
          label="Purchase cost"
          inputMode="decimal"
          required
          placeholder="0.00"
          value={form.purchase_cost}
          error={fieldError('purchase_cost')}
          onChange={(event) => update('purchase_cost', event.target.value)}
        />
        <Input
          id="residual-value"
          label="Residual value"
          inputMode="decimal"
          required
          placeholder="0.00"
          value={form.residual_value}
          error={fieldError('residual_value')}
          onChange={(event) => update('residual_value', event.target.value)}
        />
        <div>
          <label htmlFor="depreciation-method" className="mb-1 block text-sm font-medium">
            Depreciation method
          </label>
          <select
            id="depreciation-method"
            className="h-10 w-full rounded-md border border-input bg-background px-3 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
            value={form.depreciation_method}
            disabled={configuration.non_depreciable_categories.includes(form.category)}
            onChange={(event) => {
              const method = event.target.value as DepreciationMethod;
              setForm((current) => ({
                ...current,
                depreciation_method: method,
                useful_life_years: method === 'none' ? null : current.useful_life_years ?? configuration.default_useful_life_years,
                declining_balance_rate: method === 'declining_balance'
                  ? current.declining_balance_rate
                  : null,
              }));
            }}
          >
            {configuration.allowed_depreciation_methods.map((method) => <option key={method} value={method}>{titleCase(method)}</option>)}
          </select>
        </div>
        {configuration.non_depreciable_categories.includes(form.category) && (
          <p className="text-sm text-muted-foreground md:col-span-2">
            Current assets are not depreciated. The depreciation method is fixed to “None”.
          </p>
        )}
        {form.depreciation_method !== 'none' && (
          <Input
            id="useful-life"
            label="Useful life (years)"
            type="number"
            min={configuration.useful_life_min_years}
            max={configuration.useful_life_max_years}
            step={1}
            required
            value={form.useful_life_years ?? ''}
            error={fieldError('useful_life_years')}
            onChange={(event) => update('useful_life_years', event.target.value ? Number(event.target.value) : null)}
          />
        )}
        {form.depreciation_method === 'declining_balance' && (
          <Input
            id="declining-rate"
            label="Annual declining balance rate (%)"
            inputMode="decimal"
            placeholder="Optional — blank uses double declining balance"
            value={form.declining_balance_rate ?? ''}
            error={fieldError('declining_balance_rate')}
            onChange={(event) => update('declining_balance_rate', event.target.value || null)}
          />
        )}
        <Input
          id="location"
          label="Location"
          maxLength={configuration.location_max_length}
          placeholder="Optional physical or logical location"
          value={form.location}
          error={fieldError('location')}
          onChange={(event) => update('location', event.target.value)}
        />
      </Card>
      <p className="text-sm text-muted-foreground">
        Current value is calculated by the server from immutable depreciation history and cannot be edited here.
      </p>
      <div className="flex flex-col-reverse justify-end gap-3 sm:flex-row">
        <Button type="button" variant="secondary" onClick={onCancel}>Cancel</Button>
        <Button type="submit" disabled={pending || !isDirty}>
          {pending ? 'Saving…' : asset ? isDirty ? 'Save changes' : 'No changes' : 'Create asset'}
        </Button>
      </div>
    </form>
  );
}
