"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useChatStore } from "@/stores/chat-store";
import { Button } from "@/components/ui/button";
import ModelSelector from "@/components/chat/model-selector";
import { WorkspaceSelector } from "@/components/chat/workspace-selector";
import { ScrollArea } from "@/components/ui/scroll-area";
import { cn } from "@/lib/utils";
import {
  Send,
  MessageSquare,
  Loader2,
  AlertCircle,
  User,
  ListChecks,
  Sparkles,
} from "lucide-react";
import ReactMarkdown from "react-markdown";
import type { Components } from "react-markdown";
import remarkGfm from "remark-gfm";
import { CodeBlock } from "@/components/chat/code-block";
import { normalizeToolStatus, ToolCallsPanel } from "@/components/chat/tool-calls-panel";
import { ReasoningBlock } from "@/components/chat/reasoning-block";
import { useElapsedTimer } from "@/hooks/use-elapsed-timer";
import { TaskHistory } from "@/components/layout/task-history";
import type { Message, ToolCallEntry } from "@/lib/api-client";
import { buildChatTurns, getAssistantIterations, getAssistantPreviewText, getRenderableParts } from "@/lib/chat-turns";
import { isTaskConversation } from "@/lib/conversation-types";

// ---------------------------------------------------------------------------
// Markdown renderer
// ---------------------------------------------------------------------------
const markdownRemarkPlugins = [remarkGfm];

const markdownComponents: Components = {
  p: ({ children }) => <p className="mb-3 whitespace-pre-wrap leading-7 last:mb-0">{children}</p>,
  ul: ({ children, ...props }) => <ul className="mb-3 list-disc space-y-1.5 pl-5" {...props}>{children}</ul>,
  ol: ({ children, ...props }) => <ol className="mb-3 list-decimal space-y-1.5 pl-5" {...props}>{children}</ol>,
  li: ({ children, ...props }) => <li {...props}>{children}</li>,
  code({ className, children, ...props }) {
    const match = /language-(\w+)/.exec(className || "");
    const code = String(children).replace(/\n$/, "");

    // If it has a language class it is a fenced code block.
    if (match) {
      return <CodeBlock language={match[1]} code={code} />;
    }

    // Otherwise it is an inline code span.
    return (
      <code
        className="rounded bg-surface-container-high px-1.5 py-0.5 font-mono text-[0.88em] text-foreground"
        {...props}
      >
        {children}
      </code>
    );
  },
  pre: ({ children, ...props }) => <pre {...props}>{children}</pre>,
  h1: ({ children }) => <h1 className="mb-3 mt-6 text-xl font-semibold leading-8 first:mt-0">{children}</h1>,
  h2: ({ children }) => <h2 className="mb-2.5 mt-5 text-base font-semibold leading-7 first:mt-0">{children}</h2>,
  h3: ({ children }) => <h3 className="mb-2 mt-4 text-sm font-semibold leading-6 text-foreground/85 first:mt-0">{children}</h3>,
  blockquote: ({ children }) => (
    <blockquote className="my-3 border-l-2 border-outline-variant bg-surface-container-low px-4 py-2 text-muted-foreground">
      {children}
    </blockquote>
  ),
  a: ({ children, href }) => (
    <a href={href} target="_blank" rel="noopener noreferrer" className="font-medium text-primary underline underline-offset-4">
      {children}
    </a>
  ),
  table: ({ children, ...props }) => (
    <div className="overflow-x-auto my-3">
      <table className="border-collapse border border-border text-sm" {...props}>
        {children}
      </table>
    </div>
  ),
  th: ({ children, ...props }) => (
    <th className="border border-border bg-surface-container px-3 py-1.5 font-semibold" {...props}>
      {children}
    </th>
  ),
  td: ({ children, ...props }) => (
    <td className="border border-border px-3 py-1.5" {...props}>{children}</td>
  ),
  tr: ({ children, ...props }) => <tr {...props}>{children}</tr>,
};

function formatDuration(seconds: number): string {
  const normalized = Math.max(0, Math.floor(seconds));
  const min = Math.floor(normalized / 60);
  const sec = normalized % 60;
  return min > 0 ? `${min}分${sec}秒` : `${sec}秒`;
}

