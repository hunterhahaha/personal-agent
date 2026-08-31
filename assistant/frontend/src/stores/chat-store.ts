import { create } from "zustand";
import { chatApi, conversationsApi, workspacesApi, CONVERSATIONS_LIMIT, MESSAGES_LIMIT, type AssistantMsg, type Conversation, type Message, type ToolCallEntry, type ToolState, type ToolMetadata, type PartToolCall, type ToolStatus, type MsgPart } from "@/lib/api-client";
import { getMessageRole, getMessageText, getRenderableParts } from "@/lib/chat-turns";

// [MIGRATED per REQ-10.4 / AUDIT-P1-020] _optimisticMsgId and _activeLocalCalls
// have been moved into Zustand state, bucketed by conversationId, to ensure
// two concurrent conversations won't share tool call state or optimistic IDs.
// See state fields: localCallsByConv, optimisticIdByConv.

// ---------------------------------------------------------------------------
// upsertToolCall — pure helper that merges a tool-call entry into a list
// keyed by identity. Introduced for the chat-duplicate-key bugfix: the older
// logic that matched by (toolName + status) could stamp two distinct entries
// with the same Anthropic `callID`, which in turn produced React "Encountered
// two children with the same key" warnings in ToolCallsPanel / SubCallsList.
//
// Matching priority for an existing entry in `list`:
//   1. `entry.callID` non-empty AND equal to `list[i].callID` → in-place
//      merge `{ ...list[i], ...entry }`
//   2. else `entry.requestId` non-empty AND equal to `list[i].requestId` →
//      in-place merge (reconciles an approval-originated pending entry when
//      the later tool_call event finally delivers a callID)
//   3. else → append a copy of `entry` as a new entry
//
// The returned list is always a fresh array; the input is not mutated.
// ---------------------------------------------------------------------------
type UpsertToolCallInput = Partial<ToolCallEntry> & {
  toolName: string;
  callID?: string;
  requestId?: string;
};

function getToolInputCommand(input?: Record<string, unknown>): string | undefined {
  const command = input?.command;
  return typeof command === "string" && command.length > 0 ? command : undefined;
}

function toolCallEntryFromPart(part: PartToolCall): ToolCallEntry {
  const input = part.state?.input;
  return {
    toolName: part.tool,
    status: (part.state?.status as ToolStatus) || "done",
    command: getToolInputCommand(input),
    callID: part.callID,
    state: part.state,
    metadata: part.metadata,
  };
}

function upsertToolCall(
  list: ToolCallEntry[],
  entry: UpsertToolCallInput,
): ToolCallEntry[] {
  const cleanEntry = Object.fromEntries(
    Object.entries(entry).filter(([, value]) => value !== undefined),
  ) as UpsertToolCallInput;
  let idx = -1;
  if (cleanEntry.callID && cleanEntry.callID.length > 0) {
    idx = list.findIndex((tc) => tc.callID && tc.callID === cleanEntry.callID);
  }
  if (idx === -1 && cleanEntry.requestId && cleanEntry.requestId.length > 0) {
    idx = list.findIndex((tc) => tc.requestId && tc.requestId === cleanEntry.requestId);
  }
  if (idx !== -1) {
    const next = list.slice();
    next[idx] = { ...list[idx], ...cleanEntry };
    return next;
  }
  return [...list, { ...cleanEntry } as ToolCallEntry];
}

interface ApprovalRequest {
  requestId: string;
  toolName: string;
  toolArgs: Record<string, unknown>;
  resolve: ((approved: boolean) => void) | null;
}

interface ChatState {
  conversations: Conversation[];
  activeConversationId: number | null;
  messages: Message[];
  activeStreams: number[];
  activeStreamStartedAt: Record<number, number>;
  recoveredStreams: number[];
  error: string | null;
  sidebarOpen: boolean;
  toolCalls: ToolCallEntry[];
  /** Approval queue keyed by requestId — supports multiple concurrent approval requests (AUDIT-P1-015, AUDIT-P2-046) */
  approvalQueue: Record<string, ApprovalRequest>;
  unreadIds: Set<number>;
  activeModelId: string | null;
  draftWorkspaceRoot: string | null;
  /** Accumulated reasoning text per streaming message (keyed by optimistic msg id) */
  activeReasoningByMsg: Record<number | string, string>;
  /** Per-conversation tool call entries — prevents cross-conversation state leakage (AUDIT-P1-020) */
  localCallsByConv: Record<number, ToolCallEntry[]>;
  /** Per-conversation optimistic message ID counter (AUDIT-P1-020) */
  optimisticIdByConv: Record<number, number>;
  /** Whether there are more conversations to load beyond the current page */
  hasMoreConversations: boolean;
  /** Whether there are more (older) messages to load in the active conversation */
  hasMoreMessages: boolean;

