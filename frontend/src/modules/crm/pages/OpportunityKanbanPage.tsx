/**
 * Opportunity Kanban Page
 *
 * Displays opportunities in a kanban board view by stage with drag-and-drop functionality.
 */
import { useState } from 'react';
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';
import { useNavigate } from 'react-router-dom';
import { Plus } from 'lucide-react';
import { Button } from '@/components/ui/Button';
import { Card } from '@/components/ui/Card';
import { crmService } from '../services/crm-service';
import type { Opportunity } from '../contracts';

const STAGES = [
  'prospecting',
  'qualification',
  'needs_analysis',
  'proposal',
  'negotiation',
  'closed_won',
  'closed_lost',
] as const;

type Stage = (typeof STAGES)[number];

export const OpportunityKanbanPage = () => {
  const navigate = useNavigate();
  const queryClient = useQueryClient();
  const [draggedOpportunity, setDraggedOpportunity] = useState<Opportunity | null>(null);
  const [dragOverStage, setDragOverStage] = useState<Stage | null>(null);

  const { data: opportunities, isLoading } = useQuery({
    queryKey: ['crm-opportunities'],
    queryFn: () => crmService.listOpportunities({ status: 'open' }),
  });

  const updateOpportunityMutation = useMutation({
    mutationFn: ({ id, stage }: { id: string; stage: string }) =>
      crmService.updateOpportunity(id, { stage }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['crm-opportunities'] });
    },
  });

  const opportunitiesByStage = opportunities?.reduce(
    (acc, opp) => {
      const stage = opp.stage as Stage;
      if (!acc[stage]) {
        acc[stage] = [];
      }
      acc[stage].push(opp);
      return acc;
    },
    {} as Record<Stage, Opportunity[]>
  ) || {};

  const handleDragStart = (e: React.DragEvent, opportunity: Opportunity) => {
    setDraggedOpportunity(opportunity);
    e.dataTransfer.effectAllowed = 'move';
    e.dataTransfer.setData('text/plain', opportunity.id);
    // Add visual feedback
    if (e.currentTarget instanceof HTMLElement) {
      e.currentTarget.style.opacity = '0.5';
    }
  };

  const handleDragEnd = (e: React.DragEvent) => {
    // Reset visual feedback
    if (e.currentTarget instanceof HTMLElement) {
      e.currentTarget.style.opacity = '1';
    }
    setDraggedOpportunity(null);
    setDragOverStage(null);
  };

  const handleDragOver = (e: React.DragEvent, stage: Stage) => {
    e.preventDefault();
    e.dataTransfer.dropEffect = 'move';
    setDragOverStage(stage);
  };

  const handleDragLeave = () => {
    setDragOverStage(null);
  };

  const handleDrop = (e: React.DragEvent, targetStage: Stage) => {
    e.preventDefault();
    setDragOverStage(null);

    if (!draggedOpportunity) return;

    // Don't update if dropped on the same stage
    if (draggedOpportunity.stage === targetStage) {
      setDraggedOpportunity(null);
      return;
    }

    // Update opportunity stage
    updateOpportunityMutation.mutate({
      id: draggedOpportunity.id,
      stage: targetStage,
    });

    setDraggedOpportunity(null);
  };

  if (isLoading) {
    return (
      <div className="p-8">
        <div className="animate-pulse space-y-4">
          <div className="h-8 bg-muted rounded w-1/4"></div>
          <div className="grid grid-cols-7 gap-4">
            {[...Array(7)].map((_, i) => (
              <div key={i} className="h-64 bg-muted rounded"></div>
            ))}
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="p-8">
      <div className="mb-6 flex items-center justify-between">
        <h1 className="text-3xl font-bold text-foreground">Sales Pipeline</h1>
        <Button onClick={() => navigate('/crm/opportunities/new')}>
          <Plus className="w-4 h-4 mr-2" />
          Create Opportunity
        </Button>
      </div>

      <div className="grid grid-cols-7 gap-4 overflow-x-auto">
        {STAGES.map((stage) => (
          <div
            key={stage}
            className="min-w-[250px]"
            onDragOver={(e) => handleDragOver(e, stage)}
            onDragLeave={handleDragLeave}
            onDrop={(e) => handleDrop(e, stage)}
          >
            <Card
              className={`h-full transition-colors ${
                dragOverStage === stage ? 'border-primary border-2 bg-primary/5' : ''
              }`}
            >
              <div className="p-4 border-b">
                <h3 className="font-semibold capitalize">{stage.replace('_', ' ')}</h3>
                <p className="text-sm text-muted-foreground">
                  {(opportunitiesByStage[stage] || []).length} opportunities
                </p>
              </div>
              <div className="p-4 space-y-2 max-h-[600px] overflow-y-auto">
                {(opportunitiesByStage[stage] || []).map((opp) => (
                  <Card
                    key={opp.id}
                    draggable
                    onDragStart={(e) => handleDragStart(e, opp)}
                    onDragEnd={handleDragEnd}
                    className="p-3 cursor-move hover:shadow-md transition-shadow bg-background"
                  >
                    <div className="font-medium text-sm mb-1">{opp.name}</div>
                    <div className="text-xs text-muted-foreground mb-2">
                      {opp.currency} {parseFloat(opp.amount).toLocaleString()}
                    </div>
                    <div className="text-xs text-muted-foreground">
                      {opp.probability}% • {new Date(opp.close_date).toLocaleDateString()}
                    </div>
                  </Card>
                ))}
                {(!opportunitiesByStage[stage] || opportunitiesByStage[stage].length === 0) && (
                  <div className="text-sm text-muted-foreground text-center py-8">
                    Drop opportunities here
                  </div>
                )}
              </div>
            </Card>
          </div>
        ))}
      </div>
    </div>
  );
};
