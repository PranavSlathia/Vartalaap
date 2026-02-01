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
import {
  RefreshCw,
  Loader2,
  Eye,
  Star,
  AlertTriangle,
  BookOpen,
  MessageSquare,
  CheckCircle,
  XCircle,
  Clock,
  Lightbulb,
} from 'lucide-react';
import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { toast } from 'sonner';
import {
  useListReviewsApiReviewsGet,
  useGetReviewStatsApiReviewsStatsGet,
  useListSuggestionsApiReviewsSuggestionsGet,
  useUpdateSuggestionApiReviewsSuggestionsSuggestionIdPatch,
  getListSuggestionsApiReviewsSuggestionsGetQueryKey,
  getListReviewsApiReviewsGetQueryKey,
  getGetReviewStatsApiReviewsStatsGetQueryKey,
} from '@/api/endpoints/reviews/reviews';
import type { TranscriptReviewResponse, ImprovementSuggestionResponse, SuggestionStatus } from '@/api/model';
import { getBusinessId } from '@/lib/business';

// Score colors from red (1) to green (5)
const scoreColors: Record<number, string> = {
  1: 'text-red-500',
  2: 'text-orange-500',
  3: 'text-yellow-500',
  4: 'text-lime-500',
  5: 'text-green-500',
};

const categoryColors: Record<string, string> = {
  knowledge_gap: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
  prompt_weakness: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300',
  ux_issue: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300',
  stt_error: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
  tts_issue: 'bg-pink-100 text-pink-800 dark:bg-pink-900 dark:text-pink-300',
  config_error: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300',
};

const statusColors: Record<string, string> = {
  pending: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
  implemented: 'bg-green-100 text-green-800 dark:bg-green-900 dark:text-green-300',
  rejected: 'bg-red-100 text-red-800 dark:bg-red-900 dark:text-red-300',
  deferred: 'bg-gray-100 text-gray-800 dark:bg-gray-900 dark:text-gray-300',
};

function QualityStars({ score }: { score: number }) {
  return (
    <div className="flex items-center gap-0.5">
      {[1, 2, 3, 4, 5].map((i) => (
        <Star
          key={i}
          className={`h-4 w-4 ${i <= score ? scoreColors[score] : 'text-gray-300 dark:text-gray-600'}`}
          fill={i <= score ? 'currentColor' : 'none'}
        />
      ))}
    </div>
  );
}

function IssueFlags({ review }: { review: TranscriptReviewResponse }) {
  const flags = [];
  if (review.has_unanswered_query) flags.push({ label: 'Unanswered', icon: MessageSquare });
  if (review.has_knowledge_gap) flags.push({ label: 'Knowledge Gap', icon: BookOpen });
  if (review.has_prompt_weakness) flags.push({ label: 'Prompt', icon: AlertTriangle });
  if (review.has_ux_issue) flags.push({ label: 'UX', icon: AlertTriangle });

  if (flags.length === 0) {
    return <span className="text-muted-foreground text-sm">None</span>;
  }

  return (
    <div className="flex flex-wrap gap-1">
      {flags.map(({ label, icon: Icon }) => (
        <Badge key={label} variant="outline" className="text-xs">
          <Icon className="h-3 w-3 mr-1" />
          {label}
        </Badge>
      ))}
    </div>
  );
}

interface ReviewDetailModalProps {
  review: TranscriptReviewResponse;
  suggestions: ImprovementSuggestionResponse[];
  onSuggestionUpdate: (suggestionId: string, status: SuggestionStatus, rejectionReason?: string) => void;
  isUpdating: boolean;
}

