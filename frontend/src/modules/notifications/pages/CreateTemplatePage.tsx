import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";
import { PATHS, type TemplateCreateInput } from "../contracts";
import { notificationService } from "../services/notification-service";
import { PageShell } from "../components/NotificationUI";
import { TemplateForm } from "../components/TemplateForm";

export function CreateTemplatePage() { const navigate = useNavigate(); const create = useMutation({ mutationFn: (input: TemplateCreateInput) => notificationService.templates.create(input), onSuccess: (item) => navigate(PATHS.TEMPLATE_DETAIL(item.id)) }); return <PageShell title="Create notification template" description="Define safe variables and verify the sandboxed render before creating version 1." back={{ label: "Templates", to: PATHS.TEMPLATES }}><TemplateForm pending={create.isPending} error={create.error} submitLabel="Create template" onPreview={(draft) => notificationService.templates.previewDraft({ context: {}, draft: { name: draft.name, category: draft.category, subject_template: draft.subject_template, body_template: draft.body_template, variables_schema: draft.variables_schema, content_type: draft.content_type } })} onSubmit={async (draft) => { await create.mutateAsync(draft); }}/></PageShell>; }
