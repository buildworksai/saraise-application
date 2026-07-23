/** Typed public contract for the open-source quote-to-delivery funnel. */
export type UUID = string;
export type ISODate = string;
export type ISODateTime = string;
export type DecimalString = string;

export interface PaginationMeta { page: number; page_size: number; count: number; total_pages: number; has_next: boolean; has_previous: boolean }
export interface ApiMeta { correlation_id: UUID; timestamp: ISODateTime; pagination?: PaginationMeta }
export interface ApiV2Envelope<T> { data: T; meta: ApiMeta }
export interface ApiV2Page<T> { data: T[]; meta: ApiMeta & { pagination: PaginationMeta } }
export interface ApiV2Error { error: { code: string; message: string; detail: Record<string, unknown>; correlation_id: UUID } }
export interface CapabilityState { available: boolean; reason_code?: string; message?: string }
export interface ResourceCapability { key: string; state: 'available' | 'degraded' | 'not_configured' | 'unavailable'; reason_code: string }
export interface TransitionRecord { command: string; from_status: string; to_status: string; actor_id: UUID; correlation_id: UUID; occurred_at: ISODateTime; reason?: string }

export type QuotationStatus = 'draft' | 'sent' | 'accepted' | 'rejected' | 'expired' | 'converted';
export type SalesOrderStatus = 'draft' | 'confirmed' | 'picking' | 'packing' | 'ready_to_ship' | 'shipped' | 'delivered' | 'invoiced' | 'cancelled';
export type DeliveryNoteStatus = 'draft' | 'completed' | 'cancelled';
export type DocumentKind = 'quotation' | 'sales_order' | 'delivery_note';

interface MutableEntity {
  id: UUID; tenant_id: UUID; created_at: ISODateTime; updated_at: ISODateTime;
  created_by: UUID; updated_by: UUID; deleted_at: ISODateTime | null; deleted_by: UUID | null; lock_version: number;
}

export interface Customer extends MutableEntity {
  customer_code: string; customer_name: string; email: string; phone: string; address: string;
  credit_limit: DecimalString | null; currency: string; is_active: boolean;
}
export interface CustomerCreate { customer_code: string; customer_name: string; email?: string; phone?: string; address?: string; credit_limit?: DecimalString | null; currency: string; is_active?: boolean }
export type CustomerUpdate = Partial<CustomerCreate> & { expected_version: number };

export interface QuotationLine extends MutableEntity {
  quotation: UUID; line_number: number; item_id: UUID | null; item_code: string; item_name: string; description: string;
  quantity: DecimalString; unit_price: DecimalString; discount_percent: DecimalString;
  gross_amount: DecimalString; discount_amount: DecimalString; tax_amount: DecimalString; line_total: DecimalString;
}
export interface QuotationLineInput { line_number?: number; item_id?: UUID | null; item_code: string; item_name: string; description?: string; quantity: DecimalString; unit_price: DecimalString; discount_percent?: DecimalString; tax_amount?: DecimalString }
export interface Quotation extends MutableEntity {
  quotation_number: string; quotation_date: ISODate; valid_until: ISODate; customer: UUID; customer_name?: string;
  currency: string; subtotal_amount: DecimalString; discount_amount: DecimalString; tax_amount: DecimalString; total_amount: DecimalString;
  status: QuotationStatus; revision_number: number; revision_of: UUID | null; notes: string; transition_history: TransitionRecord[];
  lines: QuotationLine[]; allowed_commands: string[]; capabilities: ResourceCapability[];
}
export interface QuotationCreate { quotation_date: ISODate; valid_until: ISODate; customer: UUID; currency: string; notes?: string; lines: QuotationLineInput[] }
export type QuotationUpdate = Partial<QuotationCreate> & { expected_version: number };
export interface QuotationPreview extends Pick<Quotation, 'subtotal_amount' | 'discount_amount' | 'tax_amount' | 'total_amount'> { lines: Array<Pick<QuotationLine, 'line_number' | 'gross_amount' | 'discount_amount' | 'tax_amount' | 'line_total'>>; warnings?: string[] }

