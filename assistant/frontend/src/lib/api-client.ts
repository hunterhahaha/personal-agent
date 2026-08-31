import axios from "axios";

const API_BASE = process.env.NODE_ENV === "development"
  ? "http://localhost:8003/api"
  : "/api";

const api = axios.create({
  baseURL: API_BASE,
  headers: { "Content-Type": "application/json" },
  timeout: 300000, // 5 minutes for long LLM reasoning
});

// ---- Types ----

export type ToolStatus = "running" | "done" | "error" | "pending";

export interface ToolState {
  status: string;
  input: Record<string, unknown>;
  output: Record<string, unknown> | null;
  summary: string;
  error?: string;
  [key: string]: unknown;
}

export interface ToolMetadata {
  duration_ms: number;
  truncated: boolean;
  approval_required: boolean;
  approval_granted: boolean | null;
  provider: string;
  extra: Record<string, unknown>;
}

export interface PartText {
  type: "text" | "reasoning" | "thought";
  text: string;
  time?: { start: number; end: number } | null;
  id: string;
  sessionID: string;
  messageID: string;
}

export interface PartToolCall {
  type: "toolcall";
  tool: string;
  callID: string;
  state: ToolState;
  metadata: ToolMetadata;
  id: string;
  sessionID: string;
  messageID: string;
}

/** Union of all possible message part types */
export type MsgPart = PartText | PartToolCall;

/**
 * AssistantMsg envelope — the persistence unit for a single LLM iteration.
 *
 * Backend emits one of these per `iteration_done` SSE event; each corresponds
 * to exactly one LLM call (i.e. one `AssistantMsg` DB row). The `parts` array
 * preserves the production order of reasoning / text / toolcall blocks within
 * that single iteration — iteration boundaries are no longer flattened.
 */
export interface AssistantMsg {
  message: {
    parentID?: string;
    role: "assistant";
    mode?: string;
    agent?: string;
    variant?: string;
    path?: { cwd: string; root: string };
    cost?: number;
    token?: Record<string, unknown>;
    modelID?: string;
    providerID?: string;
    time?: { start: number; end: number };
    finish?: string;
    id: string;
    sessionID: string;
    [key: string]: unknown;
  };
  parts: MsgPart[];
}

export interface ToolCallEntry {
  toolName: string;
  status: ToolStatus;
  command?: string;
  requestId?: string;
  callID?: string;
  state?: ToolState;
  metadata?: ToolMetadata;
  /** Sub-agent tool calls nested under this parent tool call */
  subCalls?: ToolCallEntry[];
}

