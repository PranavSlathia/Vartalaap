import { User } from 'oidc-client-ts';
import { getOidcStorageKey } from '@/lib/auth';

const BUSINESS_STORAGE_KEY = 'vartalaap.business_id';

function getBusinessIdFromAuthClaims(): string | null {
  try {
    const oidcStorage = sessionStorage.getItem(getOidcStorageKey());
    if (!oidcStorage) {
      return null;
    }

    const user = User.fromStorageString(oidcStorage);
    const profile = (user?.profile || {}) as Record<string, unknown>;
    const claimsBusinessIds = profile.business_ids;

    if (!Array.isArray(claimsBusinessIds) || claimsBusinessIds.length === 0) {
      return null;
    }

    const allowedBusinessIds = claimsBusinessIds.filter(
      (id): id is string => typeof id === 'string' && id.length > 0
    );
    if (allowedBusinessIds.length === 0) {
      return null;
    }

    const selected = sessionStorage.getItem(BUSINESS_STORAGE_KEY);
    if (selected && allowedBusinessIds.includes(selected)) {
      return selected;
    }

    return allowedBusinessIds[0];
  } catch {
    return null;
  }
}

export function setBusinessId(businessId: string): void {
  if (!businessId) {
    return;
  }
  sessionStorage.setItem(BUSINESS_STORAGE_KEY, businessId);
}

/**
 * Get the current business ID.
 * Priority:
 * 1) Auth token claim (`business_ids`) with optional session selection
 * 2) VITE_BUSINESS_ID (single-tenant fallback)
 *
 * @throws Error in production if neither auth claim nor VITE_BUSINESS_ID is available
 */
export function getBusinessId(): string {
  const claimBusinessId = getBusinessIdFromAuthClaims();
  if (claimBusinessId) {
    return claimBusinessId;
  }

  const businessId = import.meta.env.VITE_BUSINESS_ID;

  if (!businessId) {
    // In production, missing config is a critical error - fail fast
    if (import.meta.env.PROD) {
      throw new Error(
        '[Vartalaap] VITE_BUSINESS_ID not configured. ' +
          'Set this in your .env file before deploying to production.'
      );
    }
    // In development, warn but allow fallback for easier onboarding
    console.warn(
      '[Vartalaap] VITE_BUSINESS_ID not set. Using "default". ' +
        'Set VITE_BUSINESS_ID in .env for proper multi-tenant support.'
    );
    return 'default';
  }

  return businessId;
}