export interface SalesOrderLine extends MutableEntity {
  sales_order: UUID; source_quotation_line_id: UUID | null; line_number: number; item_id: UUID | null; item_code: string;
  item_name: string; description: string; quantity: DecimalString; unit_price: DecimalString; discount_percent: DecimalString;
  gross_amount: DecimalString; discount_amount: DecimalString; tax_amount: DecimalString; total_price: DecimalString; delivered_quantity: DecimalString;
}
export interface SalesOrderLineInput { line_number?: number; source_quotation_line_id?: UUID | null; item_id?: UUID | null; item_code: string; item_name: string; description?: string; quantity: DecimalString; unit_price: DecimalString; discount_percent?: DecimalString; tax_amount?: DecimalString }
export interface SalesOrder extends MutableEntity {
  order_number: string; order_date: ISODate; delivery_date: ISODate | null; customer: UUID; customer_name?: string; quotation: UUID | null;
  currency: string; subtotal_amount: DecimalString; discount_amount: DecimalString; tax_amount: DecimalString; total_amount: DecimalString;
  status: SalesOrderStatus; warehouse_id: UUID | null; external_invoice_id: UUID | null; notes: string;
  transition_history: TransitionRecord[]; lines: SalesOrderLine[]; delivery_notes?: DeliveryNote[]; allowed_commands: string[]; capabilities: ResourceCapability[];
}
export interface SalesOrderCreate { order_date: ISODate; delivery_date?: ISODate | null; customer: UUID; quotation?: UUID | null; currency: string; warehouse_id?: UUID | null; notes?: string; lines: SalesOrderLineInput[] }
export type SalesOrderUpdate = Partial<SalesOrderCreate> & { expected_version: number };

export interface DeliveryNoteLine extends MutableEntity { delivery_note: UUID; sales_order_line: UUID; line_number: number; item_id: UUID | null; quantity_delivered: DecimalString; batch_number: string; serial_number: string }
export interface DeliveryNoteLineInput { sales_order_line: UUID; line_number?: number; item_id?: UUID | null; quantity_delivered: DecimalString; batch_number?: string; serial_number?: string }
export interface DeliveryNote extends MutableEntity {
  delivery_number: string; delivery_date: ISODate; sales_order: UUID; order_number?: string; warehouse_id: UUID | null;
  carrier_name: string; tracking_number: string; proof_document_id: UUID | null; status: DeliveryNoteStatus; notes: string;
  transition_history: TransitionRecord[]; lines: DeliveryNoteLine[]; allowed_commands: string[]; capabilities: ResourceCapability[];
}
export interface DeliveryNoteCreate { delivery_date: ISODate; sales_order: UUID; warehouse_id?: UUID | null; carrier_name?: string; tracking_number?: string; proof_document_id?: UUID | null; notes?: string; lines: DeliveryNoteLineInput[] }
export type DeliveryNoteUpdate = Partial<DeliveryNoteCreate> & { expected_version: number };

export interface CommandPayload { idempotency_key: UUID; reason?: string; invoice_id?: UUID }
export interface CommandResponse<T> { resource: T; command: string; replayed?: boolean }
export type QuotationCommandPayload = CommandPayload;
export type QuotationCommandResponse = Quotation | SalesOrder;
export type SalesOrderCommandPayload = CommandPayload;
export type SalesOrderCommandResponse = CommandResponse<SalesOrder>;
export type DeliveryNoteCommandPayload = CommandPayload;
export type DeliveryNoteCommandResponse = CommandResponse<DeliveryNote>;
export interface DeletePayload { expected_version: number }