export interface Tool {
  id: number;
  tool_id: string;
  name: string;
  description: string;
  category: string;
  enabled: boolean;
  provider: string;
  source: string;
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  config: Record<string, unknown>;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface Skill {
  id: string;
  name: string;
  description: string;
  enabled: boolean;
  tags: string[];
}

export interface PromptTemplate {
  id: number;
  prompt_id: string;
  name: string;
  type: string;
  version: string;
  enabled: boolean;
  created_by: string;
  description: string;
  content: string;
  draft_content?: string | null;
  version_history?: VersionEntry[] | null;
  metadata_json: Record<string, unknown>;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface VersionEntry {
  version: string;
  content: string;
  created_by: string;
  created_at: string;
}

export interface SubAgentBlueprint {
  id: number;
  blueprint_id: string;
  name: string;
  description: string;
  enabled: boolean;
  tool_ids: string[];
  prompt_template_ids: string[];
  input_schema: Record<string, unknown>;
  output_schema: Record<string, unknown>;
  memory_policy_id: string | null;
  tags: string[];
  created_at: string;
  updated_at: string;
}

export interface Task {
  id: number;
  task_id: string;
  name: string;
  description: string;
  enabled: boolean;
  cron_expr: string | null;
  run_at: string | null;
  recurring: boolean;
  created_at: string;
  updated_at: string;
}

export interface TaskRun {
  id: number;
  task_id: string;
  status: string;
  started_at: string;
  finished_at: string | null;
  result: string | null;
  error: string | null;
  logs: string[];
  conversation_id: number | null;
  created_at: string;
}

export interface Conversation {
  id: number;
  title: string;
  type?: string;
  source?: string;
  workspace_root?: string | null;
  created_at: string;
  updated_at: string;
}

export interface Message {
  id: number;
  conversation_id: number;
  msg_type: string;  // "user" | "assistant"
  msg_json: Record<string, unknown>;
  created_at: string;
  // Structured parts — first-class citizen for rendering
  parts: MsgPart[];
  // Derived for backward compatibility:
  role?: string;
  content?: string;
  toolCalls?: ToolCallEntry[];
}

export interface ChatResponse {
  reply: string;
  conversation_id: number;
  message_id: number;
}

// ---- Pagination ----

export interface PaginationParams {
  skip?: number;
  limit?: number;
}

export interface PaginatedResult<T> {
  data: T[];
  total: number;
}

// ---- Generic API Factory ----

function createEntityApi<T>(basePath: string) {
  return {
    list: (params?: PaginationParams) =>
      api.get<T[]>(basePath, { params }),
    get: (id: string) => api.get<T>(`${basePath}/${id}`),
    toggle: (id: string) => api.post<T>(`${basePath}/${id}/toggle`),
  };
}

// ---- API Functions ----

export const toolsApi = {
  ...createEntityApi<Tool>("/tools"),
  /** List only active tools (filters out disabled builtins on the client side). */
  listActive: async (params?: PaginationParams) => {
    const response = await api.get<Tool[]>("/tools", { params });
    return {
      ...response,
      data: response.data.filter(
        (t) => !(t.source === "builtin" && !t.enabled)
      ),
    };
  },
};

export const skillsApi = {
  list: () => api.get<Skill[]>("/skills"),
  toggle: (id: string) => api.post(`/skills/${id}/toggle`),
};

export const promptsApi = {
  ...createEntityApi<PromptTemplate>("/prompts"),
  create: (data: Partial<PromptTemplate>) =>
    api.post<PromptTemplate>("/prompts", data),
  update: (promptId: string, data: Partial<PromptTemplate>) =>
    api.put<PromptTemplate>(`/prompts/${promptId}`, data),
  saveDraft: (promptId: string, draftContent: string) =>
    api.post<PromptTemplate>(`/prompts/${promptId}/draft`, { draft_content: draftContent }),
  publish: (promptId: string, draftContent?: string) =>
    api.post<PromptTemplate>(`/prompts/${promptId}/publish`, draftContent ? { draft_content: draftContent } : {}),
  rollback: (promptId: string) =>
    api.post<PromptTemplate>(`/prompts/${promptId}/rollback`),
};


export const blueprintsApi = {
  ...createEntityApi<SubAgentBlueprint>("/blueprints"),
  create: (data: Partial<SubAgentBlueprint>) =>
    api.post<SubAgentBlueprint>("/blueprints", data),
  update: (blueprintId: string, data: Partial<SubAgentBlueprint>) =>
    api.put<SubAgentBlueprint>(`/blueprints/${blueprintId}`, data),
  remove: (blueprintId: string) => api.delete(`/blueprints/${blueprintId}`),
};

export const tasksApi = {
  ...createEntityApi<Task>("/tasks"),
  create: (data: Partial<Task>) => api.post<Task>("/tasks", data),
  update: (taskId: string, data: Partial<Task>) => api.put<Task>(`/tasks/${taskId}`, data),
  remove: (taskId: string) => api.delete(`/tasks/${taskId}`),
  run: (id: string) => api.post<TaskRun>(`/tasks/${id}/run`),
  runs: (taskId: string) => api.get<TaskRun[]>(`/tasks/${taskId}/runs`),
  allRuns: (params?: PaginationParams) => api.get<TaskRun[]>("/tasks/runs/history", { params }),
};

// Conversations
export const CONVERSATIONS_LIMIT = 30;
export const MESSAGES_LIMIT = 50;

export const conversationsApi = {
  list: async (params?: PaginationParams): Promise<PaginatedResult<Conversation>> => {
    const response = await api.get<Conversation[]>("/conversations", {
      params: { limit: CONVERSATIONS_LIMIT, ...params },
    });
    const total = parseInt(response.headers["x-total-count"] || "0", 10);
    return { data: response.data, total };
  },
  create: (title: string, workspaceRoot?: string | null) =>
    api.post<Conversation>("/conversations", {
      title,
      workspace_root: workspaceRoot || undefined,
    }),
  update: (id: number, title: string) =>
    api.put<Conversation>(`/conversations/${id}`, { title }),
  delete: (id: number) => api.delete(`/conversations/${id}`),
  getMessages: async (
    conversationId: number,
    params?: PaginationParams
  ): Promise<PaginatedResult<Message>> => {
    const response = await api.get<Message[]>(`/conversations/${conversationId}/messages`, {
      params: { limit: MESSAGES_LIMIT, ...params },
    });
    const total = parseInt(response.headers["x-total-count"] || "0", 10);
    return { data: response.data, total };
  },
};

// Chat (SSE stream)

export interface SSECallbacks {
  onReasoning?: (text: string) => void;
  onToolCall?: (toolName: string, toolArgs: Record<string, unknown>, callId: string) => void;
  onToolResult?: (
    toolName: string,
    callId: string,
    state?: ToolState,
    metadata?: ToolMetadata,
  ) => void;
  onApprovalRequired?: (
    requestId: string,
    toolName: string,
    toolArgs: Record<string, unknown>
  ) => Promise<boolean>;
  /** Sub-agent lifecycle events */
  onSubAgentStart?: (parentCallId: string, agentName: string) => void;
  onSubAgentToolCall?: (parentCallId: string, toolName: string, callId: string) => void;
  onSubAgentToolResult?: (parentCallId: string, toolName: string, callId: string, state?: ToolState, metadata?: ToolMetadata) => void;
  onSubAgentDone?: (parentCallId: string) => void;
  /**
   * Fired once per `iteration_done` SSE event — one per LLM iteration.
   *
   * The backend persists the `AssistantMsg` to DB before emitting this event,
   * so `messageId` is the real DB row id. Listeners should append one
   * assistant-role `Message` per invocation to support multi-iteration
   * rendering (see design.md §5 / requirement 2.6).
   */
  onIterationDone?: (messageId: number, msg: AssistantMsg) => void;
  /**
   * Fired once at the end of the whole turn.
   *
   * Per the `iteration_done` redesign, `done` no longer carries the final
   * reply text or a single `msg`; it only delivers turn-level summary info:
   * the conversation id, the ordered list of DB message ids persisted during
   * the turn (one per iteration), and aggregated token usage.
   */
  onDone?: (
    conversationId: number,
    messageIds: number[],
    tokenUsage: Record<string, unknown>,
  ) => void;
  onError?: (message: string) => void;
}

async function readSSEStream(response: Response, callbacks: SSECallbacks): Promise<void> {
  const reader = response.body?.getReader();
  if (!reader) {
    callbacks.onError?.("No response stream");
    return;
  }

  const decoder = new TextDecoder();
  let buffer = "";
  let currentEvent = "";

  const dispatchSSEData = async (dataStr: string) => {
    try {
      const data = JSON.parse(dataStr);
      switch (currentEvent) {
        case "reasoning":
          callbacks.onReasoning?.(data.text as string);
          break;
        case "tool_call":
          callbacks.onToolCall?.(
            data.tool_name as string,
            data.tool_args as Record<string, unknown>,
            (data.call_id as string) || "",
          );
          break;
        case "tool_result":
          callbacks.onToolResult?.(
            data.tool_name as string,
            (data.call_id as string) || "",
            data.state as ToolState | undefined,
            data.metadata as ToolMetadata | undefined,
          );
          break;
        case "approval_required":
          if (callbacks.onApprovalRequired) {
            await callbacks.onApprovalRequired(
              data.request_id as string,
              data.tool_name as string,
              data.tool_args as Record<string, unknown>,
            );
          }
          break;
        case "sub_agent_start":
          callbacks.onSubAgentStart?.(
            data.parent_call_id as string,
            (data.agent_name ?? data.blueprint_name ?? data.blueprint_id ?? "") as string,
          );
          break;
        case "sub_agent_tool_call":
          callbacks.onSubAgentToolCall?.(
            data.parent_call_id as string,
            data.tool_name as string,
            data.call_id as string,
          );
          break;
        case "sub_agent_tool_result":
          callbacks.onSubAgentToolResult?.(
            data.parent_call_id as string,
            data.tool_name as string,
            data.call_id as string,
            data.state as ToolState | undefined,
            data.metadata as ToolMetadata | undefined,
          );
          break;
        case "sub_agent_done":
          callbacks.onSubAgentDone?.(
            data.parent_call_id as string,
          );
          break;
        case "iteration_done":
          callbacks.onIterationDone?.(
            data.message_id as number,
            data.msg as AssistantMsg,
          );
          break;
        case "done":
          callbacks.onDone?.(
            data.conversation_id as number,
            (data.message_ids as number[] | undefined) ?? [],
            (data.token_usage as Record<string, unknown> | undefined) ?? {},
          );
          break;
        case "error":
          callbacks.onError?.(data.message as string);
          break;
      }
    } catch {
      // Skip malformed JSON in SSE stream
    }
  };

  const processLine = async (line: string) => {
    if (line.startsWith("event: ")) {
      currentEvent = line.slice(7).trim();
      return;
    }
    if (line.startsWith("data: ")) {
      await dispatchSSEData(line.slice(6));
    }
  };

  while (true) {
    const { done, value } = await reader.read();
    if (done) {
      buffer += decoder.decode();
      if (buffer.trim()) {
        await processLine(buffer.trimEnd());
      }
      break;
    }

    buffer += decoder.decode(value, { stream: true });
    const lines = buffer.split("\n");
    buffer = lines.pop() ?? "";

    for (const line of lines) {
      await processLine(line);
    }
  }
}

export const chatApi = {
  async sendSSE(
    message: string,
    conversationId: number | null,
    callbacks: SSECallbacks,
    modelId?: string | null,
    workspaceRoot?: string | null,
  ): Promise<void> {
    const response = await fetch(`${API_BASE}/chat/send`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        message,
        conversation_id: conversationId,
        model_id: modelId || undefined,
        workspace_root: workspaceRoot || undefined,
      }),
    });

