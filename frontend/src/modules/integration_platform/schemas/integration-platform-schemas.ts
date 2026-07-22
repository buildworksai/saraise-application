import { z } from 'zod';
import type { JsonValue } from '../contracts';

export const jsonValueSchema: z.ZodType<JsonValue> = z.lazy(() => z.union([z.null(), z.boolean(), z.number().finite(), z.string(), z.array(jsonValueSchema), z.record(z.string(), jsonValueSchema)]));

export const jsonObjectSchema = z.record(z.string(), jsonValueSchema);
export const connectorTypeSchema = z.enum(['api', 'webhook', 'database', 'file', 'message_queue']);
export const credentialTypeSchema = z.enum(['api_key', 'oauth_token', 'username_password', 'certificate']);
export const integrationCreateSchema = z.object({ connector_id: z.string().uuid(), name: z.string().trim().min(1).max(255), description: z.string().trim().max(4000).optional(), integration_type: connectorTypeSchema, config: jsonObjectSchema });
export const credentialCreateSchema = z.object({ credential_type: credentialTypeSchema, plaintext: z.string().min(1).max(10000), expires_at: z.string().datetime().nullable().optional() });
export const webhookSchema = z.object({ name: z.string().trim().min(1).max(255), direction: z.enum(['inbound', 'outbound']), url: z.string().url().max(2000).optional().or(z.literal('')), events: z.array(z.string().trim().min(1)).min(1).refine((values) => new Set(values).size === values.length, 'Events must be unique.'), config: jsonObjectSchema.optional(), timeout_seconds: z.number().int().min(1).max(30), max_attempts: z.number().int().min(1).max(10) }).superRefine((value, context) => { if (value.direction === 'outbound' && !value.url) context.addIssue({ code: z.ZodIssueCode.custom, path: ['url'], message: 'Outbound webhooks require a URL.' }); if (value.direction === 'inbound' && value.url) context.addIssue({ code: z.ZodIssueCode.custom, path: ['url'], message: 'Inbound webhooks do not accept an outbound URL.' }); });
export const transformationSchema = z.object({ operation: z.enum(['rename', 'string_case', 'trim', 'number', 'date_format', 'default', 'enum_map']), options: jsonObjectSchema.optional() });
export const mappingSchema = z.object({ integration_id: z.string().uuid(), name: z.string().trim().min(1).max(255), source_field: z.string().trim().min(1).max(255), target_field: z.string().trim().min(1).max(255), transform: transformationSchema, position: z.number().int().nonnegative(), is_required: z.boolean(), default_value: jsonValueSchema.optional() });
