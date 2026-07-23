import { apiClient, ApiError as ClientApiError } from '@/services/api-client';
import { z } from 'zod';
import { ENDPOINTS, INBOUND_WEBHOOK_HEADERS } from '../contracts';
import type {
  ApiEnvelope, AsyncJobReceipt, AsyncJobState, Connector, ConnectorDetail, ConnectorFilters,
  ConnectorHealth, ConnectorSchema, CredentialCreateRequest, CredentialRevokeRequest,
  ConfigurationAudit, ConfigurationPreview, ConfigurationVersion, ConfigurationWriteRequest,
  CredentialRotateRequest, DataMapping, DataMappingCreateRequest, DataMappingUpdateRequest,
  DeliveryFilters, DeliveryRedriveRequest, InboundWebhookReceipt, InboundWebhookRequest,
  Integration, IntegrationCreateRequest, IntegrationCredential, IntegrationDetail, IntegrationFilters,
  IntegrationPlatformConfiguration, IntegrationPlatformHealth, IntegrationPlatformManageCapability, IntegrationSyncRequest, IntegrationTestRequest, IntegrationUpdateRequest,
  MappingFilters, MappingPreviewRequest, MappingPreviewResult, MappingValidationRequest,
  MappingValidationResult, PaginatedEnvelope, PaginatedMeta, TransitionRequest, Webhook,
  WebhookCreateRequest, WebhookDelivery, WebhookDeliveryDetail, WebhookDetail, WebhookFilters,
  WebhookSecretOnce, WebhookUpdateRequest,
} from '../contracts';

export interface PageResult<T> { items: T[]; meta: PaginatedMeta }

function withQuery(path: string, values: readonly (readonly [string, string | number | boolean | undefined])[]): string {
  const params = new URLSearchParams();
  for (const [key, value] of values) if (value !== undefined && value !== '') params.set(key, String(value));
  const query = params.toString();
  return query ? `${path}?${query}` : path;
}
function page<T>(envelope: PaginatedEnvelope<T>): PageResult<T> { return { items: envelope.data, meta: { ...envelope.meta.pagination, correlation_id: envelope.meta.correlation_id, timestamp: envelope.meta.timestamp } }; }
function data<T>(envelope: ApiEnvelope<T>): T { return envelope.data; }

export class IntegrationPlatformService {
  async listIntegrations(filters: IntegrationFilters = {}): Promise<PageResult<Integration>> {
    const path = withQuery(ENDPOINTS.INTEGRATIONS.LIST, [['page', filters.page], ['page_size', filters.page_size], ['search', filters.search], ['status', filters.status], ['integration_type', filters.integration_type], ['connector_id', filters.connector_id], ['ordering', filters.ordering]]);
    return page(await apiClient.get<PaginatedEnvelope<Integration>>(path));
  }
  async createIntegration(request: IntegrationCreateRequest): Promise<IntegrationDetail> { return data(await apiClient.post<ApiEnvelope<IntegrationDetail>>(ENDPOINTS.INTEGRATIONS.CREATE, request)); }
  async getIntegration(id: string): Promise<IntegrationDetail> { return data(await apiClient.get<ApiEnvelope<IntegrationDetail>>(ENDPOINTS.INTEGRATIONS.DETAIL(id))); }
  async updateIntegration(id: string, request: IntegrationUpdateRequest): Promise<IntegrationDetail> { return data(await apiClient.patch<ApiEnvelope<IntegrationDetail>>(ENDPOINTS.INTEGRATIONS.UPDATE(id), request)); }
  async deleteIntegration(id: string): Promise<void> { await apiClient.delete<void>(ENDPOINTS.INTEGRATIONS.DELETE(id)); }
  async activateIntegration(id: string, request: TransitionRequest): Promise<IntegrationDetail> { return data(await apiClient.post<ApiEnvelope<IntegrationDetail>>(ENDPOINTS.INTEGRATIONS.ACTIVATE(id), request)); }
  async deactivateIntegration(id: string, request: TransitionRequest): Promise<IntegrationDetail> { return data(await apiClient.post<ApiEnvelope<IntegrationDetail>>(ENDPOINTS.INTEGRATIONS.DEACTIVATE(id), request)); }
  async testIntegration(id: string, request: IntegrationTestRequest): Promise<AsyncJobReceipt> { return data(await apiClient.post<ApiEnvelope<AsyncJobReceipt>>(ENDPOINTS.INTEGRATIONS.TEST(id), request)); }
  async syncIntegration(id: string, request: IntegrationSyncRequest): Promise<AsyncJobReceipt> { return data(await apiClient.post<ApiEnvelope<AsyncJobReceipt>>(ENDPOINTS.INTEGRATIONS.SYNC(id), request)); }
  async getIntegrationJob(id: string, jobId: string): Promise<AsyncJobState> { return data(await apiClient.get<ApiEnvelope<AsyncJobState>>(ENDPOINTS.INTEGRATIONS.JOB(id, jobId))); }