function ReviewDetailModal({ review, suggestions, onSuggestionUpdate, isUpdating }: ReviewDetailModalProps) {
  const [rejectionReason, setRejectionReason] = useState<Record<string, string>>({});

  // Parse issues JSON
  let issues: Array<{ category: string; description: string; severity: string }> = [];
  try {
    if (review.issues_json) {
      issues = JSON.parse(review.issues_json as string);
    }
  } catch {
    // Ignore parse errors
  }

  // Filter suggestions for this review
  const reviewSuggestions = suggestions.filter(s => s.review_id === review.id);

  return (
    <DialogContent className="max-w-3xl max-h-[85vh] overflow-y-auto">
      <DialogHeader>
        <DialogTitle className="flex items-center gap-2">
          Review Details
          <QualityStars score={review.quality_score} />
        </DialogTitle>
        <DialogDescription>
          Review ID: {review.id} | Call: {review.call_log_id}
        </DialogDescription>
      </DialogHeader>

      <div className="space-y-6">
        {/* Review metadata */}
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
          <div>
            <p className="text-sm font-medium">Quality Score</p>
            <p className="text-2xl font-bold">{review.quality_score}/5</p>
          </div>
          <div>
            <p className="text-sm font-medium">Reviewed At</p>
            <p className="text-sm text-muted-foreground">
              {new Date(review.reviewed_at).toLocaleString()}
            </p>
          </div>
          <div>
            <p className="text-sm font-medium">Agent Model</p>
            <p className="text-sm text-muted-foreground">{review.agent_model}</p>
          </div>
          <div>
            <p className="text-sm font-medium">Latency</p>
            <p className="text-sm text-muted-foreground">
              {review.review_latency_ms ? `${Math.round(review.review_latency_ms as number)}ms` : '—'}
            </p>
          </div>
        </div>

        {/* Issue flags */}
        <div>
          <p className="text-sm font-medium mb-2">Issue Flags</p>
          <IssueFlags review={review} />
        </div>

        {/* Issues list */}
        {issues.length > 0 && (
          <div>
            <p className="text-sm font-medium mb-2">Issues Identified ({issues.length})</p>
            <div className="space-y-2">
              {issues.map((issue, idx) => (
                <div key={idx} className="border rounded-lg p-3">
                  <div className="flex items-center gap-2 mb-1">
                    <Badge className={categoryColors[issue.category] || 'bg-gray-100'}>
                      {issue.category.replace('_', ' ')}
                    </Badge>
                    <Badge variant="outline">{issue.severity}</Badge>
                  </div>
                  <p className="text-sm">{issue.description}</p>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Suggestions */}
        {reviewSuggestions.length > 0 && (
          <div>
            <p className="text-sm font-medium mb-2">Improvement Suggestions ({reviewSuggestions.length})</p>
            <div className="space-y-3">
              {reviewSuggestions.map((suggestion) => (
                <div key={suggestion.id} className="border rounded-lg p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1">
                      <div className="flex items-center gap-2 mb-1">
                        <Lightbulb className="h-4 w-4 text-yellow-500" />
                        <span className="font-medium">{suggestion.title}</span>
                        <Badge className={categoryColors[suggestion.category] || 'bg-gray-100'}>
                          {suggestion.category.replace('_', ' ')}
                        </Badge>
                        <Badge variant="outline">P{suggestion.priority}</Badge>
                      </div>
                      <p className="text-sm text-muted-foreground mb-2">{suggestion.description}</p>
                      <Badge className={statusColors[suggestion.status]}>
                        {suggestion.status}
                      </Badge>
                      {suggestion.implemented_at && (
                        <span className="text-xs text-muted-foreground ml-2">
                          Implemented {new Date(suggestion.implemented_at as string).toLocaleDateString()}
                          {suggestion.implemented_by && ` by ${suggestion.implemented_by}`}
                        </span>
                      )}
                      {suggestion.rejection_reason && (
                        <p className="text-xs text-red-500 mt-1">
                          Rejected: {suggestion.rejection_reason}
                        </p>
                      )}
                    </div>
                    {suggestion.status === 'pending' && (
                      <div className="flex flex-col gap-2">
                        <Button
                          size="sm"
                          variant="outline"
                          className="text-green-600"
                          disabled={isUpdating}
                          onClick={() => onSuggestionUpdate(suggestion.id, 'implemented' as SuggestionStatus)}
                        >
                          <CheckCircle className="h-4 w-4 mr-1" />
                          Implement
                        </Button>
                        <div className="flex gap-1">
                          <input
                            type="text"
                            placeholder="Reason..."
                            className="text-xs border rounded px-2 py-1 w-24"
                            value={rejectionReason[suggestion.id] || ''}
                            onChange={(e) => setRejectionReason(prev => ({ ...prev, [suggestion.id]: e.target.value }))}
                          />
                          <Button
                            size="sm"
                            variant="outline"
                            className="text-red-600"
                            disabled={isUpdating}
                            onClick={() => onSuggestionUpdate(
                              suggestion.id,
                              'rejected' as SuggestionStatus,
                              rejectionReason[suggestion.id]
                            )}
                          >
                            <XCircle className="h-4 w-4" />
                          </Button>
                        </div>
                      </div>
                    )}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Raw JSON for debugging */}
        {review.issues_json && (
          <details className="text-xs">
            <summary className="cursor-pointer text-muted-foreground">Raw Issues JSON</summary>
            <pre className="bg-muted p-2 rounded mt-2 overflow-x-auto">
              {JSON.stringify(JSON.parse(review.issues_json as string), null, 2)}
            </pre>
          </details>
        )}
      </div>
    </DialogContent>
  );
}

export function Reviews() {
  const [scoreFilter, setScoreFilter] = useState<number | 'all'>('all');
  const [hasIssuesFilter, setHasIssuesFilter] = useState<boolean | null>(null);
  const businessId = getBusinessId();
  const queryClient = useQueryClient();

  // Fetch reviews
  const {
    data: reviews,
    isLoading,
    error,
    refetch,
  } = useListReviewsApiReviewsGet({
    business_id: businessId,
    ...(scoreFilter !== 'all' ? { max_score: scoreFilter, min_score: scoreFilter } : {}),
    ...(hasIssuesFilter !== null ? { has_issues: hasIssuesFilter } : {}),
  });

  // Fetch stats
  const { data: stats, isLoading: statsLoading } = useGetReviewStatsApiReviewsStatsGet({
    business_id: businessId,
  });

  // Fetch suggestions
  const { data: suggestions } = useListSuggestionsApiReviewsSuggestionsGet({
    business_id: businessId,
  });

  // Update suggestion mutation
  const updateMutation = useUpdateSuggestionApiReviewsSuggestionsSuggestionIdPatch({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({ queryKey: getListSuggestionsApiReviewsSuggestionsGetQueryKey() });
        queryClient.invalidateQueries({ queryKey: getListReviewsApiReviewsGetQueryKey() });
        queryClient.invalidateQueries({ queryKey: getGetReviewStatsApiReviewsStatsGetQueryKey() });
        toast.success('Suggestion updated');
      },
      onError: (error) => {
        toast.error(`Failed to update: ${error.message}`);
      },
    },
  });

  const handleSuggestionUpdate = (suggestionId: string, status: SuggestionStatus, rejectionReason?: string) => {
    updateMutation.mutate({
      suggestionId,
      data: {
        status,
        ...(rejectionReason ? { rejection_reason: rejectionReason } : {}),
      },
    });
  };

  const reviewList = reviews || [];
  const suggestionList = suggestions || [];
  const scoreOptions: (number | 'all')[] = ['all', 1, 2, 3, 4, 5];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Quality Reviews</h2>
          <p className="text-muted-foreground">
            AI-powered analysis of call transcripts to identify issues and improvements.
          </p>
        </div>
        <Button variant="outline" size="icon" onClick={() => refetch()}>
          <RefreshCw className={`h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      {/* Stats Cards */}
      <div className="grid gap-4 md:grid-cols-4 lg:grid-cols-7">
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Total Reviews</CardTitle>
            <Star className="h-4 w-4 text-muted-foreground" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {statsLoading ? '...' : stats?.total_reviews || 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Avg Score</CardTitle>
            <Star className="h-4 w-4 text-yellow-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {statsLoading ? '...' : (stats?.avg_quality_score?.toFixed(1) || '—')}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">With Issues</CardTitle>
            <AlertTriangle className="h-4 w-4 text-orange-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {statsLoading ? '...' : stats?.reviews_with_issues || 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Knowledge Gaps</CardTitle>
            <BookOpen className="h-4 w-4 text-blue-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {statsLoading ? '...' : stats?.knowledge_gaps || 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Prompt Issues</CardTitle>
            <MessageSquare className="h-4 w-4 text-purple-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {statsLoading ? '...' : stats?.prompt_weaknesses || 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">UX Issues</CardTitle>
            <AlertTriangle className="h-4 w-4 text-orange-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {statsLoading ? '...' : stats?.ux_issues || 0}
            </div>
          </CardContent>
        </Card>
        <Card>
          <CardHeader className="flex flex-row items-center justify-between space-y-0 pb-2">
            <CardTitle className="text-sm font-medium">Pending</CardTitle>
            <Clock className="h-4 w-4 text-yellow-500" />
          </CardHeader>
          <CardContent>
            <div className="text-2xl font-bold">
              {statsLoading ? '...' : stats?.pending_suggestions || 0}
            </div>
          </CardContent>
        </Card>
      </div>

      {/* Filters */}
      <div className="flex gap-4 flex-wrap">
        <div className="flex gap-2 items-center">
          <span className="text-sm text-muted-foreground">Score:</span>
          {scoreOptions.map((score) => (
            <Button
              key={score}
              variant={scoreFilter === score ? 'default' : 'outline'}
              size="sm"
              onClick={() => setScoreFilter(score)}
            >
              {score === 'all' ? 'All' : `${score}★`}
            </Button>
          ))}
        </div>
        <div className="flex gap-2 items-center">
          <span className="text-sm text-muted-foreground">Issues:</span>
          <Button
            variant={hasIssuesFilter === null ? 'default' : 'outline'}
            size="sm"
            onClick={() => setHasIssuesFilter(null)}
          >
            All
          </Button>
          <Button
            variant={hasIssuesFilter === true ? 'default' : 'outline'}
            size="sm"
            onClick={() => setHasIssuesFilter(true)}
          >
            Has Issues
          </Button>
          <Button
            variant={hasIssuesFilter === false ? 'default' : 'outline'}
            size="sm"
            onClick={() => setHasIssuesFilter(false)}
          >
            No Issues
          </Button>
        </div>
      </div>

      {/* Reviews Table */}
      <Card>
        <CardHeader>
          <CardTitle>Reviews ({reviewList.length})</CardTitle>
          <CardDescription>
            Click on a review to see detailed issues and suggestions.
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error ? (
            <div className="text-center py-8 text-red-500">
              <p>Error loading reviews: {error.message}</p>
              <Button variant="outline" onClick={() => refetch()} className="mt-4">
                Retry
              </Button>
            </div>
          ) : isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : reviewList.length === 0 ? (
            <p className="text-center py-8 text-muted-foreground">
              No reviews found. Reviews are generated automatically when calls end.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Quality</TableHead>
                  <TableHead>Issues</TableHead>
                  <TableHead>Call ID</TableHead>
                  <TableHead>Reviewed</TableHead>
                  <TableHead>Model</TableHead>
                  <TableHead>Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {reviewList.map((review) => (
                  <TableRow key={review.id}>
                    <TableCell>
                      <QualityStars score={review.quality_score} />
                    </TableCell>
                    <TableCell>
                      <IssueFlags review={review} />
                    </TableCell>
                    <TableCell className="font-mono text-xs">
                      {review.call_log_id.slice(0, 8)}...
                    </TableCell>
                    <TableCell className="text-sm">
                      {new Date(review.reviewed_at).toLocaleString()}
                    </TableCell>
                    <TableCell className="text-xs text-muted-foreground">
                      {review.agent_model}
                    </TableCell>
                    <TableCell>
                      <Dialog>
                        <DialogTrigger asChild>
                          <Button variant="ghost" size="sm">
                            <Eye className="h-4 w-4" />
                          </Button>
                        </DialogTrigger>
                        <ReviewDetailModal
                          review={review}
                          suggestions={suggestionList}
                          onSuggestionUpdate={handleSuggestionUpdate}
                          isUpdating={updateMutation.isPending}
                        />
                      </Dialog>
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
