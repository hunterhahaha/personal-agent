"use client";

import { useState, useEffect, useCallback, useMemo } from "react";
import { memoryApi, type MemoryItem } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Brain, Plus, Trash2, Loader2, Check, X } from "lucide-react";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { ErrorBanner } from "@/components/ui/error-banner";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/empty-state";

export default function MemoryPage() {
  const [memories, setMemories] = useState<MemoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [title, setTitle] = useState("");
  const [content, setContent] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await memoryApi.list();
      setMemories(data);
    } catch {
      setError("加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  // eslint-disable-next-line react-hooks/set-state-in-effect -- async data fetch on mount
  useEffect(() => { load(); }, [load]);

  // Split memories into inferred (candidates) and confirmed
  const inferredMemories = useMemo(
    () => memories.filter((m) => m.inferred === true),
    [memories]
  );
  const confirmedMemories = useMemo(
    () => memories.filter((m) => !m.inferred),
    [memories]
  );

  async function handleAdd() {
    const t = title.trim();
    const c = content.trim();
    if (!t || !c || adding) return;
    setAdding(true);
    try {
      const { data } = await memoryApi.create(t, c);
      setMemories((prev) => [data, ...prev]);
      setTitle("");
      setContent("");
    } catch {
      setError("添加失败");
    } finally {
      setAdding(false);
    }
  }

  async function handleDelete(id: number) {
    try {
      await memoryApi.delete(id);
      setMemories((prev) => prev.filter((m) => m.id !== id));
    } catch {
      setError("删除失败");
    }
  }

  async function handleConfirm(id: number) {
    try {
      const { data } = await memoryApi.confirm(id);
      setMemories((prev) =>
        prev.map((m) => (m.id === id ? data : m))
      );
    } catch {
      setError("确认失败");
    }
  }

  async function handleReject(id: number) {
    try {
      await memoryApi.reject(id);
      setMemories((prev) => prev.filter((m) => m.id !== id));
    } catch {
      setError("拒绝失败");
    }
  }

  if (loading) return <LoadingSpinner />;

  return (
    <div className="p-6 max-w-3xl mx-auto space-y-6">
      <PageHeader
        icon={Brain}
        title="记忆管理"
        description="管理你的个性化记忆。这些记忆会在每次新对话开始时注入到智能助手上下文中。"
      />

      <ErrorBanner message={error} />

      {/* Add form */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base">
            <Plus className="w-4 h-4" />
            添加记忆
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-3">
          <input
            value={title}
            onChange={(e) => setTitle(e.target.value)}
            placeholder="记忆标题（例如：我的编程语言偏好）"
            className="w-full rounded-lg border border-input bg-transparent px-3 py-2 text-sm outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <textarea
            value={content}
            onChange={(e) => setContent(e.target.value)}
            placeholder="记忆内容（例如：我主要使用 Python 和 TypeScript，偏好简洁的代码风格）"
            rows={3}
            className="w-full rounded-lg border border-input bg-transparent px-3 py-2 text-sm resize-none outline-none focus-visible:ring-2 focus-visible:ring-ring"
          />
          <Button
            onClick={handleAdd}
            disabled={!title.trim() || !content.trim() || adding}
            size="sm"
          >
            {adding && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
            添加
          </Button>
        </CardContent>
      </Card>

      {/* Inferred candidates section */}
      {inferredMemories.length > 0 && (
        <div className="space-y-3">
          <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
            候选偏好（智能助手推断）
          </h2>
          {inferredMemories.map((m) => (
            <Card key={`mem-inferred-${m.id}`} className="border-dashed border-amber-500/50">
              <CardContent className="flex items-start justify-between gap-4 py-4">
                <div className="min-w-0 flex-1">
                  <div className="flex items-center gap-2">
                    <h3 className="font-medium text-sm truncate">{m.title}</h3>
                    {m.confidence != null && (
                      <span className="inline-flex items-center rounded-full bg-amber-100 px-2 py-0.5 text-xs font-medium text-amber-800 dark:bg-amber-900/30 dark:text-amber-300">
                        {Math.round(m.confidence * 100)}%
                      </span>
                    )}
                  </div>
                  <p className="text-sm text-muted-foreground mt-1 line-clamp-3 whitespace-pre-wrap">
                    {m.content}
                  </p>
                  <p className="text-xs text-muted-foreground mt-2">
                    {m.created_at
                      ? new Date(m.created_at).toLocaleString("zh-CN")
                      : ""}
                  </p>
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <Button
                    variant="ghost"
                    size="icon"
                    className="text-green-600 hover:text-green-700 hover:bg-green-50 dark:hover:bg-green-900/20"
                    onClick={() => handleConfirm(m.id)}
                    title="确认"
                  >
                    <Check className="w-4 h-4" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon"
                    className="text-red-600 hover:text-red-700 hover:bg-red-50 dark:hover:bg-red-900/20"
                    onClick={() => handleReject(m.id)}
                    title="拒绝"
                  >
                    <X className="w-4 h-4" />
                  </Button>
                </div>
              </CardContent>
            </Card>
          ))}
        </div>
      )}

      {/* Confirmed memories section */}
      {confirmedMemories.length === 0 && inferredMemories.length === 0 ? (
        <EmptyState message="暂无记忆，添加你的第一条个性化记忆" />
      ) : confirmedMemories.length > 0 ? (
        <div className="space-y-3">
          {inferredMemories.length > 0 && (
            <h2 className="text-sm font-semibold text-muted-foreground uppercase tracking-wide">
              已确认
            </h2>
          )}
          {confirmedMemories.map((m) => (
            <Card key={`mem-${m.id}`}>
              <CardContent className="flex items-start justify-between gap-4 py-4">
                <div className="min-w-0 flex-1">
                  <h3 className="font-medium text-sm truncate">{m.title}</h3>
                  <p className="text-sm text-muted-foreground mt-1 line-clamp-3 whitespace-pre-wrap">
                    {m.content}
                  </p>
                  <p className="text-xs text-muted-foreground mt-2">
                    {m.created_at
                      ? new Date(m.created_at).toLocaleString("zh-CN")
                      : ""}
                  </p>
                </div>
                <Button
                  variant="ghost"
                  size="icon"
                  className="shrink-0 text-muted-foreground hover:text-destructive"
                  onClick={() => handleDelete(m.id)}
                >
                  <Trash2 className="w-4 h-4" />
                </Button>
              </CardContent>
            </Card>
          ))}
        </div>
      ) : null}
    </div>
  );
}