  async listCredentials(integrationId: string): Promise<IntegrationCredential[]> { return data(await apiClient.get<ApiEnvelope<IntegrationCredential[]>>(ENDPOINTS.INTEGRATIONS.CREDENTIALS(integrationId))); }
  async createCredential(integrationId: string, request: CredentialCreateRequest): Promise<IntegrationCredential> { return data(await apiClient.post<ApiEnvelope<IntegrationCredential>>(ENDPOINTS.INTEGRATIONS.CREDENTIALS(integrationId), request)); }
  async getCredential(id: string): Promise<IntegrationCredential> { return data(await apiClient.get<ApiEnvelope<IntegrationCredential>>(ENDPOINTS.CREDENTIALS.DETAIL(id))); }
  async rotateCredential(id: string, request: CredentialRotateRequest): Promise<IntegrationCredential> { return data(await apiClient.post<ApiEnvelope<IntegrationCredential>>(ENDPOINTS.CREDENTIALS.ROTATE(id), request)); }
  async revokeCredential(id: string, request: CredentialRevokeRequest): Promise<IntegrationCredential> { return data(await apiClient.post<ApiEnvelope<IntegrationCredential>>(ENDPOINTS.CREDENTIALS.REVOKE(id), request)); }

  async listConnectors(filters: ConnectorFilters = {}): Promise<PageResult<Connector>> {
    const path = withQuery(ENDPOINTS.CONNECTORS.LIST, [['page', filters.page], ['page_size', filters.page_size], ['search', filters.search], ['connector_type', filters.connector_type], ['module_id', filters.module_id], ['is_active', filters.is_active]]);
    return page(await apiClient.get<PaginatedEnvelope<Connector>>(path));
  }
  async getConnector(id: string): Promise<ConnectorDetail> { return data(await apiClient.get<ApiEnvelope<ConnectorDetail>>(ENDPOINTS.CONNECTORS.DETAIL(id))); }
  async getConnectorSchema(id: string): Promise<ConnectorSchema> { return data(await apiClient.get<ApiEnvelope<ConnectorSchema>>(ENDPOINTS.CONNECTORS.SCHEMA(id))); }
  async getConnectorHealth(id: string): Promise<ConnectorHealth> { return data(await apiClient.get<ApiEnvelope<ConnectorHealth>>(ENDPOINTS.CONNECTORS.HEALTH(id))); }

