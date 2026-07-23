/** Authoritative typed contract for the governed procurement API v2. */
export type SupplierStatus = 'active' | 'inactive' | 'archived';
export type RequisitionStatus = 'draft' | 'pending_approval' | 'approved' | 'rejected' | 'converted' | 'cancelled';
export type RFQStatus = 'draft' | 'open' | 'closed' | 'awarded' | 'cancelled';
export type QuoteStatus = 'draft' | 'submitted' | 'withdrawn' | 'accepted' | 'rejected';
export type PurchaseOrderStatus = 'draft' | 'pending_approval' | 'approved' | 'sent' | 'acknowledged' | 'partially_received' | 'received' | 'cancelled';
export type ReceiptStatus = 'draft' | 'completed' | 'cancelled';
export type ConfigurationStatus = 'draft' | 'active' | 'archived';
export type ConfigurationEnvironment = 'development' | 'staging' | 'production';
export type ReceiptCondition = 'accepted' | 'damaged' | 'rejected';

export interface PaginationMeta { count: number; page: number; page_size: number; total_pages: number; has_next: boolean; has_previous: boolean }
export interface ApiV2Meta { correlation_id: string; timestamp: string }
export interface ApiV2Envelope<T> { data: T; meta: ApiV2Meta }
export interface ApiV2PaginatedEnvelope<T> { data: T[]; meta: ApiV2Meta & { pagination: PaginationMeta } }
export interface MutationContext { idempotencyKey: string; lockVersion?: number }
export interface AuditedRecord { id: string; lock_version: number; created_at: string; updated_at: string; created_by: string; updated_by: string }

export interface Supplier extends AuditedRecord { supplier_code: string; supplier_name: string; email: string; phone: string; address: string; payment_terms: string; currency: string; status: SupplierStatus; archived_at: string | null; archived_by: string | null }
export interface SupplierWrite { supplier_code: string; supplier_name: string; email?: string; phone?: string; address?: string; payment_terms: string; currency: string }
export type SupplierCreate = SupplierWrite;

export interface RequisitionLine extends AuditedRecord { line_number: number; item_id: string | null; item_code: string; description: string; quantity: string; estimated_unit_price: string; estimated_total: string; preferred_supplier_id: string | null; notes: string }
export interface RequisitionLineWrite { line_number?: number; item_id?: string | null; item_code: string; description: string; quantity: string; estimated_unit_price: string; preferred_supplier_id?: string | null; notes?: string }
export interface PurchaseRequisition extends AuditedRecord { requisition_number: string; requisition_date: string; required_date: string; purpose: string; status: RequisitionStatus; requested_by: string; approved_by: string | null; approved_at: string | null; rejection_reason: string; converted_order_id: string | null; total_amount: string; currency: string; lines: RequisitionLine[] }
export interface RequisitionWrite { requisition_number?: string; requisition_date: string; required_date: string; purpose: string; currency: string; lines: RequisitionLineWrite[] }

export interface RFQLine extends AuditedRecord { line_number: number; requisition_line: string | null; item_id: string | null; item_code: string; description: string; quantity: string; required_date: string; specification: string }
export interface RFQLineWrite { line_number?: number; requisition_line_id?: string | null; item_id?: string | null; item_code: string; description: string; quantity: string; required_date: string; specification?: string }
export interface RFQInvitation extends AuditedRecord { supplier: string; supplier_name: string; status: 'pending' | 'queued' | 'sent' | 'delivered' | 'failed' | 'responded'; sent_at: string | null; delivered_at: string | null; failure_code: string; failure_message: string; job_id: string | null }
export interface RequestForQuotation extends AuditedRecord { rfq_number: string; title: string; requisition: string | null; issue_date: string; submission_deadline: string; currency: string; status: RFQStatus; terms: string; delivery_requirements: string; awarded_quote_id: string | null; lines: RFQLine[]; invitations: RFQInvitation[] }
export interface RFQWrite { rfq_number?: string; title: string; requisition_id?: string | null; issue_date: string; submission_deadline: string; currency: string; terms?: string; delivery_requirements?: string; lines: RFQLineWrite[] }

