import { useQuery } from "@tanstack/react-query";
import { Card } from "@/components/ui/Card";
import {
  EmptyState,
  PageShell,
  PageSkeleton,
  ProblemState,
  formatDateTime,
} from "../components/CommunicationHubUI";
import {
  communicationHubQueryKeys,
  communicationHubService,
} from "../services/communication-hub-service";

export function MessageListPage() {
  const query = useQuery({
    queryKey: communicationHubQueryKeys.messages,
    queryFn: () => communicationHubService.listMessages(),
  });

  if (query.isLoading) return <PageSkeleton label="Loading communication messages" />;
  if (query.error) return <ProblemState error={query.error} onRetry={() => void query.refetch()} />;

  const messages = query.data ?? [];
  return (
    <PageShell
      title="Communication messages"
      description="Inspect tenant-scoped messages returned by the Communication Hub backend."
    >
      {messages.length === 0 ? (
        <EmptyState
          title="No messages available"
          description="The backend returned no messages for this tenant."
        />
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/40 text-left">
              <tr>
                <th className="p-3 font-medium">Subject</th>
                <th className="p-3 font-medium">Channel</th>
                <th className="p-3 font-medium">Type</th>
                <th className="p-3 font-medium">Status</th>
                <th className="p-3 font-medium">Created</th>
              </tr>
            </thead>
            <tbody>
              {messages.map((message) => (
                <tr key={message.id} className="border-b last:border-b-0">
                  <td className="p-3 font-medium">{message.subject || "(No subject)"}</td>
                  <td className="p-3">{message.channel_name || message.channel_code}</td>
                  <td className="p-3 capitalize">{message.message_type}</td>
                  <td className="p-3 capitalize">{message.status}</td>
                  <td className="p-3 text-muted-foreground">
                    {formatDateTime(message.created_at)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      )}
    </PageShell>
  );
}
