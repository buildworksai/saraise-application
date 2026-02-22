/**
 * Create Report Page - Business Intelligence
 */
import { useState } from 'react';
import { useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { toast } from 'sonner';
import { ArrowLeft } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/Card';
import { Input } from '@/components/ui/Input';
import { Textarea } from '@/components/ui/Textarea';
import { biService } from '../services/bi-service';
import type { ReportCreate } from '../contracts';

const MODULE_PATH = '/business-intelligence/reports';

export const CreateReportPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [form, setForm] = useState<ReportCreate>({
    report_code: '',
    report_name: '',
    report_type: 'table',
    query: '',
    is_active: true,
  });

  const createMutation = useMutation({
    mutationFn: (data: ReportCreate) => biService.createReport(data),
    onSuccess: (report) => {
      void queryClient.invalidateQueries({ queryKey: ['bi-reports'] });
      toast.success('Report created successfully');
      navigate(`${MODULE_PATH}/${report.id}`);
    },
    onError: () => {
      toast.error('Failed to create report. Please try again.');
    },
  });

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault();
    if (
      !form.report_code.trim() ||
      !form.report_name.trim() ||
      !form.report_type.trim() ||
      !form.query.trim()
    ) {
      toast.error('Code, name, type, and query are required');
      return;
    }
    createMutation.mutate(form);
  };

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center gap-4">
        <Button variant="ghost" onClick={() => navigate(MODULE_PATH)}>
          <ArrowLeft className="w-4 h-4 mr-2" />
          Back
        </Button>
        <h1 className="text-3xl font-bold text-foreground">Create Report</h1>
      </div>

      <Card className="max-w-2xl">
        <CardHeader>
          <CardTitle>Report Details</CardTitle>
        </CardHeader>
        <CardContent>
          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="text-sm font-medium mb-2 block">Report Code</label>
              <Input
                value={form.report_code}
                onChange={(e) => setForm({ ...form, report_code: e.target.value })}
                placeholder="e.g. RPT001"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Report Name</label>
              <Input
                value={form.report_name}
                onChange={(e) => setForm({ ...form, report_name: e.target.value })}
                placeholder="Report name"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Report Type</label>
              <Input
                value={form.report_type}
                onChange={(e) => setForm({ ...form, report_type: e.target.value })}
                placeholder="e.g. table, chart"
                required
              />
            </div>
            <div>
              <label className="text-sm font-medium mb-2 block">Query</label>
              <Textarea
                value={form.query}
                onChange={(e) => setForm({ ...form, query: e.target.value })}
                placeholder="SQL or query definition"
                required
                rows={4}
              />
            </div>
            <div className="flex gap-2 pt-4">
              <Button type="submit" disabled={createMutation.isPending}>
                {createMutation.isPending ? 'Creating...' : 'Create Report'}
              </Button>
              <Button type="button" variant="outline" onClick={() => navigate(MODULE_PATH)}>
                Cancel
              </Button>
            </div>
          </form>
        </CardContent>
      </Card>
    </div>
  );
};
