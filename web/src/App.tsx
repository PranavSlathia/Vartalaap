import { AuthProvider } from 'react-oidc-context';
import { QueryClientProvider } from '@tanstack/react-query';
import { ReactQueryDevtools } from '@tanstack/react-query-devtools';
import { BrowserRouter, Routes, Route } from 'react-router';
import { Toaster } from '@/components/ui/sonner';
import { oidcConfig } from '@/lib/auth';
import { queryClient } from '@/lib/query-client';
import { ProtectedRoute } from '@/components/ProtectedRoute';

// Pages
import { Dashboard } from '@/pages/Dashboard';
import { Reservations } from '@/pages/Reservations';
import { CallLogs } from '@/pages/CallLogs';
import { Settings } from '@/pages/Settings';
import { Unauthorized } from '@/pages/Unauthorized';
import { Layout } from '@/components/layout/Layout';

// Knowledge Base pages
import { MenuEditor } from '@/pages/MenuEditor';
import { FAQEditor } from '@/pages/FAQEditor';
import { KnowledgeTest } from '@/pages/KnowledgeTest';

// Tools pages
import { VoiceTest } from '@/pages/VoiceTest';

export function App() {
  return (
    <AuthProvider {...oidcConfig}>
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Routes>
            {/* Protected routes */}
            <Route element={<ProtectedRoute roles={['admin']} />}>
              <Route element={<Layout />}>
                {/* Main */}
                <Route path="/" element={<Dashboard />} />
                <Route path="/reservations" element={<Reservations />} />
                <Route path="/call-logs" element={<CallLogs />} />

                {/* Knowledge Base */}
                <Route path="/menu-editor" element={<MenuEditor />} />
                <Route path="/faq-editor" element={<FAQEditor />} />
                <Route path="/knowledge-test" element={<KnowledgeTest />} />

                {/* Tools */}
                <Route path="/voice-test" element={<VoiceTest />} />
                <Route path="/settings" element={<Settings />} />
              </Route>
            </Route>

            {/* Public routes */}
            <Route path="/unauthorized" element={<Unauthorized />} />
          </Routes>
        </BrowserRouter>
        <Toaster />
        <ReactQueryDevtools initialIsOpen={false} />
      </QueryClientProvider>
    </AuthProvider>
  );
}
