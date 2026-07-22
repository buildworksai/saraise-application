/* eslint-disable @typescript-eslint/unbound-method, @typescript-eslint/consistent-type-imports -- Vitest mocks intentionally reference object methods and import-original types */
import { ApiError, apiClient } from '@/services/api-client';
import { crmService } from '../services/crm-service';
import type { CrmApiError } from '../services/crm-service';

vi.mock('@/services/api-client', async importOriginal => {
  const actual = await importOriginal<typeof import('@/services/api-client')>();
  return { ...actual, apiClient: { get: vi.fn(), post: vi.fn(), patch: vi.fn(), delete: vi.fn() } };
});

const meta = { correlation_id: 'req-crm-1', timestamp: '2026-07-22T00:00:00Z' };
const lead = { id:'11111111-1111-4111-8111-111111111111',tenant_id:'22222222-2222-4222-8222-222222222222',created_at:meta.timestamp,updated_at:meta.timestamp,created_by:null,updated_by:null,version:3,is_deleted:false,deleted_at:null,metadata:{},first_name:'Ada',last_name:'Lovelace',email:'ada@example.test',phone:'',company:'Analytical',title:'',score:82,grade:'A',score_source:'rules',score_explanation:{source:'profile'},source:'referral',campaign_id:null,owner_id:null,status:'qualified',converted_at:null,converted_to_opportunity_id:null,transition_history:[] };

describe('crmService governed decoding', () => {
  beforeEach(() => vi.clearAllMocks());
  it('decodes page envelopes and serializes zero-valued filters', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data:[lead], meta:{...meta,pagination:{page:1,page_size:25,total_pages:1,count:1,has_next:false,has_previous:false}} });
    const result = await crmService.listLeads({ score_min:0, search:'Ada Lovelace', page:1 });
    expect(result.items[0]?.last_name).toBe('Lovelace');
    expect(result.correlationId).toBe('req-crm-1');
    expect(vi.mocked(apiClient.get).mock.calls[0]?.[0]).toContain('score_min=0');
    expect(vi.mocked(apiClient.get).mock.calls[0]?.[0]).toContain('search=Ada+Lovelace');
  });

  it('sends optimistic concurrency in payload and If-Match', async () => {
    vi.mocked(apiClient.patch).mockResolvedValue({ data:lead, meta });
    await crmService.updateLead(lead.id, { company:'Difference Engine', version:3 });
    expect(apiClient.patch).toHaveBeenCalledWith(expect.stringContaining(lead.id), expect.objectContaining({version:3}), {headers:{'If-Match':'3'}});
  });

  it.each([[401,'authentication'],[403,'permission'],[404,'not_found'],[409,'conflict'],[422,'validation'],[429,'rate_limit'],[503,'unavailable']] as const)('maps %s distinctly', async (status, kind) => {
    vi.mocked(apiClient.get).mockRejectedValue(new ApiError('governed failure',status,{},'domain_error','req-error'));
    await expect(crmService.getLead(lead.id)).rejects.toMatchObject({kind,status,correlationId:'req-error'} satisfies Partial<CrmApiError>);
  });

  it('never accepts malformed success as an entity', async () => {
    vi.mocked(apiClient.get).mockResolvedValue({ data:{id:lead.id}, meta });
    await expect(crmService.getLead(lead.id)).rejects.toMatchObject({kind:'invalid_response'});
  });
});
