import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import type { AgentCreateRequest } from "../contracts";
import { ROUTES } from "../contracts";
import { AgentForm } from "../components/AgentForm";
import { PageHeader } from "../components/AgentUI";
import { aiAgentService } from "../services/ai-agent-service";

export const CreateAgentPage = () => { const navigate = useNavigate(); const client = useQueryClient(); const mutation = useMutation({ mutationFn: (request: AgentCreateRequest) => aiAgentService.createAgent(request), onSuccess: (agent) => { void client.invalidateQueries({ queryKey: ["ai-agents"] }); navigate(ROUTES.AGENT_DETAIL(agent.id)); } }); return <main className="mx-auto max-w-4xl space-y-6"><PageHeader title="Create governed agent" description="Configure identity, runtime, tools, approval posture, and an explicit cost boundary. Creation produces a draft; activation performs dependency checks."/><AgentForm pending={mutation.isPending} mutationError={mutation.error} onSubmit={(request) => mutation.mutate(request as AgentCreateRequest)}/></main>; };
