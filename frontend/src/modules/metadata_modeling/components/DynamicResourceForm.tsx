import { useMemo } from "react";
import type { FieldDefinition, JSONObject, JSONValue } from "../contracts";
import { DynamicFieldRenderer } from "./DynamicFieldRenderer";

interface Props { fields: readonly FieldDefinition[]; values: JSONObject; errors?: Readonly<Record<string, string>>; disabled?: boolean; onChange: (values: JSONObject) => void }
export function DynamicResourceForm({ fields, values, errors = {}, disabled = false, onChange }: Props) {
  const sorted = useMemo(() => [...fields].sort((left, right) => left.order - right.order), [fields]);
  const change = (key: string, value: JSONValue) => onChange({ ...values, [key]: value });
  return <div className="grid gap-5 md:grid-cols-2">{sorted.map((field) => <DynamicFieldRenderer key={field.id} field={field} value={values[field.key]} error={errors[field.key]} disabled={disabled} onChange={(value) => change(field.key, value)} />)}</div>;
}
