import { afterEach, describe, expect, it, vi } from "vitest";
import { chatApi } from "@/lib/api-client";

function streamFromChunks(chunks: string[]): ReadableStream<Uint8Array> {
  const encoder = new TextEncoder();
  return new ReadableStream<Uint8Array>({
    start(controller) {
      for (const chunk of chunks) {
        controller.enqueue(encoder.encode(chunk));
      }
      controller.close();
    },
  });
}

describe("chatApi.sendSSE", () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it("keeps the SSE event name when event and data arrive in separate chunks", async () => {
    const onSubAgentStart = vi.fn();
    const onSubAgentDone = vi.fn();
    const onIterationDone = vi.fn();
    const onDone = vi.fn();

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      body: streamFromChunks([
        "event: sub_agent_start\n",
        "data: {\"parent_call_id\":\"parent_1\",\"blueprint_name\":\"Daily AI News Digest\"}\n\n",
        "event: sub_agent_done\n",
        "data: {\"parent_call_id\":\"parent_1\",\"success\":true,\"result_len\":12}\n\n",
        "event: iteration_done\n",
        "data: {\"message_id\":42,\"msg\":{\"message\":{\"role\":\"assistant\",\"id\":\"msg_1\",\"sessionID\":\"ses_1\"},\"parts\":[{\"type\":\"text\",\"text\":\"done\",\"id\":\"p1\",\"sessionID\":\"ses_1\",\"messageID\":\"msg_1\"}]}}\n\n",
        "event: done\n",
        "data: {\"conversation_id\":7,\"message_ids\":[42],\"token_usage\":{\"total\":1}}\n\n",
      ]),
    }));

    await chatApi.sendSSE("use sub-agent", 7, {
      onSubAgentStart,
      onSubAgentDone,
      onIterationDone,
      onDone,
    }, "model_1", "G:\\workspace");

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/chat/send"),
      expect.objectContaining({
        body: JSON.stringify({
          message: "use sub-agent",
          conversation_id: 7,
          model_id: "model_1",
          workspace_root: "G:\\workspace",
        }),
      }),
    );
    expect(onSubAgentStart).toHaveBeenCalledWith("parent_1", "Daily AI News Digest");
    expect(onSubAgentDone).toHaveBeenCalledWith("parent_1");
    expect(onIterationDone).toHaveBeenCalledWith(
      42,
      expect.objectContaining({ parts: [expect.objectContaining({ text: "done" })] }),
    );
    expect(onDone).toHaveBeenCalledWith(7, [42], { total: 1 });
  });

  it("streams recovered conversation events from the conversation event endpoint", async () => {
    const onReasoning = vi.fn();
    const onDone = vi.fn();
    const controller = new AbortController();

    vi.stubGlobal("fetch", vi.fn().mockResolvedValue({
      ok: true,
      body: streamFromChunks([
        "event: reasoning\n",
        "data: {\"text\":\"still working\"}\n\n",
        "event: done\n",
        "data: {\"conversation_id\":7,\"message_ids\":[],\"token_usage\":{}}\n\n",
      ]),
    }));

    await chatApi.streamConversationEvents(7, {
      onReasoning,
      onDone,
    }, controller.signal);

    expect(fetch).toHaveBeenCalledWith(
      expect.stringContaining("/conversations/7/events"),
      expect.objectContaining({
        method: "GET",
        signal: controller.signal,
      }),
    );
    expect(onReasoning).toHaveBeenCalledWith("still working");
    expect(onDone).toHaveBeenCalledWith(7, [], {});
  });
});
