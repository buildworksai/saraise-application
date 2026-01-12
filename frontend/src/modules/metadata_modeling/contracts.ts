export interface EntityDefinition {
  id: string;
  name: string;
  code: string;
  description?: string;
  is_system: boolean;
  fields?: FieldDefinition[];
  created_at: string;
}

export interface FieldDefinition {
  id: string;
  name: string;
  key: string;
  field_type:
    | "text"
    | "number"
    | "date"
    | "boolean"
    | "select"
    | "reference"
    | "json";
  is_required: boolean;
  default_value?: any;
  validation_rules?: Record<string, any>;
  options?: string[];
  order: number;
}

export interface DynamicResource {
  id: string;
  entity_definition: string; // ID
  data: Record<string, any>;
  created_at: string;
  updated_at: string;
}

export const METADATA_ENDPOINTS = {
  ENTITIES: "/api/v1/metadata-modeling/entity-definitions/",
  RESOURCES: "/api/v1/metadata-modeling/resources/",
};
