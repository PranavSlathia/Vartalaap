import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Plus, RefreshCw, Loader2 } from 'lucide-react';
import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  useListReservationsApiReservationsGet,
  useCreateReservationApiReservationsPost,
  useUpdateReservationApiReservationsReservationIdPatch,
  getListReservationsApiReservationsGetQueryKey,
} from '@/api/endpoints/crud/crud';
import type { ReservationStatus } from '@/api/model';
import { getLocalDateString } from '@/lib/utils';
import { getBusinessId } from '@/lib/business';

const statusColors: Record<ReservationStatus, string> = {
  confirmed: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  cancelled: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
  completed: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
  no_show: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
};

const statusOptions: ReservationStatus[] = ['confirmed', 'cancelled', 'completed', 'no_show'];

export function Reservations() {
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
  const [statusFilter, setStatusFilter] = useState<ReservationStatus | 'all'>('all');
  const businessId = getBusinessId();
  const [newReservation, setNewReservation] = useState({
    customer_name: '',
    party_size: 2,
    reservation_date: getLocalDateString(),
    reservation_time: '19:00',
  });

  const queryClient = useQueryClient();

  // Fetch reservations from API - always scope by business_id to prevent multi-tenant data leakage
  const {
    data: reservations,
    isLoading,
    error,
    refetch,
  } = useListReservationsApiReservationsGet({
    business_id: businessId,
    ...(statusFilter !== 'all' ? { status: statusFilter } : {}),
  });

  // Create reservation mutation
  const createMutation = useCreateReservationApiReservationsPost({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getListReservationsApiReservationsGetQueryKey(),
        });
        setIsAddDialogOpen(false);
        setNewReservation({
          customer_name: '',
          party_size: 2,
          reservation_date: getLocalDateString(),
          reservation_time: '19:00',
        });
      },
    },
  });

  // Update reservation mutation
  const updateMutation = useUpdateReservationApiReservationsReservationIdPatch({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getListReservationsApiReservationsGetQueryKey(),
        });
      },
    },
  });

  const handleCreateReservation = () => {
    createMutation.mutate({
      data: {
        business_id: businessId,
        customer_name: newReservation.customer_name || undefined,
        party_size: newReservation.party_size,
        reservation_date: newReservation.reservation_date,
        reservation_time: newReservation.reservation_time,
      },
    });
  };

  const handleStatusChange = (reservationId: string, newStatus: ReservationStatus) => {
    updateMutation.mutate({
      reservationId,
      data: { status: newStatus },
    });
  };

  const filteredReservations = reservations || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Reservations</h2>
          <p className="text-muted-foreground">
            Manage table reservations made through the voice bot.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="icon" onClick={() => refetch()}>
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </Button>
          <Dialog open={isAddDialogOpen} onOpenChange={setIsAddDialogOpen}>
            <DialogTrigger asChild>
              <Button>
                <Plus className="h-4 w-4 mr-2" />
                Add Reservation
              </Button>
            </DialogTrigger>
            <DialogContent>
              <DialogHeader>
                <DialogTitle>Add Reservation</DialogTitle>
                <DialogDescription>
                  Create a new table reservation manually.
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="space-y-2">
                  <Label htmlFor="customer_name">Customer Name</Label>
                  <Input
                    id="customer_name"
                    placeholder="John Doe"
                    value={newReservation.customer_name}
                    onChange={(e) =>
                      setNewReservation({ ...newReservation, customer_name: e.target.value })
                    }
                  />
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="party_size">Party Size</Label>
                    <Input
                      id="party_size"
                      type="number"
                      min={1}
                      max={20}
                      value={newReservation.party_size}
                      onChange={(e) =>
                        setNewReservation({
                          ...newReservation,
                          party_size: parseInt(e.target.value) || 1,
                        })
                      }
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="reservation_date">Date</Label>
                    <Input
                      id="reservation_date"
                      type="date"
                      value={newReservation.reservation_date}
                      onChange={(e) =>
                        setNewReservation({ ...newReservation, reservation_date: e.target.value })
                      }
                    />
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="reservation_time">Time</Label>
                  <Input
                    id="reservation_time"
                    type="time"
                    value={newReservation.reservation_time}
                    onChange={(e) =>
                      setNewReservation({ ...newReservation, reservation_time: e.target.value })
                    }
                  />
                </div>
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setIsAddDialogOpen(false)}>
                  Cancel
                </Button>
                <Button
                  onClick={handleCreateReservation}
                  disabled={createMutation.isPending}
                >
                  {createMutation.isPending && (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  )}
                  Create Reservation
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Status filter */}
      <div className="flex gap-2 flex-wrap">
        <Button
          variant={statusFilter === 'all' ? 'default' : 'outline'}
          size="sm"
          onClick={() => setStatusFilter('all')}
        >
          All
        </Button>
        {statusOptions.map((status) => (
          <Button
            key={status}
            variant={statusFilter === status ? 'default' : 'outline'}
            size="sm"
            onClick={() => setStatusFilter(status)}
          >
            {status.replace('_', ' ')}
          </Button>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Reservations ({filteredReservations.length})</CardTitle>
          <CardDescription>
            {statusFilter === 'all'
              ? 'All reservations'
              : `Showing ${statusFilter.replace('_', ' ')} reservations`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error ? (
            <div className="text-center py-8 text-red-500">
              <p>Error loading reservations: {error.message}</p>
              <Button variant="outline" onClick={() => refetch()} className="mt-4">
                Retry
              </Button>
            </div>
          ) : isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : filteredReservations.length === 0 ? (
            <p className="text-center py-8 text-muted-foreground">
              No reservations found. Create one using the button above.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Customer</TableHead>
                  <TableHead>Party Size</TableHead>
                  <TableHead>Date</TableHead>
                  <TableHead>Time</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {filteredReservations.map((reservation) => (
                  <TableRow key={reservation.id}>
                    <TableCell className="font-medium">
                      {reservation.customer_name || 'Walk-in'}
                    </TableCell>
                    <TableCell>{reservation.party_size} guests</TableCell>
                    <TableCell>{reservation.reservation_date}</TableCell>
                    <TableCell>{reservation.reservation_time}</TableCell>
                    <TableCell>
                      <Badge className={statusColors[reservation.status]}>
                        {reservation.status.replace('_', ' ')}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <select
                        className="text-xs border rounded px-2 py-1"
                        value={reservation.status}
                        onChange={(e) =>
                          handleStatusChange(reservation.id, e.target.value as ReservationStatus)
                        }
                        disabled={updateMutation.isPending}
                      >
                        {statusOptions.map((status) => (
                          <option key={status} value={status}>
                            {status.replace('_', ' ')}
                          </option>
                        ))}
                      </select>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
