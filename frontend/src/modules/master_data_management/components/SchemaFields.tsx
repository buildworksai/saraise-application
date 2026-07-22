/* eslint-disable complexity -- declarative JSON Schema variants remain explicit and non-executable. */
import type { JsonObject, JsonSchema, JsonValue } from "../contracts";

function isJsonObject(value: JsonValue): value is JsonObject { return value !== null && typeof value === "object" && !Array.isArray(value); }

function atPath(object: JsonObject, path: readonly string[]): JsonValue | undefined {
  let value: JsonValue = object;
  for (const part of path) {
    if (!isJsonObject(value)) return undefined;
    value = value[part] ?? null;
  }
  return value;
}

function setPath(object: JsonObject, path: readonly string[], next: JsonValue): JsonObject {
  const [head, ...rest] = path;
  if (!head) return object;
  const previous = object[head];
  return { ...object, [head]: rest.length ? setPath(previous !== undefined && isJsonObject(previous) ? previous : {}, rest, next) : next };
}

function fieldValue(value: JsonValue | undefined): string | number {
  if (typeof value === "string" || typeof value === "number") return value;
  return "";
}

function parseNumber(value: string, integer: boolean): number | null { const parsed = integer ? Number.parseInt(value, 10) : Number.parseFloat(value); return Number.isFinite(parsed) ? parsed : null; }

interface Props { readonly schema: JsonSchema; readonly value: JsonObject; readonly onChange: (value: JsonObject) => void; readonly disabled?: boolean; readonly errors?: Readonly<Record<string, string | undefined>>; readonly prefix?: readonly string[]; }

// eslint-disable-next-line complexity -- JSON Schema field variants are intentionally explicit and non-executable.
export function SchemaFields({ schema, value, onChange, disabled = false, errors = {}, prefix = [] }: Props) {
  const properties = schema.properties ?? {};
  const entries = Object.entries(properties);
  if (!entries.length) return <p className="rounded-md border border-dashed p-4 text-sm text-muted-foreground">This entity type has no custom fields. Core identity fields remain available above.</p>;
  return <div className="grid gap-5 sm:grid-cols-2">{entries.map(([name, field]) => {
    const path = [...prefix, name]; const pathKey = path.join("."); const id = `mdm-field-${pathKey.replaceAll(".", "-")}`; const current = atPath(value, path); const required = schema.required?.includes(name) ?? false;
    if (field.type === "object") return <fieldset key={pathKey} className="col-span-full rounded-lg border p-4"><legend className="px-2 text-sm font-semibold">{field.title ?? name}</legend>{field.description ? <p className="mb-4 text-xs text-muted-foreground">{field.description}</p> : null}<SchemaFields schema={field} value={value} onChange={onChange} disabled={disabled} errors={errors} prefix={path}/></fieldset>;
    if (field.type === "boolean") return <label key={pathKey} className="flex items-center gap-3 rounded-md border p-3 text-sm"><input id={id} type="checkbox" disabled={disabled} checked={current === true} onChange={(event) => onChange(setPath(value, path, event.target.checked))}/><span><strong>{field.title ?? name}</strong>{field.description ? <small className="block text-muted-foreground">{field.description}</small> : null}</span></label>;
    if (field.enum) return <label key={pathKey} className="text-sm font-medium" htmlFor={id}>{field.title ?? name}{required ? " *" : ""}<select id={id} disabled={disabled} required={required} className="mt-1 block w-full rounded-md border bg-background p-2" value={fieldValue(current)} onChange={(event) => onChange(setPath(value, path, event.target.value))}><option value="">Select…</option>{field.enum.map((option) => <option key={String(option)} value={String(option)}>{String(option)}</option>)}</select>{errors[pathKey] ? <small role="alert" className="text-destructive">{errors[pathKey]}</small> : field.description ? <small className="block text-muted-foreground">{field.description}</small> : null}</label>;
    const numeric = field.type === "number" || field.type === "integer";
    return <label key={pathKey} className="text-sm font-medium" htmlFor={id}>{field.title ?? name}{required ? " *" : ""}<input id={id} disabled={disabled} required={required} type={numeric ? "number" : field.format === "date" ? "date" : field.format === "email" ? "email" : "text"} min={field.minimum} max={field.maximum} minLength={field.minLength} maxLength={field.maxLength} pattern={field.pattern} className="mt-1 block w-full rounded-md border bg-background px-3 py-2" value={fieldValue(current)} onChange={(event) => onChange(setPath(value, path, numeric ? parseNumber(event.target.value, field.type === "integer") : event.target.value))}/>{errors[pathKey] ? <small role="alert" className="text-destructive">{errors[pathKey]}</small> : field.description ? <small className="block text-muted-foreground">{field.description}</small> : null}</label>;
  })}</div>;
}
