import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Info, Mic } from 'lucide-react';

export function VoiceTest() {
  const apiUrl = import.meta.env.VITE_API_URL || 'http://localhost:8000';

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-bold tracking-tight">Voice Bot Tester</h2>
        <p className="text-muted-foreground">
          Test the voice bot with your microphone
        </p>
      </div>

      <Alert>
        <Info className="h-4 w-4" />
        <AlertDescription>
          <strong>Prerequisites:</strong>
          <ul className="list-disc list-inside mt-1 text-sm">
            <li>Backend API running at <code className="text-xs bg-muted px-1 rounded">{apiUrl}</code></li>
            <li>Allow microphone access when prompted</li>
            <li>
              <strong>localhost:</strong> Mic works on insecure origin
            </li>
            <li>
              <strong>Production:</strong> Requires HTTPS + <code className="text-xs bg-muted px-1 rounded">Permissions-Policy: microphone=*</code> header for iframes
            </li>
          </ul>
          <strong className="block mt-3">How to use:</strong>
          <ol className="list-decimal list-inside mt-1 space-y-1">
            <li>Choose a voice preset/provider from the toggle panel</li>
            <li>Click the <strong>"Hold to Speak"</strong> button</li>
            <li>Speak in <strong>Hindi or English</strong></li>
            <li>Click again to stop recording</li>
            <li>Bot will respond with voice</li>
          </ol>
        </AlertDescription>
      </Alert>

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Mic className="h-5 w-5" />
            Voice Interface
          </CardTitle>
          <CardDescription>
            Interactive voice bot testing
          </CardDescription>
        </CardHeader>
        <CardContent>
          <iframe
            src={`${apiUrl}/voice`}
            className="w-full h-[600px] border-0 rounded-lg"
            title="Voice Bot Interface"
            allow="microphone"
          />
        </CardContent>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle>Voice Services</CardTitle>
        </CardHeader>
        <CardContent className="grid gap-4 md:grid-cols-3">
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
            <p className="text-sm text-muted-foreground">Piper / ElevenLabs</p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
