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

export function ChannelListPage() {
  const query = useQuery({
    queryKey: communicationHubQueryKeys.channels,
    queryFn: () => communicationHubService.listChannels(),
  });

  if (query.isLoading) return <PageSkeleton label="Loading communication channels" />;
  if (query.error) return <ProblemState error={query.error} onRetry={() => void query.refetch()} />;

  const channels = query.data ?? [];
  return (
    <PageShell
      title="Communication channels"
      description="Review tenant-scoped channels served by the Communication Hub backend."
    >
      {channels.length === 0 ? (
        <EmptyState
          title="No channels configured"
          description="The backend returned no active communication channels for this tenant."
        />
      ) : (
        <Card className="overflow-x-auto p-0">
          <table className="w-full text-sm">
            <thead className="border-b bg-muted/40 text-left">
              <tr>
                <th className="p-3 font-medium">Code</th>
                <th className="p-3 font-medium">Name</th>
                <th className="p-3 font-medium">Type</th>
                <th className="p-3 font-medium">Status</th>
                <th className="p-3 font-medium">Updated</th>
              </tr>
            </thead>
            <tbody>
              {channels.map((channel) => (
                <tr key={channel.id} className="border-b last:border-b-0">
                  <td className="p-3 font-mono text-xs">{channel.channel_code}</td>
                  <td className="p-3 font-medium">{channel.channel_name}</td>
                  <td className="p-3 capitalize">{channel.channel_type}</td>
                  <td className="p-3">{channel.is_active ? "Active" : "Inactive"}</td>
                  <td className="p-3 text-muted-foreground">
                    {formatDateTime(channel.updated_at)}
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