    if (!response.ok) {
      callbacks.onError?.(`HTTP ${response.status}`);
      return;
    }

    await readSSEStream(response, callbacks);
  },

  async streamConversationEvents(
    conversationId: number,
    callbacks: SSECallbacks,
    signal?: AbortSignal,
  ): Promise<void> {
    const response = await fetch(`${API_BASE}/conversations/${conversationId}/events`, {
      method: "GET",
      signal,
    });

    if (!response.ok) {
      callbacks.onError?.(`HTTP ${response.status}`);
      return;
    }

    await readSSEStream(response, callbacks);
  },

  approve: (requestId: string, approved: boolean) =>
    api.post("/chat/approve", { request_id: requestId, approved }),
};

export const workspacesApi = {
  selectFolder: () => api.post<{ path: string | null }>("/workspace/select-folder"),
};

export interface ModelConfig {
  id: number;
  uid: string;
  model_id: string;
  name: string;
  base_url: string;
  api_key: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export const modelsApi = {
  list: () => api.get<ModelConfig[]>("/models"),
  create: (model_id: string, name: string, base_url: string, api_key: string) =>
    api.post<ModelConfig>("/models", { model_id, name, base_url, api_key }),
  update: (id: number, data: { name?: string; model_id?: string; base_url?: string; api_key?: string }) =>
    api.put<ModelConfig>(`/models/${id}`, data),
  delete: (id: number) => api.delete(`/models/${id}`),
  activate: (id: number) => api.post<ModelConfig>(`/models/${id}/activate`),
};

// Memory
export interface MemoryItem {
  id: number;
  title: string;
  content: string;
  created_at: string;
  inferred?: boolean;
  confidence?: number;
}

export const memoryApi = {
  list: () => api.get<MemoryItem[]>("/memory"),
  create: (title: string, content: string) =>
    api.post<MemoryItem>("/memory", { title, content }),
  delete: (id: number) => api.delete(`/memory/${id}`),
  confirm: (id: number) => api.patch<MemoryItem>(`/memory/${id}/confirm`),
  reject: (id: number) => api.delete(`/memory/${id}/reject`),
};

export default api;
