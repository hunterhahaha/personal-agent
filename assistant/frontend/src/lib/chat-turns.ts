import type { Message, MsgPart, PartText } from "@/lib/api-client";

export interface ChatTurn {
  id: string;
  userMessage: Message | null;
  assistantMessages: Message[];
}

export interface AssistantIteration {
  key: string;
  message: Message;
  parts: MsgPart[];
}

export function getMessageRole(message: Message): string {
  const envelope = message.msg_json?.message as { role?: string } | undefined;
  return message.role ?? envelope?.role ?? message.msg_type;
}

function getPersistedParts(message: Message): MsgPart[] {
  const json = message.msg_json ?? {};
  const rawParts = (json.parts ?? json.part) as MsgPart[] | undefined;
  return Array.isArray(rawParts) ? rawParts : [];
}

export function isTextLikePart(part: MsgPart): part is PartText {
  return part.type === "text" || part.type === "reasoning" || part.type === "thought";
}

export function buildChatTurns(messages: Message[]): ChatTurn[] {
  const turns: ChatTurn[] = [];
  let currentTurn: ChatTurn | null = null;

  for (const message of messages) {
    if (getMessageRole(message) === "user") {
      currentTurn = {
        id: `turn-${message.id}`,
        userMessage: message,
        assistantMessages: [],
      };
      turns.push(currentTurn);
      continue;
    }

    if (!currentTurn) {
      currentTurn = {
        id: `turn-orphan-${message.id}`,
        userMessage: null,
        assistantMessages: [],
      };
      turns.push(currentTurn);
    }

    currentTurn.assistantMessages.push(message);
  }

  return turns;
}

export function getRenderableParts(message: Message): MsgPart[] {
  if (message.parts && message.parts.length > 0) {
    return message.parts;
  }

  const persistedParts = getPersistedParts(message);
  if (persistedParts.length > 0) {
    return persistedParts;
  }

  const legacyContent =
    message.content ??
    ((message.msg_json?.content as string | undefined) || "");

  if (!legacyContent.trim()) {
    return [];
  }

  return [
    {
      type: "text",
      text: legacyContent,
      id: `legacy-${message.id}`,
      sessionID: "",
      messageID: String(message.id),
    },
  ];
}

export function getMessageText(message: Message): string {
  return getRenderableParts(message)
    .filter(isTextLikePart)
    .filter((part) => part.type === "text")
    .map((part) => part.text)
    .join("");
}

export function getAssistantIterations(turn: ChatTurn): AssistantIteration[] {
  return turn.assistantMessages.map((message) => ({
    key: `assistant-${message.id}`,
    message,
    parts: getRenderableParts(message),
  }));
}

export function getAssistantPreviewText(turn: ChatTurn): string {
  for (let i = turn.assistantMessages.length - 1; i >= 0; i -= 1) {
    const parts = getRenderableParts(turn.assistantMessages[i]!);

    for (let j = parts.length - 1; j >= 0; j -= 1) {
      const part = parts[j]!;
      if (part.type === "text" && part.text.trim()) {
        return part.text.trim();
      }
    }
  }

  return "";
}
