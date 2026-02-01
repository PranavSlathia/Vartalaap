import type { AuthProviderProps } from 'react-oidc-context';
import { WebStorageStateStore, type User } from 'oidc-client-ts';

const authority = import.meta.env.VITE_KEYCLOAK_URL
  ? `${import.meta.env.VITE_KEYCLOAK_URL}/realms/${import.meta.env.VITE_KEYCLOAK_REALM || 'vartalaap'}`
  : 'http://localhost:8080/realms/vartalaap';

const clientId = import.meta.env.VITE_KEYCLOAK_CLIENT_ID || 'vartalaap-web';

export const oidcConfig: AuthProviderProps = {
  authority,
  client_id: clientId,
  redirect_uri: window.location.origin,
  post_logout_redirect_uri: window.location.origin,
  scope: 'openid profile email',

  // PKCE flow (recommended for SPAs)
  response_type: 'code',

  // Silent refresh
  automaticSilentRenew: true,
  silent_redirect_uri: `${window.location.origin}/silent-refresh.html`,

  // Use sessionStorage to reduce XSS exposure (tokens cleared on tab close)
  // For persistent login across tabs, change to localStorage
  userStore: new WebStorageStateStore({ store: window.sessionStorage }),

  onSigninCallback: (user: User | void) => {
    // Consume returnTo state for deep link preservation
    const state = user?.state as { returnTo?: string } | undefined;
    let returnTo = state?.returnTo || '/';

    // Security: Validate returnTo is a relative path to prevent open redirect attacks
    // Reject absolute URLs, protocol-relative URLs, or paths not starting with /
    if (!returnTo.startsWith('/') || returnTo.startsWith('//')) {
      returnTo = '/';
    }

    // Full page navigation to ensure React Router initializes with correct path.
    // Note: This clears SPA state (query cache, etc.), but since this runs
    // immediately after OIDC callback, there's typically no meaningful state yet.
    // A router.navigate() would be cleaner but requires accessing router context
    // outside of React, which adds complexity for minimal benefit here.
    window.location.replace(returnTo);
  },
};

// Helper to get the storage key for the OIDC user
export function getOidcStorageKey(): string {
  return `oidc.user:${authority}:${clientId}`;
}
