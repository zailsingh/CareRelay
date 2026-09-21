import { Ionicons } from '@expo/vector-icons';
import { useCallback, useEffect, useRef, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  FlatList,
  KeyboardAvoidingView,
  NativeScrollEvent,
  NativeSyntheticEvent,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ChatToCareEventModal } from '@/components/ChatToCareEventModal';
import { ProfileSelector } from '@/components/ProfileSelector';
import {
  api,
  ChatCareEventDraft,
  ChatMessage,
  chatWebSocketUrl,
} from '@/lib/api';
import { mergeChatMessages, reconnectDelay } from '@/lib/chat';
import { formatCheckinTime } from '@/lib/dates';
import { useAuth } from '@/providers/AuthProvider';
import { useCareProfiles } from '@/providers/CareProfileProvider';
import { colors } from '@/theme/colors';

type RealtimeEvent =
  | { type: 'ready' }
  | { type: 'message_created'; message: ChatMessage }
  | { type: 'message_deleted'; message_id: string; deleted_at: string };

export default function ChatScreen() {
  const { token, user } = useAuth();
  const { activeProfile } = useCareProfiles();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [cursor, setCursor] = useState<string | null>(null);
  const [composer, setComposer] = useState('');
  const [unreadCount, setUnreadCount] = useState(0);
  const [loading, setLoading] = useState(false);
  const [loadingOlder, setLoadingOlder] = useState(false);
  const [sending, setSending] = useState(false);
  const [connected, setConnected] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [draft, setDraft] = useState<ChatCareEventDraft | null>(null);
  const listRef = useRef<FlatList<ChatMessage>>(null);
  const nearBottom = useRef(true);

  const profileId = activeProfile?.id;

  const recoverLatest = useCallback(async () => {
    if (!token || !profileId) return;
    const [page, unread] = await Promise.all([
      api.chatMessages(token, profileId, 50),
      api.chatUnread(token, profileId),
    ]);
    setMessages((current) => mergeChatMessages(current, page.items));
    setCursor((current) => current ?? page.next_cursor);
    setUnreadCount(unread.unread_count);
  }, [profileId, token]);

  useEffect(() => {
    setMessages([]);
    setCursor(null);
    setUnreadCount(0);
    setError(null);
    if (!token || !profileId) return;
    let current = true;
    setLoading(true);
    Promise.all([
      api.chatMessages(token, profileId, 50),
      api.chatUnread(token, profileId),
    ])
      .then(([page, unread]) => {
        if (!current) return;
        setMessages(mergeChatMessages([], page.items));
        setCursor(page.next_cursor);
        setUnreadCount(unread.unread_count);
      })
      .catch((cause) => {
        if (current) setError(cause instanceof Error ? cause.message : 'Unable to load chat.');
      })
      .finally(() => current && setLoading(false));
    return () => {
      current = false;
    };
  }, [profileId, token]);

  useEffect(() => {
    if (!token || !profileId) return;
    let stopped = false;
    let socket: WebSocket | null = null;
    let timer: ReturnType<typeof setTimeout> | null = null;
    let attempt = 0;

    const connect = async () => {
      if (stopped) return;
      try {
        const issued = await api.chatWebSocketTicket(token, profileId);
        if (stopped) return;
        socket = new WebSocket(chatWebSocketUrl(profileId, issued.ticket));
      } catch {
        setConnected(false);
        if (!stopped) {
          timer = setTimeout(() => void connect(), reconnectDelay(attempt));
          attempt += 1;
        }
        return;
      }
      socket.onopen = () => {
        attempt = 0;
        setConnected(true);
        void recoverLatest().catch(() => undefined);
      };
      socket.onmessage = (event) => {
        try {
          const payload = JSON.parse(String(event.data)) as RealtimeEvent;
          if (payload.type === 'message_created') {
            setMessages((current) => mergeChatMessages(current, [payload.message]));
            if (payload.message.sender_user_id !== user?.id) {
              setUnreadCount((current) => current + 1);
            }
            if (nearBottom.current) {
              setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 50);
            }
          }
          if (payload.type === 'message_deleted') {
            setMessages((current) =>
              current.map((message) =>
                message.id === payload.message_id
                  ? { ...message, body: null, is_deleted: true, deleted_at: payload.deleted_at }
                  : message,
              ),
            );
          }
        } catch {
          // Ignore malformed transient frames; REST remains the source of truth.
        }
      };
      socket.onerror = () => setConnected(false);
      socket.onclose = () => {
        setConnected(false);
        if (!stopped) {
          timer = setTimeout(() => void connect(), reconnectDelay(attempt));
          attempt += 1;
        }
      };
    };

    void connect();
    return () => {
      stopped = true;
      if (timer) clearTimeout(timer);
      socket?.close();
      setConnected(false);
    };
  }, [profileId, recoverLatest, token, user?.id]);

  useEffect(() => {
    const latest = messages.at(-1);
    if (!token || !profileId || !latest || !nearBottom.current) return;
    void api
      .markChatRead(token, profileId, latest.id)
      .then((result) => setUnreadCount(result.unread_count))
      .catch(() => undefined);
  }, [messages, profileId, token]);

  const loadOlder = async () => {
    if (!token || !profileId || !cursor || loadingOlder) return;
    setLoadingOlder(true);
    try {
      const page = await api.chatMessages(token, profileId, 30, cursor);
      setMessages((current) => mergeChatMessages(current, page.items));
      setCursor(page.next_cursor);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load earlier messages.');
    } finally {
      setLoadingOlder(false);
    }
  };

  const send = async () => {
    const body = composer.trim();
    if (!token || !profileId || !body || sending) return;
    setSending(true);
    setError(null);
    try {
      const message = await api.sendChatMessage(token, profileId, body);
      setMessages((current) => mergeChatMessages(current, [message]));
      setComposer('');
      nearBottom.current = true;
      setTimeout(() => listRef.current?.scrollToEnd({ animated: true }), 50);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to send this message.');
    } finally {
      setSending(false);
    }
  };

  const openDraft = async (message: ChatMessage) => {
    if (!token || !profileId) return;
    try {
      setDraft(await api.chatCareEventDraft(token, profileId, message.id));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to prepare a care-event draft.');
    }
  };

  const deleteMessage = async (message: ChatMessage) => {
    if (!token || !profileId) return;
    try {
      await api.deleteChatMessage(token, profileId, message.id);
      setMessages((current) =>
        current.map((item) =>
          item.id === message.id
            ? { ...item, body: null, is_deleted: true, deleted_at: new Date().toISOString() }
            : item,
        ),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to delete this message.');
    }
  };

  const showActions = (message: ChatMessage) => {
    if (message.is_deleted) return;
    const buttons: Parameters<typeof Alert.alert>[2] = [];
    if (activeProfile && ['admin', 'family', 'carer'].includes(activeProfile.role)) {
      buttons.push({ text: 'Add to Care Record', onPress: () => void openDraft(message) });
    }
    if (message.sender_user_id === user?.id) {
      buttons.push({ text: 'Delete message', style: 'destructive', onPress: () => void deleteMessage(message) });
    }
    buttons.push({ text: 'Cancel', style: 'cancel' });
    Alert.alert('Message actions', message.body ?? '', buttons);
  };

  const onScroll = (event: NativeSyntheticEvent<NativeScrollEvent>) => {
    const { contentOffset, contentSize, layoutMeasurement } = event.nativeEvent;
    const wasNearBottom = nearBottom.current;
    nearBottom.current = contentOffset.y + layoutMeasurement.height >= contentSize.height - 80;
    const latest = messages.at(-1);
    if (!wasNearBottom && nearBottom.current && token && profileId && latest) {
      void api
        .markChatRead(token, profileId, latest.id)
        .then((result) => setUnreadCount(result.unread_count))
        .catch(() => undefined);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <KeyboardAvoidingView style={styles.safe} behavior={Platform.OS === 'ios' ? 'padding' : undefined} keyboardVerticalOffset={84}>
        <View style={styles.header}>
          <View>
            <Text style={styles.brand}>CareRelay</Text>
            <View style={styles.titleRow}>
              <Text accessibilityRole="header" style={styles.title}>Family chat</Text>
              <View style={[styles.statusDot, connected && styles.statusConnected]} />
            </View>
          </View>
          <View style={styles.unreadBadge}>
            <Text style={styles.unreadText}>{unreadCount > 0 ? `${unreadCount} unread` : 'All read'}</Text>
          </View>
        </View>
        <View style={styles.selector}><ProfileSelector /></View>
        {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
        {!activeProfile ? (
          <View style={styles.empty}><Text style={styles.emptyTitle}>Choose a care profile</Text><Text style={styles.emptyBody}>Chat belongs to one care profile at a time.</Text></View>
        ) : loading ? (
          <ActivityIndicator color={colors.primary} style={styles.loader} />
        ) : (
          <FlatList
            ref={listRef}
            data={messages}
            keyExtractor={(item) => item.id}
            contentContainerStyle={[styles.list, messages.length === 0 && styles.emptyList]}
            ListHeaderComponent={cursor ? (
              <Pressable accessibilityRole="button" disabled={loadingOlder} onPress={() => void loadOlder()} style={styles.olderButton}>
                {loadingOlder ? <ActivityIndicator color={colors.primary} /> : <Text style={styles.olderText}>Load earlier messages</Text>}
              </Pressable>
            ) : null}
            ListEmptyComponent={<View style={styles.empty}><Ionicons name="chatbubbles-outline" size={34} color={colors.primary} /><Text style={styles.emptyTitle}>Start the conversation</Text><Text style={styles.emptyBody}>Messages stay private to members of this care profile.</Text></View>}
            onContentSizeChange={() => {
              if (nearBottom.current) listRef.current?.scrollToEnd({ animated: false });
            }}
            onScroll={onScroll}
            scrollEventThrottle={100}
            renderItem={({ item }) => (
              <MessageBubble message={item} own={item.sender_user_id === user?.id} onLongPress={() => showActions(item)} />
            )}
          />
        )}
        {activeProfile ? (
          <View style={styles.composerRow}>
            <TextInput
              accessibilityLabel="Message"
              editable={!sending}
              maxLength={5000}
              multiline
              onChangeText={setComposer}
              placeholder="Message your care circle"
              placeholderTextColor={colors.muted}
              style={styles.composer}
              value={composer}
            />
            <Pressable accessibilityRole="button" accessibilityLabel="Send message" disabled={!composer.trim() || sending} onPress={() => void send()} style={[styles.send, (!composer.trim() || sending) && styles.sendDisabled]}>
              {sending ? <ActivityIndicator color={colors.surface} /> : <Ionicons name="arrow-up" size={23} color={colors.surface} />}
            </Pressable>
          </View>
        ) : null}
      </KeyboardAvoidingView>
      <ChatToCareEventModal draft={draft} onClose={() => setDraft(null)} />
    </SafeAreaView>
  );
}

function MessageBubble({ message, own, onLongPress }: { message: ChatMessage; own: boolean; onLongPress: () => void }) {
  return (
    <View style={[styles.messageRow, own && styles.ownRow]}>
      <Pressable accessibilityRole="button" accessibilityHint="Long press for message actions" onLongPress={onLongPress} style={[styles.bubble, own ? styles.ownBubble : styles.otherBubble]}>
        {!own ? <Text style={styles.sender}>{message.sender.display_name}</Text> : null}
        <Text style={[styles.messageBody, own && styles.ownBody, message.is_deleted && styles.deleted]}>
          {message.is_deleted ? 'Message deleted' : message.body}
        </Text>
        <Text style={[styles.timestamp, own && styles.ownTimestamp]}>
          {formatCheckinTime(message.sent_at)}{message.edited_at ? ' · edited' : ''}
        </Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', paddingHorizontal: 20, paddingTop: 14 },
  brand: { color: colors.primary, fontSize: 18, fontWeight: '800' },
  titleRow: { flexDirection: 'row', alignItems: 'center', gap: 9, marginTop: 8 },
  title: { color: colors.ink, fontSize: 30, fontWeight: '800', letterSpacing: -0.7 },
  statusDot: { width: 9, height: 9, borderRadius: 5, backgroundColor: colors.warning },
  statusConnected: { backgroundColor: colors.primary },
  unreadBadge: { borderRadius: 99, paddingHorizontal: 11, paddingVertical: 7, backgroundColor: colors.primarySoft },
  unreadText: { color: colors.primary, fontSize: 12, fontWeight: '800' },
  selector: { paddingHorizontal: 20 },
  error: { color: colors.error, fontSize: 13, paddingHorizontal: 20, paddingVertical: 8 },
  loader: { flex: 1 },
  list: { paddingHorizontal: 16, paddingTop: 8, paddingBottom: 18 },
  emptyList: { flexGrow: 1, justifyContent: 'center' },
  olderButton: { minHeight: 46, alignItems: 'center', justifyContent: 'center', marginBottom: 10 },
  olderText: { color: colors.primary, fontSize: 14, fontWeight: '800' },
  empty: { alignItems: 'center', justifyContent: 'center', padding: 28 },
  emptyTitle: { color: colors.ink, fontSize: 19, fontWeight: '800', marginTop: 10 },
  emptyBody: { color: colors.muted, fontSize: 14, lineHeight: 21, textAlign: 'center', marginTop: 6 },
  messageRow: { alignItems: 'flex-start', marginVertical: 5 },
  ownRow: { alignItems: 'flex-end' },
  bubble: { maxWidth: '82%', borderRadius: 18, paddingHorizontal: 14, paddingVertical: 10 },
  ownBubble: { backgroundColor: colors.primary, borderBottomRightRadius: 5 },
  otherBubble: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderBottomLeftRadius: 5 },
  sender: { color: colors.primary, fontSize: 12, fontWeight: '800', marginBottom: 4 },
  messageBody: { color: colors.ink, fontSize: 16, lineHeight: 22 },
  ownBody: { color: colors.surface },
  deleted: { fontStyle: 'italic', opacity: 0.7 },
  timestamp: { color: colors.muted, fontSize: 10, marginTop: 5 },
  ownTimestamp: { color: '#D7EBE3' },
  composerRow: { flexDirection: 'row', alignItems: 'flex-end', gap: 10, paddingHorizontal: 14, paddingTop: 10, paddingBottom: 10, borderTopWidth: 1, borderTopColor: colors.border, backgroundColor: colors.surface },
  composer: { flex: 1, maxHeight: 110, minHeight: 48, borderRadius: 18, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.background, color: colors.ink, fontSize: 16, paddingHorizontal: 14, paddingVertical: 12 },
  send: { width: 48, height: 48, borderRadius: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary },
  sendDisabled: { opacity: 0.45 },
});
