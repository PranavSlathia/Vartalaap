# /frontend - React + TypeScript Frontend

## When to Use

- Creating React components or pages
- Working with TanStack Query hooks
- Modifying Orval configuration
- OIDC authentication with react-oidc-context
- shadcn/ui component usage with Tailwind v4

## Critical Notes

### Deprecated Libraries (DO NOT USE)

- **@react-keycloak/web** - Last updated 2020, not React 19 compatible
- **react-router-dom v7** - Just re-exports react-router, import from `react-router` directly
- **tailwindcss-animate** - Replaced by `tw-animate-css` for Tailwind v4

### Version Requirements

- Node.js 20.19+ or 22.12+ (Vite 7 requirement)
- React + React DOM must be pinned to same version (19.2.3)

## Project Structure

```
web/
├── src/
│   ├── api/                   # GENERATED (DO NOT EDIT)
│   │   ├── model/             # TypeScript types from OpenAPI
│   │   ├── endpoints/         # React Query hooks
│   │   └── mutator/           # Custom axios instance (MANUAL)
│   ├── components/
│   │   ├── ui/                # shadcn/ui primitives
│   │   ├── layout/            # Layout components
│   │   └── domain/            # Business-specific components
│   ├── pages/                 # Route pages
│   ├── hooks/                 # Custom React hooks
│   ├── lib/                   # Utilities (auth, query-client)
│   └── styles/                # Global CSS
├── orval.config.ts            # OpenAPI → TypeScript config
└── vite.config.ts             # Vite + Tailwind v4 config
```

## Code Generation

All API types and hooks are generated from OpenAPI. **DO NOT edit** files in:

- `web/src/api/model.ts`
- `web/src/api/endpoints/*.ts`

To regenerate after backend changes:

```bash
# Export OpenAPI from FastAPI
uv run python scripts/export_openapi.py

# Generate TypeScript client
cd web && npm run generate:api
```

Or use the full-stack script:

```bash
./scripts/generate-fullstack.sh
```

## Key Patterns

### Using Generated Hooks

```tsx
import { useGetReservations } from '@/api/endpoints/reservations';

function ReservationsList() {
  const { data, isLoading, error } = useGetReservations({
    business_id: 'current-business-id',
  });

  if (isLoading) return <Skeleton />;
  if (error) return <ErrorMessage error={error} />;

  return (
    <Table>
      {data?.map((r) => (
        <TableRow key={r.id}>...</TableRow>
      ))}
    </Table>
  );
}
```

### OIDC Authentication

```tsx
import { useAuth } from 'react-oidc-context';

function Header() {
  const auth = useAuth();

  if (!auth.isAuthenticated) {
    return <Button onClick={() => auth.signinRedirect()}>Login</Button>;
  }

  return (
    <div>
      <span>Welcome, {auth.user?.profile.name}</span>
      <Button onClick={() => auth.signoutRedirect()}>Logout</Button>
    </div>
  );
}
```

### Protected Routes

```tsx
import { ProtectedRoute } from '@/components/ProtectedRoute';

// In App.tsx
<Route element={<ProtectedRoute roles={['admin']} />}>
  <Route path="/admin" element={<AdminDashboard />} />
</Route>
```

### Router (v7 style)

```tsx
// Import from react-router, NOT react-router-dom
import { BrowserRouter, Routes, Route, Link, useNavigate } from 'react-router';
```

### shadcn/ui Components

```tsx
import { Button } from '@/components/ui/button';
import { Card, CardHeader, CardTitle, CardContent } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { toast } from 'sonner';

function MyComponent() {
  return (
    <Card>
      <CardHeader>
        <CardTitle>Example</CardTitle>
      </CardHeader>
      <CardContent>
        <Input placeholder="Enter value..." />
        <Button onClick={() => toast.success('Saved!')}>Save</Button>
      </CardContent>
    </Card>
  );
}
```

## Commands

```bash
# Development
cd web && npm run dev           # Start dev server (http://localhost:5173)

# Build
cd web && npm run build         # Production build
cd web && npm run preview       # Preview production build

# Code Generation
cd web && npm run generate:api  # Generate API client from OpenAPI
cd web && npm run generate      # Generate API + MSW mocks

# Quality
cd web && npm run typecheck     # TypeScript type check
cd web && npm run lint          # ESLint
cd web && npm run format        # Prettier formatting
cd web && npm run test          # Vitest tests
```

## Environment Variables

Create `web/.env` from `.env.example`:

```bash
VITE_API_URL=http://localhost:8000
VITE_KEYCLOAK_URL=http://localhost:8080
VITE_KEYCLOAK_REALM=vartalaap
VITE_KEYCLOAK_CLIENT_ID=vartalaap-web
```

## Keycloak Setup

1. Start Keycloak:

   ```bash
   docker-compose -f docker-compose.dev.yml up -d keycloak keycloak-db
   ```

2. Access admin console: http://localhost:8080 (admin/admin)

3. Create realm: `vartalaap`

4. Create client: `vartalaap-web`
   - Client type: Public
   - Standard flow: Enabled
   - Valid redirect URIs: `http://localhost:5173/*`
   - Web origins: `http://localhost:5173`
   - PKCE: S256

5. Create role: `admin`

6. Create user and assign `admin` role

## Troubleshooting

### "Module not found: @/..."

Path aliases not configured. Check:

- `tsconfig.json` has `baseUrl` and `paths`
- `tsconfig.app.json` has `baseUrl` and `paths`
- `vite.config.ts` has `resolve.alias`

### OIDC redirect loop

- Check Keycloak client valid redirect URIs
- Ensure `silent-refresh.html` exists in `public/`
- Clear localStorage and try again

### Type errors in generated code

Regenerate after backend changes:

```bash
./scripts/generate-fullstack.sh
```
