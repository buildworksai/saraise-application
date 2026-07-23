import { useQuery } from '@tanstack/react-query';
import type {
  ConfigurationStatusTone,
  EmailMarketingConfigurationDocument,
} from '../contracts';
import {
  EMAIL_MARKETING_QUERY_KEYS,
  emailMarketingService,
} from '../services/email-marketing-service';

/** The tenant configuration is authoritative; callers must render query failures. */
export function useEmailMarketingConfiguration() {
  return useQuery({
    queryKey: EMAIL_MARKETING_QUERY_KEYS.configuration,
    queryFn: () => emailMarketingService.configuration.current(),
  });
}

export function configuredPageSize(
  rawValue: string | null,
  document: EmailMarketingConfigurationDocument,
): number {
  const requested = Number(rawValue ?? document.pagination.default_page_size);
  if (
    !Number.isInteger(requested)
    || !document.pagination.page_size_options.includes(requested)
    || requested > document.pagination.max_page_size
  ) {
    return document.pagination.default_page_size;
  }
  return requested;
}

export function configuredStatusTone(
  value: string,
  document: EmailMarketingConfigurationDocument | undefined,
): ConfigurationStatusTone {
  return document?.display.status_semantics[value] ?? 'neutral';
}

export function configuredTransitionStates(edges: readonly string[]): readonly string[] {
  return Array.from(new Set(edges.flatMap((edge) => {
    const [, fromState, toState] = edge.split(':');
    return [fromState, toState].filter((value): value is string => Boolean(value));
  }))).sort();
}
