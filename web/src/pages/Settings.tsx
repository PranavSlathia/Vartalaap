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
import { customInstance } from '@/api/mutator/custom-instance';
import type { BusinessUpdate, ReservationRules } from '@/api/model';
import { getBusinessId } from '@/lib/business';

const DAYS = ['monday', 'tuesday', 'wednesday', 'thursday', 'friday', 'saturday', 'sunday'] as const;

interface OperatingHoursForm {
  [key: string]: { open: string; close: string; closed: boolean };
}

interface VoiceCatalogItem {
  id: string;
  name: string;
  language?: string | null;
  hindi_recommended: boolean;
}

interface VoicePreset {
  id: string;
  name: string;
  description: string;
  provider: 'auto' | 'elevenlabs' | 'piper' | 'edge';
  voice_id?: string | null;
  model_id?: string | null;
  piper_voice?: string | null;
  edge_voice?: string | null;
}

interface VoiceOptionsResponse {
  providers: Array<'auto' | 'elevenlabs' | 'piper' | 'edge'>;
  provider_status: Record<string, boolean>;
  elevenlabs_models: VoiceCatalogItem[];
  elevenlabs_voices: VoiceCatalogItem[];
  piper_voices: VoiceCatalogItem[];
  edge_voices: VoiceCatalogItem[];
  recommended_presets: VoicePreset[];
}

interface BusinessProfiles {
  voice_profile?: {
    provider?: string;
    voice_id?: string;
    model_id?: string;
    piper_voice?: string;
    edge_voice?: string;
  };
  rag_profile?: {
    enabled?: boolean;
    max_results?: number;
    min_score?: number;
  };
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
  const [voiceProvider, setVoiceProvider] = useState('auto');
  const [voiceId, setVoiceId] = useState('');
  const [voiceModelId, setVoiceModelId] = useState('');
  const [piperVoice, setPiperVoice] = useState('');
  const [edgeVoice, setEdgeVoice] = useState('');
  const [voicePresetId, setVoicePresetId] = useState('manual');
  const [voiceOptions, setVoiceOptions] = useState<VoiceOptionsResponse | null>(null);
  const [voiceOptionsLoading, setVoiceOptionsLoading] = useState(false);
  const [voiceOptionsError, setVoiceOptionsError] = useState<string | null>(null);
  const [ragEnabled, setRagEnabled] = useState(true);
  const [ragMaxResults, setRagMaxResults] = useState(5);
  const [ragMinScore, setRagMinScore] = useState(0.3);
  const [operatingHours, setOperatingHours] = useState<OperatingHoursForm>({});
  const [saveSuccess, setSaveSuccess] = useState(false);

  useEffect(() => {
    let cancelled = false;

    const loadVoiceOptions = async () => {
      setVoiceOptionsLoading(true);
      setVoiceOptionsError(null);
      try {
        const result = await customInstance<VoiceOptionsResponse>({
          url: `/api/business/${businessId}/voice-options`,
          method: 'GET',
        });
        if (!cancelled) {
          setVoiceOptions(result);
        }
      } catch (err) {
        if (!cancelled) {
          const message = err instanceof Error ? err.message : 'Failed to load voice options';
          setVoiceOptionsError(message);
        }
      } finally {
        if (!cancelled) {
          setVoiceOptionsLoading(false);
        }
      }
    };

    void loadVoiceOptions();
    return () => {
      cancelled = true;
    };
  }, [businessId]);

