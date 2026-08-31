"use client";

import { useState, useEffect, useCallback } from "react";
import { modelsApi, type ModelConfig } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogFooter } from "@/components/ui/dialog";
import { Badge } from "@/components/ui/badge";
import { WorkspaceHeader } from "@/components/layout/workspace-header";
import { WorkspacePage } from "@/components/layout/workspace-page";
import { CheckCircle2, Cpu, KeyRound, Loader2, Pencil, Plus, Server, Trash2 } from "lucide-react";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { ErrorBanner } from "@/components/ui/error-banner";
import { EmptyState } from "@/components/ui/empty-state";

const inputClassName =
  "h-9 w-full rounded-lg border border-border bg-card px-3 py-2 text-sm outline-none transition-colors placeholder:text-muted-foreground/60 focus:border-ring focus-visible:ring-2 focus-visible:ring-ring/20";

const labelClassName = "mb-1.5 block text-xs font-medium text-muted-foreground";

export default function ModelsPage() {
  const [models, setModels] = useState<ModelConfig[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [adding, setAdding] = useState(false);
  const [activatingId, setActivatingId] = useState<number | null>(null);
  const [modelId, setModelId] = useState("");
  const [name, setName] = useState("");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");

  const [editing, setEditing] = useState<ModelConfig | null>(null);
  const [editName, setEditName] = useState("");
  const [editModelId, setEditModelId] = useState("");
  const [editUrl, setEditUrl] = useState("");
  const [editKey, setEditKey] = useState("");
  const [saving, setSaving] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const { data } = await modelsApi.list();
      setModels(data);
    } catch {
      setError("加载失败");
    } finally {
      setLoading(false);
    }
  }, []);

  // eslint-disable-next-line react-hooks/set-state-in-effect -- async data fetch on mount
  useEffect(() => { load(); }, [load]);

  const openEdit = (m: ModelConfig) => {
    setEditing(m);
    setEditName(m.name);
    setEditModelId(m.model_id);
    setEditUrl(m.base_url);
    setEditKey(m.api_key);
  };

  async function handleSaveEdit() {
    if (!editing || saving) return;
    setSaving(true);
    try {
      const { data } = await modelsApi.update(editing.id, {
        name: editName.trim() || undefined,
        model_id: editModelId.trim() || undefined,
        base_url: editUrl.trim() || undefined,
        api_key: editKey.trim() || undefined,
      });
      setModels((prev) => prev.map((m) => (m.id === data.id ? data : m)));
      setEditing(null);
    } catch {
      setError("保存失败");
    } finally {
      setSaving(false);
    }
  }

  async function handleAdd() {
    const mid = modelId.trim();
    const nm = name.trim();
    const url = baseUrl.trim();
    const key = apiKey.trim();
    if (!mid || !nm || !url || !key || adding) return;
    setAdding(true);
    try {
      const { data } = await modelsApi.create(mid, nm, url, key);
      setModels((prev) => [...prev, data]);
      setModelId("");
      setName("");
      setBaseUrl("");
      setApiKey("");
    } catch (err: unknown) {
      const msg = (err as { response?: { data?: { detail?: string } } })?.response?.data?.detail;
      setError(msg ?? "添加失败");
    } finally {
      setAdding(false);
    }
  }

  async function handleDelete(id: number) {
    try {
      await modelsApi.delete(id);
      setModels((prev) => prev.filter((m) => m.id !== id));
    } catch {
      setError("删除失败");
    }
  }

  async function handleActivate(id: number) {
    if (activatingId !== null) return;
    setActivatingId(id);
    try {
      const { data } = await modelsApi.activate(id);
      setModels((prev) => prev.map((m) => ({ ...m, is_active: m.id === data.id })));
    } catch {
      setError("设置当前模型失败");
    } finally {
      setActivatingId(null);
    }
  }

  if (loading) return <LoadingSpinner />;

  return (
    <WorkspacePage className="space-y-6">
      <WorkspaceHeader
        title="模型"
        description="管理本地运行时使用的模型。这里设为当前的应用模型会用于记忆生成和标题生成；实际对话模型可在聊天界面单独选择。"
      />

      <ErrorBanner message={error} />

      <section className="rounded-lg border border-border bg-surface-container-low p-4 shadow-none">
        <div className="mb-4 flex items-center justify-between gap-3">
          <div>
            <h2 className="flex items-center gap-2 text-sm font-semibold text-foreground">
              <Plus className="h-4 w-4 text-muted-foreground" />
              添加模型
            </h2>
            <p className="mt-1 text-xs text-muted-foreground">
              为普通对话和任务会话注册可用的模型接口。
            </p>
          </div>
          <Button
            onClick={handleAdd}
            disabled={!modelId.trim() || !name.trim() || !baseUrl.trim() || !apiKey.trim() || adding}
            size="sm"
            className="bg-primary text-primary-foreground"
          >
            {adding ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <Plus className="h-3.5 w-3.5" />}
            添加
          </Button>
        </div>

        <div className="grid gap-3 lg:grid-cols-[minmax(0,1fr)_minmax(0,0.85fr)]">
          <div>
            <label className={labelClassName}>模型 ID</label>
            <input
              value={modelId}
              onChange={(e) => setModelId(e.target.value)}
              placeholder="deepseek-chat"
              className={inputClassName}
            />
          </div>
          <div>
            <label className={labelClassName}>显示名称</label>
            <input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder="DeepSeek Chat"
              className={inputClassName}
            />
          </div>
          <div>
            <label className={labelClassName}>接口地址</label>
            <div className="relative">
              <Server className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                value={baseUrl}
                onChange={(e) => setBaseUrl(e.target.value)}
                placeholder="https://api.deepseek.com"
                className={`${inputClassName} pl-8`}
              />
            </div>
          </div>
          <div>
            <label className={labelClassName}>API 密钥</label>
            <div className="relative">
              <KeyRound className="pointer-events-none absolute left-3 top-1/2 h-3.5 w-3.5 -translate-y-1/2 text-muted-foreground" />
              <input
                value={apiKey}
                onChange={(e) => setApiKey(e.target.value)}
                placeholder="sk-..."
                type="password"
                className={`${inputClassName} pl-8`}
              />
            </div>
          </div>
        </div>
      </section>

      <section className="rounded-lg border border-border bg-card shadow-none">
        <div className="flex items-center justify-between border-b border-border px-4 py-3">
          <div>
            <h2 className="text-sm font-semibold">模型列表</h2>
            <p className="mt-0.5 text-xs text-muted-foreground">已注册 {models.length} 个模型</p>
          </div>
        </div>

        {models.length === 0 ? (
          <div className="p-6">
            <EmptyState message="暂无模型配置，添加你的第一个模型" />
          </div>
        ) : (
          <div className="divide-y divide-border">
            {models.map((m) => (
              <div
                key={`model-${m.id}`}
                className="grid gap-3 px-4 py-3 transition-colors hover:bg-surface-container-low md:grid-cols-[minmax(0,1fr)_auto]"
              >
                <div className="min-w-0">
                  <div className="flex flex-wrap items-center gap-2">
                    <h3 className="truncate text-sm font-medium">{m.name}</h3>
                    {m.is_active ? (
                      <Badge variant="outline" className="h-5 border-primary/20 bg-primary/5 text-[10px] text-foreground">
                        <CheckCircle2 className="h-3 w-3" />
                        当前
                      </Badge>
                    ) : (
                      <Badge variant="outline" className="h-5 text-[10px] text-muted-foreground">
                        可用
                      </Badge>
                    )}
                  </div>
                  <div className="mt-1 flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
                    <span className="font-mono text-[11px] text-foreground/70">{m.model_id}</span>
                    <span className="truncate">{m.base_url}</span>
                    <span className="font-mono text-[10px] text-muted-foreground/70">{m.uid}</span>
                  </div>
                </div>
                <div className="flex items-center gap-1 md:justify-end">
                  <Button
                    variant={m.is_active ? "secondary" : "outline"}
                    size="sm"
                    className="h-7"
                    onClick={() => handleActivate(m.id)}
                    disabled={m.is_active || activatingId !== null}
                  >
                    {activatingId === m.id ? <Loader2 className="h-3.5 w-3.5 animate-spin" /> : <CheckCircle2 className="h-3.5 w-3.5" />}
                    {m.is_active ? "当前" : "设为当前"}
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="text-muted-foreground hover:text-foreground"
                    onClick={() => openEdit(m)}
                    aria-label={`编辑模型 ${m.name}`}
                    title="编辑"
                  >
                    <Pencil className="h-3.5 w-3.5" />
                  </Button>
                  <Button
                    variant="ghost"
                    size="icon-sm"
                    className="text-muted-foreground hover:text-destructive"
                    onClick={() => handleDelete(m.id)}
                    aria-label={`删除模型 ${m.name}`}
                    title="删除"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </section>

      <Dialog open={editing !== null} onOpenChange={(open) => { if (!open) setEditing(null); }}>
        <DialogContent className="max-w-md">
          <DialogHeader>
            <DialogTitle>编辑模型</DialogTitle>
          </DialogHeader>
          <div className="space-y-3">
            <div>
              <label className={labelClassName}>显示名称</label>
              <input
                value={editName}
                onChange={(e) => setEditName(e.target.value)}
                className={inputClassName}
              />
            </div>
            <div>
              <label className={labelClassName}>模型 ID</label>
              <input
                value={editModelId}
                onChange={(e) => setEditModelId(e.target.value)}
                className={inputClassName}
              />
            </div>
            <div>
              <label className={labelClassName}>接口地址</label>
              <input
                value={editUrl}
                onChange={(e) => setEditUrl(e.target.value)}
                className={inputClassName}
              />
            </div>
            <div>
              <label className={labelClassName}>API 密钥</label>
              <input
                value={editKey}
                onChange={(e) => setEditKey(e.target.value)}
                type="password"
                className={inputClassName}
              />
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setEditing(null)}>取消</Button>
            <Button onClick={handleSaveEdit} disabled={saving}>
              {saving && <Loader2 className="w-4 h-4 mr-1 animate-spin" />}
              保存
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </WorkspacePage>
  );
}
