import type { JsonValue, UISchemaField } from "../contracts";

export const inputClass =
  "block w-full rounded-md border border-input bg-background px-3 py-2 text-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring";

export function workflowCatalogLookupKey(lookupKey: string): readonly [string, string] {
  return ["workflow-catalog-lookup", lookupKey];
}

export function stringFieldValue(value: JsonValue | undefined): string {
  return typeof value === "string" ? value : "";
}

export function scalarFieldValue(value: JsonValue | undefined): string | number {
  return typeof value === "string" || typeof value === "number" ? value : "";
}

export function inputType(field: UISchemaField): "number" | "text" {
  return field.kind === "number" ? "number" : "text";
}

export function inputMin(field: UISchemaField): number | undefined {
  return field.kind === "number" ? field.minimum : undefined;
}

export function inputMax(field: UISchemaField): number | undefined {
  return field.kind === "number" ? field.maximum : undefined;
}

export function inputPlaceholder(field: UISchemaField): string | undefined {
  return field.kind === "text" ? field.placeholder : undefined;
}
