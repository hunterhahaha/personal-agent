"use client";

import { useState } from "react";
import { tasksApi, type Task } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { CalendarClock, Loader2, Play, Plus, Pencil, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useEntityList } from "@/hooks/use-entity-list";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { ErrorBanner } from "@/components/ui/error-banner";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { TaskHistory } from "@/components/layout/task-history";

const CRON_ALIASES: Record<string, string> = {
  "@daily": "每天 00:00",
  "@hourly": "每小时",
  "@weekly": "每周日 00:00",
  "@monthly": "每月 1 日 00:00",
  "@yearly": "每年 1 月 1 日 00:00",
};

function formatCron(expr: string | null) {
  if (!expr) return "—";
  const alias = CRON_ALIASES[expr.trim()];
  if (alias) return alias;
  const parts = expr.split(" ");
  if (parts.length !== 5) return expr;
  return `每天 ${parts[1]}:${parts[0].padStart(2, "0")}`;
}

const emptyForm = { task_id: "", name: "", description: "", cron_expr: "", run_at: "", recurring: true };

export default function TasksPage() {
  const { items: tasks, loading, error, load, toggleEnabled } = useEntityList(tasksApi);
  const [running, setRunning] = useState<string | null>(null);
  const [showForm, setShowForm] = useState(false);
  const [editing, setEditing] = useState<Task | null>(null);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);

  const openCreate = () => {
    setEditing(null);
    setForm(emptyForm);
    setShowForm(true);
  };

  const openEdit = (t: Task) => {
    setEditing(t);
    setForm({ task_id: t.task_id, name: t.name, description: t.description, cron_expr: t.cron_expr || "", run_at: t.run_at || "", recurring: t.recurring });
    setShowForm(true);
  };

  const handleSave = async () => {
    if (!form.task_id || !form.name) return;
    setSaving(true);
    try {
      if (editing) {
        await tasksApi.update(editing.task_id, { name: form.name, description: form.description, cron_expr: form.cron_expr || null, run_at: form.run_at || null, recurring: form.recurring });
        toast.success("任务已更新");
      } else {
        await tasksApi.create({ task_id: form.task_id, name: form.name, description: form.description, cron_expr: form.cron_expr || null, run_at: form.run_at || null, recurring: form.recurring });
        toast.success("任务已创建");
      }
      setShowForm(false);
      load();
    } catch {
      toast.error("保存失败");
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (taskId: string) => {
    try {
      await tasksApi.remove(taskId);
      toast.success("任务已删除");
      load();
    } catch {
      toast.error("删除失败");
    }
  };

  const runTask = async (id: string) => {
    setRunning(id);
    try {
      await tasksApi.run(id);
      toast.success("任务已执行");
    } catch {
      toast.error("执行失败");
    } finally {
      setRunning(null);
    }
  };

  if (loading) return <LoadingSpinner />;

  return (
    <div className="p-6 max-w-6xl mx-auto">
      <PageHeader icon={CalendarClock} title="任务" description="定时或一次性任务，自动发送提示词给智能助手执行。">
        <Button size="sm" onClick={openCreate}><Plus className="w-4 h-4 mr-1" />新建</Button>
      </PageHeader>

      <ErrorBanner message={error} />

      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_20rem]">
        <div className="space-y-3">
          {tasks.map((task) => (
            <Card key={task.id}>
              <CardHeader className="py-4 px-5">
                <div className="flex items-center justify-between">
                  <div className="flex items-center gap-3">
                    <CardTitle className="text-sm font-medium">{task.name}</CardTitle>
                    <Badge variant={task.recurring ? "default" : "secondary"} className="text-[10px]">
                      {task.recurring ? "持久" : "一次性"}
                    </Badge>
                    {task.cron_expr && <Badge variant="outline" className="text-xs font-mono">{task.cron_expr}</Badge>}
                  </div>
                  <div className="flex items-center gap-2">
                    <Button variant="outline" size="sm" onClick={() => runTask(task.task_id)} disabled={running === task.task_id}>
                      {running === task.task_id ? <Loader2 className="w-3.5 h-3.5 mr-1 animate-spin" /> : <Play className="w-3.5 h-3.5 mr-1" />}
                      执行
                    </Button>
                    <Button variant="ghost" size="icon" onClick={() => openEdit(task)}><Pencil className="w-3.5 h-3.5" /></Button>
                    <Button variant="ghost" size="icon" onClick={() => handleDelete(task.task_id)}><Trash2 className="w-3.5 h-3.5 text-destructive" /></Button>
                    <Switch checked={task.enabled} onCheckedChange={() => toggleEnabled(task.task_id)} />
                  </div>
                </div>
              </CardHeader>
              <CardContent className="px-5 pb-4">
                <p className="text-sm text-muted-foreground line-clamp-2">{task.description}</p>
                <p className="text-xs text-muted-foreground mt-1">调度: {formatCron(task.cron_expr)}{task.run_at ? ` | 一次性: ${new Date(task.run_at).toLocaleString()}` : ""}</p>
              </CardContent>
            </Card>
          ))}
          {tasks.length === 0 && <EmptyState message="暂无任务，点击「新建」创建一个。" />}
        </div>
        <TaskHistory embedded />
      </div>

      {/* Create / Edit Dialog */}
      <Dialog open={showForm} onOpenChange={setShowForm}>
        <DialogContent className="max-w-md">
          <DialogHeader><DialogTitle>{editing ? "编辑任务" : "新建任务"}</DialogTitle></DialogHeader>
          <div className="space-y-3">
            {!editing && (
              <div>
                <label className="text-xs font-medium">任务 ID</label>
                <Input value={form.task_id} onChange={(e) => setForm({ ...form, task_id: e.target.value })} placeholder="如 daily_news" />
              </div>
            )}
            <div>
              <label className="text-xs font-medium">名称</label>
              <Input value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} placeholder="任务名称" />
            </div>
            <div>
              <label className="text-xs font-medium">详情（发送给智能助手的提示词）</label>
              <Textarea value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} placeholder="智能助手要执行的任务描述..." rows={4} />
            </div>
            <div>
              <label className="text-xs font-medium">Cron 表达式</label>
              <Input value={form.cron_expr} onChange={(e) => setForm({ ...form, cron_expr: e.target.value })} placeholder="0 8 * * * 或 @daily, @hourly, @weekly, @monthly, @yearly" />
            </div>
            <div>
              <label className="text-xs font-medium">一次性执行时间（run_at）</label>
              <input
                type="datetime-local"
                className="flex h-9 w-full rounded-md border border-input bg-transparent px-3 py-1 text-sm shadow-sm transition-colors placeholder:text-muted-foreground focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-ring"
                value={form.run_at}
                onChange={(e) => setForm({ ...form, run_at: e.target.value })}
              />
            </div>
            <div className="flex items-center gap-2">
              <Switch checked={form.recurring} onCheckedChange={(v) => setForm({ ...form, recurring: v })} />
              <span className="text-xs">持久任务（完成后自动安排下一次）</span>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <Button variant="outline" onClick={() => setShowForm(false)}>取消</Button>
              <Button onClick={handleSave} disabled={saving}>{saving ? "保存中..." : "保存"}</Button>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
