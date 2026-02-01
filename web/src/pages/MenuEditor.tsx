import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
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
import { getBusinessId } from '@/lib/business';

export function MenuEditor() {
  const [isAddDialogOpen, setIsAddDialogOpen] = useState(false);
  const businessId = getBusinessId();
  const [newItem, setNewItem] = useState({
    title: '',
    title_hindi: '',
    content: '',
    price: '',
    is_vegetarian: true,
  });

  const queryClient = useQueryClient();

  // Fetch menu items - always scope by business_id to prevent multi-tenant data leakage
  const {
    data: menuItems,
    isLoading,
    error,
    refetch,
  } = useListKnowledgeItemsApiKnowledgeGet({ business_id: businessId, category: 'menu_item' });

  // Create mutation
  const createMutation = useCreateKnowledgeItemApiKnowledgePost({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getListKnowledgeItemsApiKnowledgeGetQueryKey({ category: 'menu_item' }),
        });
        setIsAddDialogOpen(false);
        setNewItem({ title: '', title_hindi: '', content: '', price: '', is_vegetarian: true });
      },
    },
  });

  // Update mutation
  const updateMutation = useUpdateKnowledgeItemApiKnowledgeItemIdPatch({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getListKnowledgeItemsApiKnowledgeGetQueryKey({ category: 'menu_item' }),
        });
      },
    },
  });

  // Delete mutation
  const deleteMutation = useDeleteKnowledgeItemApiKnowledgeItemIdDelete({
    mutation: {
      onSuccess: () => {
        queryClient.invalidateQueries({
          queryKey: getListKnowledgeItemsApiKnowledgeGetQueryKey({ category: 'menu_item' }),
        });
      },
    },
  });

  const handleCreate = () => {
    // Parse metadata from form fields
    const metadata = JSON.stringify({
      price: newItem.price ? parseInt(newItem.price) : null,
      is_vegetarian: newItem.is_vegetarian,
      category: 'Uncategorized',
    });

    createMutation.mutate({
      data: {
        business_id: businessId,
        category: 'menu_item',
        title: newItem.title,
        title_hindi: newItem.title_hindi || undefined,
        content: newItem.content,
        metadata_json: metadata,
        is_active: true,
        priority: 50,
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
    if (confirm('Are you sure you want to delete this menu item?')) {
      deleteMutation.mutate({ itemId });
    }
  };

  // Parse metadata from items
  const parseMetadata = (metadataJson: string | null | undefined) => {
    if (!metadataJson) return { price: null, is_vegetarian: false, category: 'Uncategorized' };
    try {
      return JSON.parse(metadataJson);
    } catch {
      return { price: null, is_vegetarian: false, category: 'Uncategorized' };
    }
  };

  const items = menuItems || [];

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h2 className="text-2xl font-bold tracking-tight">Menu Editor</h2>
          <p className="text-muted-foreground">
            Manage menu items for knowledge-based retrieval during calls
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
                <DialogTitle>Add Menu Item</DialogTitle>
                <DialogDescription>
                  Add a new item to the menu. It will be indexed for voice retrieval.
                </DialogDescription>
              </DialogHeader>
              <div className="grid gap-4 py-4">
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="title">Item Name *</Label>
                    <Input
                      id="title"
                      placeholder="Veg Steam Momos"
                      value={newItem.title}
                      onChange={(e) => setNewItem({ ...newItem, title: e.target.value })}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label htmlFor="title_hindi">Name (Hindi)</Label>
                    <Input
                      id="title_hindi"
                      placeholder="वेज स्टीम मोमोज"
                      value={newItem.title_hindi}
                      onChange={(e) => setNewItem({ ...newItem, title_hindi: e.target.value })}
                    />
                  </div>
                </div>
                <div className="grid grid-cols-2 gap-4">
                  <div className="space-y-2">
                    <Label htmlFor="price">Price (Rs.)</Label>
                    <Input
                      id="price"
                      type="number"
                      placeholder="180"
                      value={newItem.price}
                      onChange={(e) => setNewItem({ ...newItem, price: e.target.value })}
                    />
                  </div>
                  <div className="space-y-2 flex items-end">
                    <label className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={newItem.is_vegetarian}
                        onChange={(e) => setNewItem({ ...newItem, is_vegetarian: e.target.checked })}
                      />
                      <span className="text-sm">Vegetarian</span>
                    </label>
                  </div>
                </div>
                <div className="space-y-2">
                  <Label htmlFor="content">Description *</Label>
                  <textarea
                    id="content"
                    className="w-full h-20 px-3 py-2 border rounded-md"
                    placeholder="Steamed vegetable dumplings served with spicy tomato chutney"
                    value={newItem.content}
                    onChange={(e) => setNewItem({ ...newItem, content: e.target.value })}
                  />
                </div>
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

      <Card>
        <CardHeader>
          <CardTitle>Menu Items ({items.length})</CardTitle>
          <CardDescription>
            Items are indexed for semantic search during calls
          </CardDescription>
        </CardHeader>
        <CardContent>
          {error ? (
            <div className="text-center py-8 text-red-500">
              <p>Error loading menu items: {error.message}</p>
              <Button variant="outline" onClick={() => refetch()} className="mt-4">
                Retry
              </Button>
            </div>
          ) : isLoading ? (
            <div className="flex items-center justify-center py-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : items.length === 0 ? (
            <p className="text-center py-8 text-muted-foreground">
              No menu items yet. Add your first item using the button above.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Item</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead>Price</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="text-right">Actions</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {items.map((item) => {
                  const metadata = parseMetadata(item.metadata_json);
                  return (
                    <TableRow key={item.id}>
                      <TableCell>
                        <div className="flex items-center gap-2">
                          <span>{metadata.is_vegetarian ? '🥬' : '🍗'}</span>
                          <div>
                            <p className="font-medium">{item.title}</p>
                            {item.title_hindi && (
                              <p className="text-sm text-muted-foreground">{item.title_hindi}</p>
                            )}
                          </div>
                        </div>
                      </TableCell>
                      <TableCell className="max-w-xs truncate">{item.content}</TableCell>
                      <TableCell>
                        {metadata.price ? `Rs. ${metadata.price}` : '—'}
                      </TableCell>
                      <TableCell>
                        <Badge
                          variant={item.is_active ? 'default' : 'secondary'}
                          className="cursor-pointer"
                          onClick={() => handleToggleActive(item.id, item.is_active)}
                        >
                          {item.is_active ? 'Active' : 'Inactive'}
                        </Badge>
                      </TableCell>
                      <TableCell className="text-right">
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleDelete(item.id)}
                          disabled={deleteMutation.isPending}
                        >
                          <Trash2 className="h-4 w-4" />
                        </Button>
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
