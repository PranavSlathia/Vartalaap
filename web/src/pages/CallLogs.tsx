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
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { RefreshCw, Loader2, Eye, Phone, Clock, CheckCircle, XCircle, AlertTriangle, Monitor } from 'lucide-react';
import { useState } from 'react';
import {
  useListCallLogsApiCallLogsGet,
  useGetCallLogSummaryApiCallLogsSummaryGet,
} from '@/api/endpoints/call-logs/call-logs';
import type { CallOutcome } from '@/api/model';
import { getBusinessId } from '@/lib/business';

const outcomeColors: Record<string, string> = {
  resolved: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  fallback: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
  dropped: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
  error: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
  privacy_opt_out: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300',
};

const outcomeIcons: Record<string, typeof CheckCircle> = {
  resolved: CheckCircle,
  fallback: AlertTriangle,
  dropped: XCircle,
  error: XCircle,
  privacy_opt_out: XCircle,
};

function formatDuration(seconds: number | null | undefined): string {
  if (!seconds) return '—';
  const mins = Math.floor(seconds / 60);
  const secs = seconds % 60;
  return `${mins}:${secs.toString().padStart(2, '0')}`;
}

function maskCallerId(hash: string | null | undefined): string {
  if (!hash) return 'Unknown';
  // Show first 4 and last 4 chars of hash for identification
  return `${hash.slice(0, 4)}...${hash.slice(-4)}`;
}

