/**
 * Get the current business ID.
 * For MVP single-tenant mode, uses VITE_BUSINESS_ID env var.
 * Future: Replace with context provider for multi-tenant.
 *
 * @throws Error in production if VITE_BUSINESS_ID is not configured
 */
export function getBusinessId(): string {
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
