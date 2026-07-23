import { useQuery } from '@tanstack/react-query';
import { Link, useParams } from 'react-router-dom';
import { Detail, DetailGrid, formatDate, GovernedError, Page, PageSkeleton, Status, Surface } from '../components/EmailMarketingUI';
import { ROUTES } from '../contracts';
import { EMAIL_MARKETING_QUERY_KEYS, emailMarketingService } from '../services/email-marketing-service';

export function EmailDeliveryDetailPage() {
  const { id = '' } = useParams();
  const query = useQuery({
    queryKey: EMAIL_MARKETING_QUERY_KEYS.delivery(id),
    queryFn: () => emailMarketingService.deliveries.get(id),
    enabled: Boolean(id),
  });
  if (query.isLoading) return <PageSkeleton label="Loading delivery evidence"/>;
  if (query.error) return <Page title="Delivery attempt" description="Sanitized operational evidence."><GovernedError error={query.error} retry={() => void query.refetch()}/></Page>;
  if (!query.data) return <Page title="Delivery attempt" description="Sanitized operational evidence."><GovernedError error={new Error('No governed delivery response was received.')} retry={() => void query.refetch()}/></Page>;
  const item = query.data.data;
  return <Page title={`Delivery attempt ${item.attempt_number}`} description="Accepted means a real gateway acknowledgement; delivered requires verified provider evidence. Internal provider and job identifiers are redacted." back={{ label: 'Audience & delivery', to: `${ROUTES.DELIVERY}?view=deliveries` }}>
    <Surface title="Operational evidence"><DetailGrid>
      <Detail label="Status"><Status value={item.status}/></Detail>
      <Detail label="Recipient"><Link className="text-primary hover:underline" to={ROUTES.RECIPIENT_DETAIL(item.recipient_id)}>{item.recipient_id}</Link></Detail>
      <Detail label="Started">{formatDate(item.started_at)}</Detail>
      <Detail label="Accepted">{formatDate(item.accepted_at)}</Detail>
      <Detail label="Completed">{formatDate(item.completed_at)}</Detail>
      <Detail label="Recorded">{formatDate(item.created_at)}</Detail>
      <Detail label="Updated">{formatDate(item.updated_at)}</Detail>
      <Detail label="Error code">{item.error_code || 'No operational error'}</Detail>
    </DetailGrid></Surface>
    <Surface title="Verified events">{item.events.length ? <ol className="space-y-3">{item.events.map((event) => <li key={event.id} className="rounded border p-3 text-sm"><Status value={event.event_type}/><span className="ml-2">{formatDate(event.occurred_at)}</span><p className="mt-1 font-mono text-xs">correlation {event.correlation_id}</p></li>)}</ol> : <p className="text-sm text-muted-foreground">No verified provider event has been appended.</p>}</Surface>
  </Page>;
}