export function CallLogs() {
  const [_selectedLog, setSelectedLog] = useState<string | null>(null);
  const [outcomeFilter, setOutcomeFilter] = useState<CallOutcome | 'all'>('all');
  const businessId = getBusinessId();

  // Fetch call logs - always scope by business_id to prevent multi-tenant data leakage
  const {
    data: callLogs,
    isLoading,
    error,
    refetch,
  } = useListCallLogsApiCallLogsGet({
    business_id: businessId,
    ...(outcomeFilter !== 'all' ? { outcome: outcomeFilter } : {}),
  });

  // Fetch summary stats - scoped by business_id
  const { data: summary, isLoading: summaryLoading } = useGetCallLogSummaryApiCallLogsSummaryGet({
    business_id: businessId,
  });

  const logs = callLogs || [];
  const outcomeOptions: (CallOutcome | 'all')[] = ['all', 'resolved', 'fallback', 'dropped', 'error', 'privacy_opt_out'];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Call Logs</h2>
          <p className="text-muted-foreground">
            View and analyze voice bot call history.
          </p>
        </div>
        <Button variant="outline" size="icon" onClick={() => refetch()}>
          <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      {/* Summary Stats */}
      <div className="grid gap-4 md:grid-cols-4">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Calls</CardTitle>
            <Phone className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {summaryLoading ? '...' : summary?.total_calls || 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Avg Duration</CardTitle>
            <Clock className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {summaryLoading ? '...' : formatDuration(summary?.avg_duration_seconds)}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Resolved</CardTitle>
            <CheckCircle className="h-4 w-4 text-green-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {summaryLoading ? '...' : summary?.calls_by_outcome?.resolved || 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Fallbacks</CardTitle>
            <AlertTriangle className="h-4 w-4 text-yellow-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {summaryLoading ? '...' : summary?.calls_by_outcome?.fallback || 0}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Outcome filter */}
      <div className="flex gap-2 flex-wrap">
        {outcomeOptions.map((outcome) => (
          <Button
            key={outcome}
            variant={outcomeFilter === outcome ? 'default' : 'outline'}
            size="sm"
            onClick={() => setOutcomeFilter(outcome)}
          >
            {outcome === 'all' ? 'All' : outcome.replace('_', ' ')}
          </Button>
        ))}
      </div>

      <Card>
        <CardHeader>
          <CardTitle>Call History ({logs.length})</CardTitle>
          <CardDescription>
            {outcomeFilter === 'all'
              ? 'All calls'
              : `Showing ${outcomeFilter.replace('_', ' ')} calls`}
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error ? (
            <div className="text-center py-8 text-red-500">
              <p>Error loading call logs: {error.message}</p>
              <Button variant="outline" onClick={() => refetch()} className="mt-4">
                Retry
              </Button>
            </div>
          ) : isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : logs.length === 0 ? (
            <p className="text-center py-8 text-muted-foreground">
              No call logs found. Calls will appear here after the voice bot handles them.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Source</TableHead>
                  <TableHead>Caller ID</TableHead>
                  <TableHead>Duration</TableHead>
                  <TableHead>Language</TableHead>
                  <TableHead>Timestamp</TableHead>
                  <TableHead>Outcome</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {logs.map((log) => {
                  const OutcomeIcon = outcomeIcons[log.outcome || 'error'] || XCircle;
                  const isVoiceTest = log.call_source === 'voice_test';
                  return (
                    <TableRow key={log.id}>
                      <TableCell>
                        <Badge
                          variant="outline"
                          className={isVoiceTest
                            ? 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300'
                            : 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300'
                          }
                        >
                          {isVoiceTest ? (
                            <><Monitor className="h-3 w-3 mr-1" />Test</>
                          ) : (
                            <><Phone className="h-3 w-3 mr-1" />Phone</>
                          )}
                        </Badge>
                      </TableCell>
                      <TableCell className="font-mono text-xs">
                        {maskCallerId(log.caller_id_hash)}
                      </TableCell>
                      <TableCell>{formatDuration(log.duration_seconds)}</TableCell>
                      <TableCell>
                        <Badge variant="outline">
                          {log.detected_language || 'unknown'}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-sm">
                        {new Date(log.call_start).toLocaleString()}
                      </TableCell>
                      <TableCell>
                        <Badge className={outcomeColors[log.outcome || 'error']}>
                          <OutcomeIcon className="h-3 w-3 mr-1" />
                          {(log.outcome || 'unknown').replace('_', ' ')}
                        </Badge>
                      </TableCell>
                      <TableCell>
                        <Dialog>
                          <DialogTrigger asChild>
                            <Button
                              variant="ghost"
                              size="sm"
                              onClick={() => setSelectedLog(log.id)}
                            >
                              <Eye className="h-4 w-4" />
                            </Button>
                          </DialogTrigger>
                          <DialogContent className="max-w-2xl max-h-[80vh] overflow-y-auto">
                            <DialogHeader>
                              <DialogTitle>Call Details</DialogTitle>
                              <DialogDescription>
                                Call ID: {log.id}
                              </DialogDescription>
                            </DialogHeader>
                            <div className="space-y-4">
                              <div className="grid grid-cols-2 gap-4">
                                <div>
                                  <p className="text-sm font-medium">Duration</p>
                                  <p className="text-sm text-muted-foreground">
                                    {formatDuration(log.duration_seconds)}
                                  </p>
                                </div>
                                <div>
                                  <p className="text-sm font-medium">Language</p>
                                  <p className="text-sm text-muted-foreground">
                                    {log.detected_language || 'Unknown'}
                                  </p>
                                </div>
                                <div>
                                  <p className="text-sm font-medium">Outcome</p>
                                  <p className="text-sm text-muted-foreground">
                                    {log.outcome || 'Unknown'}
                                  </p>
                                </div>
                                <div>
                                  <p className="text-sm font-medium">Consent</p>
                                  <p className="text-sm text-muted-foreground">
                                    {log.consent_type || 'None'}
                                  </p>
                                </div>
                              </div>
                              {log.transcript && (
                                <div>
                                  <p className="text-sm font-medium mb-2">Transcript</p>
                                  <pre className="text-xs bg-muted p-4 rounded-lg overflow-x-auto">
                                    {log.transcript}
                                  </pre>
                                </div>
                              )}
                              {log.extracted_info && (
                                <div>
                                  <p className="text-sm font-medium mb-2">Extracted Info</p>
                                  <pre className="text-xs bg-muted p-4 rounded-lg overflow-x-auto">
                                    {log.extracted_info}
                                  </pre>
                                </div>
                              )}
                            </div>
                          </DialogContent>
                        </Dialog>
                      </TableCell>
                    </TableRow>
                  );
                })}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>
    </div>
  );
}
