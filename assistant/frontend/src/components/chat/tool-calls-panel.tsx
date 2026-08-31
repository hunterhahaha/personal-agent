"use client";

import { useState } from "react";
import { cn } from "@/lib/utils";
import type { ToolCallEntry } from "@/lib/api-client";
import { CheckCircle2, CircleDashed, Clock3, HelpCircle, XCircle } from "lucide-react";

// ---------------------------------------------------------------------------
// dedupByCallID — defensive de-duplication of tool call entries by callID.
//
// Rules:
//   - Entries with a non-empty `callID` are collapsed so that the LAST
//     occurrence wins (later status/metadata updates supersede earlier ones),
//     while preserving the original relative order of the surviving entries.
//   - Entries with an empty/missing `callID` pass through in their original
//     order — they cannot collide on `callID`, and their React key falls back
//     to the array index via `${tc.callID || 'noid'}:${i}`.
//
// This is a belt-and-suspenders guard that complements the upsert-by-callID
// logic in chat-store.ts; even if upstream state transiently contains two
// entries with the same callID, the rendered sibling keys remain unique.
// ---------------------------------------------------------------------------
function dedupByCallID(list: ToolCallEntry[]): ToolCallEntry[] {
  // First pass: for each non-empty callID, record the LAST index it appears at.
  const lastIndexByCallID = new Map<string, number>();
  list.forEach((tc, i) => {
    if (tc.callID) {
      lastIndexByCallID.set(tc.callID, i);
    }
  });

  // Second pass: keep entries with no callID (in order), and entries whose
  // callID's last-seen index matches the current index (i.e. the final one).
  const result: ToolCallEntry[] = [];
  list.forEach((tc, i) => {
    if (!tc.callID) {
      result.push(tc);
      return;
    }
    if (lastIndexByCallID.get(tc.callID) === i) {
      result.push(tc);
    }
  });
  return result;
}

// ---------------------------------------------------------------------------
// Status normalization helper
// ---------------------------------------------------------------------------
export function normalizeToolStatus(status?: string): ToolCallEntry["status"] {
  switch ((status || "").toLowerCase()) {
    case "done":
    case "completed":
    case "complete":
    case "success":
    case "succeeded":
    case "finished":
      return "done";
    case "running":
    case "in_progress":
    case "in-progress":
    case "processing":
    case "executing":
      return "running";
    case "pending":
    case "approval_required":
    case "pending_approval":
    case "waiting_approval":
    case "waiting-for-approval":
      return "pending";
    case "error":
    case "failed":
    case "failure":
    case "crashed":
    case "crash":
    case "cancelled":
    case "canceled":
    case "denied":
      return "error";
    default:
      return "running";
  }
}

// ---------------------------------------------------------------------------
// Status icon helper
// ---------------------------------------------------------------------------
export function toolStatusIcon(status: string) {
  switch (normalizeToolStatus(status)) {
    case "done": return { Icon: CheckCircle2, cls: "text-emerald-600", label: "完成" };
    case "running": return { Icon: CircleDashed, cls: "text-primary animate-spin", label: "运行中" };
    case "error": return { Icon: XCircle, cls: "text-destructive", label: "失败" };
    case "pending": return { Icon: Clock3, cls: "text-amber-600", label: "等待审批" };
    default: return { Icon: HelpCircle, cls: "text-muted-foreground", label: "未知" };
  }
}

// ---------------------------------------------------------------------------
// SubCallsList — renders nested sub-agent tool calls
// ---------------------------------------------------------------------------
interface SubCallsListProps {
  subCalls: ToolCallEntry[];
  /** Whether the sub-calls are from an active stream (default expanded) or history (default collapsed) */
  streaming?: boolean;
}