  loadConversations: () => Promise<void>;
  selectConversation: (id: number) => Promise<boolean>;
  startNewChat: () => void;
  createConversation: () => Promise<number>;
  deleteConversation: (id: number) => Promise<void>;
  updateConversationTitle: (id: number, title: string) => Promise<void>;
  sendMessage: (content: string) => Promise<number | null>;
  resolveApproval: (requestId: string, approved: boolean) => void;
  setSidebarOpen: (open: boolean) => void;
  setActiveModelId: (modelId: string | null) => void;
  setDraftWorkspaceRoot: (workspaceRoot: string | null) => void;
  selectWorkspaceFolder: () => Promise<void>;
  loadMoreConversations: () => Promise<void>;
  loadMoreMessages: () => Promise<void>;
  refreshActiveConversationMessages: () => Promise<void>;
  subscribeRecoveredConversationEvents: (conversationId: number, signal: AbortSignal) => Promise<void>;
}

const _addStream = (streams: number[], id: number) => {
  if (streams.includes(id)) return streams;
  return [...streams, id];
};
const _removeStream = (streams: number[], id: number) => streams.filter((s) => s !== id);
const ACTIVE_STREAMS_STORAGE_KEY = "cc-chat-active-streams-v1";
const MAX_PERSISTED_STREAM_AGE_MS = 24 * 60 * 60 * 1000;
let selectionRequestSeq = 0;
let draftSessionSeq = 0;
const _withoutKey = <K extends string | number, T>(
  record: Record<K, T>,
  key: K
): Record<K, T> => {
  const next = { ...record };
  delete next[key];
  return next;
};

function readPersistedActiveStreamStartedAt(): Record<number, number> {
  if (typeof window === "undefined") {
    return {};
  }

  try {
    const raw = window.localStorage.getItem(ACTIVE_STREAMS_STORAGE_KEY);
    if (!raw) {
      return {};
    }

    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const now = Date.now();
    const activeStreamStartedAt: Record<number, number> = {};
    for (const [key, value] of Object.entries(parsed)) {
      const conversationId = Number(key);
      const startedAt = Number(value);
      if (
        Number.isInteger(conversationId) &&
        conversationId > 0 &&
        Number.isFinite(startedAt) &&
        now - startedAt < MAX_PERSISTED_STREAM_AGE_MS
      ) {
        activeStreamStartedAt[conversationId] = startedAt;
      }
    }

    return activeStreamStartedAt;
  } catch {
    return {};
  }
}

function persistActiveStreamStartedAt(activeStreamStartedAt: Record<number, number>): void {
  if (typeof window === "undefined") {
    return;
  }

  try {
    if (Object.keys(activeStreamStartedAt).length === 0) {
      window.localStorage.removeItem(ACTIVE_STREAMS_STORAGE_KEY);
      return;
    }
    window.localStorage.setItem(ACTIVE_STREAMS_STORAGE_KEY, JSON.stringify(activeStreamStartedAt));
  } catch {
    // Persistence is best-effort; the in-memory stream state still drives UI.
  }
}

function compareMessagesForDisplay(a: Message, b: Message): number {
  const timeA = Date.parse(a.created_at);
  const timeB = Date.parse(b.created_at);
  const normalizedTimeA = Number.isNaN(timeA) ? 0 : timeA;
  const normalizedTimeB = Number.isNaN(timeB) ? 0 : timeB;

  if (normalizedTimeA !== normalizedTimeB) {
    return normalizedTimeA - normalizedTimeB;
  }

  return a.id - b.id;
}

function sortMessagesForDisplay(messages: Message[]): Message[] {
  return [...messages].sort(compareMessagesForDisplay);
}

function mapMessagesForDisplay(data: Message[]): Message[] {
  return sortMessagesForDisplay(data.map((m: Message) => {
    const role = getMessageRole(m);
    const parts = getRenderableParts(m);

    const content = getMessageText(m);
    const toolCalls: ToolCallEntry[] = [];
    for (const p of parts) {
      if (p.type === "toolcall") {
        toolCalls.push(toolCallEntryFromPart(p as PartToolCall));
      }
    }

    return { ...m, role, parts, content, toolCalls: toolCalls.length > 0 ? toolCalls : undefined };
  }));
}

function assistantMessageFromIteration(
  conversationId: number,
  messageId: number,
  msg: AssistantMsg,
): Message {
  const parts: MsgPart[] = msg.parts ?? [];
  const toolCalls: ToolCallEntry[] = [];
  for (const p of parts) {
    if (p.type === "toolcall") {
      toolCalls.push(toolCallEntryFromPart(p));
    }
  }

  const replyMsg: Message = {
    id: messageId,
    conversation_id: conversationId,
    msg_type: "assistant",
    msg_json: msg as unknown as Record<string, unknown>,
    created_at: new Date().toISOString(),
    parts,
    role: "assistant",
    content: "",
    toolCalls: toolCalls.length > 0 ? toolCalls : undefined,
  };
  replyMsg.content = getMessageText(replyMsg);
  return replyMsg;
}

