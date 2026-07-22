import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useNavigate, useParams } from "react-router-dom";
import type { AgentUpdateRequest } from "../contracts";
import { ROUTES } from "../contracts";
import { AgentForm } from "../components/AgentForm";
import { GovernedError, PageHeader, PageSkeleton } from "../components/AgentUI";
import { aiAgentService } from "../services/ai-agent-service";

export const EditAgentPage = () => { const { id = "" } = useParams(); const navigate = useNavigate(); const client = useQueryClient(); const query = useQuery({ queryKey: ["ai-agent", id], queryFn: () => aiAgentService.getAgent(id), enabled: Boolean(id) }); const mutation = useMutation({ mutationFn: (request: AgentUpdateRequest) => aiAgentService.updateAgent(id, request), onSuccess: (agent) => { void client.invalidateQueries({ queryKey: ["ai-agent", id] }); void client.invalidateQueries({ queryKey: ["ai-agents"] }); navigate(ROUTES.AGENT_DETAIL(agent.id)); } }); if (query.isLoading) return <PageSkeleton/>; if (query.error) return <GovernedError error={query.error} retry={() => void query.refetch()}/>; if (!query.data) return <GovernedError error={new Error("Agent not found.")}/>; return <main className="mx-auto max-w-4xl space-y-6"><PageHeader title={`Edit ${query.data.name}`} description="PATCH the merged definition while preserving immutable execution evidence."/><AgentForm initial={query.data} pending={mutation.isPending} mutationError={mutation.error} onSubmit={(request) => mutation.mutate(request as AgentUpdateRequest)}/></main>; };
