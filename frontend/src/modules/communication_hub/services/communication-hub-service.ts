import { ApiError, apiClient } from "@/services/api-client";
import {
  ENDPOINTS,
  type CommunicationChannel,
  type CommunicationMessage,
  type ListEnvelope,
  isCommunicationChannel,
  isCommunicationMessage,
} from "../contracts";

export class CommunicationHubApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly code: string,
    readonly correlationId: string | null
  ) {
    super(message);
    this.name = "CommunicationHubApiError";
  }
}

function malformed(message: string): never {
  throw new CommunicationHubApiError(message, 502, "MALFORMED_RESPONSE", null);
}

function isListEnvelope<T>(value: readonly T[] | ListEnvelope<T>): value is ListEnvelope<T> {
  return !Array.isArray(value) && "results" in value;
}

async function translate<T>(request: Promise<T>): Promise<T> {
  try {
    return await request;
  } catch (failure) {
    if (!(failure instanceof ApiError)) throw failure;
    throw new CommunicationHubApiError(
      failure.message,
      failure.status,
      failure.code ?? "REQUEST_FAILED",
      failure.correlationId ?? null
    );
  }
}

function listFromResponse<T>(
  response: readonly T[] | ListEnvelope<T>,
  guard: (value: unknown) => value is T,
  subject: string
): readonly T[] {
  const candidate: unknown = isListEnvelope(response) ? response.results : response;
  if (!Array.isArray(candidate) || !candidate.every(guard)) {
    malformed(`Communication Hub ${subject} response was malformed.`);
  }
  return candidate;
}

export const communicationHubQueryKeys = {
  channels: ["communication-hub", "channels"] as const,
  messages: ["communication-hub", "messages"] as const,
};

export const communicationHubService = {
  async listChannels(): Promise<readonly CommunicationChannel[]> {
    const response = await translate(
      apiClient.get<readonly CommunicationChannel[] | ListEnvelope<CommunicationChannel>>(
        ENDPOINTS.CHANNELS.LIST
      )
    );
    return listFromResponse(response, isCommunicationChannel, "channels");
  },

  async listMessages(): Promise<readonly CommunicationMessage[]> {
    const response = await translate(
      apiClient.get<readonly CommunicationMessage[] | ListEnvelope<CommunicationMessage>>(
        ENDPOINTS.MESSAGES.LIST
      )
    );
    return listFromResponse(response, isCommunicationMessage, "messages");
  },
};
