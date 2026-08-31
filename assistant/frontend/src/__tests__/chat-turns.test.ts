import { describe, expect, it } from "vitest";
import { buildChatTurns, getAssistantIterations, getAssistantPreviewText, getRenderableParts } from "@/lib/chat-turns";
import type { Message } from "@/lib/api-client";

function makeMessage(overrides: Partial<Message>): Message {
  return {
    id: 1,
    conversation_id: 1,
    msg_type: "assistant",
    msg_json: {},
    created_at: "2026-05-10T00:00:00.000Z",
    parts: [],
    role: "assistant",
    content: "",
    ...overrides,
  };
}

describe("chat-turns", () => {
  it("groups all assistant messages after one user message into the same turn", () => {
    const messages: Message[] = [
      makeMessage({
        id: 1,
        msg_type: "user",
        role: "user",
        content: "question",
        parts: [{ type: "text", text: "question", id: "u1", sessionID: "", messageID: "1" }],
      }),
      makeMessage({
        id: 2,
        parts: [{ type: "thought", text: "thinking", id: "a1", sessionID: "", messageID: "2" }],
      }),
      makeMessage({
        id: 3,
        parts: [{ type: "text", text: "answer", id: "a2", sessionID: "", messageID: "3" }],
      }),
      makeMessage({
        id: 4,
        msg_type: "user",
        role: "user",
        content: "next",
        parts: [{ type: "text", text: "next", id: "u2", sessionID: "", messageID: "4" }],
      }),
    ];

    const turns = buildChatTurns(messages);

    expect(turns).toHaveLength(2);
    expect(turns[0]?.userMessage?.id).toBe(1);
    expect(turns[0]?.assistantMessages.map((message) => message.id)).toEqual([2, 3]);
    expect(turns[1]?.userMessage?.id).toBe(4);
    expect(turns[1]?.assistantMessages).toEqual([]);
  });

  it("keeps assistant iterations in original order across multiple AssistantMsg entries", () => {
    const turn = buildChatTurns([
      makeMessage({
        id: 1,
        msg_type: "user",
        role: "user",
        content: "question",
        parts: [{ type: "text", text: "question", id: "u1", sessionID: "", messageID: "1" }],
      }),
      makeMessage({
        id: 2,
        parts: [
          { type: "thought", text: "step 1", id: "p1", sessionID: "", messageID: "2" },
          { type: "text", text: "draft", id: "p2", sessionID: "", messageID: "2" },
        ],
      }),
      makeMessage({
        id: 3,
        parts: [{ type: "text", text: "final", id: "p3", sessionID: "", messageID: "3" }],
      }),
    ])[0]!;

    const iterations = getAssistantIterations(turn);

    expect(iterations).toHaveLength(2);
    expect(iterations[0]?.message.id).toBe(2);
    expect(iterations[1]?.message.id).toBe(3);
    expect(iterations[0]?.parts.map((part) => part.type)).toEqual(["thought", "text"]);
    expect(iterations[1]?.parts.map((part) => part.type)).toEqual(["text"]);
  });

  it("uses the last assistant text as the collapsed turn preview", () => {
    const turn = buildChatTurns([
      makeMessage({
        id: 1,
        msg_type: "user",
        role: "user",
        content: "question",
        parts: [{ type: "text", text: "question", id: "u1", sessionID: "", messageID: "1" }],
      }),
      makeMessage({
        id: 2,
        parts: [{ type: "text", text: "first answer", id: "p1", sessionID: "", messageID: "2" }],
      }),
      makeMessage({
        id: 3,
        parts: [
          { type: "thought", text: "thinking", id: "p2", sessionID: "", messageID: "3" },
          { type: "text", text: "final answer", id: "p3", sessionID: "", messageID: "3" },
        ],
      }),
    ])[0]!;

    expect(getAssistantPreviewText(turn)).toBe("final answer");
  });

  it("creates a synthetic text part for legacy assistant messages without parts", () => {
    const parts = getRenderableParts(
      makeMessage({
        id: 9,
        parts: [],
        content: "legacy content",
      }),
    );

    expect(parts).toHaveLength(1);
    expect(parts[0]).toMatchObject({
      type: "text",
      text: "legacy content",
    });
  });
});