function getMessageDurationSeconds(message: Message): number | null {
  const time = (message.msg_json?.message as { time?: { start?: number; end?: number } } | undefined)?.time;
  if (!time?.start || !time?.end) {
    return null;
  }

  const durationMs = time.end - time.start;
  if (durationMs < 0) {
    return null;
  }

  return durationMs / 1000;
}

function getTurnDurationSeconds(messages: Message[]): number | null {
  const durations = messages
    .map(getMessageDurationSeconds)
    .filter((value): value is number => value !== null);

  if (durations.length === 0) {
    return null;
  }

  return durations.reduce((sum, value) => sum + value, 0);
}

function textScrollSignature(text: string): string {
  let checksum = 0;
  for (let index = 0; index < text.length; index += 1) {
    checksum = (checksum + text.charCodeAt(index) * (index + 1)) % 1000003;
  }

  return `${text.length}:${checksum}`;
}

function toolCallScrollSignature(toolCall: ToolCallEntry): string {
  return [
    toolCall.callID,
    toolCall.requestId,
    toolCall.toolName,
    toolCall.status,
    toolCall.command ? textScrollSignature(toolCall.command) : "",
    toolCall.state?.status,
    toolCall.state?.summary ? textScrollSignature(toolCall.state.summary) : "",
    toolCall.state?.error ? textScrollSignature(toolCall.state.error) : "",
    toolCall.subCalls?.map(toolCallScrollSignature).join(",") ?? "",
  ].join(":");
}

interface AssistantIterationProps {
  message: Message;
}

interface AssistantTurnGroupProps {
  messages: Message[];
  isStreaming: boolean;
  activeReasoningText: string;
  toolCalls: ToolCallEntry[];
  formatted: string;
  completedFormatted: string | null;
  resolveApproval: (requestId: string, approved: boolean) => void;
  previewText: string;
  defaultOpen?: boolean;
}

function AssistantIteration({
  message,
}: AssistantIterationProps) {
  const parts = useMemo(() => getRenderableParts(message), [message]);
  const historicalToolCalls = useMemo(
    () =>
      parts.flatMap((part) => {
        if (part.type !== "toolcall") {
          return [];
        }

        return [{
          toolName: part.tool,
          status: normalizeToolStatus(part.state?.status),
          callID: part.callID,
          state: part.state,
          metadata: part.metadata,
        }];
      }),
    [parts],
  );

  const contentParts = useMemo(
    () => parts.filter((part) => part.type !== "toolcall"),
    [parts],
  );

  const hasAnyContent = contentParts.length > 0 || historicalToolCalls.length > 0;

  if (!hasAnyContent) {
    return null;
  }

  return (
    <div className="space-y-3">
      {(historicalToolCalls.length > 0 || parts.some((part) => part.type === "reasoning" || part.type === "thought")) && (
        <details className="group text-xs text-muted-foreground">
          <summary className="flex cursor-pointer list-none items-center gap-2 py-1 font-medium transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
            <span className="text-[10px] transition-transform group-open:rotate-90">▸</span>
            <span>查看本条助手详情</span>
          </summary>
          <div className="mt-1 space-y-3 pl-5">
            {parts.map((part, index) => {
              const key = `${part.type}-${part.id || index}`;

              if (part.type === "reasoning" || part.type === "thought") {
                return <ReasoningBlock key={key} content={part.text} defaultOpen />;
              }

              return null;
            })}
            {historicalToolCalls.length > 0 && (
              <details className="group text-xs text-muted-foreground">
                <summary className="flex cursor-pointer list-none items-center gap-2 py-1 font-medium transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  <span className="text-[10px] transition-transform group-open:rotate-90">▸</span>
                  <span>{`查看工具调用 (${historicalToolCalls.length})`}</span>
                </summary>
                <div className="mt-1 pl-5">
                  <ToolCallsPanel toolCalls={historicalToolCalls} />
                </div>
              </details>
            )}
          </div>
        </details>
      )}

      {contentParts.map((part, index) => {
        const key = `${part.type}-${part.id || index}`;

        if (part.type === "text") {
          return (
            <div
              key={key}
              className="prose prose-sm max-w-none text-[15px] leading-7 text-foreground dark:prose-invert"
            >
              <ReactMarkdown components={markdownComponents} remarkPlugins={markdownRemarkPlugins}>
                {part.text}
              </ReactMarkdown>
            </div>
          );
        }

        return null;
      })}
    </div>
  );
}

