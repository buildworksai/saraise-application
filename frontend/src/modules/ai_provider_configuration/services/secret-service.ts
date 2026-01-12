/**
 * Secret Management Service
 *
 * Handles encryption key rotation and secret re-encryption.
 */

import { apiClient } from '@/services/api-client';
import { ENDPOINTS } from '../contracts';

export interface SecretMetadata {
  id: string;
  provider_name: string;
  provider_type: string;
  created_at: string;
  updated_at: string;
  last_used_at?: string;
}

export interface RotateKeyResponse {
  new_key: string;
  message: string;
}

export interface ReEncryptResponse {
  success: boolean;
  re_encrypted_count: number;
  message: string;
}

export const secretService = {
  /**
   * List all encrypted secrets (metadata only, no decrypted values)
   */
  listSecrets: async (): Promise<SecretMetadata[]> => {
    const credentials = await apiClient.get<Array<{
      id: string;
      provider: {
        name: string;
        provider_type: string;
      };
      created_at: string;
      updated_at: string;
    }>>(ENDPOINTS.SECRETS.LIST);

    return credentials.map(cred => ({
      id: cred.id,
      provider_name: cred.provider.name,
      provider_type: cred.provider.provider_type,
      created_at: cred.created_at,
      updated_at: cred.updated_at,
    }));
  },

  /**
   * Get secret metadata by ID
   */
  getSecret: async (id: string): Promise<SecretMetadata> => {
    const credential = await apiClient.get<{
      id: string;
      provider: {
        name: string;
        provider_type: string;
      };
      created_at: string;
      updated_at: string;
    }>(ENDPOINTS.SECRETS.DETAIL(id));

    return {
      id: credential.id,
      provider_name: credential.provider.name,
      provider_type: credential.provider.provider_type,
      created_at: credential.created_at,
      updated_at: credential.updated_at,
    };
  },

  /**
   * Rotate encryption key (generates new key)
   */
  rotateKey: async (): Promise<RotateKeyResponse> => {
    return apiClient.post<RotateKeyResponse>(ENDPOINTS.SECRETS.ROTATE_KEY);
  },

  /**
   * Re-encrypt all secrets with new key
   */
  reEncrypt: async (oldKey: string, newKey: string): Promise<ReEncryptResponse> => {
    return apiClient.post<ReEncryptResponse>(ENDPOINTS.SECRETS.RE_ENCRYPT, {
      old_key: oldKey,
      new_key: newKey,
    });
  },
};
