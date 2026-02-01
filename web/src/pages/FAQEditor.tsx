import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Plus, Trash2, RefreshCw, Loader2 } from 'lucide-react';
import { useState } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import {
  useListKnowledgeItemsApiKnowledgeGet,
  useCreateKnowledgeItemApiKnowledgePost,
  useUpdateKnowledgeItemApiKnowledgeItemIdPatch,
  useDeleteKnowledgeItemApiKnowledgeItemIdDelete,
  getListKnowledgeItemsApiKnowledgeGetQueryKey,
} from '@/api/endpoints/knowledge/knowledge';
import type { KnowledgeCategory } from '@/api/model';
import { getBusinessId } from '@/lib/business';

const categoryLabels: Record<KnowledgeCategory, string> = {
  menu_item: 'Menu Item',
  faq: 'FAQ',
  policy: 'Policy',
  announcement: 'Announcement',
};

const topics = ['All', 'Hours & Location', 'Reservations', 'Menu & Dietary', 'Delivery & Takeaway', 'Payment', 'Events & Parties', 'Other'];

export function FAQEditor() {
  const [selectedCategory, setSelectedCategory] = useState<KnowledgeCategory | 'all'>('all');
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
  const [addType, setAddType] = useState<KnowledgeCategory>('faq');
  const businessId = getBusinessId();
  const [newItem, setNewItem] = useState({
    title: '',
    title_hindi: '',
    content: '',
    content_hindi: '',
    topic: 'Other',
    priority: 50,
  });

  const queryClient = useQueryClient();

  // Fetch all non-menu knowledge items - always scope by business_id to prevent multi-tenant data leakage
  const {
    data: allItems,
    isLoading,
    error,
    refetch,
  } = useListKnowledgeItemsApiKnowledgeGet({
    business_id: businessId,
    ...(selectedCategory !== 'all' ? { category: selectedCategory } : {}),
  });

  // Filter out menu_items if showing all
  const items = (allItems || []).filter(item =>
    selectedCategory === 'all' ? item.category !== 'menu_item' : true
  );

  // Create mutation
  const createMutation = useCreateKnowledgeItemApiKnowledgePost({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getListKnowledgeItemsApiKnowledgeGetQueryKey(),
        });
        setIsAddDialogOpen(false);
        setNewItem({ title: '', title_hindi: '', content: '', content_hindi: '', topic: 'Other', priority: 50 });
      },
    },
  });

  // Update mutation
  const updateMutation = useUpdateKnowledgeItemApiKnowledgeItemIdPatch({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getListKnowledgeItemsApiKnowledgeGetQueryKey(),
        });
      },
    },
  });

  // Delete mutation
  const deleteMutation = useDeleteKnowledgeItemApiKnowledgeItemIdDelete({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getListKnowledgeItemsApiKnowledgeGetQueryKey(),
        });
      },
    },
  });

  const handleCreate = () => {
    const metadata = JSON.stringify({ topic: newItem.topic });
    createMutation.mutate({
      data: {
        business_id: businessId,
        category: addType,
        title: newItem.title,
        title_hindi: newItem.title_hindi || undefined,
        content: newItem.content,
        content_hindi: newItem.content_hindi || undefined,
        metadata_json: metadata,
        is_active: true,
        priority: newItem.priority,
      },
    });
  };

  const handleToggleActive = (itemId: string, currentActive: boolean) => {
    updateMutation.mutate({
      itemId,
      data: { is_active: !currentActive },
    });
  };

  const handleDelete = (itemId: string) => {
    if (confirm('Are you sure you want to delete this item?')) {
      deleteMutation.mutate({ itemId });
    }
  };

  const parseMetadata = (metadataJson: string | null | undefined) => {
    if (!metadataJson) return { topic: 'Other' };
    try {
      return JSON.parse(metadataJson);
    } catch {
      return { topic: 'Other' };
    }
  };

  // Group items by category
  const faqs = items.filter(i => i.category === 'faq');
  const policies = items.filter(i => i.category === 'policy');
  const announcements = items.filter(i => i.category === 'announcement');

  const categoryOptions: (KnowledgeCategory | 'all')[] = ['all', 'faq', 'policy', 'announcement'];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">FAQ Editor</h2>
          <p className="text-muted-foreground">
            Manage frequently asked questions for knowledge-based retrieval
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
                Add Item
              </Button>
            </DialogTrigger>
            <DialogContent className="max-w-2xl">
              <DialogHeader>
                <DialogTitle>Add Knowledge Item</DialogTitle>
                <DialogDescription>
                  Add a new FAQ, policy, or announcement. It will be indexed for voice retrieval.
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="space-y-2">
                  <Label htmlFor="type">Type</Label>
                  <select
                    id="type"
                    className="w-full h-10 px-3 border rounded-md"
                    value={addType}
                    onChange={(e) => setAddType(e.target.value as KnowledgeCategory)}
                  >
                    <option value="faq">FAQ</option>
                    <option value="policy">Policy</option>
                    <option value="announcement">Announcement</option>
                  </select>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="title">{addType === 'faq' ? 'Question' : 'Title'} *</Label>
                  <Input
                    id="title"
                    placeholder={addType === 'faq' ? 'What are your opening hours?' : 'Cancellation Policy'}
                    value={newItem.title}
                    onChange={(e) => setNewItem({ ...newItem, title: e.target.value })}
                  />
                </div>
                {addType === 'faq' && (
                  <div className="space-y-2">
                    <Label htmlFor="title_hindi">Question (Hindi)</Label>
                    <Input
                      id="title_hindi"
                      placeholder="आपके खुलने का समय क्या है?"
                      value={newItem.title_hindi}
                      onChange={(e) => setNewItem({ ...newItem, title_hindi: e.target.value })}
                    />
                  </div>
                )}
                <div className="space-y-2">
                  <Label htmlFor="content">{addType === 'faq' ? 'Answer' : 'Content'} *</Label>
                  <textarea
                    id="content"
                    className="w-full h-24 px-3 py-2 border rounded-md"
                    placeholder={addType === 'faq' ? 'We are open Tuesday to Sunday...' : 'Policy details...'}
                    value={newItem.content}
                    onChange={(e) => setNewItem({ ...newItem, content: e.target.value })}
                  />
                </div>
                {addType === 'faq' && (
                  <div className="grid grid-cols-2 gap-4">
                    <div className="space-y-2">
                      <Label htmlFor="topic">Topic</Label>
                      <select
                        id="topic"
                        className="w-full h-10 px-3 border rounded-md"
                        value={newItem.topic}
                        onChange={(e) => setNewItem({ ...newItem, topic: e.target.value })}
                      >
                        {topics.slice(1).map(t => (
                          <option key={t} value={t}>{t}</option>
                        ))}
                      </select>
                    </div>
                    <div className="space-y-2">
                      <Label htmlFor="priority">Priority (0-100)</Label>
                      <Input
                        id="priority"
                        type="number"
                        min={0}
                        max={100}
                        value={newItem.priority}
                        onChange={(e) => setNewItem({ ...newItem, priority: parseInt(e.target.value) || 50 })}
                      />
                    </div>
                  </div>
                )}
              </div>
              <div className="flex justify-end gap-2">
                <Button variant="outline" onClick={() => setIsAddDialogOpen(false)}>
                  Cancel
                </Button>
                <Button onClick={handleCreate} disabled={createMutation.isPending || !newItem.title || !newItem.content}>
                  {createMutation.isPending && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
                  Add Item
                </Button>
              </div>
            </DialogContent>
          </Dialog>
        </div>
      </div>

      {/* Category filter */}
      <div className="flex gap-2 flex-wrap">
        {categoryOptions.map((cat) => (
          <Button
            key={cat}
            variant={selectedCategory === cat ? 'default' : 'outline'}
            size="sm"
            onClick={() => setSelectedCategory(cat)}
          >
            {cat === 'all' ? 'All' : categoryLabels[cat]}
          </Button>
        ))}
      </div>

      {error ? (
        <div className="text-center py-8 text-red-500">
          <p>Error loading items: {error.message}</p>
          <Button variant="outline" onClick={() => refetch()} className="mt-4">
            Retry
          </Button>
        </div>
      ) : isLoading ? (
        <div className="flex items-center justify-center py-8">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </div>
      ) : (
        <div className="grid gap-6 lg:grid-cols-4">
          {/* Sidebar Stats */}
          <div className="space-y-4">
            <Card>
              <CardHeader>
                <CardTitle className="text-sm">Quick Stats</CardTitle>
              </CardHeader>
              <CardContent className="space-y-2 text-sm">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">FAQs</span>
                  <span className="font-medium">{faqs.length}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Policies</span>
                  <span className="font-medium">{policies.length}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Announcements</span>
                  <span className="font-medium">{announcements.length}</span>
                </div>
              </CardContent>
            </Card>
          </div>

          {/* Main Content */}
          <div className="lg:col-span-3 space-y-4">
            {/* FAQs */}
            {(selectedCategory === 'all' || selectedCategory === 'faq') && (
              <Card>
                <CardHeader>
                  <CardTitle>FAQs ({faqs.length})</CardTitle>
                </CardHeader>
                <CardContent className="space-y-4">
                  {faqs.length === 0 ? (
                    <p className="text-muted-foreground text-center py-4">No FAQs yet.</p>
                  ) : (
                    faqs.map((faq) => {
                      const metadata = parseMetadata(faq.metadata_json);
                      return (
                        <div key={faq.id} className="border rounded-lg p-4">
                          <div className="flex items-start justify-between">
                            <div className="space-y-2 flex-1">
                              <div className="flex items-center gap-2">
                                <p className="font-medium">Q: {faq.title}</p>
                                <Badge
                                  variant={faq.is_active ? 'default' : 'secondary'}
                                  className="text-xs cursor-pointer"
                                  onClick={() => handleToggleActive(faq.id, faq.is_active)}
                                >
                                  {faq.is_active ? 'Active' : 'Inactive'}
                                </Badge>
                              </div>
                              {faq.title_hindi && (
                                <p className="text-sm text-muted-foreground">{faq.title_hindi}</p>
                              )}
                              <p className="text-sm"><strong>A:</strong> {faq.content}</p>
                              <div className="flex gap-2 text-xs text-muted-foreground">
                                <span>Topic: {metadata.topic || 'Other'}</span>
                                <span>|</span>
                                <span>Priority: {faq.priority}</span>
                              </div>
                            </div>
                            <Button
                              variant="ghost"
                              size="icon"
                              onClick={() => handleDelete(faq.id)}
                              disabled={deleteMutation.isPending}
                            >
                              <Trash2 className="h-4 w-4" />
                            </Button>
                          </div>
                        </div>
                      );
                    })
                  )}
                </CardContent>
              </Card>
            )}

            {/* Policies */}
            {(selectedCategory === 'all' || selectedCategory === 'policy') && (
              <Card>
                <CardHeader>
                  <CardTitle>Policies ({policies.length})</CardTitle>
                  <CardDescription>Business policies that the bot can reference</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  {policies.length === 0 ? (
                    <p className="text-muted-foreground text-center py-4">No policies yet.</p>
                  ) : (
                    policies.map((policy) => (
                      <div key={policy.id} className="flex items-center justify-between p-3 border rounded-lg">
                        <div>
                          <p className="font-medium">{policy.title}</p>
                          <p className="text-sm text-muted-foreground">{policy.content}</p>
                        </div>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleDelete(policy.id)}
                          disabled={deleteMutation.isPending}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>
            )}

            {/* Announcements */}
            {(selectedCategory === 'all' || selectedCategory === 'announcement') && (
              <Card>
                <CardHeader>
                  <CardTitle>Announcements ({announcements.length})</CardTitle>
                  <CardDescription>Current announcements the bot will mention</CardDescription>
                </CardHeader>
                <CardContent className="space-y-2">
                  {announcements.length === 0 ? (
                    <p className="text-muted-foreground text-center py-4">No announcements yet.</p>
                  ) : (
                    announcements.map((ann) => (
                      <div key={ann.id} className="flex items-center justify-between p-3 border rounded-lg bg-yellow-50 dark:bg-yellow-950">
                        <div>
                          <p className="font-medium">{ann.title}</p>
                          <p className="text-sm text-muted-foreground">{ann.content}</p>
                        </div>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleDelete(ann.id)}
                          disabled={deleteMutation.isPending}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
                      </div>
                    ))
                  )}
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
