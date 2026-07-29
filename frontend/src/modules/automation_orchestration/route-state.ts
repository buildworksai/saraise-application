import { ApiError } from "@/services/api-client";

const UUID_PATTERN =
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-5][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/iu;

export function isRouteUuid(value: string): boolean {
  return UUID_PATTERN.test(value);
}

export function routeRecordNotFoundError(recordName: string): ApiError {
  return new ApiError(`${recordName} not found.`, 404);
}
