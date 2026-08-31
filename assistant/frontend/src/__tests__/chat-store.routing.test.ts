import { beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { conversationsApi, type Message } from "@/lib/api-client";
import { useChatStore } from "@/stores/chat-store";

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>(
    "@/lib/api-client",
  );
  return {
    ...actual,
    chatApi: {
      sendSSE: vi.fn(),
      approve: vi.fn(),
    },
    conversationsApi: {
      list: vi.fn(),
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
  });
}

function message(
  id: number,
  conversationId: number,
  content: string,
  createdAt = "2026-01-01T00:00:00.000Z",
): Message {
  return {
    id,
    conversation_id: conversationId,
    msg_type: "user",
    msg_json: {},
    created_at: createdAt,
    parts: [],
    content,
  };
}

function deferred<T>() {
  let resolve!: (value: T) => void;
  let reject!: (reason?: unknown) => void;
  const promise = new Promise<T>((res, rej) => {
    resolve = res;
    reject = rej;
  });
  return { promise, resolve, reject };
}

describe("chat-store routing selection", () => {
  beforeEach(() => {
    resetStore();
    (conversationsApi.getMessages as unknown as Mock).mockReset();
  });

  it("loads messages for the selected conversation and clears its unread marker", async () => {
    useChatStore.setState({ unreadIds: new Set([7]) });
    (conversationsApi.getMessages as unknown as Mock).mockResolvedValueOnce({
      data: [message(1, 7, "hello")],
      total: 3,
    });

    const loaded = await useChatStore.getState().selectConversation(7);

    expect(loaded).toBe(true);
    expect(conversationsApi.getMessages).toHaveBeenCalledWith(7);
    expect(useChatStore.getState().activeConversationId).toBe(7);
    expect(useChatStore.getState().messages).toHaveLength(1);
    expect(useChatStore.getState().unreadIds.has(7)).toBe(false);
    expect(useChatStore.getState().hasMoreMessages).toBe(true);
  });

  it("normalizes loaded conversation messages to chronological order", async () => {
    (conversationsApi.getMessages as unknown as Mock).mockResolvedValueOnce({
      data: [
        message(2, 7, "newer", "2026-01-01T00:00:02.000Z"),
        message(1, 7, "older", "2026-01-01T00:00:01.000Z"),
      ],
      total: 2,
    });

    await useChatStore.getState().selectConversation(7);

    expect(useChatStore.getState().messages.map((msg) => msg.content)).toEqual([
      "older",
      "newer",
    ]);
  });

  it("keeps messages chronological when loading older pages", async () => {
    useChatStore.setState({
      activeConversationId: 7,
      messages: [
        message(3, 7, "newest", "2026-01-01T00:00:03.000Z"),
      ],
    });
    (conversationsApi.getMessages as unknown as Mock).mockResolvedValueOnce({
      data: [
        message(2, 7, "middle", "2026-01-01T00:00:02.000Z"),
        message(1, 7, "oldest", "2026-01-01T00:00:01.000Z"),
      ],
      total: 3,
    });

    await useChatStore.getState().loadMoreMessages();

    expect(useChatStore.getState().messages.map((msg) => msg.content)).toEqual([
      "oldest",
      "middle",
      "newest",
    ]);
  });

  it("does not let an older selection response overwrite the newer route", async () => {
    const first = deferred<{ data: Message[]; total: number }>();
    const second = deferred<{ data: Message[]; total: number }>();
    (conversationsApi.getMessages as unknown as Mock).mockImplementation((id: number) => {
      if (id === 1) return first.promise;
      if (id === 2) return second.promise;
      throw new Error(`Unexpected conversation id ${id}`);
    });

    const firstLoad = useChatStore.getState().selectConversation(1);
    const secondLoad = useChatStore.getState().selectConversation(2);

    second.resolve({ data: [message(2, 2, "new")], total: 1 });
    await secondLoad;
    first.resolve({ data: [message(1, 1, "old")], total: 1 });
    await firstLoad;

    expect(useChatStore.getState().activeConversationId).toBe(2);
    expect(useChatStore.getState().messages).toHaveLength(1);
    expect(useChatStore.getState().messages[0].content).toBe("new");
  });

  it("reports failed route loads without replacing a newer active conversation", async () => {
    const first = deferred<{ data: Message[]; total: number }>();
    (conversationsApi.getMessages as unknown as Mock).mockImplementation((id: number) => {
      if (id === 1) return first.promise;
      return Promise.resolve({ data: [message(2, 2, "new")], total: 1 });
    });

    const firstLoad = useChatStore.getState().selectConversation(1);
    const secondLoad = useChatStore.getState().selectConversation(2);
    await secondLoad;
    first.reject(new Error("missing"));

    await expect(firstLoad).resolves.toBe(false);
    expect(useChatStore.getState().activeConversationId).toBe(2);
    expect(useChatStore.getState().error).toBeNull();
  });
});
