import { ArrowDown, ArrowUp, Plus, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import type { FieldDefinitionInput } from "../contracts";
import { SchemaFieldEditor } from "./SchemaFieldEditor";

interface Props { fields: readonly FieldDefinitionInput[]; onChange: (fields: readonly FieldDefinitionInput[]) => void; disabled?: boolean }
function emptyField(order: number): FieldDefinitionInput { return { name: "", key: "", field_type: "text", is_required: false, is_read_only: false, is_searchable: false, default_value: null, validation_rules: {}, options: [], reference_entity_code: null, help_text: "", placeholder: "", order }; }

export function SchemaFieldBuilder({ fields, onChange, disabled = false }: Props) {
  const replace = (index: number, field: FieldDefinitionInput) => onChange(fields.map((item, current) => current === index ? field : item));
  const move = (index: number, direction: -1 | 1) => {
    const destination = index + direction;
    if (destination < 0 || destination >= fields.length) return;
    const next = [...fields]; const current = next[index]; const other = next[destination];
    if (!current || !other) return;
    next[index] = { ...other, order: index + 1 }; next[destination] = { ...current, order: destination + 1 }; onChange(next);
  };
  return <section aria-labelledby="schema-fields-heading" className="space-y-4">
    <div className="flex items-center justify-between"><div><h2 id="schema-fields-heading" className="text-lg font-semibold">Fields</h2><p className="text-sm text-muted-foreground">Use the arrow controls or keyboard focus order to arrange the generated form.</p></div><Button type="button" disabled={disabled} onClick={() => onChange([...fields, emptyField(fields.length + 1)])}><Plus className="mr-2 h-4 w-4" />Add field</Button></div>
    {fields.length === 0 && <div className="rounded-lg border border-dashed border-border p-8 text-center text-muted-foreground">No fields yet. Add the first field to generate a form.</div>}
    {fields.map((field, index) => <div key={`${field.key}:${index}`} className="space-y-2">
      <div className="flex justify-end gap-1" aria-label={`Reorder ${field.name || `field ${index + 1}`}`}>
        <Button type="button" size="icon" variant="ghost" aria-label="Move field up" disabled={disabled || index === 0} onClick={() => move(index, -1)}><ArrowUp className="h-4 w-4" /></Button>
        <Button type="button" size="icon" variant="ghost" aria-label="Move field down" disabled={disabled || index === fields.length - 1} onClick={() => move(index, 1)}><ArrowDown className="h-4 w-4" /></Button>
        <Button type="button" size="icon" variant="ghost" aria-label="Remove field" disabled={disabled} onClick={() => onChange(fields.filter((_item, current) => current !== index).map((item, order) => ({ ...item, order: order + 1 })))}><Trash2 className="h-4 w-4" /></Button>
      </div>
      <SchemaFieldEditor field={field} disabled={disabled} onChange={(next) => replace(index, next)} />
    </div>)}
  </section>;
}