  async listWebhooks(filters: WebhookFilters = {}): Promise<PageResult<Webhook>> {
    const path = withQuery(ENDPOINTS.WEBHOOKS.LIST, [['page', filters.page], ['page_size', filters.page_size], ['search', filters.search], ['direction', filters.direction], ['status', filters.status], ['event', filters.event]]);
    return page(await apiClient.get<PaginatedEnvelope<Webhook>>(path));
  }
  async createWebhook(request: WebhookCreateRequest): Promise<WebhookSecretOnce> { return data(await apiClient.post<ApiEnvelope<WebhookSecretOnce>>(ENDPOINTS.WEBHOOKS.CREATE, request)); }
  async getWebhook(id: string): Promise<WebhookDetail> { return data(await apiClient.get<ApiEnvelope<WebhookDetail>>(ENDPOINTS.WEBHOOKS.DETAIL(id))); }
  async updateWebhook(id: string, request: WebhookUpdateRequest): Promise<WebhookDetail> { return data(await apiClient.patch<ApiEnvelope<WebhookDetail>>(ENDPOINTS.WEBHOOKS.UPDATE(id), request)); }
  async deleteWebhook(id: string): Promise<void> { await apiClient.delete<void>(ENDPOINTS.WEBHOOKS.DELETE(id)); }
  async activateWebhook(id: string, request: TransitionRequest): Promise<WebhookDetail> { return data(await apiClient.post<ApiEnvelope<WebhookDetail>>(ENDPOINTS.WEBHOOKS.ACTIVATE(id), request)); }
  async deactivateWebhook(id: string, request: TransitionRequest): Promise<WebhookDetail> { return data(await apiClient.post<ApiEnvelope<WebhookDetail>>(ENDPOINTS.WEBHOOKS.DEACTIVATE(id), request)); }
  async rotateWebhookSecret(id: string, request: TransitionRequest): Promise<WebhookSecretOnce> { return data(await apiClient.post<ApiEnvelope<WebhookSecretOnce>>(ENDPOINTS.WEBHOOKS.ROTATE_SECRET(id), request)); }
  async receiveInboundWebhook(publicId: string, request: InboundWebhookRequest): Promise<InboundWebhookReceipt> {
    const baseUrl = import.meta.env.VITE_API_BASE_URL ?? '';
    const response = await fetch(`${baseUrl}${ENDPOINTS.WEBHOOKS.INBOUND(publicId)}`, { method: 'POST', credentials: 'omit', headers: { 'Content-Type': 'application/json', [INBOUND_WEBHOOK_HEADERS.TIMESTAMP]: request.timestamp, [INBOUND_WEBHOOK_HEADERS.NONCE]: request.nonce, [INBOUND_WEBHOOK_HEADERS.SIGNATURE]: request.signature }, body: request.raw_body });
    if (!response.ok) throw new ClientApiError('Inbound webhook transport was rejected.', response.status, undefined, 'webhook_rejected', response.headers.get('X-Correlation-ID') ?? undefined);
    const payload: unknown = await response.json();
    const envelope = z.object({ data: z.object({ job_id: z.string().uuid(), correlation_id: z.string(), accepted_at: z.string() }), meta: z.object({ correlation_id: z.string(), timestamp: z.string() }) }).parse(payload);
    return envelope.data;
  }

  async listDeliveries(filters: DeliveryFilters = {}): Promise<PageResult<WebhookDelivery>> {
    const path = withQuery(ENDPOINTS.DELIVERIES.LIST, [['page', filters.page], ['page_size', filters.page_size], ['webhook_id', filters.webhook_id], ['status', filters.status], ['event', filters.event], ['created_after', filters.created_after], ['created_before', filters.created_before]]);
    return page(await apiClient.get<PaginatedEnvelope<WebhookDelivery>>(path));
  }
  async getDelivery(id: string): Promise<WebhookDeliveryDetail> { return data(await apiClient.get<ApiEnvelope<WebhookDeliveryDetail>>(ENDPOINTS.DELIVERIES.DETAIL(id))); }
  async redriveDelivery(id: string, request: DeliveryRedriveRequest): Promise<WebhookDeliveryDetail> { return data(await apiClient.post<ApiEnvelope<WebhookDeliveryDetail>>(ENDPOINTS.DELIVERIES.REDRIVE(id), request)); }

