import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { useChatStore } from "@/stores/chat-store";
import { chatApi, conversationsApi, type SSECallbacks } from "@/lib/api-client";

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>(
    "@/lib/api-client",
  );
  return {
    ...actual,
    chatApi: {
      sendSSE: vi.fn(),
      streamConversationEvents: vi.fn(),
      approve: vi.fn(),
    },
    conversationsApi: {
      list: vi.fn().mockResolvedValue({ data: [], total: 0 }),
      create: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
      getMessages: vi.fn(),
    },
  };
});

function resetStore(): void {
  useChatStore.setState({
    conversations: [],
    activeConversationId: null,
    messages: [],
    activeStreams: [],
    activeStreamStartedAt: {},
    recoveredStreams: [],
    error: null,
    toolCalls: [],
    approvalQueue: {},
    unreadIds: new Set<number>(),
    activeReasoningByMsg: {},
    localCallsByConv: {},
    optimisticIdByConv: {},
    hasMoreConversations: false,
    hasMoreMessages: false,
    draftWorkspaceRoot: null,
  });
  (chatApi.sendSSE as unknown as Mock).mockReset();
  (chatApi.streamConversationEvents as unknown as Mock).mockReset();
  (conversationsApi.list as unknown as Mock).mockResolvedValue({ data: [], total: 0 });
  (conversationsApi.create as unknown as Mock).mockReset();
  window.localStorage.clear();
}

describe("chat-store new chat flow", () => {
  beforeEach(() => {
    resetStore();
  });

  it("enters a blank new-chat surface without creating a conversation", () => {
    useChatStore.setState({
      activeConversationId: 7,
      messages: [
        {
          id: 1,
          conversation_id: 7,
          msg_type: "user",
          msg_json: {},
          created_at: "2026-01-01T00:00:00.000Z",
          parts: [],
          content: "previous",
        },
      ],
      error: "old error",
      hasMoreMessages: true,
    });

    useChatStore.getState().startNewChat();

    expect(conversationsApi.create).not.toHaveBeenCalled();
    expect(useChatStore.getState()).toMatchObject({
      activeConversationId: null,
      messages: [],
      error: null,
      toolCalls: [],
      approvalQueue: {},
      hasMoreMessages: false,
    });
  });

  it("creates the real conversation only when the first draft message is sent", async () => {
    let sawDraftStream = false;
    (chatApi.sendSSE as unknown as Mock).mockImplementationOnce(
      async (
        _message: string,
        conversationId: number | null,
        callbacks: SSECallbacks,
      ) => {
        expect(conversationId).toBeNull();
        sawDraftStream = useChatStore.getState().activeStreams.includes(0);
        callbacks.onDone?.(42, [], {});
      },
    );

    await useChatStore.getState().sendMessage("hello");

    expect(sawDraftStream).toBe(true);
    expect(conversationsApi.create).not.toHaveBeenCalled();
    expect(chatApi.sendSSE).toHaveBeenCalledWith(
      "hello",
      null,
      expect.any(Object),
      null,
      null,
    );
    expect(useChatStore.getState().activeConversationId).toBe(42);
    expect(useChatStore.getState().activeStreams).not.toContain(0);
  });

  it("passes the draft workspace when creating and sending a new chat", async () => {
    useChatStore.getState().setDraftWorkspaceRoot("G:\\workspace");
    (conversationsApi.create as unknown as Mock).mockResolvedValueOnce({
      data: {
        id: 42,
        title: "新会话",
        source: "chat",
        workspace_root: "G:\\workspace",
        created_at: "2026-01-01T00:00:00.000Z",
        updated_at: "2026-01-01T00:00:00.000Z",
      },
    });
    (chatApi.sendSSE as unknown as Mock).mockImplementationOnce(
      async (
        _message: string,
        _conversationId: number | null,
        callbacks: SSECallbacks,
      ) => {
        callbacks.onDone?.(42, [], {});
      },
    );

    const createdConversationId = await useChatStore.getState().createConversation();
    await useChatStore.getState().sendMessage("hello");

    expect(createdConversationId).toBe(42);
    expect(conversationsApi.create).toHaveBeenCalledWith("新会话", "G:\\workspace");
    expect(chatApi.sendSSE).toHaveBeenCalledWith(
      "hello",
      42,
      expect.any(Object),
      null,
      "G:\\workspace",
    );
  });

  it("does not restore an old conversation after New Chat while that old stream finishes", async () => {
    useChatStore.setState({ activeConversationId: 7 });
    (chatApi.sendSSE as unknown as Mock).mockImplementationOnce(
      async (
        _message: string,
        _conversationId: number | null,
        callbacks: SSECallbacks,
      ) => {
        useChatStore.getState().startNewChat();
        callbacks.onDone?.(7, [], {});
      },
    );

    await useChatStore.getState().sendMessage("still running");

    expect(useChatStore.getState().activeConversationId).toBeNull();
    expect(useChatStore.getState().messages).toEqual([]);
  });

  it("does not materialize an abandoned draft after New Chat while the draft stream finishes", async () => {
    (chatApi.sendSSE as unknown as Mock).mockImplementationOnce(
      async (
        _message: string,
        _conversationId: number | null,
        callbacks: SSECallbacks,
      ) => {
        useChatStore.getState().startNewChat();
        callbacks.onDone?.(42, [], {});
      },
    );

    const completedConversationId = await useChatStore.getState().sendMessage("draft");

    expect(completedConversationId).toBeNull();
    expect(useChatStore.getState().activeConversationId).toBeNull();
    expect(useChatStore.getState().messages).toEqual([]);
    expect(useChatStore.getState().activeStreams).not.toContain(0);
  });

  it("keeps a real conversation recoverable when the transport stream is interrupted", async () => {
    useChatStore.setState({ activeConversationId: 42 });
    (chatApi.sendSSE as unknown as Mock).mockRejectedValueOnce(new Error("aborted"));

    const completedConversationId = await useChatStore.getState().sendMessage("keep working");

    expect(completedConversationId).toBeNull();
    expect(useChatStore.getState().activeStreams).toContain(42);
    expect(useChatStore.getState().recoveredStreams).toContain(42);
    expect(useChatStore.getState().activeStreamStartedAt[42]).toEqual(expect.any(Number));
    expect(window.localStorage.getItem("cc-chat-active-streams-v1")).toContain("42");
  });
});
