import { useEffect, useRef } from 'react';
import { useAuth } from 'react-oidc-context';
import { Navigate, Outlet, useLocation } from 'react-router';
import { Loader2 } from 'lucide-react';

interface Props {
  roles?: string[];
}

/**
 * Decode JWT payload without verification (client-side only).
 * For role checking - actual token validation happens server-side.
 */
function decodeJwtPayload(token: string): Record<string, unknown> | null {
  try {
    const parts = token.split('.');
    if (parts.length !== 3) return null;

    // Convert base64url to base64 and add padding
    let payload = parts[1].replace(/-/g, '+').replace(/_/g, '/');
    const padding = (4 - (payload.length % 4)) % 4;
    payload += '='.repeat(padding);

    // Decode base64 to binary string, then handle Unicode via decodeURIComponent
    // This handles non-ASCII characters in JWT payloads (e.g., Hindi names)
    const decoded = decodeURIComponent(
      atob(payload)
        .split('')
        .map((c) => '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2))
        .join('')
    );
    return JSON.parse(decoded);
  } catch {
    return null;
  }
}

/**
 * Extract realm roles from Keycloak access token.
 * Keycloak puts roles in access_token.realm_access.roles, not in ID token profile.
 */
function getRolesFromAccessToken(accessToken: string | undefined): string[] {
  if (!accessToken) return [];
  const payload = decodeJwtPayload(accessToken);
  if (!payload) return [];
  const realmAccess = payload.realm_access as { roles?: string[] } | undefined;
  return realmAccess?.roles || [];
}

export function ProtectedRoute({ roles }: Props) {
  const auth = useAuth();
  const location = useLocation();
  const redirectingRef = useRef(false);

  // Handle redirect in useEffect to avoid StrictMode double-execution issues
  useEffect(() => {
    if (!auth.isLoading && !auth.isAuthenticated && !auth.error && !redirectingRef.current) {
      redirectingRef.current = true;
      auth.signinRedirect({
        state: { returnTo: location.pathname + location.search + location.hash },
      });
    }
  }, [auth.isLoading, auth.isAuthenticated, auth.error, auth, location]);

  if (auth.isLoading) {
    return (
      <div className="flex h-screen w-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (auth.error) {
    return (
      <div className="flex h-screen w-full flex-col items-center justify-center gap-4">
        <p className="text-destructive">Authentication error: {auth.error.message}</p>
        <button
          onClick={() => auth.signinRedirect()}
          className="text-primary underline"
        >
          Try again
        </button>
      </div>
    );
  }

  if (!auth.isAuthenticated) {
    // Show loading while redirect happens in useEffect
    return (
      <div className="flex h-screen w-full items-center justify-center">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        <span className="ml-2 text-muted-foreground">Redirecting to login...</span>
      </div>
    );
  }

  // Role-based access - read from access token, not profile
  if (roles && roles.length > 0) {
    const userRoles = getRolesFromAccessToken(auth.user?.access_token);
    const hasRequiredRole = roles.some((role) => userRoles.includes(role));
    if (!hasRequiredRole) {
      return <Navigate to="/unauthorized" replace />;
    }
  }

  return <Outlet />;
}
