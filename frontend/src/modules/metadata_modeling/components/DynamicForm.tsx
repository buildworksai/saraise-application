import React from "react";
import { useForm } from "react-hook-form";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Checkbox } from "@/components/ui/checkbox";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/Select";
import { EntityDefinition, FieldDefinition } from "../contracts";

interface DynamicFormProps {
  entityDef: EntityDefinition;
  onSubmit: (data: any) => void;
  initialData?: any;
}

export const DynamicForm: React.FC<DynamicFormProps> = ({
  entityDef,
  onSubmit,
  initialData = {},
}) => {
  const {
    register,
    handleSubmit,
    formState: { errors },
    setValue,
  } = useForm({
    defaultValues: initialData,
  });

  const renderField = (field: FieldDefinition) => {
    switch (field.field_type) {
      case "text":
        return (
          <Input {...register(field.key, { required: field.is_required })} />
        );
      case "number":
        return (
          <Input
            type="number"
            step="any"
            {...register(field.key, {
              required: field.is_required,
              valueAsNumber: true,
            })}
          />
        );
      case "date":
        return (
          <Input
            type="date"
            {...register(field.key, { required: field.is_required })}
          />
        );
      case "boolean":
        return (
          <div className="flex items-center space-x-2">
            <Checkbox
              id={field.key}
              onCheckedChange={(checked) => setValue(field.key, checked)}
            />
            <label
              htmlFor={field.key}
              className="text-sm font-medium leading-none peer-disabled:cursor-not-allowed peer-disabled:opacity-70"
            >
              {field.name}
            </label>
          </div>
        );
      case "select":
        return (
          <Select onValueChange={(val) => setValue(field.key, val)}>
            <SelectTrigger>
              <SelectValue placeholder="Select..." />
            </SelectTrigger>
            <SelectContent>
              {field.options?.map((opt) => (
                <SelectItem key={opt} value={opt}>
                  {opt}
                </SelectItem>
              ))}
            </SelectContent>
          </Select>
        );
      default:
        return (
          <div className="text-red-500">
            Unsupported field type: {field.field_type}
          </div>
        );
    }
  };

  return (
    <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
      {entityDef.fields
        ?.sort((a, b) => a.order - b.order)
        .map((field) => (
          <div key={field.key} className="space-y-2">
            {field.field_type !== "boolean" && (
              <label className="text-sm font-medium">
                {field.name}{" "}
                {field.is_required && <span className="text-red-500">*</span>}
              </label>
            )}
            {renderField(field)}
            {errors[field.key] && (
              <span className="text-sm text-red-500">
                This field is required
              </span>
            )}
          </div>
        ))}
      <Button type="submit">Submit</Button>
    </form>
  );
};