function AssistantTurnGroup({
  messages,
  isStreaming,
  activeReasoningText,
  toolCalls,
  formatted,
  completedFormatted,
  resolveApproval,
  previewText,
  defaultOpen = false,
}: AssistantTurnGroupProps) {
  const [open, setOpen] = useState(defaultOpen);
  const wasStreamingRef = useRef(isStreaming);
  const iterations = useMemo(
    () => messages.map((message) => ({ message, key: `assistant-${message.id}` })),
    [messages],
  );

  const liveToolCalls = useMemo(
    () => toolCalls.map((toolCall) => ({ ...toolCall, status: normalizeToolStatus(toolCall.status) })),
    [toolCalls],
  );

  const hasStreamingStatus = isStreaming || activeReasoningText.length > 0 || liveToolCalls.length > 0;

  useEffect(() => {
    const wasStreaming = wasStreamingRef.current;
    wasStreamingRef.current = isStreaming;

    let cancelled = false;
    queueMicrotask(() => {
      if (cancelled) return;
      if (isStreaming) {
        setOpen(true);
      } else if (wasStreaming && messages.length > 0) {
        setOpen(false);
      }
    });

    return () => {
      cancelled = true;
    };
  }, [isStreaming, messages.length]);

  if (!iterations.length && !hasStreamingStatus) {
    return null;
  }

  return (
    <div className="min-w-0 flex-1 border-b border-border/80 pb-6">
      <button
        type="button"
        onClick={() => setOpen((value) => !value)}
        className="flex w-full items-start gap-2 py-1 text-left text-sm transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-expanded={open}
      >
        <span className={cn(
          "pt-0.5 text-[10px] text-muted-foreground transition-transform",
          open && "rotate-90",
        )}>▸</span>
        <div className="min-w-0 flex-1">
          <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
            <span className="inline-flex items-center gap-2 font-medium text-foreground/80">
              <Sparkles className="h-3.5 w-3.5 text-primary" />
              {isStreaming ? "处理中" : "已处理"}
            </span>
            {(isStreaming ? formatted : completedFormatted) && (
              <span className="tabular-nums">{isStreaming ? formatted : completedFormatted}</span>
            )}
            {messages.length > 1 && <span>{messages.length} 条助手消息</span>}
          </div>
        </div>
      </button>

      {!open && previewText && (
        <div className="mt-2 pl-5">
          <div className="prose prose-sm max-w-none text-[15px] leading-7 text-foreground dark:prose-invert">
            <ReactMarkdown components={markdownComponents} remarkPlugins={markdownRemarkPlugins}>
              {previewText}
            </ReactMarkdown>
          </div>
        </div>
      )}

      {open && (
      <div className="mt-3 space-y-5 pl-5">
        {iterations.map((iteration, index) => (
          <div key={iteration.key} className="space-y-3">
            {messages.length > 1 && (
              <div className="text-xs font-medium text-muted-foreground">
                助手消息 {index + 1}
              </div>
            )}
            <AssistantIteration message={iteration.message} />
          </div>
        ))}

        {hasStreamingStatus && (
          <div className="space-y-2 pb-1">
            <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-muted-foreground">
              <span className="inline-flex items-center gap-2 font-medium text-foreground/80">
                <Sparkles className="h-3.5 w-3.5 text-primary" />
                {liveToolCalls.length > 0 ? "正在检索与处理" : "正在思考"}
              </span>
              {isStreaming && (
                <span className="inline-flex items-center gap-1.5 tabular-nums">
                  <Loader2 className="h-3.5 w-3.5 animate-spin" />
                  {formatted}
                </span>
              )}
              {liveToolCalls.length > 0 && (
                <span>{liveToolCalls.length} 个工具调用</span>
              )}
            </div>
            {activeReasoningText && (
              <ReasoningBlock content={activeReasoningText} defaultOpen label="查看当前思考" />
            )}
            {liveToolCalls.length > 0 && (
              <details className="group text-xs text-muted-foreground" open={isStreaming}>
                <summary className="flex cursor-pointer list-none items-center gap-2 py-1 font-medium transition-colors hover:text-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring">
                  <span className="text-[10px] transition-transform group-open:rotate-90">▸</span>
                  <span>{`查看工具调用 (${liveToolCalls.length})`}</span>
                </summary>
                <div className="mt-1 pl-5">
                  <ToolCallsPanel
                    toolCalls={liveToolCalls}
                    onApprove={(requestId) => resolveApproval(requestId, true)}
                    onDeny={(requestId) => resolveApproval(requestId, false)}
                    streaming={isStreaming}
                  />
                </div>
              </details>
            )}
          </div>
        )}
      </div>
      )}
    </div>
  );
}

