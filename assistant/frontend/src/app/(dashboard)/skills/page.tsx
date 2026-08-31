"use client";

import { skillsApi } from "@/lib/api-client";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { Switch } from "@/components/ui/switch";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Layers, RefreshCw } from "lucide-react";
import { LoadingSpinner } from "@/components/ui/loading-spinner";
import { ErrorBanner } from "@/components/ui/error-banner";
import { PageHeader } from "@/components/ui/page-header";
import { EmptyState } from "@/components/ui/empty-state";
import { useEntityList } from "@/hooks/use-entity-list";

export default function SkillsPage() {
  const { items: skills, loading, error, load, toggleEnabled } = useEntityList(skillsApi);

  if (loading) return <LoadingSpinner />;

  return (
    <div className="p-6 max-w-5xl mx-auto">
      <PageHeader
        icon={Layers}
        title="技能"
        description="可复用的能力包，数据源自 assistant/skills/ 目录。"
      >
        <Button variant="outline" size="sm" onClick={load} disabled={loading}>
          <RefreshCw className={`w-4 h-4 mr-1 ${loading ? "animate-spin" : ""}`} />
          刷新
        </Button>
      </PageHeader>

      <ErrorBanner message={error} />

      <div className="space-y-3">
        {skills.map((skill) => (
          <Card key={skill.id}>
            <CardHeader className="py-4 px-5">
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3 min-w-0">
                  <CardTitle className="text-sm font-medium truncate">{skill.name}</CardTitle>
                  {skill.tags.length > 0 && skill.tags.map((t) => (
                    <Badge key={t} variant="outline" className="text-xs shrink-0">{t}</Badge>
                  ))}
                </div>
                <div className="flex items-center gap-1 shrink-0">
                  <Switch checked={skill.enabled} onCheckedChange={() => toggleEnabled(skill.id)} />
                </div>
              </div>
            </CardHeader>
            <CardContent className="px-5 pb-4">
              <p className="text-sm text-muted-foreground line-clamp-2">{skill.description}</p>
            </CardContent>
          </Card>
        ))}
        {skills.length === 0 && (
          <EmptyState message="暂无技能。将包含 SKILL.md 的文件夹放入 assistant/skills/ 目录后点击刷新。" />
        )}
      </div>
    </div>
  );
}