const initialActiveStreamStartedAt = readPersistedActiveStreamStartedAt();

export const useChatStore = create<ChatState>((set, get) => ({
  conversations: [],
  activeConversationId: null,
  messages: [],
  activeStreams: Object.keys(initialActiveStreamStartedAt).map(Number),
  activeStreamStartedAt: initialActiveStreamStartedAt,
  recoveredStreams: Object.keys(initialActiveStreamStartedAt).map(Number),
  error: null,
  sidebarOpen: true,
  toolCalls: [],
  approvalQueue: {},
  unreadIds: new Set<number>(),
  activeModelId: null,
  draftWorkspaceRoot: null,
  activeReasoningByMsg: {},
  localCallsByConv: {},
  optimisticIdByConv: {},
  hasMoreConversations: false,
  hasMoreMessages: false,

  loadConversations: async () => {
    try {
      const { data, total } = await conversationsApi.list();
      set({ conversations: data, hasMoreConversations: data.length < total });
    } catch {
      set({ error: "加载会话失败" });
    }
  },

  selectConversation: async (id: number) => {
    const requestSeq = ++selectionRequestSeq;
    const { unreadIds } = get();
    const updated = new Set(unreadIds);
    updated.delete(id);
    set({ activeConversationId: id, messages: [], error: null, unreadIds: updated, hasMoreMessages: false });
    try {
      const { data, total } = await conversationsApi.getMessages(id);
      const messages = mapMessagesForDisplay(data);
      if (requestSeq !== selectionRequestSeq || get().activeConversationId !== id) {
        return true;
      }

      set({ messages, hasMoreMessages: messages.length < total });
      return true;
    } catch {
      if (requestSeq === selectionRequestSeq && get().activeConversationId === id) {
        set({ error: "加载消息失败" });
      }
      return false;
    }
  },

  startNewChat: () => {
    draftSessionSeq += 1;
    set({
      activeConversationId: null,
      messages: [],
      error: null,
      toolCalls: [],
      approvalQueue: {},
      hasMoreMessages: false,
      draftWorkspaceRoot: null,
    });
  },

  createConversation: async () => {
    try {
      const { draftWorkspaceRoot } = get();
      const { data } = await conversationsApi.create("新会话", draftWorkspaceRoot);
      set((state) => ({
        conversations: [data, ...state.conversations],
        activeConversationId: data.id,
        messages: [],
      }));
      return data.id;
    } catch {
      set({ error: "创建会话失败" });
      return 0;
    }
  },

  deleteConversation: async (id: number) => {
    try {
      await conversationsApi.delete(id);
      set((state) => {
        const updated = new Set(state.unreadIds);
        updated.delete(id);
        const deletedActive = state.activeConversationId === id;
        const activeStreamStartedAt = _withoutKey(state.activeStreamStartedAt, id);
        persistActiveStreamStartedAt(activeStreamStartedAt);

        return {
          conversations: state.conversations.filter((c) => c.id !== id),
          activeConversationId: deletedActive ? null : state.activeConversationId,
          messages: deletedActive ? [] : state.messages,
          unreadIds: updated,
          activeStreams: _removeStream(state.activeStreams, id),
          activeStreamStartedAt,
          recoveredStreams: _removeStream(state.recoveredStreams, id),
        };
      });
    } catch {
      set({ error: "删除会话失败" });
    }
  },

  updateConversationTitle: async (id: number, title: string) => {
    try {
      await conversationsApi.update(id, title);
      set((state) => ({
        conversations: state.conversations.map((c) =>
          c.id === id ? { ...c, title } : c
        ),
      }));
    } catch {
      set({ error: "更新标题失败" });
    }
  },

  sendMessage: async (content: string) => {
    const { activeConversationId, activeModelId, draftWorkspaceRoot } = get();
    const convId = activeConversationId;
    const isDraftConversation = convId === null;
    const draftSessionAtStart = isDraftConversation ? draftSessionSeq : null;
    let completedConversationId: number | null = convId;
    let streamHadError = false;

    const streamKey = convId ?? 0;
    set((state) => ({
      activeStreams: _addStream(state.activeStreams, streamKey),
      activeStreamStartedAt: {
        ...state.activeStreamStartedAt,
        [streamKey]: state.activeStreamStartedAt[streamKey] ?? Date.now(),
      },
      recoveredStreams: _removeStream(state.recoveredStreams, streamKey),
      error: null,
      toolCalls: [],
      approvalQueue: {},
      localCallsByConv: { ...state.localCallsByConv, [streamKey]: [] },
    }));
    if (streamKey > 0) {
      persistActiveStreamStartedAt(useChatStore.getState().activeStreamStartedAt);
    }

    // Per-conversation optimistic ID: decrement from the conversation's current counter
    const currentOptId = get().optimisticIdByConv[streamKey] ?? 0;
    const newOptId = currentOptId - 1;
    set((state) => ({
      optimisticIdByConv: { ...state.optimisticIdByConv, [streamKey]: newOptId },
    }));

    const userMsg: Message = {
      id: newOptId,
      conversation_id: convId ?? 0,
      msg_type: "user",
      msg_json: {
        message: {
          role: "user", time: { start: Date.now(), end: Date.now() },
          agent: "", modelID: activeModelId || "", providerID: "",
          variant: "", id: "", sessionID: ""
        },
        part: [{ type: "text", text: content, id: "", sessionID: "", messageID: "" }],
      },
      created_at: new Date().toISOString(),
      parts: [{ type: "text", text: content, id: "", sessionID: "", messageID: "" }],
      role: "user",
      content,
    };
    set((state) => ({ messages: [...state.messages, userMsg] }));

    const isStillHere = () => {
      const current = get().activeConversationId;
      if (
        convId === null &&
        current === null &&
        draftSessionAtStart === draftSessionSeq
      ) {
        return true;
      }
      if (convId !== null && current === convId) return true;
      return false;
    };

    const stopStream = () => {
      set((state) => {
        const activeStreamStartedAt = _withoutKey(state.activeStreamStartedAt, streamKey);
        persistActiveStreamStartedAt(activeStreamStartedAt);
        return {
          activeStreams: _removeStream(state.activeStreams, streamKey),
          activeStreamStartedAt,
          recoveredStreams: _removeStream(state.recoveredStreams, streamKey),
          toolCalls: [],
          activeReasoningByMsg: _withoutKey(state.activeReasoningByMsg, streamKey),
          localCallsByConv: _withoutKey(state.localCallsByConv, streamKey),
        };
      });
    };

    try {
      // localCalls is a mutable reference into the per-conversation bucket in state
      const localCalls: ToolCallEntry[] = get().localCallsByConv[streamKey] ?? [];
      set((state) => ({
        localCallsByConv: { ...state.localCallsByConv, [streamKey]: localCalls },
      }));

      // Apply an upsert to the shared localCalls array in place so the
      // reference stored in state.localCallsByConv[streamKey] keeps seeing
      // the updated contents (existing pattern: localCalls is aliased into
      // state, and set() is only used to trigger subscribers).
      const _applyLocal = (entry: UpsertToolCallInput): void => {
        const next = upsertToolCall(localCalls, entry);
        localCalls.length = 0;
        for (const tc of next) localCalls.push(tc);
      };

      // For a tool_call SSE event (which carries only `call_id`), locate an
      // unreconciled pending entry that was pushed earlier by an
      // approval_required event so we can reconcile it by its `requestId`
      // without ever using toolName+status as an upsert key (which was the
      // root cause of the duplicate-callID bug).
      const _findUnreconciledPending = (
        list: readonly ToolCallEntry[],
        toolName: string,
      ): ToolCallEntry | undefined =>
        list.find(
          (tc) => tc.toolName === toolName && tc.status === "pending" && !tc.callID,
        );

      await chatApi.sendSSE(content, convId, {
        onReasoning: (text: string) => {
          if (!isStillHere()) return;
          set((state) => ({
            activeReasoningByMsg: {
              ...state.activeReasoningByMsg,
              [streamKey]: (state.activeReasoningByMsg[streamKey] || "") + text,
            },
          }));
        },
        onToolCall: (toolName: string, toolArgs: Record<string, unknown>, callId: string) => {
          if (!isStillHere()) return;

          // state.toolCalls: upsert by callID; if an approval-originated
          // pending entry exists, inherit its requestId so upsertToolCall
          // reconciles the same entry (priority 2) instead of appending.
          set((state) => {
            const prior = _findUnreconciledPending(state.toolCalls, toolName);
            const entry: UpsertToolCallInput = {
              toolName,
              status: "running",
              command: getToolInputCommand(toolArgs),
              callID: callId,
              ...(prior?.requestId ? { requestId: prior.requestId } : {}),
            };
            return { toolCalls: upsertToolCall(state.toolCalls, entry) };
          });

          // localCalls: preserve the UNFIXED Observe 2 quirk — when a
          // pending approval entry exists, flip it to running WITHOUT
          // stamping the callID onto the localCalls copy. Only the
          // state.toolCalls path carries the callID in that scenario.
          const priorLocal = _findUnreconciledPending(localCalls, toolName);
          if (priorLocal) {
            _applyLocal({
              toolName,
              status: "running",
              command: getToolInputCommand(toolArgs),
              ...(priorLocal.requestId ? { requestId: priorLocal.requestId } : {}),
            });
          } else {
            _applyLocal({
              toolName,
              status: "running",
              command: getToolInputCommand(toolArgs),
              callID: callId,
            });
          }
        },
        onToolResult: (toolName: string, callId: string, toolState?: ToolState, toolMeta?: ToolMetadata) => {
          if (!isStillHere()) return;

          // state.toolCalls: upsert by callID, transitioning to done and
          // merging in state/metadata.
          set((s) => ({
            toolCalls: upsertToolCall(s.toolCalls, {
              toolName,
              status: "done",
              callID: callId,
              state: toolState,
              metadata: toolMeta,
            }),
          }));

          // localCalls: preserve the Observe 2 quirk — an approval-originated
          // running entry (requestId but no callID) must transition to done
          // by requestId, without gaining callID/state/metadata on the
          // localCalls copy.
          const runningApproval = localCalls.find(
            (tc) =>
              tc.toolName === toolName &&
              tc.status === "running" &&
              !tc.callID &&
              !!tc.requestId,
          );
          if (runningApproval?.requestId) {
            _applyLocal({
              toolName,
              status: "done",
              requestId: runningApproval.requestId,
            });
          } else {
            _applyLocal({
              toolName,
              status: "done",
              callID: callId,
              command: getToolInputCommand(toolState?.input),
              state: toolState,
              metadata: toolMeta,
            });
          }
        },
        onSubAgentStart: (parentCallId: string) => {
          if (!isStillHere()) return;
          // Initialize subCalls array on the parent tool call. Mirror the
          // pre-fix asymmetry: localCalls resets subCalls to [] when the
          // parent exists; state.toolCalls only initializes when undefined.
          const parentIdx = localCalls.findIndex((tc) => tc.callID === parentCallId);
          if (parentIdx !== -1) {
            localCalls[parentIdx] = { ...localCalls[parentIdx], subCalls: [] };
          }
          set((s) => ({
            toolCalls: s.toolCalls.map((tc) =>
              tc.callID === parentCallId ? { ...tc, subCalls: tc.subCalls ?? [] } : tc
            ),
          }));
        },
        onSubAgentToolCall: (parentCallId: string, subToolName: string, subCallId: string) => {
          if (!isStillHere()) return;
          const subEntry: UpsertToolCallInput = {
            toolName: subToolName,
            status: "running",
            callID: subCallId,
          };
          // localCalls: upsert the sub-call onto parent.subCalls by callID.
          const parentIdx = localCalls.findIndex((tc) => tc.callID === parentCallId);
          if (parentIdx !== -1) {
            const parent = localCalls[parentIdx];
            localCalls[parentIdx] = {
              ...parent,
              subCalls: upsertToolCall(parent.subCalls ?? [], subEntry),
            };
          }
          set((s) => ({
            toolCalls: s.toolCalls.map((tc) =>
              tc.callID === parentCallId
                ? { ...tc, subCalls: upsertToolCall(tc.subCalls ?? [], subEntry) }
                : tc
            ),
          }));
        },
        onSubAgentToolResult: (parentCallId: string, subToolName: string, subCallId: string, subState?: ToolState, subMeta?: ToolMetadata) => {
          if (!isStillHere()) return;
          const subEntry: UpsertToolCallInput = {
            toolName: subToolName,
            status: "done",
            callID: subCallId,
            state: subState,
            metadata: subMeta,
          };
          const parentIdx = localCalls.findIndex((tc) => tc.callID === parentCallId);
          if (parentIdx !== -1) {
            const parent = localCalls[parentIdx];
            localCalls[parentIdx] = {
              ...parent,
              subCalls: upsertToolCall(parent.subCalls ?? [], subEntry),
            };
          }
          set((s) => ({
            toolCalls: s.toolCalls.map((tc) =>
              tc.callID === parentCallId
                ? { ...tc, subCalls: upsertToolCall(tc.subCalls ?? [], subEntry) }
                : tc
            ),
          }));
        },
        onSubAgentDone: (parentCallId: string) => {
          if (!isStillHere()) return;
          // Mark parent tool call as done when sub-agent completes
          const parentIdx = localCalls.findIndex((tc) => tc.callID === parentCallId);
          if (parentIdx !== -1 && localCalls[parentIdx].status === "running") {
            localCalls[parentIdx] = { ...localCalls[parentIdx], status: "done" };
          }
          set((s) => ({
            toolCalls: s.toolCalls.map((tc) =>
              tc.callID === parentCallId && tc.status === "running"
                ? { ...tc, status: "done" }
                : tc
            ),
          }));
        },
        onApprovalRequired: (
          requestId: string,
          toolName: string,
          toolArgs: Record<string, unknown>,
        ): Promise<boolean> => {
          return new Promise((resolve) => {
            if (!isStillHere()) {
              resolve(false);
              return;
            }
            const entry: ToolCallEntry = {
              toolName,
              status: "pending",
              command: String(toolArgs.command ?? ""),
              requestId,
            };
            // Upsert (not push) so two approval_required events with the
            // same requestId can't produce duplicate entries.
            _applyLocal(entry);
            set((state) => ({
              approvalQueue: {
                ...state.approvalQueue,
                [requestId]: {
                  requestId,
                  toolName,
                  toolArgs,
                  resolve,
                },
              },
              toolCalls: upsertToolCall(state.toolCalls, entry),
            }));
          });
        },
        onIterationDone: (messageId: number, msg: AssistantMsg) => {
          if (!isStillHere()) {
            // Conversation switched away mid-stream: don't append to
            // `messages` (that belongs to the user's currently-viewed
            // conversation), but still mark the origin conversation as
            // unread. We intentionally leave per-stream state cleanup to
            // `onDone`, which runs once at the end of the turn.
            set((state) => {
              const updated = new Set(state.unreadIds);
              if (convId !== null) updated.add(convId);
              return { unreadIds: updated };
            });
            return;
          }

          const replyMsg = assistantMessageFromIteration(convId ?? 0, messageId, msg);

          // Append the iteration as a new Message and reset the per-iteration
          // realtime buffers so the next iteration's reasoning / tool_call
          // events start from a clean slate. Note: we clear the reasoning
          // bucket for this streamKey (not the whole record) and reset the
          // top-level `toolCalls` list — `localCallsByConv[streamKey]` is kept
          // as the per-conversation bucket for the remaining iterations on
          // this turn; it's cleared in `onDone`.
          set((state) => ({
            messages: state.messages.some((message) => message.id === messageId)
              ? state.messages
              : [...state.messages, replyMsg],
            toolCalls: [],
            activeReasoningByMsg: {
              ...state.activeReasoningByMsg,
              [streamKey]: "",
            },
          }));
        },
        onDone: (conversationId: number) => {
          const shouldMaterializeDraft =
            isDraftConversation && draftSessionAtStart === draftSessionSeq;
          completedConversationId = !isDraftConversation || shouldMaterializeDraft
            ? conversationId
            : null;
          // Per-iteration persistence and UI append are handled by
          // `onIterationDone`. `onDone` is now pure turn-level cleanup: drop
          // the active stream marker and per-stream buffers, then refresh
          // the sidebar so the conversation title / updated_at reflects the
          // just-finished turn.
          set((state) => ({
            activeConversationId:
              shouldMaterializeDraft && state.activeConversationId === null
                ? conversationId
                : state.activeConversationId,
            activeStreams: _removeStream(state.activeStreams, streamKey),
            activeStreamStartedAt: (() => {
              const activeStreamStartedAt = _withoutKey(state.activeStreamStartedAt, streamKey);
              persistActiveStreamStartedAt(activeStreamStartedAt);
              return activeStreamStartedAt;
            })(),
            recoveredStreams: _removeStream(state.recoveredStreams, streamKey),
            toolCalls: [],
            activeReasoningByMsg: _withoutKey(state.activeReasoningByMsg, streamKey),
            localCallsByConv: _withoutKey(state.localCallsByConv, streamKey),
          }));

          get().loadConversations();
        },
        onError: (errorMsg: string) => {
          streamHadError = true;
          stopStream();
          set({ error: errorMsg });
        },
      }, activeModelId, draftWorkspaceRoot);
      return streamHadError ? null : completedConversationId;
    } catch {
      if (streamKey > 0) {
        set((state) => ({
          recoveredStreams: _addStream(state.recoveredStreams, streamKey),
        }));
        persistActiveStreamStartedAt(useChatStore.getState().activeStreamStartedAt);
      } else {
        stopStream();
      }
      set({ error: "发送消息失败" });
      return null;
    }
  },

  resolveApproval: (requestId: string, approved: boolean) => {
    const { approvalQueue, activeConversationId } = get();
    const approvalRequest = approvalQueue[requestId];
    if (!approvalRequest) return;
    if (approvalRequest.resolve) {
      approvalRequest.resolve(approved);
      chatApi.approve(requestId, approved);
      if (!approved) {
        const convKey = activeConversationId ?? 0;
        // Update store
        set((state) => {
          const convCalls = state.localCallsByConv[convKey];
          let updatedLocalCalls = state.localCallsByConv;
          if (convCalls) {
            const idx = convCalls.findIndex(
              (tc) => tc.requestId === requestId && tc.status === "pending"
            );
            if (idx !== -1) {
              const updated = [...convCalls];
              updated[idx] = { ...updated[idx], status: "error" };
              updatedLocalCalls = { ...state.localCallsByConv, [convKey]: updated };
            }
          }
          return {
            approvalQueue: _withoutKey(state.approvalQueue, requestId),
            toolCalls: state.toolCalls.map((tc) =>
              tc.requestId === requestId && tc.status === "pending"
                ? { ...tc, status: "error" }
                : tc
            ),
            localCallsByConv: updatedLocalCalls,
          };
        });
      } else {
        set((state) => {
          return { approvalQueue: _withoutKey(state.approvalQueue, requestId) };
        });
      }
      return;
    }
    void chatApi.approve(requestId, approved);
    const convKey = activeConversationId ?? 0;
    set((state) => {
      const convCalls = state.localCallsByConv[convKey];
      let updatedLocalCalls = state.localCallsByConv;
      if (convCalls) {
        const idx = convCalls.findIndex((tc) => tc.requestId === requestId && tc.status === "pending");
        if (idx !== -1) {
          const updated = [...convCalls];
          updated[idx] = { ...updated[idx], status: approved ? "running" : "error" };
          updatedLocalCalls = { ...state.localCallsByConv, [convKey]: updated };
        }
      }
      return {
        approvalQueue: _withoutKey(state.approvalQueue, requestId),
        toolCalls: state.toolCalls.map((tc) =>
          tc.requestId === requestId && tc.status === "pending"
            ? { ...tc, status: approved ? "running" : "error" }
            : tc
        ),
        localCallsByConv: updatedLocalCalls,
      };
    });
  },

  setSidebarOpen: (open: boolean) => set({ sidebarOpen: open }),
  setActiveModelId: (modelId: string | null) => set({ activeModelId: modelId }),
  setDraftWorkspaceRoot: (workspaceRoot: string | null) =>
    set({ draftWorkspaceRoot: workspaceRoot || null, error: null }),
  selectWorkspaceFolder: async () => {
    try {
      const { data } = await workspacesApi.selectFolder();
      if (data.path) {
        set({ draftWorkspaceRoot: data.path, error: null });
      }
    } catch {
      set({ error: "选择工作区失败" });
    }
  },

  loadMoreConversations: async () => {
    const { conversations } = get();
    try {
      const { data, total } = await conversationsApi.list({ skip: conversations.length, limit: CONVERSATIONS_LIMIT });
      set((state) => {
        const merged = [...state.conversations, ...data];
        return { conversations: merged, hasMoreConversations: merged.length < total };
      });
    } catch {
      set({ error: "加载更多会话失败" });
    }
  },

  loadMoreMessages: async () => {
    const { activeConversationId, messages } = get();
    if (!activeConversationId) return;
    try {
      const { data, total } = await conversationsApi.getMessages(activeConversationId, {
        skip: messages.length,
        limit: MESSAGES_LIMIT,
      });
      if (get().activeConversationId !== activeConversationId) {
        return;
      }
      const olderMessages = mapMessagesForDisplay(data);
      set((state) => {
        const merged = sortMessagesForDisplay([...olderMessages, ...state.messages]);
        return { messages: merged, hasMoreMessages: merged.length < total };
      });
    } catch {
      set({ error: "加载更多消息失败" });
    }
  },

  refreshActiveConversationMessages: async () => {
    const { activeConversationId } = get();
    if (!activeConversationId) return;

    try {
      const { data, total } = await conversationsApi.getMessages(activeConversationId, {
        limit: Math.max(MESSAGES_LIMIT, get().messages.length || MESSAGES_LIMIT),
      });
      if (get().activeConversationId !== activeConversationId) {
        return;
      }
      const refreshedMessages = mapMessagesForDisplay(data);
      set({
        messages: refreshedMessages,
        hasMoreMessages: refreshedMessages.length < total,
      });
    } catch {
      set({ error: "刷新消息失败" });
    }
  },

  subscribeRecoveredConversationEvents: async (conversationId: number, signal: AbortSignal) => {
    const streamKey = conversationId;
    const isStillHere = () => get().activeConversationId === conversationId;

    try {
      await chatApi.streamConversationEvents(conversationId, {
        onReasoning: (text: string) => {
          if (!isStillHere()) return;
          set((state) => ({
            activeReasoningByMsg: {
              ...state.activeReasoningByMsg,
              [streamKey]: (state.activeReasoningByMsg[streamKey] || "") + text,
            },
          }));
        },
        onToolCall: (toolName: string, toolArgs: Record<string, unknown>, callId: string) => {
          if (!isStillHere()) return;
          set((state) => {
            const prior = state.toolCalls.find(
              (tc) => tc.toolName === toolName && tc.status === "pending" && !tc.callID,
            );
            const entry: UpsertToolCallInput = {
              toolName,
              status: "running",
              command: getToolInputCommand(toolArgs),
              callID: callId,
              ...(prior?.requestId ? { requestId: prior.requestId } : {}),
            };
            return { toolCalls: upsertToolCall(state.toolCalls, entry) };
          });
        },
        onToolResult: (toolName: string, callId: string, toolState?: ToolState, toolMeta?: ToolMetadata) => {
          if (!isStillHere()) return;
          set((state) => ({
            toolCalls: upsertToolCall(state.toolCalls, {
              toolName,
              status: "done",
              callID: callId,
              command: getToolInputCommand(toolState?.input),
              state: toolState,
              metadata: toolMeta,
            }),
          }));
        },
        onSubAgentStart: (parentCallId: string) => {
          if (!isStillHere()) return;
          set((state) => ({
            toolCalls: state.toolCalls.map((tc) =>
              tc.callID === parentCallId ? { ...tc, subCalls: tc.subCalls ?? [] } : tc
            ),
          }));
        },
        onSubAgentToolCall: (parentCallId: string, subToolName: string, subCallId: string) => {
          if (!isStillHere()) return;
          const subEntry: UpsertToolCallInput = {
            toolName: subToolName,
            status: "running",
            callID: subCallId,
          };
          set((state) => ({
            toolCalls: state.toolCalls.map((tc) =>
              tc.callID === parentCallId
                ? { ...tc, subCalls: upsertToolCall(tc.subCalls ?? [], subEntry) }
                : tc
            ),
          }));
        },
        onSubAgentToolResult: (
          parentCallId: string,
          subToolName: string,
          subCallId: string,
          subState?: ToolState,
          subMeta?: ToolMetadata,
        ) => {
          if (!isStillHere()) return;
          const subEntry: UpsertToolCallInput = {
            toolName: subToolName,
            status: "done",
            callID: subCallId,
            state: subState,
            metadata: subMeta,
          };
          set((state) => ({
            toolCalls: state.toolCalls.map((tc) =>
              tc.callID === parentCallId
                ? { ...tc, subCalls: upsertToolCall(tc.subCalls ?? [], subEntry) }
                : tc
            ),
          }));
        },
        onSubAgentDone: (parentCallId: string) => {
          if (!isStillHere()) return;
          set((state) => ({
            toolCalls: state.toolCalls.map((tc) =>
              tc.callID === parentCallId && tc.status === "running"
                ? { ...tc, status: "done" }
                : tc
            ),
          }));
        },
        onApprovalRequired: async (
          requestId: string,
          toolName: string,
          toolArgs: Record<string, unknown>,
        ) => {
          if (!isStillHere()) return false;
          const entry: ToolCallEntry = {
            toolName,
            status: "pending",
            command: String(toolArgs.command ?? ""),
            requestId,
          };
          set((state) => ({
            approvalQueue: {
              ...state.approvalQueue,
              [requestId]: {
                requestId,
                toolName,
                toolArgs,
                resolve: null,
              },
            },
            toolCalls: upsertToolCall(state.toolCalls, entry),
          }));
          return false;
        },
        onIterationDone: (messageId: number, msg: AssistantMsg) => {
          if (!isStillHere()) return;
          const replyMsg = assistantMessageFromIteration(conversationId, messageId, msg);
          set((state) => ({
            messages: state.messages.some((message) => message.id === messageId)
              ? state.messages
              : [...state.messages, replyMsg],
            toolCalls: [],
            activeReasoningByMsg: {
              ...state.activeReasoningByMsg,
              [streamKey]: "",
            },
          }));
        },
        onDone: () => {
          if (!isStillHere()) return;
          set((state) => {
            const activeStreamStartedAt = _withoutKey(state.activeStreamStartedAt, streamKey);
            persistActiveStreamStartedAt(activeStreamStartedAt);
            return {
              activeStreams: _removeStream(state.activeStreams, streamKey),
              activeStreamStartedAt,
              recoveredStreams: _removeStream(state.recoveredStreams, streamKey),
              toolCalls: [],
              activeReasoningByMsg: _withoutKey(state.activeReasoningByMsg, streamKey),
              localCallsByConv: _withoutKey(state.localCallsByConv, streamKey),
            };
          });
          void get().loadConversations();
          void get().refreshActiveConversationMessages();
        },
        onError: (errorMsg: string) => {
          if (signal.aborted) return;
          set({ error: errorMsg });
        },
      }, signal);
    } catch (error) {
      if (!signal.aborted) {
        set({ error: error instanceof Error ? error.message : "恢复事件流失败" });
      }
    }
  },
}));