export interface QuoteLine extends AuditedRecord { rfq_line: string; quantity: string; unit_price: string; tax_amount: string; line_total: string; lead_time_days: number | null; notes: string }
export interface QuoteLineWrite { rfq_line_id: string; quantity: string; unit_price: string; tax_amount?: string; lead_time_days?: number | null; notes?: string }
export interface SupplierQuote extends AuditedRecord { quote_number: string; rfq: string; supplier: string; supplier_name: string; valid_until: string; currency: string; status: QuoteStatus; subtotal: string; tax_amount: string; shipping_amount: string; total_amount: string; delivery_date: string | null; payment_terms: string; supplier_notes: string; submitted_at: string | null; lines: QuoteLine[] }
export interface QuoteWrite { quote_number?: string; rfq_id: string; supplier_id: string; valid_until: string; currency: string; delivery_date?: string | null; payment_terms: string; shipping_amount?: string; supplier_notes?: string; lines: QuoteLineWrite[] }

export interface PurchaseOrderLine extends AuditedRecord { line_number: number; item_id: string | null; item_code: string; item_name: string; quantity: string; unit_price: string; tax_amount: string; total_price: string; received_quantity: string; cancelled_quantity: string }
export interface PurchaseOrderLineWrite { line_number?: number; requisition_line_id?: string | null; quote_line_id?: string | null; item_id?: string | null; item_code: string; item_name: string; quantity: string; unit_price: string; tax_amount?: string }
export interface PurchaseOrder extends AuditedRecord { po_number: string; po_date: string; supplier: string; supplier_name: string; expected_delivery_date: string | null; total_amount: string; currency: string; status: PurchaseOrderStatus; requisition: string | null; rfq: string | null; accepted_quote: string | null; payment_terms: string; delivery_terms: string; shipping_address: Record<string, string>; notes: string; dispatch_status: 'not_requested' | 'queued' | 'sent' | 'failed'; dispatch_job_id: string | null; acknowledged_at: string | null; lines: PurchaseOrderLine[] }
export interface PurchaseOrderWrite { po_number?: string; po_date: string; supplier_id: string; expected_delivery_date?: string | null; currency: string; requisition_id?: string | null; rfq_id?: string | null; accepted_quote_id?: string | null; payment_terms: string; delivery_terms?: string; shipping_address?: Record<string, string>; notes?: string; lines: PurchaseOrderLineWrite[] }

export interface ReceiptLine extends AuditedRecord { line_number: number; purchase_order_line: string; item_id: string | null; quantity_received: string; condition: ReceiptCondition; batch_no: string; serial_no: string; notes: string }
export interface ReceiptLineWrite { line_number?: number; purchase_order_line_id: string; quantity_received: string; condition?: ReceiptCondition; batch_no?: string; serial_no?: string; notes?: string }
export interface PurchaseReceipt extends AuditedRecord { receipt_number: string; receipt_date: string; purchase_order: string; po_number: string; warehouse_id: string; status: ReceiptStatus; inventory_status: 'not_required' | 'pending' | 'posted' | 'failed'; inventory_reference: string | null; inventory_job_id: string | null; failure_code: string; failure_message: string; lines: ReceiptLine[] }
export interface ReceiptWrite { receipt_number?: string; receipt_date: string; purchase_order_id: string; warehouse_id: string; lines: ReceiptLineWrite[] }