export type Ordering<T extends string> = T | `-${T}`;
export interface PageFilters { page?: number; page_size?: number }
export interface CustomerFilters extends PageFilters { search?: string; is_active?: boolean; currency?: string; ordering?: Ordering<'customer_code' | 'customer_name' | 'created_at'> }
export interface QuotationFilters extends PageFilters { search?: string; customer_id?: UUID; status?: QuotationStatus; currency?: string; date_from?: ISODate; date_to?: ISODate; valid_until_from?: ISODate; valid_until_to?: ISODate; ordering?: Ordering<'quotation_number' | 'quotation_date' | 'valid_until' | 'total_amount' | 'created_at'> }
export interface SalesOrderFilters extends PageFilters { search?: string; customer_id?: UUID; quotation_id?: UUID; status?: SalesOrderStatus; warehouse_id?: UUID; currency?: string; date_from?: ISODate; date_to?: ISODate; delivery_from?: ISODate; delivery_to?: ISODate; ordering?: Ordering<'order_number' | 'order_date' | 'delivery_date' | 'total_amount' | 'created_at'> }
export interface DeliveryNoteFilters extends PageFilters { search?: string; sales_order_id?: UUID; status?: DeliveryNoteStatus; warehouse_id?: UUID; date_from?: ISODate; date_to?: ISODate; tracking_number?: string; ordering?: Ordering<'delivery_number' | 'delivery_date' | 'created_at'> }

export type RoundingMode = 'ROUND_HALF_UP' | 'ROUND_HALF_EVEN';
export interface SalesConfiguration extends MutableEntity { environment: string; default_currency: string; currency_decimal_places: number; rounding_mode: RoundingMode; quotation_validity_days: number; credit_check_enabled: boolean; inventory_confirmation_required: boolean; manual_discount_enabled: boolean; maximum_manual_discount_percent: DecimalString; manual_tax_enabled: boolean; quotation_prefix: string; order_prefix: string; delivery_prefix: string; sequence_padding: number; version: number }
export type SalesConfigurationValues = Pick<SalesConfiguration, 'default_currency' | 'currency_decimal_places' | 'rounding_mode' | 'quotation_validity_days' | 'credit_check_enabled' | 'inventory_confirmation_required' | 'manual_discount_enabled' | 'maximum_manual_discount_percent' | 'manual_tax_enabled' | 'quotation_prefix' | 'order_prefix' | 'delivery_prefix' | 'sequence_padding'>;
export interface ConfigurationDiff { field: keyof SalesConfigurationValues; before: string | number | boolean | null; after: string | number | boolean | null }
export interface ConfigurationPreview { valid: boolean; errors?: Record<string, string[]>; diff: ConfigurationDiff[]; affected_workflows: string[]; restart_required: boolean; proposed?: SalesConfigurationValues }
export interface SalesConfigurationVersion { id: UUID; tenant_id: UUID; configuration_id: UUID; version: number; snapshot: SalesConfigurationValues; change_reason: string; actor_id: UUID; correlation_id: UUID; created_at: ISODateTime }
export interface ConfigurationChange { expected_version: number; values: Partial<SalesConfigurationValues>; reason: string }
export interface ConfigurationRollback { target_version: number; expected_version: number; reason: string; idempotency_key: UUID }
export interface ConfigurationExport { schema_version: 1; environment: string; exported_at: ISODateTime; values: SalesConfigurationValues }
export interface ConfigurationImport { expected_version: number; document: ConfigurationExport; dry_run: boolean; reason: string }
export interface SalesHealth { status: 'available' | 'degraded' | 'unavailable'; database: CapabilityState; outbox: CapabilityState; adapters: Record<string, 'available' | 'degraded' | 'not_configured'> }
export interface SalesDashboardDelivery { id: UUID; delivery_number: string; delivery_date: ISODate; status: DeliveryNoteStatus }
export interface SalesDashboardSummary { open_quotations: number; confirmed_orders: number; fulfillment_stages: Record<string, number>; recent_deliveries: SalesDashboardDelivery[] }
export type SalesCapabilityStatus = 'available' | 'not_installed' | 'not_entitled' | 'not_configured' | 'temporarily_unavailable';
export interface SalesExtensionCapability { capability: string; status: SalesCapabilityStatus; reason_code: string; provider_id: string | null; provider_version: string | null }

