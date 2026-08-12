import { useQuery } from "@tanstack/react-query";
import { Input } from "@/components/ui/Input";
import type { JsonValue, UISchemaField } from "../contracts";
import { workflowService } from "../services/workflow-service";
import {
  inputClass,
  inputMax,
  inputMin,
  inputPlaceholder,
  inputType,
  scalarFieldValue,
  stringFieldValue,
  workflowCatalogLookupKey,
} from "./workflow-schema-field-utils";

export function WorkflowSchemaField({
  field,
  value,
  onChange,
}: {
  field: UISchemaField;
  value: JsonValue | undefined;
  onChange: (value: JsonValue) => void;
}) {
  if (field.kind === "lookup")
    return <LookupSchemaField field={field} value={value} onChange={onChange} />;
  const id = `descriptor-${field.key}`;
  if (field.kind === "boolean")
    return (
      <label className="flex items-center gap-2 text-sm">
        <input
          id={id}
          type="checkbox"
          checked={value === true}
          onChange={(event) => onChange(event.target.checked)}
        />
        {field.label}
      </label>
    );
  if (field.kind === "select")
    return (
      <label htmlFor={id} className="block text-sm font-medium">
        {field.label}
        <select
          id={id}
          required={field.required}
          className={`${inputClass} mt-1`}
          value={stringFieldValue(value)}
          onChange={(event) => onChange(event.target.value)}
        >
          <option value="">Select…</option>
          {field.options.map((option) => (
            <option key={option.value} value={option.value}>
              {option.label}
            </option>
          ))}
        </select>
      </label>
    );
  return (
    <Input
      id={id}
      label={field.label}
      type={inputType(field)}
      required={field.required}
      min={inputMin(field)}
      max={inputMax(field)}
      placeholder={inputPlaceholder(field)}
      value={scalarFieldValue(value)}
      onChange={(event) =>
        onChange(field.kind === "number" ? Number(event.target.value) : event.target.value)
      }
    />
  );
}

function LookupSchemaField({
  field,
  value,
  onChange,
}: {
  field: Extract<UISchemaField, { kind: "lookup" }>;
  value: JsonValue | undefined;
  onChange: (value: JsonValue) => void;
}) {
  const lookup = useQuery({
    queryKey: workflowCatalogLookupKey(field.lookup_key),
    queryFn: () => workflowService.catalog.lookup(field.lookup_key),
  });
  const id = `descriptor-${field.key}`;
  return (
    <label htmlFor={id} className="block text-sm font-medium">
      {field.label}
      <select
        id={id}
        required={field.required}
        disabled={lookup.isLoading || lookup.isError}
        className={`${inputClass} mt-1`}
        value={stringFieldValue(value)}
        onChange={(event) => onChange(event.target.value)}
      >
        <option value="">{lookup.isError ? "Lookup unavailable" : "Select…"}</option>
        {lookup.data?.map((option) => (
          <option key={option.id} value={option.id}>
            {option.label}
          </option>
        ))}
      </select>
    </label>
  );
}
