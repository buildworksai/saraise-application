import { Input } from "@/components/ui/Input";
import { Label } from "@/components/ui/Label";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/Select";
import type { FieldDefinitionInput, FieldType, JSONValue, ValidationRules } from "../contracts";

interface Props { field: FieldDefinitionInput; onChange: (field: FieldDefinitionInput) => void; disabled?: boolean }
const TYPES: readonly FieldType[] = ["text", "number", "date", "boolean", "select", "reference", "json"];

function parseDefault(value: string, type: FieldType): JSONValue {
  if (value === "") return null;
  if (type === "number") return Number(value);
  if (type === "boolean") return value === "true";
  if (type === "json") {
    try { return JSON.parse(value) as JSONValue; } catch { return value; }
  }
  return value;
}

export function SchemaFieldEditor({ field, onChange, disabled = false }: Props) {
  const set = <K extends keyof FieldDefinitionInput>(key: K, value: FieldDefinitionInput[K]) => onChange({ ...field, [key]: value });
  const rules = field.validation_rules;
  const setRule = <K extends keyof ValidationRules>(key: K, value: ValidationRules[K]) => {
    const next: ValidationRules = { ...rules, [key]: value };
    set("validation_rules", next);
  };
  const defaultText = field.default_value === null ? "" : typeof field.default_value === "string" ? field.default_value : JSON.stringify(field.default_value);

  return (
    <fieldset disabled={disabled} className="grid gap-4 rounded-lg border border-border bg-card p-4 md:grid-cols-2">
      <legend className="sr-only">Edit {field.name || "new field"}</legend>
      <Input id={`field-name-${field.order}`} label="Label" value={field.name} required onChange={(event) => set("name", event.target.value)} />
      <Input id={`field-key-${field.order}`} label="API key" value={field.key} required pattern="[a-z][a-z0-9_]*" onChange={(event) => set("key", event.target.value.toLowerCase().replace(/[^a-z0-9_]/gu, "_"))} />
      <div>
        <Label htmlFor={`field-type-${field.order}`}>Field type</Label>
        <Select value={field.field_type} onValueChange={(value: FieldType) => onChange({ ...field, field_type: value, options: value === "select" ? field.options : [], reference_entity_code: value === "reference" ? field.reference_entity_code : null, validation_rules: {} })}>
          <SelectTrigger id={`field-type-${field.order}`}><SelectValue /></SelectTrigger>
          <SelectContent>{TYPES.map((type) => <SelectItem key={type} value={type}>{type}</SelectItem>)}</SelectContent>
        </Select>
      </div>
      <Input id={`field-placeholder-${field.order}`} label="Placeholder" value={field.placeholder} onChange={(event) => set("placeholder", event.target.value)} />
      <Input id={`field-help-${field.order}`} label="Help text" value={field.help_text} onChange={(event) => set("help_text", event.target.value)} />
      <Input id={`field-default-${field.order}`} label="Default value" value={defaultText} onChange={(event) => set("default_value", parseDefault(event.target.value, field.field_type))} />
      {field.field_type === "select" && <Input id={`field-options-${field.order}`} label="Options (comma separated)" value={field.options.join(", ")} required onChange={(event) => set("options", event.target.value.split(",").map((option) => option.trim()).filter(Boolean))} />}
      {field.field_type === "reference" && <Input id={`field-reference-${field.order}`} label="Published entity code" value={field.reference_entity_code ?? ""} required onChange={(event) => set("reference_entity_code", event.target.value)} />}
      {field.field_type === "text" && <>
        <Input id={`field-min-${field.order}`} type="number" min={0} label="Minimum length" value={typeof rules.min_length === "number" ? rules.min_length : ""} onChange={(event) => setRule("min_length", event.target.value ? Number(event.target.value) : undefined)} />
        <Input id={`field-max-${field.order}`} type="number" min={1} max={100000} label="Maximum length" value={typeof rules.max_length === "number" ? rules.max_length : ""} onChange={(event) => setRule("max_length", event.target.value ? Number(event.target.value) : undefined)} />
        <Input id={`field-regex-${field.order}`} label="Validation pattern" value={typeof rules.regex === "string" ? rules.regex : ""} onChange={(event) => setRule("regex", event.target.value || undefined)} />
      </>}
      {field.field_type === "number" && <>
        <Input id={`field-minimum-${field.order}`} type="number" label="Minimum" value={typeof rules.minimum === "number" ? rules.minimum : ""} onChange={(event) => setRule("minimum", event.target.value ? Number(event.target.value) : undefined)} />
        <Input id={`field-maximum-${field.order}`} type="number" label="Maximum" value={typeof rules.maximum === "number" ? rules.maximum : ""} onChange={(event) => setRule("maximum", event.target.value ? Number(event.target.value) : undefined)} />
      </>}
      <div className="col-span-full flex flex-wrap gap-6 text-sm">
        {(["is_required", "is_searchable", "is_read_only"] as const).map((key) => <label key={key} className="flex items-center gap-2"><input type="checkbox" checked={field[key]} onChange={(event) => set(key, event.target.checked)} />{key.replace("is_", "").replace("_", " ")}</label>)}
      </div>
    </fieldset>
  );
}
