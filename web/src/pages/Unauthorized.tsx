import { useAuth } from 'react-oidc-context';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { ShieldX } from 'lucide-react';

export function Unauthorized() {
  const auth = useAuth();

  return (
    <div className="flex min-h-screen items-center justify-center p-4">
      <Card className="w-full max-w-md">
        <CardHeader className="text-center">
          <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-full bg-destructive/10">
            <ShieldX className="h-6 w-6 text-destructive" />
          </div>
          <CardTitle>Access Denied</CardTitle>
          <CardDescription>
            You don't have permission to access this page. Please contact your
            administrator if you believe this is an error.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-4">
          <Button onClick={() => window.history.back()} variant="outline">
            Go Back
          </Button>
          <Button onClick={() => auth.signoutRedirect()} variant="ghost">
            Sign Out
          </Button>
        </CardContent>
      </Card>
    </div>
  );
}