export const MODULE_API_PREFIX = '/api/v2/sales-management' as const;
const encoded = (value: string | number) => encodeURIComponent(String(value));
export const ENDPOINTS = {
  SUMMARY: `${MODULE_API_PREFIX}/summary/`,
  CAPABILITIES: `${MODULE_API_PREFIX}/capabilities/`,
  CUSTOMERS: { LIST: `${MODULE_API_PREFIX}/customers/`, CREATE: `${MODULE_API_PREFIX}/customers/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/customers/${encoded(id)}/`, UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/customers/${encoded(id)}/`, DELETE: (id: UUID) => `${MODULE_API_PREFIX}/customers/${encoded(id)}/` },
  QUOTATIONS: { LIST: `${MODULE_API_PREFIX}/quotations/`, CREATE: `${MODULE_API_PREFIX}/quotations/`, PREVIEW: `${MODULE_API_PREFIX}/quotations/preview/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/quotations/${encoded(id)}/`, UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/quotations/${encoded(id)}/`, DELETE: (id: UUID) => `${MODULE_API_PREFIX}/quotations/${encoded(id)}/`, COMMAND: (id: UUID, command: 'send'|'accept'|'reject'|'expire'|'revise'|'convert') => `${MODULE_API_PREFIX}/quotations/${encoded(id)}/commands/${encoded(command)}/` },
  SALES_ORDERS: { LIST: `${MODULE_API_PREFIX}/sales-orders/`, CREATE: `${MODULE_API_PREFIX}/sales-orders/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/sales-orders/${encoded(id)}/`, UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/sales-orders/${encoded(id)}/`, DELETE: (id: UUID) => `${MODULE_API_PREFIX}/sales-orders/${encoded(id)}/`, COMMAND: (id: UUID, command: 'confirm'|'start-picking'|'start-packing'|'mark-ready'|'ship'|'deliver'|'mark-invoiced'|'cancel') => `${MODULE_API_PREFIX}/sales-orders/${encoded(id)}/commands/${encoded(command)}/` },
  DELIVERY_NOTES: { LIST: `${MODULE_API_PREFIX}/delivery-notes/`, CREATE: `${MODULE_API_PREFIX}/delivery-notes/`, DETAIL: (id: UUID) => `${MODULE_API_PREFIX}/delivery-notes/${encoded(id)}/`, UPDATE: (id: UUID) => `${MODULE_API_PREFIX}/delivery-notes/${encoded(id)}/`, DELETE: (id: UUID) => `${MODULE_API_PREFIX}/delivery-notes/${encoded(id)}/`, COMMAND: (id: UUID, command: 'complete'|'cancel') => `${MODULE_API_PREFIX}/delivery-notes/${encoded(id)}/commands/${encoded(command)}/` },
  CONFIGURATION: { CURRENT: `${MODULE_API_PREFIX}/configuration/`, PREVIEW: `${MODULE_API_PREFIX}/configuration/preview/`, VERSIONS: `${MODULE_API_PREFIX}/configuration/versions/`, VERSION: (version: number) => `${MODULE_API_PREFIX}/configuration/versions/${encoded(version)}/`, ROLLBACK: `${MODULE_API_PREFIX}/configuration/rollback/`, EXPORT: `${MODULE_API_PREFIX}/configuration/export/`, IMPORT: `${MODULE_API_PREFIX}/configuration/import/` },
  HEALTH: `${MODULE_API_PREFIX}/health/`,
} as const;

export const SALES_PATHS = { OVERVIEW: '/sales-management', CUSTOMERS: '/sales-management/customers', QUOTATIONS: '/sales-management/quotations', ORDERS: '/sales-management/sales-orders', DELIVERIES: '/sales-management/deliveries', CONFIGURATION: '/sales-management/configuration' } as const;
