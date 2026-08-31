import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi, type Mock } from "vitest";
import { Sidebar } from "@/components/layout/sidebar";
import { TaskHistory } from "@/components/layout/task-history";
import { conversationsApi, type Conversation } from "@/lib/api-client";
import { useChatStore } from "@/stores/chat-store";

const navigationMock = vi.hoisted(() => ({
  pathname: "/chat",
  router: {
    push: vi.fn(),
    replace: vi.fn(),
  },
}));

vi.mock("next/navigation", () => ({
  usePathname: () => navigationMock.pathname,
  useRouter: () => navigationMock.router,
}));

vi.mock("@/lib/api-client", async () => {
  const actual = await vi.importActual<typeof import("@/lib/api-client")>(
    "@/lib/api-client",
  );
  return {
    ...actual,
    conversationsApi: {
      list: vi.fn(),
      create: vi.fn(),
      update: vi.fn(),
      delete: vi.fn(),
      getMessages: vi.fn(),
    },
  };
});

const conversations: Conversation[] = [
  {
    id: 7,
    title: "Project A",
    type: "chat",
    created_at: "2026-01-01T00:00:00.000Z",
    updated_at: "2026-01-01T00:00:00.000Z",
  },
  {
    id: 9,
    title: "Task Project",
    type: "task",
    created_at: "2026-01-01T00:00:00.000Z",
    updated_at: "2026-01-01T00:00:00.000Z",
  },
];

function resetStore(): void {
  useChatStore.setState({
    conversations,
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

describe("layout chat routing", () => {
  beforeEach(() => {
    resetStore();
    navigationMock.pathname = "/chat";
    navigationMock.router.push.mockReset();
    navigationMock.router.replace.mockReset();
    (conversationsApi.list as unknown as Mock).mockResolvedValue({
      data: conversations,
      total: conversations.length,
    });
    (conversationsApi.delete as unknown as Mock).mockResolvedValue(undefined);
  });

  afterEach(() => {
    cleanup();
  });

  it("routes sidebar history entries to /chat/:id while keeping 新对话 at /chat", async () => {
    render(<Sidebar />);

    await screen.findByText("Project A");
    fireEvent.click(screen.getByText("Project A"));
    expect(navigationMock.router.push).toHaveBeenCalledWith("/chat/7");

    fireEvent.click(screen.getByText("新对话"));
    expect(navigationMock.router.push).toHaveBeenCalledWith("/chat");
  });

  it("returns to /chat after deleting the current route conversation", async () => {
    navigationMock.pathname = "/chat/7";
    useChatStore.setState({ activeConversationId: 7 });
    render(<Sidebar />);

    await screen.findByLabelText("删除会话：Project A");
    fireEvent.click(screen.getByLabelText("删除会话：Project A"));

    await waitFor(() => {
      expect(conversationsApi.delete).toHaveBeenCalledWith(7);
      expect(navigationMock.router.replace).toHaveBeenCalledWith("/chat");
    });
  });

  it("routes task history entries to /chat/:id", async () => {
    render(<TaskHistory />);

    await screen.findByText("Task Project");
    expect(screen.queryByText("Project A")).not.toBeInTheDocument();

    fireEvent.click(screen.getByText("Task Project"));
    expect(navigationMock.router.push).toHaveBeenCalledWith("/chat/9");
  });
});