export interface ApprovalRule { minimum_amount: string; maximum_amount?: string; category?: string; approver_permission: string }
export interface QuoteScoringWeights { price: number; delivery: number; quality: number; service: number }
export interface RolloutConfiguration { roles: string[]; cohorts: string[]; percentage: number }
export interface ConfigurationWrite { default_currency: string; default_payment_terms: string; supplier_code_prefix: string; requisition_prefix: string; rfq_prefix: string; po_prefix: string; receipt_prefix: string; approval_rules: ApprovalRule[]; receipt_tolerance_percent: string; minimum_rfq_suppliers: number; quote_scoring_weights: QuoteScoringWeights; inventory_integration_enabled: boolean; accounting_integration_enabled: boolean; supplier_delivery_enabled: boolean; rollout: RolloutConfiguration }
export interface ProcurementConfiguration extends AuditedRecord, ConfigurationWrite { environment: ConfigurationEnvironment; version: number; status: ConfigurationStatus; activated_at: string | null; activated_by: string | null }
export interface ConfigurationDiff { field: string; before: unknown; after: unknown }
export interface ConfigurationPreview { valid: boolean; diff: ConfigurationDiff[]; affected_workflows: string[]; simulations: { input: Record<string, unknown>; approval_required: boolean; matched_rules: ApprovalRule[] }[]; restart_required: boolean }
export interface ConfigurationDocument { schema: 'saraise.purchase.configuration.v1'; configuration: Record<string, unknown>; checksum: string }
export interface QuoteComparison { rfq_id: string; quotes: { quote_id: string; supplier_id: string; total_amount: string; delivery_date: string | null; components: { price: string; delivery: string; quality: null; service: null }; configured_score: string; warnings: string[] }[]; weights?: QuoteScoringWeights; warnings?: string[] }
export interface ProcurementJob { id: string; command: string; status: 'queued' | 'running' | 'succeeded' | 'failed' | 'cancelled' | 'timed_out' | 'retrying'; attempts: number; result: unknown; error_message: string; correlation_id: string; created_at: string; updated_at: string }
export interface ModuleHealth { status: 'healthy' | 'degraded' | 'unhealthy'; checks: Record<string, unknown> }

export interface ListFilters { page?: number; page_size?: number; search?: string; status?: string; ordering?: string; [key: string]: string | number | undefined }
export type SupplierFilters = ListFilters & { currency?: string; ordering?: 'supplier_code' | 'supplier_name' | '-created_at' };
export type RequisitionFilters = ListFilters & { requester?: string; ordering?: '-requisition_date' | 'required_date' | 'requisition_number' };
export type RFQFilters = ListFilters & { supplier?: string; ordering?: '-issue_date' | 'submission_deadline' | 'rfq_number' };
export type QuoteFilters = ListFilters & { rfq?: string; supplier?: string; ordering?: 'total_amount' | 'delivery_date' | '-submitted_at' };
export type PurchaseOrderFilters = ListFilters & { supplier?: string; requisition?: string; ordering?: '-po_date' | 'expected_delivery_date' | 'total_amount' };
export type ReceiptFilters = ListFilters & { order?: string; warehouse?: string; ordering?: '-receipt_date' | 'receipt_number' };

export const ROUTES = {
  SUPPLIERS: { LIST: '/purchase-management/suppliers', CREATE: '/purchase-management/suppliers/new', DETAIL: (id = ':id') => `/purchase-management/suppliers/${id}`, EDIT: (id = ':id') => `/purchase-management/suppliers/${id}/edit` },
  REQUISITIONS: { LIST: '/purchase-management/requisitions', CREATE: '/purchase-management/requisitions/new', DETAIL: (id = ':id') => `/purchase-management/requisitions/${id}`, EDIT: (id = ':id') => `/purchase-management/requisitions/${id}/edit` },
  RFQS: { LIST: '/purchase-management/rfqs', CREATE: '/purchase-management/rfqs/new', DETAIL: (id = ':id') => `/purchase-management/rfqs/${id}`, EDIT: (id = ':id') => `/purchase-management/rfqs/${id}/edit` },
  QUOTES: { LIST: '/purchase-management/quotes', CREATE: '/purchase-management/quotes/new', DETAIL: (id = ':id') => `/purchase-management/quotes/${id}`, EDIT: (id = ':id') => `/purchase-management/quotes/${id}/edit` },
  ORDERS: { LIST: '/purchase-management/purchase-orders', CREATE: '/purchase-management/purchase-orders/new', DETAIL: (id = ':id') => `/purchase-management/purchase-orders/${id}`, EDIT: (id = ':id') => `/purchase-management/purchase-orders/${id}/edit` },
  RECEIPTS: { LIST: '/purchase-management/receipts', CREATE: '/purchase-management/receipts/new', DETAIL: (id = ':id') => `/purchase-management/receipts/${id}`, EDIT: (id = ':id') => `/purchase-management/receipts/${id}/edit` },
  SETTINGS: '/purchase-management/settings', CONFIGURATION_VERSION: (id = ':id') => `/purchase-management/settings/versions/${id}`, CONFIGURATION_IMPORT: '/purchase-management/settings/import',
} as const;

