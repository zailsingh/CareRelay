import { ChatMessage, chatWebSocketUrl } from '@/lib/api';
import { mergeChatMessages, reconnectDelay } from '@/lib/chat';

function message(id: string, sentAt: string, body = id): ChatMessage {
  return {
    id,
    chat_room_id: 'room',
    sender_user_id: 'sender',
    sender: { id: 'sender', display_name: 'Sarah' },
    body,
    sent_at: sentAt,
    edited_at: null,
    deleted_at: null,
    is_deleted: false,
    attachments: [],
  };
}

describe('chat recovery helpers', () => {
  it('merges REST recovery pages without duplicates and in chronological order', () => {
    const newer = message('newer', '2026-09-18T02:00:00Z');
    const older = message('older', '2026-09-18T01:00:00Z');
    const recoveredUpdate = { ...newer, body: null, is_deleted: true };
    expect(mergeChatMessages([newer], [older, recoveredUpdate])).toEqual([
      older,
      recoveredUpdate,
    ]);
  });

  it('uses bounded exponential reconnect delays', () => {
    expect(reconnectDelay(0)).toBe(1000);
    expect(reconnectDelay(3)).toBe(8000);
    expect(reconnectDelay(20)).toBe(30_000);
  });

  it('builds an authenticated profile-scoped WebSocket URL', () => {
    const url = chatWebSocketUrl('profile id', 'ticket/value');
    expect(url).toContain('/care-profiles/profile%20id/chat/ws?ticket=ticket%2Fvalue');
    expect(url).not.toContain('token=');
    expect(url.startsWith('ws://') || url.startsWith('wss://')).toBe(true);
  });
});