  async listMappings(filters: MappingFilters = {}): Promise<PageResult<DataMapping>> {
    const path = withQuery(ENDPOINTS.MAPPINGS.LIST, [['page', filters.page], ['page_size', filters.page_size], ['search', filters.search], ['integration_id', filters.integration_id], ['source_field', filters.source_field], ['target_field', filters.target_field]]);
    return page(await apiClient.get<PaginatedEnvelope<DataMapping>>(path));
  }
  async createMapping(request: DataMappingCreateRequest): Promise<DataMapping> { return data(await apiClient.post<ApiEnvelope<DataMapping>>(ENDPOINTS.MAPPINGS.CREATE, request)); }
  async getMapping(id: string): Promise<DataMapping> { return data(await apiClient.get<ApiEnvelope<DataMapping>>(ENDPOINTS.MAPPINGS.DETAIL(id))); }
  async updateMapping(id: string, request: DataMappingUpdateRequest): Promise<DataMapping> { return data(await apiClient.patch<ApiEnvelope<DataMapping>>(ENDPOINTS.MAPPINGS.UPDATE(id), request)); }
  async deleteMapping(id: string): Promise<void> { await apiClient.delete<void>(ENDPOINTS.MAPPINGS.DELETE(id)); }
  async validateMappings(request: MappingValidationRequest): Promise<MappingValidationResult> { return data(await apiClient.post<ApiEnvelope<MappingValidationResult>>(ENDPOINTS.MAPPINGS.VALIDATE, request)); }
  async previewMappings(request: MappingPreviewRequest): Promise<MappingPreviewResult> { return data(await apiClient.post<ApiEnvelope<MappingPreviewResult>>(ENDPOINTS.MAPPINGS.PREVIEW, request)); }
  async getHealth(): Promise<IntegrationPlatformHealth> { return data(await apiClient.get<ApiEnvelope<IntegrationPlatformHealth>>(ENDPOINTS.HEALTH)); }
  async getManageCapability(): Promise<IntegrationPlatformManageCapability> { return data(await apiClient.get<ApiEnvelope<IntegrationPlatformManageCapability>>(ENDPOINTS.CONFIGURATION.MANAGE_CAPABILITY)); }
  async getConfiguration(): Promise<IntegrationPlatformConfiguration> { return data(await apiClient.get<ApiEnvelope<IntegrationPlatformConfiguration>>(ENDPOINTS.CONFIGURATION.CURRENT)); }
  async saveConfiguration(request: ConfigurationWriteRequest): Promise<IntegrationPlatformConfiguration> { return data(await apiClient.post<ApiEnvelope<IntegrationPlatformConfiguration>>(ENDPOINTS.CONFIGURATION.CURRENT, request)); }
  async previewConfiguration(request: ConfigurationWriteRequest): Promise<ConfigurationPreview> { return data(await apiClient.post<ApiEnvelope<ConfigurationPreview>>(ENDPOINTS.CONFIGURATION.PREVIEW, request)); }
  async rollbackConfiguration(environment: string, version: number): Promise<IntegrationPlatformConfiguration> { return data(await apiClient.post<ApiEnvelope<IntegrationPlatformConfiguration>>(ENDPOINTS.CONFIGURATION.ROLLBACK, { environment, version })); }
  async importConfiguration(request: ConfigurationWriteRequest): Promise<IntegrationPlatformConfiguration> { return data(await apiClient.post<ApiEnvelope<IntegrationPlatformConfiguration>>(ENDPOINTS.CONFIGURATION.IMPORT, request)); }
  async exportConfiguration(): Promise<{ schema_version: number; environment: string; version: number; document: IntegrationPlatformConfiguration['document'] }> { return data(await apiClient.get<ApiEnvelope<{ schema_version: number; environment: string; version: number; document: IntegrationPlatformConfiguration['document'] }>>(ENDPOINTS.CONFIGURATION.EXPORT)); }
  async listConfigurationVersions(): Promise<PageResult<ConfigurationVersion>> { return page(await apiClient.get<PaginatedEnvelope<ConfigurationVersion>>(ENDPOINTS.CONFIGURATION.VERSIONS)); }
  async listConfigurationAudits(): Promise<PageResult<ConfigurationAudit>> { return page(await apiClient.get<PaginatedEnvelope<ConfigurationAudit>>(ENDPOINTS.CONFIGURATION.AUDITS)); }
}

export const integrationPlatformService = new IntegrationPlatformService();
