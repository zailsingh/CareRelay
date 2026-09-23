import { useEffect, useMemo, useState } from 'react';
import { ActivityIndicator, ScrollView, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ProfileSelector } from '@/components/ProfileSelector';
import { QuickAddCareEvent } from '@/components/QuickAddCareEvent';
import {
  api,
  CareEvent,
  careEventLabels,
  symptomLabels,
  WellbeingCheckin,
} from '@/lib/api';
import { formatCheckinTime } from '@/lib/dates';
import { formatMedicationClock } from '@/lib/medications';
import { useAuth } from '@/providers/AuthProvider';
import { useCareProfiles } from '@/providers/CareProfileProvider';
import { colors } from '@/theme/colors';

type TimelineEntry =
  | { kind: 'self_report'; occurredAt: string; item: WellbeingCheckin }
  | { kind: 'care_event'; occurredAt: string; item: CareEvent };

export default function TimelineScreen() {
  const { token } = useAuth();
  const { activeProfile, wellbeingRevision, careEventRevision } = useCareProfiles();
  const [checkins, setCheckins] = useState<WellbeingCheckin[]>([]);
  const [events, setEvents] = useState<CareEvent[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!token || !activeProfile) {
      setCheckins([]);
      setEvents([]);
      return;
    }
    let current = true;
    setLoading(true);
    Promise.all([
      api.checkins(token, activeProfile.id, 200),
      api.careEvents(token, activeProfile.id, 200),
    ])
      .then(([checkinResult, eventResult]) => {
        if (current) {
          setCheckins(checkinResult);
          setEvents(eventResult);
          setError(null);
        }
      })
      .catch((cause) => current && setError(cause instanceof Error ? cause.message : 'Unable to load the timeline.'))
      .finally(() => current && setLoading(false));
    return () => { current = false; };
  }, [token, activeProfile, wellbeingRevision, careEventRevision]);

  const entries = useMemo<TimelineEntry[]>(() => [
    ...checkins.map((item): TimelineEntry => ({ kind: 'self_report', occurredAt: item.occurred_at, item })),
    ...events.map((item): TimelineEntry => ({ kind: 'care_event', occurredAt: item.occurred_at, item })),
  ].sort((a, b) => Date.parse(b.occurredAt) - Date.parse(a.occurredAt)), [checkins, events]);

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.headerRow}>
          <View style={styles.headerCopy}>
            <Text style={styles.brand}>CareRelay</Text>
            <Text style={styles.title} accessibilityRole="header">Timeline</Text>
          </View>
          <QuickAddCareEvent />
        </View>
        <Text style={styles.subtitle}>Self reports and care-team observations, kept distinct.</Text>
        <ProfileSelector />
        {loading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> : null}
        {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
        {!loading && activeProfile && entries.length === 0 ? (
          <View style={styles.empty}>
            <Text style={styles.emptyTitle}>Nothing recorded yet</Text>
            <Text style={styles.emptyBody}>Self reports and confirmed care observations will appear here.</Text>
          </View>
        ) : null}
        {entries.map((entry) => entry.kind === 'self_report' ? (
          <SelfReportCard key={`self-${entry.item.id}`} checkin={entry.item} />
        ) : (
          <CareEventCard key={`event-${entry.item.id}`} event={entry.item} />
        ))}
      </ScrollView>
    </SafeAreaView>
  );
}

function SelfReportCard({ checkin }: { checkin: WellbeingCheckin }) {
  return (
    <View style={[styles.card, styles.selfCard]}>
      <CardHeader label="Self Report" timestamp={checkin.occurred_at} tone="self" />
      <View style={styles.scoreRow}>
        <Text style={styles.score}>{checkin.score}</Text>
        <Text style={styles.outOf}>/ 100 · How I feel</Text>
      </View>
      {checkin.symptoms.length > 0 ? (
        <Text style={styles.detail}>{checkin.symptoms.map((symptom) => symptomLabels[symptom]).join(', ')}</Text>
      ) : null}
      {checkin.note ? <Text style={styles.summary}>{checkin.note}</Text> : null}
      <Text style={styles.reporter}>Reported by {checkin.reported_by.display_name}</Text>
    </View>
  );
}

