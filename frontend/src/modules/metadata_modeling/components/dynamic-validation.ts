import type { FieldDefinition, JSONObject, JSONValue } from "../contracts";

function isBlank(value: JSONValue | undefined): boolean { return value === undefined || value === null || value === ""; }
function validateType(field: FieldDefinition, value: JSONValue | undefined): string | null {
  switch (field.field_type) {
    case "select": return typeof value === "string" && value !== "" && !field.options.includes(value) ? "Choose an available option." : null;
    case "number": return !isBlank(value) && (typeof value !== "number" || !Number.isFinite(value)) ? "Enter a finite number." : null;
    case "date": return typeof value === "string" && value !== "" && !/^\d{4}-\d{2}-\d{2}$/u.test(value) ? "Use YYYY-MM-DD." : null;
    case "json": return typeof value === "string" ? "Enter valid JSON." : null;
    default: return null;
  }
}
function validateField(field: FieldDefinition, value: JSONValue | undefined): string | null { return field.is_required && isBlank(value) ? "This field is required." : validateType(field, value); }
export function validateDynamicValues(fields: readonly FieldDefinition[], values: JSONObject): Readonly<Record<string, string>> {
  const errors: Record<string, string> = {};
  for (const field of fields) { const error = validateField(field, values[field.key]); if (error) errors[field.key] = error; }
  return errors;
}