// ---------------------------------------------------------------------------
// ChatPageClient
// ---------------------------------------------------------------------------
interface ChatPageClientProps {
  routeConversationId?: number | null;
  invalidRoute?: boolean;
}

export function ChatPageClient({
  routeConversationId = null,
  invalidRoute = false,
}: ChatPageClientProps) {
  const router = useRouter();
  const {
    conversations,
    activeConversationId,
    messages,
    activeStreams,
    activeStreamStartedAt,
    recoveredStreams,
    error,
    toolCalls,
    activeReasoningByMsg,
    hasMoreMessages,
    loadConversations,
    selectConversation,
    startNewChat,
    createConversation,
    updateConversationTitle,
    sendMessage,
    resolveApproval,
    activeModelId,
    setActiveModelId,
    draftWorkspaceRoot,
    setDraftWorkspaceRoot,
    selectWorkspaceFolder,
    loadMoreMessages,
    refreshActiveConversationMessages,
    subscribeRecoveredConversationEvents,
  } = useChatStore();

  const streamKey = activeConversationId ?? 0;
  const isStreaming = activeStreams.includes(streamKey);
  const isRecoveredStreaming = recoveredStreams.includes(streamKey);
  const streamStartedAt = activeStreamStartedAt[streamKey] ?? null;

  // Active reasoning text for the currently streaming message
  const activeReasoningText = activeReasoningByMsg[streamKey] || "";

  // Deduplicate by id; a message is truly empty only when ALL of:
  // parts is empty AND toolCalls is empty/undefined AND content is empty/falsy.
  const uniqueMessages = useMemo(() => {
    const seen = new Set<number>();
    return messages.filter((msg) => {
      if (seen.has(msg.id)) return false;
      const hasNoParts = !msg.parts || msg.parts.length === 0;
      const hasNoToolCalls = !msg.toolCalls || msg.toolCalls.length === 0;
      const hasNoContent = !msg.content?.trim();
      if (hasNoParts && hasNoToolCalls && hasNoContent) return false;
      seen.add(msg.id);
      return true;
    });
  }, [messages]);

  const chatTurns = useMemo(() => buildChatTurns(uniqueMessages), [uniqueMessages]);

  const [input, setInput] = useState("");
  const [editingTitle, setEditingTitle] = useState(false);
  const [editValue, setEditValue] = useState("");
  const [taskHistoryOpen, setTaskHistoryOpen] = useState(false);
  const pendingDraftNavigationRef = useRef(false);
  const syncedRouteConversationRef = useRef<number | null>(null);
  const titleInputRef = useRef<HTMLInputElement>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const { formatted } = useElapsedTimer(isStreaming, streamStartedAt);
  const messageScrollSignature = useMemo(() => {
    const lastMessage = uniqueMessages.at(-1);
    if (!lastMessage) {
      return "empty";
    }

    const parts = getRenderableParts(lastMessage);
    const partsSignature = parts
      .map((part) => {
        if (part.type === "toolcall") {
          return [
            part.type,
            part.callID,
            part.state?.status,
            part.state?.summary?.length ?? 0,
            part.state?.error?.length ?? 0,
          ].join(":");
        }

        return [part.type, textScrollSignature(part.text)].join(":");
      })
      .join("|");

    return [
      lastMessage.id,
      textScrollSignature(lastMessage.content ?? ""),
      parts.length,
      partsSignature,
    ].join(":");
  }, [uniqueMessages]);
  const liveToolCallSignature = useMemo(
    () =>
      toolCalls
        .map(toolCallScrollSignature)
        .join("|"),
    [toolCalls],
  );

  useEffect(() => {
    loadConversations();
  }, [loadConversations]);

  useEffect(() => {
    if (routeConversationId !== null) {
      pendingDraftNavigationRef.current = false;
    }
  }, [routeConversationId]);

  useEffect(() => {
    if (invalidRoute) {
      startNewChat();
      router.replace("/chat");
      return;
    }

    const currentActiveConversationId = useChatStore.getState().activeConversationId;

    if (routeConversationId === null) {
      syncedRouteConversationRef.current = null;
      if (currentActiveConversationId !== null && !pendingDraftNavigationRef.current) {
        startNewChat();
      }
      return;
    }

    if (currentActiveConversationId === routeConversationId) {
      syncedRouteConversationRef.current = routeConversationId;
      return;
    }

    syncedRouteConversationRef.current = routeConversationId;
    let cancelled = false;
    void selectConversation(routeConversationId).then((loaded) => {
      if (!cancelled && !loaded) {
        startNewChat();
        router.replace("/chat");
      }
    });

    return () => {
      cancelled = true;
    };
  }, [
    activeConversationId,
    invalidRoute,
    routeConversationId,
    router,
    selectConversation,
    startNewChat,
  ]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [activeReasoningText, isStreaming, liveToolCallSignature, messageScrollSignature]);

  useEffect(() => {
    if (
      !isStreaming ||
      !isRecoveredStreaming ||
      routeConversationId === null ||
      activeConversationId !== routeConversationId
    ) {
      return;
    }

    const poll = () => {
      void refreshActiveConversationMessages();
      void loadConversations();
    };

    poll();
    const interval = window.setInterval(poll, 2500);
    const controller = new AbortController();
    void subscribeRecoveredConversationEvents(routeConversationId, controller.signal);

    return () => {
      window.clearInterval(interval);
      controller.abort();
    };
  }, [
    activeConversationId,
    isRecoveredStreaming,
    isStreaming,
    loadConversations,
    refreshActiveConversationMessages,
    routeConversationId,
    subscribeRecoveredConversationEvents,
  ]);

  const handleSend = async () => {
    const text = input.trim();
    if (!text || isStreaming) return;
    setInput("");
    const shouldNavigateToCreatedConversation =
      routeConversationId === null && activeConversationId === null;
    if (shouldNavigateToCreatedConversation) {
      pendingDraftNavigationRef.current = true;
      const createdConversationId = await createConversation();
      if (!createdConversationId) {
        pendingDraftNavigationRef.current = false;
        return;
      }
      router.replace(`/chat/${createdConversationId}`);
    }

    const conversationId = await sendMessage(text);
    if (!shouldNavigateToCreatedConversation && conversationId && routeConversationId === null) {
      router.replace(`/chat/${conversationId}`);
    }
  };

  const handleInputKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  };

  const startEditingTitle = () => {
    setEditValue(activeConv?.title || "");
    setEditingTitle(true);
    setTimeout(() => titleInputRef.current?.focus(), 0);
  };

  const confirmTitle = async () => {
    const trimmed = editValue.trim();
    setEditingTitle(false);
    if (trimmed && activeConversationId && trimmed !== activeConv?.title) {
      await updateConversationTitle(activeConversationId, trimmed);
    }
  };

  const cancelTitle = () => {
    setEditingTitle(false);
  };

  const handleTitleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "Enter") {
      e.preventDefault();
      confirmTitle();
    } else if (e.key === "Escape") {
      cancelTitle();
    }
  };

  const activeConv = conversations.find(
    (c) => c.id === activeConversationId
  );
  const activeIsTask = isTaskConversation(activeConv);
  const displayTitle = activeConv?.title || "新会话";
  const currentWorkspaceRoot = activeConversationId
    ? activeConv?.workspace_root ?? null
    : draftWorkspaceRoot;

  return (
    <div className="flex h-full min-h-0 min-w-0 flex-col bg-background">
      <div className="relative flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden">
        <div className="flex h-14 shrink-0 items-center gap-2 border-b border-border bg-background/95 px-3 sm:px-5">
          {editingTitle ? (
            <div className="flex items-center gap-2">
              <input
                ref={titleInputRef}
                value={editValue}
                onChange={(e) => setEditValue(e.target.value)}
                onKeyDown={handleTitleKeyDown}
                onBlur={cancelTitle}
                className="w-[220px] rounded-md border border-input bg-card px-2 py-1 text-sm font-semibold outline-none focus-visible:ring-2 focus-visible:ring-ring"
                maxLength={25}
              />
              <span className="text-xs text-muted-foreground shrink-0">
                {editValue.length}/{25}
              </span>
            </div>
          ) : (
            <button
              type="button"
              className="ml-1 flex max-w-[34vw] cursor-pointer items-center gap-2 truncate text-left text-sm font-semibold transition-colors hover:text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring sm:max-w-[46ch]"
              onClick={startEditingTitle}
              title={displayTitle}
              onKeyDown={(e) => {
                if (e.key === "Enter" || e.key === " ") {
                  e.preventDefault();
                  startEditingTitle();
                }
              }}
            >
              {activeIsTask && (
                <span className="shrink-0 rounded border border-border bg-surface-container-high px-1.5 py-0.5 text-[10px] font-medium leading-none text-muted-foreground">
                  任务
                </span>
              )}
              <span className="truncate">{displayTitle}</span>
            </button>
          )}

          <div className="ml-auto flex items-center gap-1">
            {activeIsTask && (
              <Button
                variant={taskHistoryOpen ? "secondary" : "ghost"}
                size="icon"
                onClick={() => setTaskHistoryOpen((open) => !open)}
                aria-pressed={taskHistoryOpen}
                aria-label={taskHistoryOpen ? "隐藏任务历史" : "显示任务历史"}
                title={taskHistoryOpen ? "隐藏任务历史" : "显示任务历史"}
              >
                <ListChecks className="h-4 w-4" />
              </Button>
            )}
          </div>
        </div>

        <ScrollArea className="min-h-0 flex-1">
          <div className="mx-auto w-full max-w-[980px] space-y-7 px-4 pb-44 pt-7 sm:px-6 sm:pb-48 lg:px-10">
            {hasMoreMessages && (
              <div className="flex justify-center">
                <Button
                  variant="ghost"
                  size="sm"
                  className="text-xs text-muted-foreground"
                  onClick={loadMoreMessages}
                >
                  加载更多
                </Button>
              </div>
            )}
            {chatTurns.map((turn, index) => {
              const isLastTurn = index === chatTurns.length - 1;
              const showStreamingState = isLastTurn && isStreaming;
              const assistantIterations = getAssistantIterations(turn);
              const previewText = getAssistantPreviewText(turn);
              const completedFormatted = !showStreamingState
                ? (() => {
                    const duration = getTurnDurationSeconds(turn.assistantMessages);
                    return duration === null ? null : formatDuration(duration);
                  })()
                : null;
              const hasAssistantDocument =
                assistantIterations.length > 0 ||
                showStreamingState ||
                (isLastTurn && (activeReasoningText.length > 0 || toolCalls.length > 0));

              return (
                <div
                  key={turn.id}
                  className="space-y-5"
                  style={{ contentVisibility: "auto", containIntrinsicSize: "0 180px" }}
                >
                  {turn.userMessage && (
                    <div className="flex justify-end gap-3 sm:gap-4">
                      <div className="max-w-[min(88%,720px)]">
                        <div className="rounded-lg bg-primary px-4 py-3 text-sm leading-7 text-primary-foreground shadow-sm">
                          <p className="whitespace-pre-wrap">{turn.userMessage.content}</p>
                        </div>
                      </div>
                      <div className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg border border-border bg-card text-muted-foreground">
                        <User className="h-4 w-4" />
                      </div>
                    </div>
                  )}

                  {hasAssistantDocument && (
                    <div className="flex justify-start">
                      <AssistantTurnGroup
                        messages={turn.assistantMessages}
                        isStreaming={showStreamingState}
                        activeReasoningText={isLastTurn ? activeReasoningText : ""}
                        toolCalls={isLastTurn ? toolCalls : []}
                        formatted={formatted}
                        completedFormatted={completedFormatted}
                        resolveApproval={resolveApproval}
                        previewText={previewText}
                        defaultOpen={showStreamingState || turn.assistantMessages.length <= 1}
                      />
                    </div>
                  )}
                </div>
              );
            })}

            {chatTurns.length === 0 && isStreaming && (
              <div key="streaming-only" className="flex justify-start">
                <AssistantTurnGroup
                  messages={[]}
                  isStreaming
                  activeReasoningText={activeReasoningText}
                  toolCalls={toolCalls}
                  formatted={formatted}
                  completedFormatted={null}
                  resolveApproval={resolveApproval}
                  previewText=""
                  defaultOpen
                />
              </div>
            )}

            {error && (
              <div key="error" className="flex items-center justify-center gap-2 rounded-lg border border-destructive/25 bg-destructive/5 px-4 py-3 text-sm text-destructive">
                <AlertCircle className="w-4 h-4" />
                {error}
              </div>
            )}

            {messages.length === 0 && !isStreaming && !error && (
              <div key="empty-state" className="py-20 text-center">
                <div className="mx-auto mb-4 flex h-12 w-12 items-center justify-center rounded-lg border border-border bg-card">
                  <MessageSquare className="h-6 w-6 text-muted-foreground" />
                </div>
                <h3 className="mb-1 text-lg font-semibold">开始对话</h3>
                <p className="text-sm text-muted-foreground">
                  发送一条消息开始与智能助手对话
                </p>
              </div>
            )}

            <div key="scroll-anchor" ref={messagesEndRef} />
          </div>
        </ScrollArea>

        <div className="pointer-events-none absolute inset-x-0 bottom-0 z-20 px-4 pb-4 sm:px-6 sm:pb-5">
          <div className="w-[calc(100vw-2rem)] min-w-0 max-w-none md:mx-auto md:w-full md:max-w-[980px]">
            <div className="pointer-events-auto w-full min-w-0 overflow-hidden rounded-2xl border border-border/80 bg-card/95 p-2.5 shadow-[0_18px_55px_rgba(15,23,42,0.13)] backdrop-blur supports-[backdrop-filter]:bg-card/85">
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                onKeyDown={handleInputKeyDown}
                placeholder="输入消息...（按 Shift+Enter 换行）"
                disabled={isStreaming}
                rows={1}
                aria-label="输入消息"
                className="min-h-[50px] max-h-[160px] w-full min-w-0 resize-none rounded-xl border-0 bg-transparent px-3 py-3 text-sm leading-6 outline-none transition-colors placeholder:text-muted-foreground/60 focus-visible:ring-0 disabled:opacity-50"
                onInput={(e) => {
                  const el = e.currentTarget;
                  el.style.height = "auto";
                  el.style.height = Math.min(el.scrollHeight, 160) + "px";
                }}
              />
              <div className="mt-1 grid w-full min-w-0 grid-cols-[116px_1fr_40px] items-center gap-2 md:grid-cols-[auto_auto_1fr_44px]">
                <ModelSelector
                  selectedModelId={activeModelId}
                  disabled={isStreaming}
                  onChange={setActiveModelId}
                />
                <WorkspaceSelector
                  workspaceRoot={currentWorkspaceRoot}
                  disabled={isStreaming}
                  readOnly={activeConversationId !== null}
                  onSelect={selectWorkspaceFolder}
                  onClear={() => setDraftWorkspaceRoot(null)}
                />
                <div className="hidden min-w-0 md:block" />
                <Button
                  onClick={handleSend}
                  disabled={!input.trim() || isStreaming}
                  size="icon"
                  className="h-10 w-10 shrink-0 rounded-full bg-muted-foreground text-background hover:bg-foreground disabled:bg-muted-foreground/70 md:h-11 md:w-11"
                  aria-label="发送消息"
                >
                  {isStreaming ? (
                    <Loader2 className="w-4 h-4 animate-spin" />
                  ) : (
                    <Send className="w-4 h-4" />
                  )}
                </Button>
              </div>
            </div>
          </div>
        </div>

      </div>
      {activeIsTask && taskHistoryOpen && <TaskHistory onClose={() => setTaskHistoryOpen(false)} />}
    </div>
  );
}
