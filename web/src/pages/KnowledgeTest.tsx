import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Search, RefreshCw, Play, Info, Loader2 } from 'lucide-react';
import { useState } from 'react';
import {
  useListKnowledgeItemsApiKnowledgeGet,
  useSearchKnowledgeApiKnowledgeSearchPost,
} from '@/api/endpoints/knowledge/knowledge';
import type { KnowledgeCategory } from '@/api/model';
import { getBusinessId } from '@/lib/business';

const sampleQueries = [
  'Momos kitne ke hain?',
  'What are your opening hours?',
  'Do you have vegetarian options?',
  'Can I book a table for 8 people?',
  'Aaj special kya hai?',
  'Delivery available hai?',
];

const categoryColors: Record<KnowledgeCategory, string> = {
  menu_item: 'bg-orange-100 text-orange-800 dark:bg-orange-900 dark:text-orange-300',
  faq: 'bg-blue-100 text-blue-800 dark:bg-blue-900 dark:text-blue-300',
  policy: 'bg-purple-100 text-purple-800 dark:bg-purple-900 dark:text-purple-300',
  announcement: 'bg-yellow-100 text-yellow-800 dark:bg-yellow-900 dark:text-yellow-300',
};

export function KnowledgeTest() {
  const [query, setQuery] = useState('');
  const [searchResults, setSearchResults] = useState<Array<{ item: any; score: number }>>([]);
  const [searchTime, setSearchTime] = useState<number | null>(null);
  const [batchQueries, setBatchQueries] = useState(sampleQueries.join('\n'));
  const [batchResults, setBatchResults] = useState<Array<{ query: string; results: number; topScore: number }>>([]);
  const businessId = getBusinessId();

  // Fetch all knowledge items for stats - scoped by business_id
  const { data: allItems, isLoading: statsLoading, refetch } = useListKnowledgeItemsApiKnowledgeGet({
    business_id: businessId,
  });

  // Search mutation
  const searchMutation = useSearchKnowledgeApiKnowledgeSearchPost();

  const handleSearch = async () => {
    if (!query.trim()) return;

    const startTime = performance.now();
    try {
      const results = await searchMutation.mutateAsync({
        params: {
          query: query,
          business_id: getBusinessId(),
          limit: 5,
        },
      });
      const endTime = performance.now();
      setSearchTime(Math.round(endTime - startTime));
      setSearchResults(results.map(r => ({ item: r.item, score: r.score })));
    } catch (error) {
      console.error('Search failed:', error);
      setSearchResults([]);
    }
  };

  const handleBatchTest = async () => {
    const queries = batchQueries.split('\n').filter(q => q.trim());
    const results: Array<{ query: string; results: number; topScore: number }> = [];

    for (const q of queries) {
      try {
        const searchResults = await searchMutation.mutateAsync({
          params: {
            query: q.trim(),
            business_id: getBusinessId(),
            limit: 3,
          },
        });
        results.push({
          query: q.trim(),
          results: searchResults.length,
          topScore: searchResults.length > 0 ? searchResults[0].score : 0,
        });
      } catch {
        results.push({
          query: q.trim(),
          results: 0,
          topScore: 0,
        });
      }
    }

    setBatchResults(results);
  };

  const getScoreColor = (score: number) => {
    if (score >= 0.7) return 'text-green-600 dark:text-green-400';
    if (score >= 0.4) return 'text-yellow-600 dark:text-yellow-400';
    return 'text-red-600 dark:text-red-400';
  };

  const getScoreBadge = (score: number): 'default' | 'secondary' | 'destructive' => {
    if (score >= 0.7) return 'default';
    if (score >= 0.4) return 'secondary';
    return 'destructive';
  };

  // Calculate stats
  const stats = {
    total: allItems?.length || 0,
    menuItems: allItems?.filter(i => i.category === 'menu_item').length || 0,
    faqs: allItems?.filter(i => i.category === 'faq').length || 0,
    policies: allItems?.filter(i => i.category === 'policy').length || 0,
    announcements: allItems?.filter(i => i.category === 'announcement').length || 0,
  };

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Knowledge Test</h2>
          <p className="text-muted-foreground">
            Test knowledge retrieval before going live with voice calls
          </p>
        </div>
        <Button variant="outline" size="icon" onClick={() => refetch()}>
          <RefreshCw className={`h-4 w-4 ${statsLoading ? 'animate-spin' : ''}`} />
        </Button>
      </div>

      <div className="grid gap-6 lg:grid-cols-4">
        {/* Sidebar */}
        <div className="space-y-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-sm">Index Stats</CardTitle>
            </CardHeader>
            <CardContent className="space-y-2 text-sm">
              {statsLoading ? (
                <div className="flex justify-center py-2">
                  <Loader2 className="h-4 w-4 animate-spin" />
                </div>
              ) : (
                <>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">Indexed Items</span>
                    <span className="font-medium">{stats.total}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">- Menu Items</span>
                    <span>{stats.menuItems}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">- FAQs</span>
                    <span>{stats.faqs}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">- Policies</span>
                    <span>{stats.policies}</span>
                  </div>
                  <div className="flex justify-between">
                    <span className="text-muted-foreground">- Announcements</span>
                    <span>{stats.announcements}</span>
                  </div>
                </>
              )}
            </CardContent>
          </Card>
        </div>

        {/* Main Content */}
        <div className="lg:col-span-3 space-y-4">
          <Card>
            <CardHeader>
              <CardTitle>Test Query</CardTitle>
              <CardDescription>
                Enter a query to test knowledge retrieval
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <div className="flex gap-2">
                <div className="flex-1">
                  <Input
                    placeholder="Momos kitne ke hain?"
                    value={query}
                    onChange={(e) => setQuery(e.target.value)}
                    onKeyDown={(e) => e.key === 'Enter' && handleSearch()}
                  />
                </div>
                <Button onClick={handleSearch} disabled={searchMutation.isPending}>
                  {searchMutation.isPending ? (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  ) : (
                    <Search className="h-4 w-4 mr-2" />
                  )}
                  {searchMutation.isPending ? 'Searching...' : 'Search'}
                </Button>
              </div>

              <div>
                <Label className="text-xs text-muted-foreground">Quick Test Queries:</Label>
                <div className="flex flex-wrap gap-2 mt-2">
                  {sampleQueries.slice(0, 4).map((q) => (
                    <Button
                      key={q}
                      variant="outline"
                      size="sm"
                      onClick={() => {
                        setQuery(q);
                        // Trigger search after setting query
                        setTimeout(() => handleSearch(), 0);
                      }}
                    >
                      {q}
                    </Button>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>

          {searchResults.length > 0 && (
            <Card>
              <CardHeader>
                <CardTitle>Results ({searchResults.length})</CardTitle>
                <CardDescription>
                  Query: "{query}" | Time: {searchTime}ms
                </CardDescription>
              </CardHeader>
              <CardContent className="space-y-4">
                {searchResults.map((result, index) => (
                  <div
                    key={result.item.id}
                    className="border rounded-lg p-4 space-y-2"
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-medium text-muted-foreground">
                          #{index + 1}
                        </span>
                        <Badge className={categoryColors[result.item.category as KnowledgeCategory]}>
                          {result.item.category}
                        </Badge>
                        <span className="font-medium">{result.item.title}</span>
                      </div>
                      <Badge variant={getScoreBadge(result.score)} className={getScoreColor(result.score)}>
                        Score: {result.score.toFixed(3)}
                      </Badge>
                    </div>
                    <p className="text-sm text-muted-foreground">
                      {result.item.content}
                    </p>
                  </div>
                ))}
              </CardContent>
            </Card>
          )}

          <Card>
            <CardHeader>
              <CardTitle>Batch Test</CardTitle>
              <CardDescription>
                Test multiple queries at once to verify coverage
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-4">
              <textarea
                className="w-full h-40 px-3 py-2 border rounded-md text-sm"
                placeholder="Enter test queries (one per line)..."
                value={batchQueries}
                onChange={(e) => setBatchQueries(e.target.value)}
              />
              <Button onClick={handleBatchTest} disabled={searchMutation.isPending}>
                {searchMutation.isPending ? (
                  <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                ) : (
                  <Play className="h-4 w-4 mr-2" />
                )}
                Run Batch Test
              </Button>

              {batchResults.length > 0 && (
                <div className="mt-4 space-y-2">
                  <h4 className="font-medium">Batch Results:</h4>
                  {batchResults.map((r, i) => (
                    <div key={i} className="flex items-center justify-between p-2 border rounded text-sm">
                      <span className="truncate flex-1">{r.query}</span>
                      <div className="flex gap-2 items-center">
                        <span className="text-muted-foreground">{r.results} results</span>
                        <Badge variant={getScoreBadge(r.topScore)} className={getScoreColor(r.topScore)}>
                          {r.topScore.toFixed(2)}
                        </Badge>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </CardContent>
          </Card>

          <Alert>
            <Info className="h-4 w-4" />
            <AlertDescription>
              <strong>Score Guide:</strong>
              <ul className="list-disc list-inside mt-1 text-sm">
                <li><span className="text-green-600">≥ 0.7</span> - Excellent match (Pass)</li>
                <li><span className="text-yellow-600">0.4 - 0.7</span> - Good match (Weak)</li>
                <li><span className="text-red-600">&lt; 0.4</span> - Poor match (Miss)</li>
              </ul>
            </AlertDescription>
          </Alert>
        </div>
      </div>
    </div>
  );
}
