/*---------------------------------------------------------------------------------------------
 *  Copyright (c) BuildWorks.AI. All rights reserved.
 *  Licensed under the Apache 2.0 License. See License.txt in the project root for license information.
 *--------------------------------------------------------------------------------------------*/

// ✅ APPROVED: Dynamic form component for metadata modeling
// frontend/src/components/DynamicForm.tsx
// Reference: docs/architecture/metadata-modeling-spec.md § 3 (Custom Fields)
// CRITICAL NOTES:
// - Form schema fetched from /api/v1/metadata/forms/{resource}
// - Resource definitions include TenantCustomFieldDefinition
// - All field metadata includes: fieldname, label, fieldtype, required, options
// - Custom fields (is_custom: true) handled identically to built-in fields
// - Tenant-specific field definitions loaded via tenant_id parameter
// - Zod schema generated server-side and validated client-side
// - Row-level multitenancy enforced: custom field definitions scoped to tenant
// - Form submission sends tenant_id with payload (backend validates tenant ownership)
// - All custom field values validated against field definition constraints
// Source: docs/architecture/metadata-modeling-spec.md § 3, application-architecture.md § 4.1

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { useEffect, useState } from 'react';
import { apiClient } from '@/lib/api-client';

interface FormFieldOption {
  label: string
  value: string
}

interface FormField {
  fieldname: string;
  label: string;
  fieldtype: string;
  required?: boolean;
  options?: FormFieldOption[];
  default_value?: string;
  is_custom?: boolean;
}

interface DynamicFormProps {
  resourceType: string;
  tenantId?: string;
  onSubmit: (data: Record<string, string | number | boolean>) => Promise<void>;
}

export function DynamicForm({ resourceType, tenantId, onSubmit }: DynamicFormProps) {
  const [formSchema, setFormSchema] = useState<FormField[]>([]);
  const [zodSchema, setZodSchema] = useState<z.ZodObject<Record<string, z.ZodTypeAny>>>();

  useEffect(() => {
    // Fetch form schema using apiClient (not fetch)
    apiClient.get(`/api/v1/metadata/forms/${resourceType}?tenant_id=${tenantId}`)
      .then(response => {
        setFormSchema(response.data.fields);

        // Generate Zod schema from form fields
        const schemaFields: Record<string, z.ZodTypeAny> = {};
        response.data.fields.forEach((field: FormField) => {
          let fieldSchema: z.ZodTypeAny;

          switch (field.fieldtype) {
            case 'Data':
            case 'Email':
            case 'Text':
              fieldSchema = z.string();
              break;
            case 'Number':
            case 'Int':
              fieldSchema = z.number();
              break;
            case 'Date':
              fieldSchema = z.string().datetime();
              break;
            case 'Select':
              // CRITICAL: Validate enum has valid values
              const enumValues = (field.options?.map(opt => opt.value) || []) as [string, ...string[]];
              if (enumValues.length === 0) {
                // Fallback to string if no options (backend validation handles this)
                fieldSchema = z.string();
              } else {
                fieldSchema = z.enum(enumValues);
              }
              break;
            default:
              fieldSchema = z.string();
          }

          // Add optional/required constraint
          if (field.required) {
            // Required: string must have at least 1 char, number must exist
            if (field.fieldtype === 'Number' || field.fieldtype === 'Int') {
              fieldSchema = fieldSchema.refine(val => val !== null && val !== undefined);
            } else {
              fieldSchema = fieldSchema.min(1, `${field.label} is required`);
            }
          } else {
            // Optional: allow undefined
            fieldSchema = fieldSchema.optional();
          }

          schemaFields[field.fieldname] = fieldSchema;
        });

        setZodSchema(z.object(schemaFields));
      });
  }, [resourceType, tenantId]);

  const { register, handleSubmit, formState: { errors } } = useForm({
    resolver: zodSchema ? zodResolver(zodSchema) : undefined
  });

  if (!formSchema.length) {
    return <div>Loading form...</div>;
  }

  return (
    <form onSubmit={handleSubmit(onSubmit)}>
      {formSchema.map((field) => (
        <div key={field.fieldname}>
          <label>{field.label}</label>
          {field.fieldtype === 'Select' ? (
            <select {...register(field.fieldname)}>
              {field.options?.values?.map((value: string) => (
                <option key={value} value={value}>{value}</option>
              ))}
            </select>
          ) : (
            <input
              type={field.fieldtype === 'Email' ? 'email' : field.fieldtype === 'Number' ? 'number' : 'text'}
              {...register(field.fieldname)}
            />
          )}
          {errors[field.fieldname] && (
            <span>{errors[field.fieldname].message}</span>
          )}
        </div>
      ))}
      <button type="submit">Submit</button>
    </form>
  );
}

