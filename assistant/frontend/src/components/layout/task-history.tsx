"use client";

import { useCallback, useEffect, useMemo } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Button } from "@/components/ui/button";
import { Badge } from "@/components/ui/badge";
import { ListChecks, X } from "lucide-react";
import { useChatStore } from "@/stores/chat-store";
import { cn } from "@/lib/utils";
import { isTaskConversation } from "@/lib/conversation-types";

interface TaskHistoryProps {
  onClose?: () => void;
  embedded?: boolean;
}

export function TaskHistory({ onClose, embedded = false }: TaskHistoryProps) {
  const router = useRouter();
  const conversations = useChatStore((s) => s.conversations);
  const activeConversationId = useChatStore((s) => s.activeConversationId);
  const loadConversations = useChatStore((s) => s.loadConversations);

  const taskConversations = useMemo(
    () => conversations.filter(isTaskConversation),
    [conversations],
  );

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  const handleClick = useCallback((conversationId: number) => {
    router.push(`/chat/${conversationId}`);
  }, [router]);

  return (
    <aside
      className={cn(
        "flex shrink-0 flex-col border-l bg-background",
        embedded
          ? "h-[560px] rounded-lg border shadow-sm"
          : "fixed inset-y-0 right-0 z-40 w-[min(22rem,calc(100vw-3.5rem))] shadow-lg xl:static xl:z-auto xl:w-72 xl:bg-muted/25 xl:shadow-none",
      )}
    >
      <div className="flex h-14 items-center justify-between border-b p-3">
        <h2 className="text-sm font-semibold flex items-center gap-2">
          <ListChecks className="w-4 h-4" /> 任务历史
        </h2>
        <div className="flex items-center gap-1">
          <Link href="/tasks">
            <Button variant="outline" size="sm" className="h-7 text-xs">任务</Button>
          </Link>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={onClose}
            aria-label="关闭任务历史"
            title="关闭任务历史"
            className={embedded ? "hidden" : undefined}
          >
            <X className="h-4 w-4" />
          </Button>
        </div>
      </div>
      <ScrollArea className="flex-1">
        <div className="p-2 space-y-2">
          {taskConversations.length === 0 && (
            <p className="text-xs text-muted-foreground text-center py-4">暂无任务会话</p>
          )}
          {taskConversations.map((conversation) => (
            <button
              key={conversation.id}
              onClick={() => handleClick(conversation.id)}
              className={cn(
                "w-full rounded-lg border bg-card p-3 text-left text-sm transition-colors hover:bg-accent/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring",
                activeConversationId === conversation.id && "border-primary bg-primary/5",
              )}
              style={{ contentVisibility: "auto", containIntrinsicSize: "0 80px" }}
            >
              <div className="flex items-center justify-between mb-1">
                <span className="font-medium text-xs truncate">{conversation.title || "任务会话"}</span>
                <Badge variant="secondary" className="text-[10px]">
                  任务
                </Badge>
              </div>
              <p className="text-xs text-muted-foreground line-clamp-2">
                任务触发的对话，可继续输入消息
              </p>
              <p className="text-[10px] text-muted-foreground mt-1">
                {new Date(conversation.updated_at).toLocaleString("zh-CN")}
              </p>
            </button>
          ))}
        </div>
      </ScrollArea>
    </aside>
  );
}