export const MODULE_API_PREFIX = '/api/v2/purchase-management';
const resource = (name: string) => ({ LIST: `${MODULE_API_PREFIX}/${name}/`, CREATE: `${MODULE_API_PREFIX}/${name}/`, DETAIL: (id: string) => `${MODULE_API_PREFIX}/${name}/${id}/`, UPDATE: (id: string) => `${MODULE_API_PREFIX}/${name}/${id}/`, DELETE: (id: string) => `${MODULE_API_PREFIX}/${name}/${id}/` } as const);
export const ENDPOINTS = {
  SUPPLIERS: { ...resource('suppliers'), ACTIVATE: (id: string) => `${MODULE_API_PREFIX}/suppliers/${id}/activate/`, DEACTIVATE: (id: string) => `${MODULE_API_PREFIX}/suppliers/${id}/deactivate/` },
  REQUISITIONS: { ...resource('requisitions'), SUBMIT: (id: string) => `${MODULE_API_PREFIX}/requisitions/${id}/submit/`, APPROVE: (id: string) => `${MODULE_API_PREFIX}/requisitions/${id}/approve/`, REJECT: (id: string) => `${MODULE_API_PREFIX}/requisitions/${id}/reject/`, REVISE: (id: string) => `${MODULE_API_PREFIX}/requisitions/${id}/revise/`, CANCEL: (id: string) => `${MODULE_API_PREFIX}/requisitions/${id}/cancel/`, CONVERT: (id: string) => `${MODULE_API_PREFIX}/requisitions/${id}/convert-to-order/` },
  RFQS: { ...resource('rfqs'), PUBLISH: (id: string) => `${MODULE_API_PREFIX}/rfqs/${id}/publish/`, CLOSE: (id: string) => `${MODULE_API_PREFIX}/rfqs/${id}/close/`, CANCEL: (id: string) => `${MODULE_API_PREFIX}/rfqs/${id}/cancel/`, COMPARE: (id: string) => `${MODULE_API_PREFIX}/rfqs/${id}/compare-quotes/`, AWARD: (id: string) => `${MODULE_API_PREFIX}/rfqs/${id}/award/` },
  QUOTES: { ...resource('quotes'), SUBMIT: (id: string) => `${MODULE_API_PREFIX}/quotes/${id}/submit/`, WITHDRAW: (id: string) => `${MODULE_API_PREFIX}/quotes/${id}/withdraw/` },
  PURCHASE_ORDERS: { ...resource('purchase-orders'), SUBMIT: (id: string) => `${MODULE_API_PREFIX}/purchase-orders/${id}/submit/`, APPROVE: (id: string) => `${MODULE_API_PREFIX}/purchase-orders/${id}/approve/`, REJECT: (id: string) => `${MODULE_API_PREFIX}/purchase-orders/${id}/reject/`, DISPATCH: (id: string) => `${MODULE_API_PREFIX}/purchase-orders/${id}/dispatch/`, ACKNOWLEDGE: (id: string) => `${MODULE_API_PREFIX}/purchase-orders/${id}/acknowledge/`, CANCEL: (id: string) => `${MODULE_API_PREFIX}/purchase-orders/${id}/cancel/` },
  RECEIPTS: { ...resource('receipts'), COMPLETE: (id: string) => `${MODULE_API_PREFIX}/receipts/${id}/complete/`, CANCEL: (id: string) => `${MODULE_API_PREFIX}/receipts/${id}/cancel/` },
  CONFIGURATIONS: { ACTIVE: `${MODULE_API_PREFIX}/configurations/active/`, VERSIONS: `${MODULE_API_PREFIX}/configurations/versions/`, VERSION: (id: string) => `${MODULE_API_PREFIX}/configurations/versions/${id}/`, PREVIEW: `${MODULE_API_PREFIX}/configurations/preview/`, ACTIVATE: (id: string) => `${MODULE_API_PREFIX}/configurations/versions/${id}/activate/`, ROLLBACK: (id: string) => `${MODULE_API_PREFIX}/configurations/versions/${id}/rollback/`, EXPORT: `${MODULE_API_PREFIX}/configurations/export/`, IMPORT: `${MODULE_API_PREFIX}/configurations/import/` },
  HEALTH: `${MODULE_API_PREFIX}/health/`, JOB: (id: string) => `${MODULE_API_PREFIX}/jobs/${id}/`,
} as const;
