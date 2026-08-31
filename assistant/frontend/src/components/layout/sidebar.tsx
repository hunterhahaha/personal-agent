"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import {
  Layers,
  CalendarClock,
  Brain,
  GitBranch,
  Cpu,
  PanelLeftClose,
  PanelLeft,
  CircleHelp,
  Settings,
  MessageSquarePlus,
  Trash2,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useChatStore } from "@/stores/chat-store";
import { memo, useCallback, useEffect, useMemo, useState } from "react";
import type React from "react";
import type { Conversation } from "@/lib/api-client";
import { isTaskConversation } from "@/lib/conversation-types";

const navItems = [
  { href: "/models", label: "模型", icon: Cpu },
  { href: "/memory", label: "记忆", icon: Brain },
  { href: "/skills", label: "技能", icon: Layers },
  { href: "/blueprints", label: "子智能体", icon: GitBranch },
  { href: "/tasks", label: "任务", icon: CalendarClock },
];

const utilityItems = [
  { href: "/settings", label: "设置", icon: Settings },
  { href: "/support", label: "支持", icon: CircleHelp },
];

interface ConversationNavItemProps {
  conv: Conversation;
  isActive: boolean;
  hasUnread: boolean;
  collapsed: boolean;
  onSelect: (id: number) => void;
  onDelete: (e: React.MouseEvent, id: number) => void;
}

const ConversationNavItem = memo(function ConversationNavItem({
  conv,
  isActive,
  hasUnread,
  collapsed,
  onSelect,
  onDelete,
}: ConversationNavItemProps) {
  const isTask = isTaskConversation(conv);
  const displayTitle = conv.title || "新会话";

  return (
    <div className="group relative" style={{ contentVisibility: "auto", containIntrinsicSize: "0 40px" }}>
      <button
        type="button"
        onClick={() => onSelect(conv.id)}
        title={collapsed ? displayTitle : undefined}
        className={cn(
          "flex h-9 w-full items-center rounded-lg text-left text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring",
          collapsed ? "justify-center px-0" : "gap-3 px-3 pr-9",
          isActive
            ? "bg-sidebar-accent text-sidebar-accent-foreground shadow-[inset_2px_0_0_var(--sidebar-primary)]"
            : "text-sidebar-foreground/68 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
        )}
      >
        <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-current opacity-45" />
        {!collapsed && (
          <>
            {isTask && (
              <span className="shrink-0 rounded border border-sidebar-border bg-sidebar-accent px-1.5 py-0.5 text-[10px] font-medium leading-none text-sidebar-foreground/62">
                任务
              </span>
            )}
            <span className="truncate">{displayTitle}</span>
          </>
        )}
        {hasUnread && !collapsed && <span className="ml-auto h-2 w-2 shrink-0 rounded-full bg-sidebar-primary" />}
      </button>
      {!collapsed && (
        <button
          type="button"
          onClick={(e) => onDelete(e, conv.id)}
          className="absolute right-2 top-1/2 hidden -translate-y-1/2 rounded-md p-1 text-sidebar-foreground/45 outline-none hover:bg-destructive/10 hover:text-destructive focus-visible:block focus-visible:ring-2 focus-visible:ring-sidebar-ring group-hover:block"
          aria-label={`删除会话：${displayTitle}`}
          title="删除会话"
        >
          <Trash2 className="h-3.5 w-3.5" />
        </button>
      )}
    </div>
  );
});

