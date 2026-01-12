import { apiClient } from "@/services/api-client";
import {
  EntityDefinition,
  FieldDefinition,
  DynamicResource,
  METADATA_ENDPOINTS,
} from "../contracts";

export const metadataService = {
  getEntities: async (): Promise<EntityDefinition[]> => {
    const response = await apiClient.get<EntityDefinition[]>(
      METADATA_ENDPOINTS.ENTITIES
    );
    return response.data;
  },

  getEntity: async (id: string): Promise<EntityDefinition> => {
    const response = await apiClient.get<EntityDefinition>(
      `${METADATA_ENDPOINTS.ENTITIES}${id}/`
    );
    return response.data;
  },

  createEntity: async (
    entity: Partial<EntityDefinition>
  ): Promise<EntityDefinition> => {
    const response = await apiClient.post<EntityDefinition>(
      METADATA_ENDPOINTS.ENTITIES,
      entity
    );
    return response.data;
  },

  updateEntity: async (
    id: string,
    entity: Partial<EntityDefinition>
  ): Promise<EntityDefinition> => {
    const response = await apiClient.put<EntityDefinition>(
      `${METADATA_ENDPOINTS.ENTITIES}${id}/`,
      entity
    );
    return response.data;
  },

  getResources: async (entityId: string): Promise<DynamicResource[]> => {
    // Filter resources by entity ID using query parameter
    const response = await apiClient.get<DynamicResource[]>(
      `${METADATA_ENDPOINTS.RESOURCES}?entity_definition=${entityId}`
    );
    return response.data;
  },

  createResource: async (
    resource: Partial<DynamicResource>
  ): Promise<DynamicResource> => {
    const response = await apiClient.post<DynamicResource>(
      METADATA_ENDPOINTS.RESOURCES,
      resource
    );
    return response.data;
  },
};
