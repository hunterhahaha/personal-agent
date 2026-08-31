"use client";

import { blueprintsApi, type SubAgentBlueprint } from "@/lib/api-client";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { ErrorBanner } from "@/components/ui/error-banner";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { GitBranch, Trash2 } from "lucide-react";
import { toast } from "sonner";
import { useEntityList } from "@/hooks/use-entity-list";

export default function BlueprintsPage() {
  const { items: blueprints, loading, error, load } = useEntityList(blueprintsApi);

  const handleDelete = async (blueprintId: string) => {
    try {
      await blueprintsApi.remove(blueprintId);
      toast.success("子智能体已删除");
      load();
    } catch {
      toast.error("删除失败");
    }
  };

  if (loading) return <LoadingSpinner />;

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <PageHeader
        icon={GitBranch}
        title="子智能体"
        description="子智能体定义了专门的身份、可用工具和系统提示词。主智能助手根据任务需求自动选择合适的子智能体协作完成任务。"
      />

      <ErrorBanner message={error} />

      <div className="space-y-3">
        {blueprints.map((bp: SubAgentBlueprint) => (
          <Card key={bp.blueprint_id}>
            <CardHeader className="py-4 px-5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <CardTitle className="text-sm font-medium">{bp.name}</CardTitle>
                  {bp.tags.map((t) => (
                    <Badge key={t} variant="outline" className="text-xs">{t}</Badge>
                  ))}
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="ghost"
                    size="icon"
                    onClick={() => handleDelete(bp.blueprint_id)}
                    aria-label={`删除子智能体 ${bp.name}`}
                    title="删除子智能体"
                  >
                    <Trash2 className="w-3.5 h-3.5 text-destructive" />
                  </Button>
                </div>
              </div>
            </CardHeader>
            <CardContent className="px-5 pb-4 space-y-2">
              <p className="text-sm text-muted-foreground">{bp.description}</p>
              <div className="flex flex-wrap gap-4 text-xs text-muted-foreground">
                <span>
                  工具:{" "}
                  {bp.tool_ids.length > 0
                    ? bp.tool_ids.map((t) => (
                      <Badge key={t} variant="secondary" className="ml-0.5 text-[11px]">{t}</Badge>
                    ))
                    : "—"}
                </span>
                <span>
                  关联提示词:{" "}
                  {bp.prompt_template_ids.length > 0
                    ? bp.prompt_template_ids.map((p) => (
                      <Badge key={p} variant="secondary" className="ml-0.5 text-[11px]">{p}</Badge>
                    ))
                    : "—"}
                </span>
              </div>
            </CardContent>
          </Card>
        ))}
        {blueprints.length === 0 && (
          <EmptyState message="暂无子智能体。" />
        )}
      </div>
    </div>
  );
}
