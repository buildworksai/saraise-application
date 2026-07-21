import { useMutation } from '@tanstack/react-query';
import { ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router-dom';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { TemplateForm, type TemplateFormValue } from '../components/TemplateForm';
import { ApiProblem, PageHeader } from '../components/ModuleShell';
import { documentIntelligenceService } from '../services/document-intelligence-service';

export function CreateTemplatePage() {
  const navigate = useNavigate();
  const mutation = useMutation({ mutationFn: (value: TemplateFormValue) => documentIntelligenceService.createTemplate(value), onSuccess: (template) => navigate(`/document-intelligence/templates/${template.id}`) });
  return <main className="space-y-6 p-4 sm:p-8"><PageHeader title="Create extraction template" description="Define provider-neutral fields on normalized page coordinates, then validate before activation." actions={<Button variant="ghost" onClick={() => navigate('/document-intelligence/templates')}><ArrowLeft className="mr-2 h-4 w-4" />Back</Button>} />{mutation.error && <ApiProblem error={mutation.error} onRetry={() => mutation.reset()} inline />}<Card className="p-6"><TemplateForm pending={mutation.isPending} submitLabel="Create draft" onSubmit={(value) => mutation.mutateAsync(value).then(() => undefined)} /></Card></main>;
}
