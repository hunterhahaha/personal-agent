import { describe, expect, it } from "vitest";
import type { Message } from "@/lib/api-client";
import {
  getAssistantPreviewText,
  getRenderableParts,
} from "@/lib/chat-turns";

function baseMessage(overrides: Partial<Message>): Message {
  return {
    id: 1,
    conversation_id: 1,
    msg_type: "assistant",
    msg_json: {},
    created_at: "2026-06-22T00:00:00.000Z",
    parts: [],
    ...overrides,
  };
}

describe("chat-turns rendering adapters", () => {
  it("renders assistant parts from persisted msg_json.parts when top-level parts are empty", () => {
    const message = baseMessage({
      msg_json: {
        message: { role: "assistant" },
        parts: [
          {
            type: "reasoning",
            text: "thinking",
            id: "reasoning-1",
            sessionID: "ses_1",
            messageID: "msg_1",
          },
          {
            type: "toolcall",
            tool: "run_read",
            callID: "call_1",
            state: {
              status: "success",
              input: { path: "README.md" },
              output: { result: "ok" },
              summary: "read README",
            },
            metadata: {},
            id: "tool-1",
            sessionID: "ses_1",
            messageID: "msg_1",
          },
          {
            type: "text",
            text: "final answer",
            id: "text-1",
            sessionID: "ses_1",
            messageID: "msg_1",
          },
        ],
      },
    });

    const parts = getRenderableParts(message);

    expect(parts).toHaveLength(3);
    expect(parts[0]?.type).toBe("reasoning");
    expect(parts[1]?.type).toBe("toolcall");
    expect(parts[2]).toMatchObject({ type: "text", text: "final answer" });
  });

  it("renders user text from persisted msg_json.part when top-level content is empty", () => {
    const message = baseMessage({
      msg_type: "user",
      msg_json: {
        message: { role: "user" },
        part: [
          {
            type: "text",
            text: "hello from db",
            id: "text-1",
            sessionID: "ses_1",
            messageID: "msg_1",
          },
        ],
      },
    });

    expect(getRenderableParts(message)).toEqual([
      {
        type: "text",
        text: "hello from db",
        id: "text-1",
        sessionID: "ses_1",
        messageID: "msg_1",
      },
    ]);
  });

  it("builds collapsed assistant preview text from persisted msg_json parts", () => {
    const user = baseMessage({
      id: 1,
      msg_type: "user",
      msg_json: {
        message: { role: "user" },
        part: [{ type: "text", text: "question", id: "u1", sessionID: "s", messageID: "u" }],
      },
    });
    const assistant = baseMessage({
      id: 2,
      msg_json: {
        message: { role: "assistant" },
        parts: [{ type: "text", text: "preview me", id: "a1", sessionID: "s", messageID: "a" }],
      },
    });

    expect(getAssistantPreviewText({
      id: "turn-1",
      userMessage: user,
      assistantMessages: [assistant],
    })).toBe("preview me");
  });

  it("preserves legacy persisted msg_json.content rendering", () => {
    const message = baseMessage({
      msg_json: {
        message: { role: "assistant" },
        content: "legacy body",
      },
    });

    expect(getRenderableParts(message)).toEqual([
      {
        type: "text",
        text: "legacy body",
        id: "legacy-1",
        sessionID: "",
        messageID: "1",
      },
    ]);
  });
});
