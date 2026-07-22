import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Textarea } from "@/components/ui/Textarea";
import type { FieldDefinition, JSONValue } from "../contracts";

interface Props { field: FieldDefinition; value: JSONValue | undefined; error?: string; disabled?: boolean; onChange: (value: JSONValue) => void }
function textValue(value: JSONValue | undefined): string { return typeof value === "string" || typeof value === "number" ? String(value) : ""; }

function renderControl({ field, value, error, disabled = false, onChange }: Props, id: string, describedBy: string): ReactNode {
  const common = { id, disabled: disabled || field.is_read_only, required: field.is_required, "aria-invalid": Boolean(error), "aria-describedby": describedBy };
  switch (field.field_type) {
    case "boolean": return <label className="flex min-h-10 items-center gap-2"><input {...common} type="checkbox" checked={value === true} onChange={(event) => onChange(event.target.checked)} /><span>{field.name}</span></label>;
    case "select": return <select {...common} value={textValue(value)} onChange={(event) => onChange(event.target.value)} className="h-10 w-full rounded-md border border-input bg-background px-3 text-foreground"><option value="">Select {field.name}</option>{field.options.map((option) => <option key={option} value={option}>{option}</option>)}</select>;
    case "json": return <Textarea {...common} rows={7} value={value === undefined || value === null ? "" : JSON.stringify(value, null, 2)} onChange={(event) => { try { onChange(JSON.parse(event.target.value) as JSONValue); } catch { onChange(event.target.value); } }} />;
    case "number": return <Input {...common} type="number" value={textValue(value)} onChange={(event) => onChange(event.target.value === "" ? null : Number(event.target.value))} />;
    case "date": return <Input {...common} type="date" value={textValue(value)} onChange={(event) => onChange(event.target.value)} />;
    case "reference": return <Input {...common} value={textValue(value)} placeholder={field.placeholder || "Record UUID"} onChange={(event) => onChange(event.target.value)} />;
    case "text": return <Input {...common} value={textValue(value)} minLength={field.validation_rules.min_length} maxLength={field.validation_rules.max_length} pattern={field.validation_rules.regex} placeholder={field.placeholder} onChange={(event) => onChange(event.target.value)} />;
  }
}

export function DynamicFieldRenderer(props: Props) {
  const { field, error } = props;
  const id = `dynamic-${field.key}`;
  const describedBy = `${id}-help${error ? ` ${id}-error` : ""}`;
  const control = renderControl(props, id, describedBy);
  return <div className="space-y-1">{field.field_type !== "boolean" && <Label htmlFor={id}>{field.name}{field.is_required && <span aria-hidden="true" className="text-destructive"> *</span>}</Label>}{control}<p id={`${id}-help`} className="text-xs text-muted-foreground">{field.help_text || `${field.field_type} field`}</p>{error && <p id={`${id}-error`} role="alert" className="text-sm text-destructive">{error}</p>}</div>;
}
import type { ReactNode } from "react";