  // Initialize form when data loads
  useEffect(() => {
    if (business) {
      setName(business.name);
      setTimezone(business.timezone);
      setTotalSeats(business.reservation_rules?.total_seats ?? 40);
      setMaxPartySize(business.reservation_rules?.max_party_size ?? 10);
      setMaxPhonePartySize(business.reservation_rules?.max_phone_party_size ?? 10);
      setGreetingText(business.greeting_text ?? '');
      const profiles = business as unknown as BusinessProfiles;
      const voiceProfile = profiles.voice_profile;
      const ragProfile = profiles.rag_profile;

      setVoiceProvider(voiceProfile?.provider ?? 'auto');
      setVoiceId(voiceProfile?.voice_id ?? '');
      setVoiceModelId(voiceProfile?.model_id ?? '');
      setPiperVoice(voiceProfile?.piper_voice ?? '');
      setEdgeVoice(voiceProfile?.edge_voice ?? '');
      setVoicePresetId('manual');

      setRagEnabled(ragProfile?.enabled ?? true);
      setRagMaxResults(ragProfile?.max_results ?? 5);
      setRagMinScore(ragProfile?.min_score ?? 0.3);

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

    const reservationRules = {
      min_party_size: 1,
      max_party_size: maxPartySize,
      max_phone_party_size: maxPhonePartySize,
      total_seats: totalSeats,
      advance_days: 30,
      slot_duration_minutes: 90,
      buffer_between_bookings_minutes: 15,
    } as ReservationRules;

    const update: BusinessUpdate & {
      voice_profile?: Record<string, unknown>;
      rag_profile?: Record<string, unknown>;
    } = {
      name,
      timezone,
      operating_hours: hoursForApi,
      reservation_rules: reservationRules,
      greeting_text: greetingText || undefined,
      voice_profile: {
        provider: voiceProvider,
        voice_id: voiceId || undefined,
        model_id: voiceModelId || undefined,
        piper_voice: piperVoice || undefined,
        edge_voice: edgeVoice || undefined,
      },
      rag_profile: {
        enabled: ragEnabled,
        max_results: ragMaxResults,
        min_score: ragMinScore,
      },
    };

    updateMutation.mutate({ businessId, data: update });
  };

  const handleVoicePresetChange = (presetId: string) => {
    setVoicePresetId(presetId);
    if (presetId === 'manual') {
      return;
    }

    const preset = voiceOptions?.recommended_presets.find((p) => p.id === presetId);
    if (!preset) {
      return;
    }

    setVoiceProvider(preset.provider);
    setVoiceId(preset.voice_id ?? '');
    setVoiceModelId(preset.model_id ?? '');
    setPiperVoice(preset.piper_voice ?? '');
    setEdgeVoice(preset.edge_voice ?? '');
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

  const availableProviders = voiceOptions?.providers ?? ['auto', 'elevenlabs', 'piper'];
  const providerStatus = voiceOptions?.provider_status ?? {};
  const elevenlabsModels = voiceOptions?.elevenlabs_models ?? [];
  const elevenlabsVoices = voiceOptions?.elevenlabs_voices ?? [];
  const piperVoices = voiceOptions?.piper_voices ?? [];
  const edgeVoices = voiceOptions?.edge_voices ?? [];

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
            <strong>Failed to save:</strong>{' '}
            {(() => {
              const err = updateMutation.error as { response?: { data?: { detail?: string | Array<{ loc: string[]; msg: string }> } } };
              const detail = err.response?.data?.detail;

              // Handle FastAPI validation errors (array of {loc, msg})
              if (Array.isArray(detail)) {
                return (
                  <ul className="list-disc list-inside mt-1">
                    {detail.map((d, i) => (
                      <li key={i}>
                        <strong>{d.loc.join(' → ')}:</strong> {d.msg}
                      </li>
                    ))}
                  </ul>
                );
              }

              // Handle string error message
              if (typeof detail === 'string') {
                return detail;
              }

              // Fallback to generic message
              return updateMutation.error.message || 'Unknown error';
            })()}
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
                <p className="text-sm font-medium">Voice Catalog</p>
                <p className="text-sm text-muted-foreground">
                  {voiceOptionsLoading
                    ? 'Loading providers...'
                    : voiceOptionsError
                      ? 'Using local fallback options'
                      : 'Live catalog loaded'}
                </p>
              </div>
            </div>

            <div className="space-y-2 pt-2">
              <Label htmlFor="voice-preset">Testing Preset</Label>
              <select
                id="voice-preset"
                className="w-full h-9 px-3 border rounded-md text-sm"
                value={voicePresetId}
                onChange={(e) => handleVoicePresetChange(e.target.value)}
              >
                <option value="manual">Manual (Custom)</option>
                {(voiceOptions?.recommended_presets ?? []).map((preset) => (
                  <option key={preset.id} value={preset.id}>
                    {preset.name}
                  </option>
                ))}
              </select>
              {voicePresetId !== 'manual' && (
                <p className="text-xs text-muted-foreground">
                  {voiceOptions?.recommended_presets.find((preset) => preset.id === voicePresetId)?.description}
                </p>
              )}
            </div>

            <div className="grid gap-4 md:grid-cols-2">
              <div className="space-y-2">
                <Label htmlFor="voice-provider">TTS Provider</Label>
                <select
                  id="voice-provider"
                  className="w-full h-9 px-3 border rounded-md text-sm"
                  value={voiceProvider}
                  onChange={(e) => setVoiceProvider(e.target.value)}
                >
                  {availableProviders.map((provider) => (
                    <option key={provider} value={provider}>
                      {provider === 'auto' ? 'Auto (fallback chain)' : provider}
                    </option>
                  ))}
                </select>
                {providerStatus[voiceProvider] === false && (
                  <p className="text-xs text-amber-600">
                    This provider is currently not available in runtime settings.
                  </p>
                )}
              </div>

              {voiceProvider === 'elevenlabs' && (
                <div className="space-y-2">
                  <Label htmlFor="voice-model">ElevenLabs Model</Label>
                  <select
                    id="voice-model"
                    className="w-full h-9 px-3 border rounded-md text-sm"
                    value={voiceModelId}
                    onChange={(e) => setVoiceModelId(e.target.value)}
                  >
                    <option value="">Default model</option>
                    {voiceModelId && !elevenlabsModels.some((model) => model.id === voiceModelId) && (
                      <option value={voiceModelId}>Custom ({voiceModelId})</option>
                    )}
                    {elevenlabsModels.map((model) => (
                      <option key={model.id} value={model.id}>
                        {model.name}{model.hindi_recommended ? ' (Hindi-ready)' : ''}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {voiceProvider === 'piper' && (
                <div className="space-y-2">
                  <Label htmlFor="piper-voice">Piper Voice</Label>
                  <select
                    id="piper-voice"
                    className="w-full h-9 px-3 border rounded-md text-sm"
                    value={piperVoice}
                    onChange={(e) => setPiperVoice(e.target.value)}
                  >
                    <option value="">Default Piper voice</option>
                    {piperVoices.map((voice) => (
                      <option key={voice.id} value={voice.id}>
                        {voice.name}{voice.hindi_recommended ? ' (Hindi)' : ''}
                      </option>
                    ))}
                  </select>
                </div>
              )}

              {voiceProvider === 'edge' && (
                <div className="space-y-2">
                  <Label htmlFor="edge-voice">Edge Voice</Label>
                  <select
                    id="edge-voice"
                    className="w-full h-9 px-3 border rounded-md text-sm"
                    value={edgeVoice}
                    onChange={(e) => setEdgeVoice(e.target.value)}
                  >
                    <option value="">Default Edge voice</option>
                    {edgeVoices.map((voice) => (
                      <option key={voice.id} value={voice.id}>
                        {voice.name}
                      </option>
                    ))}
                  </select>
                </div>
              )}
            </div>

            {voiceProvider === 'elevenlabs' && (
              <div className="space-y-2">
                <Label htmlFor="voice-id">ElevenLabs Voice</Label>
                <select
                  id="voice-id"
                  className="w-full h-9 px-3 border rounded-md text-sm"
                  value={voiceId}
                  onChange={(e) => setVoiceId(e.target.value)}
                >
                  <option value="">Default voice</option>
                  {voiceId && !elevenlabsVoices.some((voice) => voice.id === voiceId) && (
                    <option value={voiceId}>Custom ({voiceId})</option>
                  )}
                  {elevenlabsVoices.map((voice) => (
                    <option key={voice.id} value={voice.id}>
                      {voice.name}
                      {voice.language ? ` (${voice.language})` : ''}
                      {voice.hindi_recommended ? ' • Hindi-ready' : ''}
                    </option>
                  ))}
                </select>
              </div>
            )}

            <div className="space-y-2">
              <Label htmlFor="rag-max-results">RAG Max Results</Label>
              <Input
                id="rag-max-results"
                type="number"
                min={1}
                max={10}
                value={ragMaxResults}
                onChange={(e) => setRagMaxResults(parseInt(e.target.value) || 5)}
              />
            </div>
            <div className="grid gap-4 md:grid-cols-2">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={ragEnabled}
                  onChange={(e) => setRagEnabled(e.target.checked)}
                />
                Enable knowledge retrieval (RAG)
              </label>
              <div className="space-y-2">
                <Label htmlFor="rag-min-score">RAG Min Score</Label>
                <Input
                  id="rag-min-score"
                  type="number"
                  min={0}
                  max={1}
                  step={0.05}
                  value={ragMinScore}
                  onChange={(e) => setRagMinScore(parseFloat(e.target.value) || 0.3)}
                />
              </div>
            </div>
            <p className="text-xs text-muted-foreground">
              Voice provider and RAG settings are saved per business.
            </p>
          </CardContent>
        </Card>
      </div>
    </div>
  );
}
