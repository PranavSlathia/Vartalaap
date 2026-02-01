import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Badge } from '@/components/ui/badge';
import { PhoneCall, CalendarCheck, Clock, Users, CheckCircle, XCircle, Loader2 } from 'lucide-react';
import { useListReservationsApiReservationsGet } from '@/api/endpoints/crud/crud';
import { useDetailedHealthCheckHealthDetailedGet } from '@/api/endpoints/health/health';
import { useGetCallLogSummaryApiCallLogsSummaryGet } from '@/api/endpoints/call-logs/call-logs';
import { useGetBusinessApiBusinessBusinessIdGet } from '@/api/endpoints/business/business';
import type { ReservationStatus } from '@/api/model';
import { getLocalDateString } from '@/lib/utils';
import { getBusinessId } from '@/lib/business';

const statusColors: Record<ReservationStatus, string> = {
  confirmed: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  cancelled: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
  completed: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
  no_show: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
};

export function Dashboard() {
  const businessId = getBusinessId();

  // Fetch business settings (for capacity)
  const { data: business } = useGetBusinessApiBusinessBusinessIdGet(businessId);

  // Fetch reservations - scoped by business_id
  const { data: reservations, isLoading: reservationsLoading } =
    useListReservationsApiReservationsGet({ business_id: businessId });

  // Fetch call log summary for today - scoped by business_id
  // NOTE: Uses browser local date. For accurate cross-timezone stats,
  // dates should be computed server-side using business timezone.
  const today = getLocalDateString();
  const { data: callSummary, isLoading: callsLoading } =
    useGetCallLogSummaryApiCallLogsSummaryGet({
      business_id: businessId,
      date_from: today,
      date_to: today,
    });

  // Fetch health status
  const { data: health, isLoading: healthLoading } =
    useDetailedHealthCheckHealthDetailedGet();

  // Calculate reservation stats
  const todayReservations = reservations?.filter(
    (r) => r.reservation_date === today
  ) || [];
  const upcomingReservations = reservations?.filter(
    (r) => r.reservation_date >= today && r.status === 'confirmed'
  ).slice(0, 5) || [];

  const confirmedToday = todayReservations.filter((r) => r.status === 'confirmed').length;
  const totalGuests = todayReservations
    .filter((r) => r.status === 'confirmed')
    .reduce((sum, r) => sum + r.party_size, 0);

  // Get capacity from business settings or fallback
  const totalSeats = business?.reservation_rules?.total_seats ?? 40;

  const stats = [
    {
      name: 'Total Calls Today',
      value: callsLoading ? '...' : (callSummary?.total_calls ?? 0).toString(),
      icon: PhoneCall,
      description: callsLoading
        ? 'Loading...'
        : `${callSummary?.calls_by_outcome?.resolved ?? 0} resolved`,
      loading: callsLoading,
    },
    {
      name: 'Reservations Today',
      value: reservationsLoading ? '...' : confirmedToday.toString(),
      icon: CalendarCheck,
      description: `${totalGuests} guests expected`,
      loading: reservationsLoading,
    },
    {
      name: 'API Status',
      value: healthLoading ? '...' : health?.status === 'healthy' ? 'Healthy' : 'Degraded',
      icon: health?.status === 'healthy' ? CheckCircle : Clock,
      description: healthLoading ? 'Checking...' : `${Object.keys(health?.checks || {}).length} services`,
      loading: healthLoading,
    },
    {
      name: 'Active Capacity',
      value: `${totalSeats} seats`,
      icon: Users,
      description: 'Restaurant capacity',
      loading: false,
    },
  ];

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Welcome back</h2>
        <p className="text-muted-foreground">
          Here's an overview of your voice bot activity.
        </p>
      </div>

      <div className="grid gap-4 md:grid-cols-2 lg:grid-cols-4">
        {stats.map((stat) => (
          <Card key={stat.name}>
            <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
              <CardTitle className="text-sm font-medium">{stat.name}</CardTitle>
              {stat.loading ? (
                <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" />
              ) : (
                <stat.icon className="h-4 w-4 text-muted-foreground" />
              )}
            </CardHeader>
            <CardContent>
              <div className="text-2xl font-bold">{stat.value}</div>
              <p className="text-xs text-muted-foreground">{stat.description}</p>
            </CardContent>
          </Card>
        ))}
      </div>

      <div className="grid gap-4 md:grid-cols-2">
        <Card>
          <CardHeader>
            <CardTitle>Upcoming Reservations</CardTitle>
            <CardDescription>Next 5 confirmed bookings</CardDescription>
          </CardHeader>
          <CardContent>
            {reservationsLoading ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : upcomingReservations.length === 0 ? (
              <p className="text-sm text-muted-foreground py-4 text-center">
                No upcoming reservations.
              </p>
            ) : (
              <div className="space-y-3">
                {upcomingReservations.map((res) => (
                  <div
                    key={res.id}
                    className="flex items-center justify-between p-3 border rounded-lg"
                  >
                    <div>
                      <p className="font-medium">{res.customer_name || 'Walk-in'}</p>
                      <p className="text-sm text-muted-foreground">
                        {res.reservation_date} at {res.reservation_time} · {res.party_size} guests
                      </p>
                    </div>
                    <Badge className={statusColors[res.status]}>
                      {res.status}
                    </Badge>
                  </div>
                ))}
              </div>
            )}
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>System Health</CardTitle>
            <CardDescription>Service connectivity status</CardDescription>
          </CardHeader>
          <CardContent>
            {healthLoading ? (
              <div className="flex items-center justify-center py-4">
                <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
              </div>
            ) : health ? (
              <div className="space-y-3">
                {Object.entries(health.checks || {}).map(([service, status]) => (
                  <div
                    key={service}
                    className="flex items-center justify-between p-3 border rounded-lg"
                  >
                    <div className="flex items-center gap-2">
                      {status === 'ok' ? (
                        <CheckCircle className="h-4 w-4 text-green-500" />
                      ) : (
                        <XCircle className="h-4 w-4 text-red-500" />
                      )}
                      <span className="font-medium capitalize">{service}</span>
                    </div>
                    <Badge variant={status === 'ok' ? 'default' : 'destructive'}>
                      {status}
                    </Badge>
                  </div>
                ))}
              </div>
            ) : (
              <p className="text-sm text-muted-foreground py-4 text-center">
                Unable to fetch health status.
              </p>
            )}
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
