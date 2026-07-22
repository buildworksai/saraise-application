import { apiClient } from '@/services/api-client';
import {
  ENDPOINTS,
  type ReEncryptRequest,
  type ReEncryptResponse,
  type RotateKeyResponse,
} from '../contracts';

export const secretService = {
  rotateKey: () => apiClient.post<RotateKeyResponse>(ENDPOINTS.SECRETS.ROTATE_KEY),
  reEncrypt: (request: ReEncryptRequest) =>
    apiClient.post<ReEncryptResponse>(ENDPOINTS.SECRETS.RE_ENCRYPT, request),
};