function SubCallsList({ subCalls, streaming }: SubCallsListProps) {
  const [expanded, setExpanded] = useState(streaming ?? true);

  if (!subCalls.length) return null;

  const items = dedupByCallID(subCalls);

  return (
    <div className="ml-5 mt-1 border-l border-muted-foreground/20 pl-2">
      <button
        type="button"
        onClick={() => setExpanded(!expanded)}
        className="flex w-full items-center gap-1 text-left text-[10px] font-medium text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
        aria-expanded={expanded}
      >
        <span className="text-[8px]">{expanded ? "▾" : "▸"}</span>
        子智能体 ({subCalls.length})
      </button>
      {expanded && (
        <div className="mt-1 space-y-1">
          {items.map((sc, i) => {
            const { Icon, cls, label } = toolStatusIcon(sc.status);
            return (
              <div key={`${sc.callID || "noid"}:${i}`}>
                <div className="flex items-center gap-2 text-xs">
                  <Icon className={cn("h-3.5 w-3.5 shrink-0", cls)} aria-label={label} />
                  <span className="text-muted-foreground truncate">{sc.toolName}</span>
                </div>
                {/* Recursively render deeper sub-calls if present */}
                {sc.subCalls && sc.subCalls.length > 0 && (
                  <SubCallsList subCalls={sc.subCalls} streaming={streaming} />
                )}
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function getToolInputPreview(tc: ToolCallEntry): string {
  if (tc.command) return tc.command;

  const command = tc.state?.input?.command;
  if (typeof command === "string" && command.length > 0) return command;
  return "";
}

// ---------------------------------------------------------------------------
// ToolCallsPanel
// ---------------------------------------------------------------------------
interface ToolCallsPanelProps {
  toolCalls: ToolCallEntry[];
  /** If true, the list is collapsible via a header toggle. */
  collapsible?: boolean;
  /** Only used when collapsible=true */
  expanded?: boolean;
  onToggle?: () => void;
  /** Approve/deny handlers for pending tools — accept requestId to target specific approval */
  onApprove?: (requestId: string) => void;
  onDeny?: (requestId: string) => void;
  /** Whether the panel is showing during active streaming (affects sub-call default expand state) */
  streaming?: boolean;
}

export function ToolCallsPanel({
  toolCalls,
  collapsible,
  expanded,
  onToggle,
  onApprove,
  onDeny,
  streaming,
}: ToolCallsPanelProps) {
  if (!toolCalls.length) return null;

  const items = dedupByCallID(toolCalls);

  const list = (
    <div className="space-y-1">
      {items.map((tc, i) => {
        const normalizedStatus = normalizeToolStatus(tc.status);
        const { Icon, cls, label } = toolStatusIcon(normalizedStatus);
        const inputPreview = getToolInputPreview(tc);
        return (
          <div key={`${tc.callID || "noid"}:${i}`}>
            <div className="flex items-center gap-2 text-xs">
              <Icon className={cn("h-3.5 w-3.5 shrink-0", cls)} aria-label={label} />
              <span className="text-muted-foreground truncate">{tc.toolName}</span>
              <span className="shrink-0 text-[10px] text-muted-foreground/80">
                {label}
              </span>
              {normalizedStatus === "pending" && tc.requestId && onApprove && onDeny && (
                <div className="flex gap-1 ml-auto shrink-0">
                  <button
                    type="button"
                    onClick={() => onApprove(tc.requestId!)}
                    className="rounded-md bg-emerald-600 px-1.5 py-0.5 text-[10px] text-[oklch(0.985_0.006_248)] hover:bg-emerald-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-emerald-500/50"
                    aria-label={`批准工具调用 ${tc.toolName}`}
                  >
                    批准
                  </button>
                  <button
                    type="button"
                    onClick={() => onDeny(tc.requestId!)}
                    className="rounded-md bg-destructive px-1.5 py-0.5 text-[10px] text-[oklch(0.985_0.006_248)] hover:bg-destructive/90 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-destructive/40"
                    aria-label={`拒绝工具调用 ${tc.toolName}`}
                  >
                    拒绝
                  </button>
                </div>
              )}
            </div>
            {inputPreview && (
              <pre className="mt-1 bg-muted rounded px-2 py-1 text-[11px] font-mono text-muted-foreground overflow-x-auto max-h-16">
                {inputPreview}
              </pre>
            )}
            {tc.state?.summary && (
              <p className="mt-1 text-[11px] leading-relaxed text-muted-foreground">
                {tc.state.summary}
              </p>
            )}
            {/* Render nested sub-agent tool calls */}
            {tc.subCalls && tc.subCalls.length > 0 && (
              <SubCallsList subCalls={tc.subCalls} streaming={streaming} />
            )}
          </div>
        );
      })}
    </div>
  );

  if (collapsible) {
    return (
      <div className="mb-1 rounded-md border border-border/70 bg-muted/35 px-3 py-1.5">
        <button
          type="button"
          onClick={onToggle}
          className="flex w-full items-center gap-1 text-left text-[10px] font-medium text-muted-foreground focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
          aria-expanded={expanded}
        >
          <span className="text-[8px]">{expanded ? "▾" : "▸"}</span>
          工具调用 ({toolCalls.length})
        </button>
        {expanded && <div className="mt-1">{list}</div>}
      </div>
    );
  }

  return <div className="space-y-1">{list}</div>;
}
