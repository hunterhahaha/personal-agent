import { ChatPageClient } from "@/components/chat/chat-page-client";

interface ChatConversationPageProps {
  params: Promise<{
    conversationId: string;
  }>;
}

export default async function ChatConversationPage({
  params,
}: ChatConversationPageProps) {
  const { conversationId } = await params;
  const parsedConversationId = Number(conversationId);
  const isValidConversationId =
    Number.isInteger(parsedConversationId) && parsedConversationId > 0;

  return (
    <ChatPageClient
      routeConversationId={isValidConversationId ? parsedConversationId : null}
      invalidRoute={!isValidConversationId}
    />
  );
}
