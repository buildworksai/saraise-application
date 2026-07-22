import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { CampaignForm } from '../components/CampaignForm';
import { Page } from '../components/EmailMarketingUI';
import { ROUTES } from '../contracts';
import { EMAIL_MARKETING_QUERY_KEYS, emailMarketingService } from '../services/email-marketing-service';
export function CreateEmailCampaignPage() { const navigate = useNavigate(); const client = useQueryClient(); const mutation = useMutation({ mutationFn: emailMarketingService.campaigns.create, onSuccess: async (result) => { await client.invalidateQueries({ queryKey: EMAIL_MARKETING_QUERY_KEYS.all }); navigate(ROUTES.CAMPAIGN_DETAIL(result.data.id)); } }); return <Page title="Create email campaign" description="Start in draft, then resolve a consent-aware audience and pass preflight before queueing." back={{ label: 'Campaigns', to: ROUTES.CAMPAIGNS }}><CampaignForm pending={mutation.isPending} serverError={mutation.error} onSubmit={(input) => mutation.mutate(input)}/></Page>; }
