import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { ChatPageClient } from "@/components/chat/chat-page-client";
import { chatApi, conversationsApi, modelsApi } from "@/lib/api-client";
import { useChatStore } from "@/stores/chat-store";

const routerMock = vi.hoisted(() => ({
  push: vi.fn(),
  replace: vi.fn(),
}));

vi.mock("next/navigation", () => ({
  useRouter: () => routerMock,
}));

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
      list: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
      getMessages: vi.fn(),
    },
    modelsApi: {
      list: vi.fn(),
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
  });
}

describe("chat route deep links", () => {
  beforeEach(() => {
    vi.useRealTimers();
    resetStore();
    routerMock.push.mockReset();
    routerMock.replace.mockReset();
    Element.prototype.scrollIntoView = vi.fn();
    (chatApi.sendSSE as unknown as Mock).mockReset();
    (chatApi.streamConversationEvents as unknown as Mock).mockReset();
    (chatApi.streamConversationEvents as unknown as Mock).mockResolvedValue(undefined);
    (conversationsApi.list as unknown as Mock).mockResolvedValue({ data: [], total: 0 });
    (conversationsApi.create as unknown as Mock).mockResolvedValue({
      data: {
        id: 42,
        title: "新会话",
        created_at: "2026-01-01T00:00:00.000Z",
        updated_at: "2026-01-01T00:00:00.000Z",
      },
    });
    (conversationsApi.getMessages as unknown as Mock).mockResolvedValue({ data: [], total: 0 });
    (modelsApi.list as unknown as Mock).mockResolvedValue({ data: [] });
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
    vi.restoreAllMocks();
    resetStore();
    vi.clearAllMocks();
  });

  it("selects and loads the conversation from /chat/:id", async () => {
    (conversationsApi.getMessages as unknown as Mock).mockResolvedValueOnce({
      data: [
        {
          id: 10,
          conversation_id: 42,
          msg_type: "user",
          msg_json: {},
          created_at: "2026-01-01T00:00:00.000Z",
          parts: [],
          content: "hello",
        },
      ],
      total: 1,
    });

    render(<ChatPageClient routeConversationId={42} />);

    await waitFor(() => {
      expect(conversationsApi.getMessages).toHaveBeenCalledWith(42);
    });

    expect(useChatStore.getState().activeConversationId).toBe(42);
    expect(useChatStore.getState().messages).toHaveLength(1);
  });

  it("does not reload when the route id already matches the active conversation", async () => {
    useChatStore.setState({
      activeConversationId: 42,
      messages: [
        {
          id: 10,
          conversation_id: 42,
          msg_type: "user",
          msg_json: {},
          created_at: "2026-01-01T00:00:00.000Z",
          parts: [],
          content: "already loaded",
        },
      ],
    });

    render(<ChatPageClient routeConversationId={42} />);

    await waitFor(() => {
      expect(conversationsApi.list).toHaveBeenCalled();
    });
    expect(conversationsApi.getMessages).not.toHaveBeenCalled();
  });

  it("returns invalid chat ids to the new chat route", async () => {
    useChatStore.setState({
      activeConversationId: 42,
      messages: [
        {
          id: 10,
          conversation_id: 42,
          msg_type: "user",
          msg_json: {},
          created_at: "2026-01-01T00:00:00.000Z",
          parts: [],
          content: "old",
        },
      ],
    });

    render(<ChatPageClient invalidRoute />);

    await waitFor(() => {
      expect(routerMock.replace).toHaveBeenCalledWith("/chat");
    });
    expect(useChatStore.getState().activeConversationId).toBeNull();
    expect(useChatStore.getState().messages).toEqual([]);
  });

  it("precreates a draft conversation and routes to /chat/:id before streaming finishes", async () => {
    let finishStream!: () => void;
    (chatApi.sendSSE as unknown as Mock).mockImplementationOnce(
      (
        _message: string,
        conversationId: number | null,
        callbacks: { onDone?: (conversationId: number, messageIds: number[], tokenUsage: Record<string, unknown>) => void },
      ) => {
        expect(conversationId).toBe(42);
        return new Promise<void>((resolve) => {
          finishStream = () => {
            callbacks.onDone?.(42, [], {});
            resolve();
          };
        });
      },
    );

    render(<ChatPageClient />);

    fireEvent.change(screen.getByLabelText("输入消息"), {
      target: { value: "hello" },
    });
    fireEvent.click(screen.getByLabelText("发送消息"));

    await waitFor(() => {
      expect(conversationsApi.create).toHaveBeenCalledWith("新会话", null);
      expect(routerMock.replace).toHaveBeenCalledWith("/chat/42");
      expect(chatApi.sendSSE).toHaveBeenCalledWith(
        "hello",
        42,
        expect.any(Object),
        null,
        null,
      );
    });
    expect(useChatStore.getState().activeConversationId).toBe(42);
    finishStream();
  });

  it("does not route back to a precreated conversation after New Chat while it streams", async () => {
    let completeStream!: () => void;
    (chatApi.sendSSE as unknown as Mock).mockImplementationOnce(
      (
        _message: string,
        conversationId: number | null,
        callbacks: { onDone?: (conversationId: number, messageIds: number[], tokenUsage: Record<string, unknown>) => void },
      ) => {
        expect(conversationId).toBe(42);
        return new Promise<void>((resolve) => {
          completeStream = () => {
            callbacks.onDone?.(42, [], {});
            resolve();
          };
        });
      },
    );

    render(<ChatPageClient />);

    fireEvent.change(screen.getByLabelText("输入消息"), {
      target: { value: "hello" },
    });
    fireEvent.click(screen.getByLabelText("发送消息"));

    await waitFor(() => {
      expect(chatApi.sendSSE).toHaveBeenCalled();
      expect(routerMock.replace).toHaveBeenCalledWith("/chat/42");
    });

    routerMock.replace.mockClear();
    useChatStore.getState().startNewChat();
    completeStream();

    await waitFor(() => {
      expect(useChatStore.getState().activeStreams).not.toContain(42);
    });
    expect(routerMock.replace).not.toHaveBeenCalledWith("/chat/42");
    expect(useChatStore.getState().activeConversationId).toBeNull();
  });

  it("keeps the running timer based on the stored stream start time", async () => {
    const now = new Date("2026-01-01T00:02:05.000Z").getTime();
    vi.spyOn(Date, "now").mockReturnValue(now);
    const startedAt = now - 65_000;
    useChatStore.setState({
      activeConversationId: 42,
      activeStreams: [42],
      activeStreamStartedAt: {
        42: startedAt,
      },
      messages: [
        {
          id: 1,
          conversation_id: 42,
          msg_type: "user",
          msg_json: {},
          created_at: "2026-01-01T00:00:00.000Z",
          parts: [],
          content: "work",
        },
      ],
    });
    (conversationsApi.getMessages as unknown as Mock).mockResolvedValue({
      data: useChatStore.getState().messages,
      total: 1,
    });

    render(<ChatPageClient routeConversationId={42} />);

    await waitFor(() => {
      expect(screen.getAllByText("1分5秒").length).toBeGreaterThan(0);
    });
  });

  it("renders live streaming details after completed assistant iterations", async () => {
    useChatStore.setState({
      activeConversationId: 42,
      activeStreams: [42],
      activeStreamStartedAt: { 42: Date.now() - 5000 },
      messages: [
        {
          id: 1,
          conversation_id: 42,
          msg_type: "user",
          msg_json: {},
          created_at: "2026-01-01T00:00:00.000Z",
          parts: [{ type: "text", text: "run code", id: "u1", sessionID: "s1", messageID: "m1" }],
          content: "run code",
        },
        {
          id: 2,
          conversation_id: 42,
          msg_type: "assistant",
          msg_json: {},
          created_at: "2026-01-01T00:00:01.000Z",
          parts: [{ type: "text", text: "first answer", id: "a1", sessionID: "s1", messageID: "m2" }],
          content: "first answer",
        },
        {
          id: 3,
          conversation_id: 42,
          msg_type: "assistant",
          msg_json: {},
          created_at: "2026-01-01T00:00:02.000Z",
          parts: [{ type: "text", text: "second answer", id: "a2", sessionID: "s1", messageID: "m3" }],
          content: "second answer",
        },
      ],
      toolCalls: [
        {
          toolName: "run_terminal",
          status: "running",
          callID: "call-1",
          command: "go run hello.go",
        },
      ],
    });

    render(<ChatPageClient routeConversationId={42} />);

    await waitFor(() => {
      expect(screen.getByText("正在检索与处理")).toBeInTheDocument();
    });

    const pageText = document.body.textContent ?? "";
    expect(pageText.indexOf("first answer")).toBeLessThan(pageText.indexOf("second answer"));
    expect(pageText.indexOf("second answer")).toBeLessThan(pageText.indexOf("正在检索与处理"));
  });

  it("scrolls to the latest live reasoning and tool updates", async () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    useChatStore.setState({
      activeConversationId: 42,
      activeStreams: [42],
      activeStreamStartedAt: { 42: Date.now() - 5000 },
      messages: [
        {
          id: 1,
          conversation_id: 42,
          msg_type: "user",
          msg_json: {},
          created_at: "2026-01-01T00:00:00.000Z",
          parts: [{ type: "text", text: "work", id: "u1", sessionID: "s1", messageID: "m1" }],
          content: "work",
        },
      ],
    });

    render(<ChatPageClient routeConversationId={42} />);

    await waitFor(() => {
      expect(scrollIntoView).toHaveBeenCalled();
    });
    scrollIntoView.mockClear();

    act(() => {
      useChatStore.setState({
        activeReasoningByMsg: { 42: "thinking about the latest step" },
      });
    });

    await waitFor(() => {
      expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth" });
    });
    scrollIntoView.mockClear();

    act(() => {
      useChatStore.setState({
        messages: [
          {
            id: 1,
            conversation_id: 42,
            msg_type: "user",
            msg_json: {},
            created_at: "2026-01-01T00:00:00.000Z",
            parts: [{ type: "text", text: "done", id: "u1", sessionID: "s1", messageID: "m1" }],
            content: "done",
          },
        ],
      });
    });

    await waitFor(() => {
      expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth" });
    });
    scrollIntoView.mockClear();

    act(() => {
      useChatStore.setState({
        toolCalls: [
          {
            toolName: "run_terminal",
            status: "running",
            callID: "call-1",
            command: "go run hello.go",
          },
        ],
      });
    });

    await waitFor(() => {
      expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth" });
    });
    scrollIntoView.mockClear();

    act(() => {
      useChatStore.setState({
        toolCalls: [
          {
            toolName: "run_sub_agent",
            status: "running",
            callID: "parent-1",
            subCalls: [
              {
                toolName: "run_terminal",
                status: "running",
                callID: "sub-1",
              },
            ],
          },
        ],
      });
    });

    await waitFor(() => {
      expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth" });
    });
    scrollIntoView.mockClear();

    act(() => {
      useChatStore.setState({
        toolCalls: [
          {
            toolName: "run_sub_agent",
            status: "running",
            callID: "parent-1",
            subCalls: [
              {
                toolName: "run_terminal",
                status: "done",
                callID: "sub-1",
                state: {
                  status: "done",
                  input: {},
                  output: null,
                  summary: "sub command completed",
                },
              },
            ],
          },
        ],
      });
    });

    await waitFor(() => {
      expect(scrollIntoView).toHaveBeenCalledWith({ behavior: "smooth" });
    });
  });

  it("polls fresh messages when a routed conversation is still marked running", async () => {
    useChatStore.setState({
      activeConversationId: 42,
      activeStreams: [42],
      activeStreamStartedAt: { 42: Date.now() - 5000 },
      recoveredStreams: [42],
      messages: [
        {
          id: 1,
          conversation_id: 42,
          msg_type: "user",
          msg_json: {},
          created_at: "2026-01-01T00:00:00.000Z",
          parts: [],
          content: "work",
        },
      ],
    });
    (conversationsApi.getMessages as unknown as Mock).mockResolvedValueOnce({
      data: [
        {
          id: 1,
          conversation_id: 42,
          msg_type: "user",
          msg_json: {},
          created_at: "2026-01-01T00:00:00.000Z",
          parts: [],
          content: "work",
        },
        {
          id: 2,
          conversation_id: 42,
          msg_type: "assistant",
          msg_json: {
            parts: [{ type: "text", text: "done" }],
          },
          created_at: "2026-01-01T00:00:01.000Z",
          parts: [],
          content: "",
        },
      ],
      total: 2,
    });

    render(<ChatPageClient routeConversationId={42} />);

    await waitFor(() => {
      expect(conversationsApi.getMessages).toHaveBeenCalledWith(42, {
        limit: expect.any(Number),
      });
    });
    await waitFor(() => {
      expect(useChatStore.getState().messages).toHaveLength(2);
    });
  });

  it("subscribes to recovered stream events and applies live updates after refresh", async () => {
    const persistedMessages = [
      {
        id: 1,
        conversation_id: 42,
        msg_type: "user",
        msg_json: {},
        created_at: "2026-01-01T00:00:00.000Z",
        parts: [],
        content: "work",
      },
      {
        id: 2,
        conversation_id: 42,
        msg_type: "assistant",
        msg_json: {
          parts: [{ type: "text", text: "done", id: "p1", sessionID: "ses_1", messageID: "msg_1" }],
        },
        created_at: "2026-01-01T00:00:01.000Z",
        parts: [],
        content: "",
      },
    ];
    (conversationsApi.getMessages as unknown as Mock).mockResolvedValue({
      data: persistedMessages,
      total: persistedMessages.length,
    });
    useChatStore.setState({
      activeConversationId: 42,
      activeStreams: [42],
      activeStreamStartedAt: { 42: Date.now() - 5000 },
      recoveredStreams: [42],
      messages: [persistedMessages[0]],
    });
    (chatApi.streamConversationEvents as unknown as Mock).mockImplementationOnce(
      async (
        _conversationId: number,
        callbacks: {
          onReasoning?: (text: string) => void;
          onIterationDone?: (messageId: number, msg: unknown) => void;
          onDone?: () => void;
        },
      ) => {
        callbacks.onReasoning?.("thinking");
        callbacks.onIterationDone?.(2, {
          message: { role: "assistant", id: "msg_1", sessionID: "ses_1" },
          parts: [{ type: "text", text: "done", id: "p1", sessionID: "ses_1", messageID: "msg_1" }],
        });
        callbacks.onDone?.();
      },
    );

    render(<ChatPageClient routeConversationId={42} />);

    await waitFor(() => {
      expect(chatApi.streamConversationEvents).toHaveBeenCalledWith(
        42,
        expect.any(Object),
        expect.any(AbortSignal),
      );
    });
    await waitFor(() => {
      expect(useChatStore.getState().messages.map((message) => message.id)).toContain(2);
    });
    expect(useChatStore.getState().activeStreams).not.toContain(42);
  });
});
