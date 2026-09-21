import { ChatMessage } from '@/lib/api';

export function mergeChatMessages(
  current: ChatMessage[],
  incoming: ChatMessage[],
): ChatMessage[] {
  const byId = new Map(current.map((message) => [message.id, message]));
  incoming.forEach((message) => byId.set(message.id, message));
  return [...byId.values()].sort(
    (left, right) =>
      Date.parse(left.sent_at) - Date.parse(right.sent_at) || left.id.localeCompare(right.id),
  );
}

export function reconnectDelay(attempt: number): number {
  return Math.min(1000 * 2 ** Math.max(0, attempt), 30_000);
}
