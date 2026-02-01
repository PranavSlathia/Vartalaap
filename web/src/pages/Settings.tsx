import { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, Save, RefreshCw, AlertCircle, CheckCircle } from 'lucide-react';
import { useQueryClient } from '@tanstack/react-query';
import {
  useGetBusinessApiBusinessBusinessIdGet,
  useUpdateBusinessApiBusinessBusinessIdPatch,
  getGetBusinessApiBusinessBusinessIdGetQueryKey,
} from '@/api/endpoints/business/business';
import type { BusinessUpdate, ReservationRules } from '@/api/model';
import { getBusinessId } from '@/lib/business';

const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'] as const;

interface OperatingHoursForm {
  [key: string]: { open: string; close: string; closed: boolean };
}

export function Settings() {
  const businessId = getBusinessId();
  const queryClient = useQueryClient();

  // Fetch business settings
  const {
    data: business,
    isLoading,
    error,
    refetch,
  } = useGetBusinessApiBusinessBusinessIdGet(businessId);

  // Update mutation
  const updateMutation = useUpdateBusinessApiBusinessBusinessIdPatch({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getGetBusinessApiBusinessBusinessIdGetQueryKey(businessId),
        });
        setSaveSuccess(true);
        setTimeout(() => setSaveSuccess(false), 3000);
      },
    },
  });

  // Form state
  const [name, setName] = useState('');
  const [timezone, setTimezone] = useState('');
  const [totalSeats, setTotalSeats] = useState(40);
  const [maxPartySize, setMaxPartySize] = useState(10);
  const [maxPhonePartySize, setMaxPhonePartySize] = useState(10);
  const [greetingText, setGreetingText] = useState('');
  const [operatingHours, setOperatingHours] = useState<OperatingHoursForm>({});
  const [saveSuccess, setSaveSuccess] = useState(false);

  // Initialize form when data loads
  useEffect(() => {
    if (business) {
      setName(business.name);
      setTimezone(business.timezone);
      setTotalSeats(business.reservation_rules?.total_seats ?? 40);
      setMaxPartySize(business.reservation_rules?.max_party_size ?? 10);
      setMaxPhonePartySize(business.reservation_rules?.max_phone_party_size ?? 10);
      setGreetingText(business.greeting_text ?? '');

      // Parse operating hours
      const hours: OperatingHoursForm = {};
      for (const day of DAYS) {
        const dayHours = business.operating_hours?.[day];
        if (typeof dayHours === 'string' && dayHours.toLowerCase() === 'closed') {
          hours[day] = { open: '', close: '', closed: true };
        } else if (dayHours && typeof dayHours === 'object') {
          hours[day] = {
            open: (dayHours as { open?: string }).open ?? '',
            close: (dayHours as { close?: string }).close ?? '',
            closed: false,
          };
        } else {
          hours[day] = { open: '11:00', close: '22:30', closed: false };
        }
      }
      setOperatingHours(hours);
    }
  }, [business]);

  const handleSave = () => {
    // Build operating hours for API
    const hoursForApi: Record<string, string | { open: string; close: string }> = {};
    for (const day of DAYS) {
      const dayHours = operatingHours[day];
      if (dayHours?.closed) {
        hoursForApi[day] = 'closed';
      } else if (dayHours) {
        hoursForApi[day] = { open: dayHours.open, close: dayHours.close };
      }
    }

    const reservationRules: ReservationRules = {
      min_party_size: 1,
      max_party_size: maxPartySize,
      max_phone_party_size: maxPhonePartySize,
      total_seats: totalSeats,
      advance_days: 30,
      slot_duration_minutes: 90,
    };

    const update: BusinessUpdate = {
      name,
      timezone,
      operating_hours: hoursForApi,
      reservation_rules: reservationRules,
      greeting_text: greetingText || undefined,
    };

    updateMutation.mutate({ businessId, data: update });
  };

  const handleHoursChange = (day: string, field: 'open' | 'close', value: string) => {
    setOperatingHours((prev) => ({
      ...prev,
      [day]: { ...prev[day], [field]: value },
    }));
  };

  const handleClosedToggle = (day: string) => {
    setOperatingHours((prev) => ({
      ...prev,
      [day]: { ...prev[day], closed: !prev[day]?.closed },
    }));
  };

  if (isLoading) {
    return (
      <div className="flex items-center justify-center py-12">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (error) {
    return (
      <div className="space-y-6">
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Failed to load business settings: {error.message}
            <Button variant="outline" size="sm" className="ml-4" onClick={() => refetch()}>
              Retry
            </Button>
          </AlertDescription>
        </Alert>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Settings</h2>
          <p className="text-muted-foreground">
            Configure your voice bot and business settings.
          </p>
        </div>
        <div className="flex gap-2">
          <Button variant="outline" size="icon" onClick={() => refetch()}>
            <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
          </Button>
          <Button onClick={handleSave} disabled={updateMutation.isPending}>
            {updateMutation.isPending ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Save className="h-4 w-4 mr-2" />
            )}
            Save Changes
          </Button>
        </div>
      </div>

      {saveSuccess && (
        <Alert className="border-green-500 bg-green-50 dark:bg-green-950">
          <CheckCircle className="h-4 w-4 text-green-600" />
          <AlertDescription className="text-green-600">
            Settings saved successfully!
          </AlertDescription>
        </Alert>
      )}

      {updateMutation.error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            Failed to save: {updateMutation.error.message}
          </AlertDescription>
        </Alert>
      )}

      <div className="grid gap-6">
        <Card>
          <CardHeader>
            <CardTitle>Business Information</CardTitle>
            <CardDescription>
              Basic details about your business.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="business-name">Business Name</Label>
                <Input
                  id="business-name"
                  value={name}
                  onChange={(e) => setName(e.target.value)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="business-id">Business ID</Label>
                <div className="flex items-center gap-2">
                  <Input id="business-id" value={businessId} disabled />
                  <Badge variant="secondary">{business?.status}</Badge>
                </div>
              </div>
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="timezone">Timezone</Label>
                <Input
                  id="timezone"
                  value={timezone}
                  onChange={(e) => setTimezone(e.target.value)}
                  placeholder="Asia/Kolkata"
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="type">Business Type</Label>
                <Input id="type" value={business?.type ?? ''} disabled />
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Reservation Settings</CardTitle>
            <CardDescription>
              Configure capacity and booking limits.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid gap-4 md:grid-cols-3">
              <div className="space-y-2">
                <Label htmlFor="total-seats">Total Seats</Label>
                <Input
                  id="total-seats"
                  type="number"
                  min={1}
                  value={totalSeats}
                  onChange={(e) => setTotalSeats(parseInt(e.target.value) || 1)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="max-party">Max Party Size</Label>
                <Input
                  id="max-party"
                  type="number"
                  min={1}
                  value={maxPartySize}
                  onChange={(e) => setMaxPartySize(parseInt(e.target.value) || 1)}
                />
              </div>
              <div className="space-y-2">
                <Label htmlFor="max-phone-party">Max Phone Party Size</Label>
                <Input
                  id="max-phone-party"
                  type="number"
                  min={1}
                  value={maxPhonePartySize}
                  onChange={(e) => setMaxPhonePartySize(parseInt(e.target.value) || 1)}
                />
                <p className="text-xs text-muted-foreground">
                  Larger groups are directed to WhatsApp
                </p>
              </div>
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Operating Hours</CardTitle>
            <CardDescription>
              Set your business hours for each day.
            </CardDescription>
          </CardHeader>
          <CardContent>
            <div className="space-y-3">
              {DAYS.map((day) => (
                <div key={day} className="flex items-center gap-4">
                  <span className="w-24 capitalize font-medium">{day}</span>
                  <label className="flex items-center gap-2">
                    <input
                      type="checkbox"
                      checked={operatingHours[day]?.closed ?? false}
                      onChange={() => handleClosedToggle(day)}
                    />
                    <span className="text-sm">Closed</span>
                  </label>
                  {!operatingHours[day]?.closed && (
                    <>
                      <Input
                        type="time"
                        className="w-32"
                        value={operatingHours[day]?.open ?? ''}
                        onChange={(e) => handleHoursChange(day, 'open', e.target.value)}
                      />
                      <span>to</span>
                      <Input
                        type="time"
                        className="w-32"
                        value={operatingHours[day]?.close ?? ''}
                        onChange={(e) => handleHoursChange(day, 'close', e.target.value)}
                      />
                    </>
                  )}
                </div>
              ))}
            </div>
          </CardContent>
        </Card>

        <Card>
          <CardHeader>
            <CardTitle>Voice Bot Configuration</CardTitle>
            <CardDescription>
              Customize the voice bot greeting and behavior.
            </CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="greeting">Custom Greeting</Label>
              <textarea
                id="greeting"
                className="w-full h-24 px-3 py-2 border rounded-md"
                placeholder="Namaste! Welcome to our restaurant..."
                value={greetingText}
                onChange={(e) => setGreetingText(e.target.value)}
              />
              <p className="text-xs text-muted-foreground">
                This greeting is spoken when a customer calls.
              </p>
            </div>
            <div className="grid gap-4 md:grid-cols-3 pt-4 border-t">
              <div className="space-y-1">
                <p className="text-sm font-medium">STT Engine</p>
                <p className="text-sm text-muted-foreground">Deepgram Nova-2</p>
              </div>
              <div className="space-y-1">
                <p className="text-sm font-medium">LLM Provider</p>
                <p className="text-sm text-muted-foreground">Groq Llama 3.3 70B</p>
              </div>
              <div className="space-y-1">
                <p className="text-sm font-medium">TTS Engine</p>
                <p className="text-sm text-muted-foreground">Piper (Self-hosted)</p>
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Voice pipeline engines are configured via environment variables.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
