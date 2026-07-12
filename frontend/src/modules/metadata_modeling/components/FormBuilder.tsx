import React from "react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/Select";
import { Card } from "@/components/ui/Card";
import type { FieldDefinition } from "../contracts";
import { Plus, Trash2 } from "lucide-react";

interface FormBuilderProps {
  fields: FieldDefinition[];
  onChange: (fields: FieldDefinition[]) => void;
}

export const FormBuilder: React.FC<FormBuilderProps> = ({
  fields,
  onChange,
}) => {
  const addField = () => {
    const newField: FieldDefinition = {
      id: crypto.randomUUID(), // Temp ID
      name: "New Field",
      key: `field_${fields.length + 1}`,
      field_type: "text",
      is_required: false,
      order: fields.length,
    };
    onChange([...fields, newField]);
  };

  const updateField = (index: number, updates: Partial<FieldDefinition>) => {
    const newFields = [...fields];
    const field = newFields[index];
    if (!field) return;
    newFields[index] = { ...field, ...updates };
    onChange(newFields);
  };

  const removeField = (index: number) => {
    const newFields = fields.filter((_, i) => i !== index);
    onChange(newFields);
  };

  return (
    <div className="space-y-4">
      {fields.map((field, index) => (
        <Card key={field.id || index} className="p-4">
          <div className="flex gap-4 items-start">
            <div className="flex-1 space-y-2">
              <div className="flex gap-2">
                <div className="flex-1">
                  <label className="text-sm font-medium">Field Name</label>
                  <Input
                    value={field.name}
                    onChange={(e) =>
                      updateField(index, { name: e.target.value })
                    }
                  />
                </div>
                <div className="flex-1">
                  <label className="text-sm font-medium">Key</label>
                  <Input
                    value={field.key}
                    onChange={(e) =>
                      updateField(index, { key: e.target.value })
                    }
                  />
                </div>
                <div className="w-32">
                  <label className="text-sm font-medium">Type</label>
                  <Select
                    value={field.field_type}
                    onValueChange={(value) =>
                      updateField(index, {
                        field_type: value as FieldDefinition["field_type"],
                      })
                    }
                  >
                    <SelectTrigger>
                      <SelectValue />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="text">Text</SelectItem>
                      <SelectItem value="number">Number</SelectItem>
                      <SelectItem value="date">Date</SelectItem>
                      <SelectItem value="boolean">Boolean</SelectItem>
                      <SelectItem value="select">Select</SelectItem>
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <div className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={field.is_required}
                  onChange={(e) =>
                    updateField(index, { is_required: e.target.checked })
                  }
                />
                <span className="text-sm">Required</span>

                {field.field_type === "select" && (
                  <Input
                    placeholder="Options (comma separated)"
                    value={field.options?.join(",") ?? ""}
                    onChange={(e) =>
                      updateField(index, { options: e.target.value.split(",") })
                    }
                    className="w-full ml-4"
                  />
                )}
              </div>
            </div>

            <Button
              variant="ghost"
              size="icon"
              onClick={() => removeField(index)}
              className="text-red-500"
            >
              <Trash2 className="w-4 h-4" />
            </Button>
          </div>
        </Card>
      ))}

      <Button onClick={addField} variant="outline" className="w-full">
        <Plus className="w-4 h-4 mr-2" /> Add Field
      </Button>
    </div>
  );
};
