export type User = {
  id: string;
  email: string;
  display_name: string;
  created_at: string;
};

export type AuthResponse = {
  access_token: string;
  token_type: 'bearer';
  user: User;
};

export type CareRole = 'admin' | 'family' | 'carer' | 'cared_person';

export type CareProfile = {
  id: string;
  name: string;
  role: CareRole;
  subject_user_id: string | null;
  timezone: string;
  created_at: string;
};

export type CareMembership = {
  id: string;
  user_id: string;
  display_name: string;
  email: string;
  role: CareRole;
  created_at: string;
};

export const careEventTypes = [
  'family_observation',
  'symptom_observation',
  'fall',
  'activity',
  'sleep_observation',
  'appointment',
  'medication_taken',
  'medication_missed',
  'general_note',
] as const;

export type CareEventType = (typeof careEventTypes)[number];
export type CareEventSource = 'admin' | 'family' | 'carer';

export const careEventLabels: Record<CareEventType, string> = {
  family_observation: 'Observation',
  symptom_observation: 'Symptom',
  fall: 'Fall',
  activity: 'Activity',
  sleep_observation: 'Sleep',
  appointment: 'Appointment',
  medication_taken: 'Medication taken',
  medication_missed: 'Medication missed',
  general_note: 'Note',
};

export type CareEvent = {
  id: string;
  care_profile_id: string;
  event_type: CareEventType;
  occurred_at: string;
  entered_by_user_id: string;
  entered_by: { id: string; display_name: string };
  source: CareEventSource;
  summary: string;
  metadata: Record<string, unknown>;
  confirmation_status: 'draft' | 'confirmed';
  source_chat_message_id: string | null;
  created_at: string;
  updated_at: string;
};

export type ChatMessage = {
  id: string;
  chat_room_id: string;
  sender_user_id: string;
  sender: { id: string; display_name: string };
  body: string | null;
  sent_at: string;
  edited_at: string | null;
  deleted_at: string | null;
  is_deleted: boolean;
  attachments: Array<{
    id: string;
    file_name: string;
    content_type: string;
    byte_size: number;
  }>;
};

export type ChatMessagePage = {
  items: ChatMessage[];
  next_cursor: string | null;
};

export type ChatCareEventDraft = {
  source_chat_message_id: string;
  occurred_at: string;
  summary: string;
  event_type: null;
  metadata: Record<string, unknown>;
};

export type AskEvidence = {
  record_type: 'wellbeing_checkin' | 'care_event';
  record_id: string;
  occurred_at: string;
  label: string;
};

export type AskResponse = {
  answer: string;
  metrics: Record<string, unknown>;
  evidence: AskEvidence[];
  period: {
    start_date: string;
    end_date: string;
    timezone: string;
    description: string;
  };
  visualization: {
    type: 'wellbeing_summary';
    average: number;
    checkin_count: number;
    daily_averages: Array<{
      date: string;
      checkin_count: number;
      average_score: number | null;
    }>;
  } | null;
  diagnostics: {
    provider: string;
    model: string;
    tools_used: string[];
    tool_call_count: number;
  };
};

export const symptomKinds = [
  'dizziness',
  'fatigue',
  'pain',
  'weakness',
  'nausea',
  'breathlessness',
  'poor_sleep',
  'low_appetite',
  'feeling_good',
  'other',
] as const;

export type SymptomKind = (typeof symptomKinds)[number];

export const symptomLabels: Record<SymptomKind, string> = {
  dizziness: 'Dizziness',
  fatigue: 'Fatigue',
  pain: 'Pain',
  weakness: 'Weakness',
  nausea: 'Nausea',
  breathlessness: 'Breathlessness',
  poor_sleep: 'Poor sleep',
  low_appetite: 'Low appetite',
  feeling_good: 'Feeling good',
  other: 'Other',
};

export type WellbeingCheckin = {
  id: string;
  care_profile_id: string;
  reported_by_user_id: string;
  reported_by: { id: string; display_name: string };
  score: number;
  occurred_at: string;
  symptoms: SymptomKind[];
  note: string | null;
  voice_transcript: string | null;
  created_at: string;
  updated_at: string;
};

export type WellbeingSummary = {
  start_date: string;
  end_date: string;
  timezone: string;
  checkin_count: number;
  latest_score: number | null;
  average_score: number | null;
  minimum_score: number | null;
  maximum_score: number | null;
  daily_averages: Array<{
    date: string;
    checkin_count: number;
    average_score: number | null;
  }>;
  symptom_frequency: Record<SymptomKind, number>;
};

export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000/api/v1';

export function chatWebSocketUrl(profileId: string, ticket: string): string {
  const base = API_URL.replace(/^http:/, 'ws:').replace(/^https:/, 'wss:');
  return `${base}/care-profiles/${encodeURIComponent(profileId)}/chat/ws?ticket=${encodeURIComponent(ticket)}`;
}

