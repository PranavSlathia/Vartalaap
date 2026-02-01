import { Outlet } from 'react-router';
import { useAuth } from 'react-oidc-context';
import {
  SidebarProvider,
  Sidebar,
  SidebarContent,
  SidebarHeader,
  SidebarMenu,
  SidebarMenuItem,
  SidebarMenuButton,
  SidebarFooter,
  SidebarInset,
  SidebarTrigger,
  SidebarGroup,
  SidebarGroupLabel,
  SidebarGroupContent,
} from '@/components/ui/sidebar';
import { Separator } from '@/components/ui/separator';
import { Avatar, AvatarFallback } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import {
  LayoutDashboard,
  CalendarCheck,
  PhoneCall,
  Settings,
  LogOut,
  Mic,
  UtensilsCrossed,
  HelpCircle,
  FlaskConical,
} from 'lucide-react';
import { Link, useLocation } from 'react-router';

const mainNavigation = [
  { name: 'Dashboard', href: '/', icon: LayoutDashboard },
  { name: 'Reservations', href: '/reservations', icon: CalendarCheck },
  { name: 'Call Logs', href: '/call-logs', icon: PhoneCall },
];

const knowledgeNavigation = [
  { name: 'Menu Editor', href: '/menu-editor', icon: UtensilsCrossed },
  { name: 'FAQ Editor', href: '/faq-editor', icon: HelpCircle },
  { name: 'Knowledge Test', href: '/knowledge-test', icon: FlaskConical },
];

const toolsNavigation = [
  { name: 'Voice Test', href: '/voice-test', icon: Mic },
  { name: 'Settings', href: '/settings', icon: Settings },
];

export function Layout() {
  const auth = useAuth();
  const location = useLocation();

  const userInitials = auth.user?.profile.name
    ?.split(' ')
    .map((n) => n[0])
    .join('')
    .toUpperCase() || 'U';

  return (
    <SidebarProvider>
      <Sidebar>
        <SidebarHeader className="border-b px-6 py-4">
          <Link to="/" className="flex items-center gap-2">
            <span className="text-xl font-bold">Vartalaap</span>
          </Link>
          <span className="text-xs text-muted-foreground">Voice Bot Admin</span>
        </SidebarHeader>
        <SidebarContent className="px-2 py-2">
          <SidebarGroup>
            <SidebarGroupLabel>Main</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {mainNavigation.map((item) => (
                  <SidebarMenuItem key={item.name}>
                    <SidebarMenuButton
                      asChild
                      isActive={location.pathname === item.href}
                    >
                      <Link to={item.href}>
                        <item.icon className="h-4 w-4" />
                        <span>{item.name}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>

          <SidebarGroup>
            <SidebarGroupLabel>Knowledge Base</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {knowledgeNavigation.map((item) => (
                  <SidebarMenuItem key={item.name}>
                    <SidebarMenuButton
                      asChild
                      isActive={location.pathname === item.href}
                    >
                      <Link to={item.href}>
                        <item.icon className="h-4 w-4" />
                        <span>{item.name}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>

          <SidebarGroup>
            <SidebarGroupLabel>Tools</SidebarGroupLabel>
            <SidebarGroupContent>
              <SidebarMenu>
                {toolsNavigation.map((item) => (
                  <SidebarMenuItem key={item.name}>
                    <SidebarMenuButton
                      asChild
                      isActive={location.pathname === item.href}
                    >
                      <Link to={item.href}>
                        <item.icon className="h-4 w-4" />
                        <span>{item.name}</span>
                      </Link>
                    </SidebarMenuButton>
                  </SidebarMenuItem>
                ))}
              </SidebarMenu>
            </SidebarGroupContent>
          </SidebarGroup>
        </SidebarContent>
        <SidebarFooter className="border-t p-4">
          <div className="flex items-center gap-3">
            <Avatar className="h-8 w-8">
              <AvatarFallback>{userInitials}</AvatarFallback>
            </Avatar>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium truncate">
                {auth.user?.profile.name || 'Admin'}
              </p>
              <p className="text-xs text-muted-foreground truncate">
                {auth.user?.profile.email}
              </p>
            </div>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => auth.signoutRedirect()}
              title="Logout"
            >
              <LogOut className="h-4 w-4" />
            </Button>
          </div>
        </SidebarFooter>
      </Sidebar>
      <SidebarInset>
        <header className="flex h-16 shrink-0 items-center gap-2 border-b px-4">
          <SidebarTrigger className="-ml-1" />
          <Separator orientation="vertical" className="mr-2 h-4" />
          <h1 className="text-lg font-semibold">
            {[...mainNavigation, ...knowledgeNavigation, ...toolsNavigation].find(
              (n) => n.href === location.pathname
            )?.name || 'Dashboard'}
          </h1>
        </header>
        <main className="flex-1 overflow-auto p-6">
          <Outlet />
        </main>
      </SidebarInset>
    </SidebarProvider>
  );
}
