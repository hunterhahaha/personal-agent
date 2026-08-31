import type { Conversation } from "@/lib/api-client";

export type ConversationMode = "chat" | "task";

function rawConversationMode(conversation: Conversation | null | undefined): string {
  if (!conversation) return "chat";
  const typed = conversation as Conversation & { type?: unknown };
  const value = typed.type ?? typed.source;
  return typeof value === "string" ? value.toLowerCase() : "chat";
}

export function getConversationMode(conversation: Conversation | null | undefined): ConversationMode {
  return rawConversationMode(conversation) === "task" ? "task" : "chat";
}

export function isTaskConversation(conversation: Conversation | null | undefined): boolean {
  return getConversationMode(conversation) === "task";
}

export function isChatConversation(conversation: Conversation | null | undefined): boolean {
  return getConversationMode(conversation) === "chat";
}
