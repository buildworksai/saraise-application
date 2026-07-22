import { useQuery } from '@tanstack/react-query';
import { documentIntelligenceService } from '../services/document-intelligence-service';

export const documentIntelligenceConfigurationKey = ['document-intelligence', 'configuration'] as const;

export function useDocumentIntelligenceConfiguration() {
  return useQuery({
    queryKey: documentIntelligenceConfigurationKey,
    queryFn: documentIntelligenceService.getConfiguration,
  });
}