function CareEventCard({ event }: { event: CareEvent }) {
  const medicationEvent = event.event_type.startsWith('medication_');
  const scheduledTime = typeof event.metadata.scheduled_local_time === 'string'
    ? event.metadata.scheduled_local_time
    : null;
  return (
    <View style={[styles.card, styles.eventCard]}>
      <CardHeader label={careEventLabels[event.event_type]} timestamp={event.occurred_at} tone="event" />
      <Text style={styles.summary}>{event.summary}</Text>
      {medicationEvent && scheduledTime ? <Text style={styles.detail}>Scheduled {formatMedicationClock(scheduledTime)}</Text> : null}
      <Text style={styles.reporter}>{medicationEvent ? 'Recorded by ' : ''}{event.entered_by.display_name} · {event.source}</Text>
    </View>
  );
}

function CardHeader({ label, timestamp, tone }: { label: string; timestamp: string; tone: 'self' | 'event' }) {
  return (
    <View style={styles.cardTop}>
      <View style={[styles.badge, tone === 'event' && styles.eventBadge]}>
        <Text style={[styles.badgeText, tone === 'event' && styles.eventBadgeText]}>{label}</Text>
      </View>
      <Text style={styles.timestamp}>{formatCheckinTime(timestamp)}</Text>
    </View>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  content: { paddingHorizontal: 20, paddingTop: 14, paddingBottom: 120 },
  headerRow: { flexDirection: 'row', alignItems: 'flex-end', justifyContent: 'space-between', gap: 12 },
  headerCopy: { flex: 1 },
  brand: { color: colors.primary, fontSize: 18, fontWeight: '800' },
  title: { color: colors.ink, fontSize: 32, fontWeight: '800', letterSpacing: -0.8, marginTop: 10 },
  subtitle: { color: colors.muted, fontSize: 15, lineHeight: 21, marginTop: 8 },
  loader: { marginTop: 40 },
  error: { color: colors.error, fontSize: 14, marginTop: 18 },
  empty: { alignItems: 'center', padding: 30, borderRadius: 22, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, marginTop: 24 },
  emptyTitle: { color: colors.ink, fontSize: 19, fontWeight: '800' },
  emptyBody: { color: colors.muted, fontSize: 14, lineHeight: 21, textAlign: 'center', marginTop: 6 },
  card: { borderRadius: 20, borderWidth: 1, backgroundColor: colors.surface, padding: 18, marginTop: 14 },
  selfCard: { borderColor: '#BADCCD' },
  eventCard: { borderColor: '#D9D5E8' },
  cardTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10 },
  badge: { backgroundColor: colors.primarySoft, borderRadius: 99, paddingHorizontal: 10, paddingVertical: 6 },
  eventBadge: { backgroundColor: '#ECE9F5' },
  badgeText: { color: colors.primary, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 0.7 },
  eventBadgeText: { color: '#5B4A85' },
  timestamp: { color: colors.muted, fontSize: 12, flexShrink: 1, textAlign: 'right' },
  scoreRow: { flexDirection: 'row', alignItems: 'baseline', marginTop: 14 },
  score: { color: colors.ink, fontSize: 34, fontWeight: '800' },
  outOf: { color: colors.muted, fontSize: 14, marginLeft: 4 },
  detail: { color: colors.primary, fontSize: 13, fontWeight: '700', marginTop: 7 },
  summary: { color: colors.ink, fontSize: 16, lineHeight: 23, marginTop: 14 },
  reporter: { color: colors.muted, fontSize: 12, textTransform: 'capitalize', marginTop: 14 },
});