async function request<T>(path: string, init: RequestInit = {}, token?: string): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    ...init,
    headers: {
      'Content-Type': 'application/json',
      ...init.headers,
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail ?? 'Something went wrong. Please try again.');
  }
  if (response.status === 204) return undefined as T;
  return response.json() as Promise<T>;
}

export const api = {
  devLogin: (email: string, displayName: string) =>
    request<AuthResponse>('/auth/dev-login', {
      method: 'POST',
      body: JSON.stringify({ email, display_name: displayName }),
    }),
  me: (token: string) => request<User>('/auth/me', {}, token),
  profiles: (token: string) => request<CareProfile[]>('/care-profiles', {}, token),
  createProfile: (token: string, name: string, timezone: string) =>
    request<CareProfile>(
      '/care-profiles',
      { method: 'POST', body: JSON.stringify({ name, timezone }) },
      token,
    ),
  updateProfile: (
    token: string,
    profileId: string,
    payload: { subject_user_id?: string | null; timezone?: string },
  ) =>
    request<CareProfile>(
      `/care-profiles/${profileId}`,
      { method: 'PATCH', body: JSON.stringify(payload) },
      token,
    ),
  members: (token: string, profileId: string) =>
    request<CareMembership[]>(`/care-profiles/${profileId}/members`, {}, token),
  checkins: (token: string, profileId: string, limit = 100) =>
    request<WellbeingCheckin[]>(
      `/care-profiles/${profileId}/wellbeing-checkins?limit=${limit}`,
      {},
      token,
    ),
  createCheckin: (
    token: string,
    profileId: string,
    payload: {
      score: number;
      occurred_at: string;
      symptoms: SymptomKind[];
      note?: string | null;
    },
  ) =>
    request<WellbeingCheckin>(
      `/care-profiles/${profileId}/wellbeing-checkins`,
      { method: 'POST', body: JSON.stringify(payload) },
      token,
    ),
  wellbeingSummary: (
    token: string,
    profileId: string,
    startDate: string,
    endDate: string,
  ) => {
    const query = new URLSearchParams({
      start_date: startDate,
      end_date: endDate,
    });
    return request<WellbeingSummary>(
      `/care-profiles/${profileId}/wellbeing-checkins/summary?${query.toString()}`,
      {},
      token,
    );
  },
  careEvents: (token: string, profileId: string, limit = 200) =>
    request<CareEvent[]>(
      `/care-profiles/${profileId}/care-events?limit=${limit}&order=newest`,
      {},
      token,
    ),
  createCareEvent: (
    token: string,
    profileId: string,
    payload: {
      event_type: CareEventType;
      occurred_at: string;
      summary: string;
      metadata: Record<string, unknown>;
      confirmation_status?: 'draft' | 'confirmed';
      source_chat_message_id?: string;
    },
  ) =>
    request<CareEvent>(
      `/care-profiles/${profileId}/care-events`,
      { method: 'POST', body: JSON.stringify(payload) },
      token,
    ),
  chatMessages: (token: string, profileId: string, limit = 30, before?: string) => {
    const query = new URLSearchParams({ limit: String(limit) });
    if (before) query.set('before', before);
    return request<ChatMessagePage>(
      `/care-profiles/${profileId}/chat/messages?${query.toString()}`,
      {},
      token,
    );
  },
  sendChatMessage: (token: string, profileId: string, body: string) =>
    request<ChatMessage>(
      `/care-profiles/${profileId}/chat/messages`,
      { method: 'POST', body: JSON.stringify({ body }) },
      token,
    ),
  chatUnread: (token: string, profileId: string) =>
    request<{ unread_count: number }>(
      `/care-profiles/${profileId}/chat/unread`,
      {},
      token,
    ),
  chatWebSocketTicket: (token: string, profileId: string) =>
    request<{ ticket: string; expires_at: string }>(
      `/care-profiles/${profileId}/chat/ws-ticket`,
      { method: 'POST' },
      token,
    ),
  markChatRead: (token: string, profileId: string, throughMessageId?: string) =>
    request<{ unread_count: number }>(
      `/care-profiles/${profileId}/chat/read`,
      {
        method: 'POST',
        body: JSON.stringify({ through_message_id: throughMessageId ?? null }),
      },
      token,
    ),
  deleteChatMessage: (token: string, profileId: string, messageId: string) =>
    request<void>(
      `/care-profiles/${profileId}/chat/messages/${messageId}`,
      { method: 'DELETE' },
      token,
    ),
  chatCareEventDraft: (token: string, profileId: string, messageId: string) =>
    request<ChatCareEventDraft>(
      `/care-profiles/${profileId}/chat/messages/${messageId}/care-event-draft`,
      {},
      token,
    ),
  ask: (token: string, profileId: string, question: string) =>
    request<AskResponse>(
      `/care-profiles/${profileId}/ask`,
      { method: 'POST', body: JSON.stringify({ question }) },
      token,
    ),
};
