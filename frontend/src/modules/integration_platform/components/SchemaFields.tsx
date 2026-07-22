import type { ChangeEvent } from 'react';
import { Input } from '@/components/ui/Input';
import type { ConnectorJsonSchema, JsonObject, JsonValue } from '../contracts';

export function SchemaFields({ schema, values, disabled, onChange }: { schema: ConnectorJsonSchema; values: JsonObject; disabled?: boolean; onChange: (values: JsonObject) => void }) {
  const update = (key: string, event: ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const property = schema.properties[key];
    if (!property) return;
    let value: JsonValue = event.target.value;
    if (property.type === 'number' || property.type === 'integer') value = Number(event.target.value);
    if (property.type === 'boolean') value = event.target.value === 'true';
    onChange({ ...values, [key]: value });
  };
  // Each schema property selects its accessible control, value coercion, help, and required state.
  // eslint-disable-next-line complexity
  return <div className="grid gap-5 md:grid-cols-2">{Object.entries(schema.properties).map(([key, property]) => {
    const required = schema.required?.includes(key) === true;
    const current = values[key];
    const stringValue = current === undefined || current === null ? '' : typeof current === 'string' || typeof current === 'number' || typeof current === 'boolean' ? String(current) : JSON.stringify(current);
    return <div key={key}>{property.enum ? <label className="block text-sm font-medium" htmlFor={`schema-${key}`}>{property.title ?? key}{required ? ' *' : ''}<select id={`schema-${key}`} className="mt-1 block w-full rounded-md border border-input bg-background px-3 py-2" required={required} disabled={disabled} value={stringValue} onChange={(event) => update(key, event)}><option value="">Select…</option>{property.enum.map((option) => <option key={String(option)} value={String(option)}>{String(option)}</option>)}</select></label> : <Input id={`schema-${key}`} label={`${property.title ?? key}${required ? ' *' : ''}`} required={required} disabled={disabled} type={property.format === 'password' || property.secret ? 'password' : property.type === 'number' || property.type === 'integer' ? 'number' : 'text'} value={stringValue} onChange={(event) => update(key, event)} />}{property.description && <p className="mt-1 text-xs text-muted-foreground">{property.description}</p>}</div>;
  })}</div>;
}