export function Sidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const [collapsed, setCollapsed] = useState(false);
  const conversations = useChatStore((s) => s.conversations);
  const activeConversationId = useChatStore((s) => s.activeConversationId);
  const unreadIds = useChatStore((s) => s.unreadIds);
  const hasMoreConversations = useChatStore((s) => s.hasMoreConversations);
  const loadConversations = useChatStore((s) => s.loadConversations);
  const loadMoreConversations = useChatStore((s) => s.loadMoreConversations);
  const startNewChat = useChatStore((s) => s.startNewChat);
  const deleteConversation = useChatStore((s) => s.deleteConversation);

  const uniqueConversations = useMemo(() => {
    const seen = new Set<number>();
    return conversations.filter((conversation) => {
      if (seen.has(conversation.id)) return false;
      seen.add(conversation.id);
      return true;
    });
  }, [conversations]);

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  const handleNewChat = useCallback(() => {
    startNewChat();
    router.push("/chat");
  }, [router, startNewChat]);

  const handleSelectConversation = useCallback((id: number) => {
    router.push(`/chat/${id}`);
  }, [router]);

  const handleDeleteConversation = useCallback(async (e: React.MouseEvent, id: number) => {
    e.stopPropagation();
    await deleteConversation(id);
    if (activeConversationId === id || pathname === `/chat/${id}`) {
      router.replace("/chat");
    }
  }, [activeConversationId, deleteConversation, pathname, router]);

  return (
    <aside
      className={cn(
        "hidden h-screen flex-col border-r border-sidebar-border bg-sidebar text-sidebar-foreground transition-[width] duration-200 ease-out md:flex",
        collapsed ? "w-16" : "w-60"
      )}
    >
      <div
        className={cn(
          "flex h-16 items-center border-b border-sidebar-border px-4",
          collapsed ? "justify-center" : "gap-3"
        )}
      >
        <button
          type="button"
          className="group flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-sidebar-primary text-sidebar-primary-foreground outline-none transition-colors hover:bg-sidebar-primary/90 focus-visible:ring-2 focus-visible:ring-sidebar-ring focus-visible:ring-offset-2 focus-visible:ring-offset-sidebar"
          onClick={() => collapsed && setCollapsed(false)}
          aria-label={collapsed ? "展开主导航" : "个人智能助手"}
        >
          <Brain className={cn("h-4 w-4", collapsed && "group-hover:hidden")} />
          {collapsed && <PanelLeft className="hidden h-4 w-4 group-hover:block" />}
        </button>

        {!collapsed && (
          <>
            <div className="min-w-0">
              <span className="block truncate text-sm font-semibold leading-tight">CC 工作区</span>
              <span className="block truncate text-[11px] text-sidebar-foreground/55">
                本地优先智能体
              </span>
            </div>
            <Button
              variant="ghost"
              size="icon-sm"
              className="ml-auto text-sidebar-foreground/55 hover:text-sidebar-foreground"
              onClick={() => setCollapsed(true)}
              aria-label="收起主导航"
              title="收起主导航"
            >
              <PanelLeftClose className="h-4 w-4" />
            </Button>
          </>
        )}
      </div>

      <div className="border-b border-sidebar-border px-3 py-3">
        <Button
          type="button"
          onClick={handleNewChat}
          title={collapsed ? "新对话" : undefined}
          className={cn(
            "h-9 rounded-lg bg-sidebar-primary text-sm text-sidebar-primary-foreground hover:bg-sidebar-primary/90",
            collapsed ? "w-full px-0" : "w-full justify-start gap-2"
          )}
        >
          <MessageSquarePlus className="h-4 w-4" />
          {!collapsed && <span>新对话</span>}
        </Button>
      </div>

      <nav className="space-y-1 border-b border-sidebar-border px-3 py-3" aria-label="功能导航">
        {navItems.map((item) => {
          const isActive = pathname.startsWith(item.href);
          return (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              aria-current={isActive ? "page" : undefined}
              className={cn(
                "flex h-9 items-center rounded-lg text-sm transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring",
                collapsed ? "justify-center px-0" : "gap-3 px-3",
                isActive
                  ? "bg-sidebar-accent text-sidebar-accent-foreground shadow-[inset_2px_0_0_var(--sidebar-primary)]"
                  : "text-sidebar-foreground/68 hover:bg-sidebar-accent/60 hover:text-sidebar-foreground"
              )}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          );
        })}
      </nav>

      {!collapsed ? (
        <div className="flex min-h-0 flex-1 flex-col px-3 py-3">
          <div className="mb-2 flex items-center justify-between px-1">
            <h2 className="text-sm font-semibold text-sidebar-foreground">
              最近
            </h2>
            <span className="text-[11px] text-sidebar-foreground/45">{uniqueConversations.length}</span>
          </div>
          <ScrollArea className="min-h-0 flex-1 pr-1">
            <div className="space-y-1 pb-2">
              {uniqueConversations.map((conversation) => (
                <ConversationNavItem
                  key={conversation.id}
                  conv={conversation}
                  isActive={activeConversationId === conversation.id}
                  hasUnread={unreadIds.has(conversation.id) && activeConversationId !== conversation.id}
                  collapsed={collapsed}
                  onSelect={handleSelectConversation}
                  onDelete={handleDeleteConversation}
                />
              ))}
              {uniqueConversations.length === 0 && (
                <p className="px-2 py-4 text-center text-xs text-sidebar-foreground/45">
                  暂无历史会话
                </p>
              )}
              {hasMoreConversations && (
                <Button
                  variant="ghost"
                  size="sm"
                  className="w-full text-xs text-sidebar-foreground/55 hover:bg-sidebar-accent/60"
                  onClick={loadMoreConversations}
                >
                  加载更多会话
                </Button>
              )}
            </div>
          </ScrollArea>
        </div>
      ) : (
        <div className="flex-1" />
      )}

      <div className="border-t border-sidebar-border px-3 py-3">
        <nav className="space-y-1" aria-label="辅助导航">
          {utilityItems.map((item) => (
            <Link
              key={item.href}
              href={item.href}
              title={collapsed ? item.label : undefined}
              className={cn(
                "flex h-9 items-center rounded-lg text-sm text-sidebar-foreground/62 transition-colors hover:bg-sidebar-accent/60 hover:text-sidebar-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sidebar-ring",
                collapsed ? "justify-center px-0" : "gap-3 px-3"
              )}
            >
              <item.icon className="h-4 w-4 shrink-0" />
              {!collapsed && <span>{item.label}</span>}
            </Link>
          ))}
        </nav>
        <div
          className={cn(
            "mt-3 flex items-center border-t border-sidebar-border pt-3",
            collapsed ? "justify-center" : "gap-3 px-2"
          )}
        >
          <div className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-surface-container-high text-xs font-semibold text-sidebar-foreground">
            U
          </div>
          {!collapsed && (
            <div className="min-w-0">
              <div className="truncate text-xs font-medium">用户</div>
              <div className="truncate text-[11px] text-sidebar-foreground/50">本地档案</div>
            </div>
          )}
        </div>
      </div>
    </aside>
  );
}
