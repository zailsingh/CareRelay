import { Ionicons } from '@expo/vector-icons';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Modal,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { buildEventMetadata } from '@/components/QuickAddCareEvent';
import { SymptomSelector } from '@/components/SymptomSelector';
import {
  api,
  careEventLabels,
  careEventTypes,
  CareEventType,
  ChatCareEventDraft,
  SymptomKind,
} from '@/lib/api';
import { useAuth } from '@/providers/AuthProvider';
import { useCareProfiles } from '@/providers/CareProfileProvider';
import { colors } from '@/theme/colors';

type Props = {
  draft: ChatCareEventDraft | null;
  onClose: () => void;
};

export function ChatToCareEventModal({ draft, onClose }: Props) {
  const { token } = useAuth();
  const { activeProfile, notifyCareEventChanged } = useCareProfiles();
  const [eventType, setEventType] = useState<CareEventType>('family_observation');
  const [occurredAt, setOccurredAt] = useState('');
  const [summary, setSummary] = useState('');
  const [symptoms, setSymptoms] = useState<SymptomKind[]>([]);
  const [medicationName, setMedicationName] = useState('');
  const [duration, setDuration] = useState('');
  const [provider, setProvider] = useState('');
  const [injuryObserved, setInjuryObserved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!draft) return;
    setEventType('family_observation');
    setOccurredAt(draft.occurred_at);
    setSummary(draft.summary);
    setSymptoms([]);
    setMedicationName('');
    setDuration('');
    setProvider('');
    setInjuryObserved(false);
    setError(null);
  }, [draft]);

  const confirm = async () => {
    if (!draft || !token || !activeProfile) return;
    if (!summary.trim()) {
      setError('Add a short factual summary.');
      return;
    }
    const parsedTime = new Date(occurredAt);
    if (Number.isNaN(parsedTime.getTime())) {
      setError('Use a valid date and time with a timezone.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.createCareEvent(token, activeProfile.id, {
        event_type: eventType,
        occurred_at: parsedTime.toISOString(),
        summary: summary.trim(),
        metadata: buildEventMetadata(eventType, {
          symptoms,
          medicationName,
          duration,
          provider,
          injuryObserved,
        }),
        confirmation_status: 'confirmed',
        source_chat_message_id: draft.source_chat_message_id,
      });
      notifyCareEventChanged();
      onClose();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to add this care event.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <Modal
      visible={draft !== null}
      animationType="slide"
      presentationStyle="pageSheet"
      onRequestClose={onClose}
    >
      <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
        <View style={styles.header}>
          <View style={styles.headerCopy}>
            <Text style={styles.eyebrow}>Chat → care record</Text>
            <Text style={styles.title}>Review draft</Text>
          </View>
          <Pressable accessibilityRole="button" accessibilityLabel="Close draft" onPress={onClose} style={styles.close}>
            <Ionicons name="close" size={24} color={colors.ink} />
          </Pressable>
        </View>
        <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
          <Text style={styles.notice}>
            Nothing has been saved. Choose the event type, review every field, then confirm.
          </Text>
          <Text style={styles.label}>Event type</Text>
          <View style={styles.types}>
            {careEventTypes.map((type) => {
              const selected = type === eventType;
              return (
                <Pressable
                  key={type}
                  accessibilityRole="button"
                  accessibilityState={{ selected }}
                  onPress={() => setEventType(type)}
                  style={[styles.typeButton, selected && styles.typeSelected]}
                >
                  <Text style={[styles.typeText, selected && styles.typeTextSelected]}>
                    {careEventLabels[type]}
                  </Text>
                </Pressable>
              );
            })}
          </View>
          <Text style={styles.label}>Occurred at</Text>
          <TextInput
            accessibilityLabel="Care event occurred at"
            autoCapitalize="none"
            onChangeText={setOccurredAt}
            style={styles.input}
            value={occurredAt}
          />
          <Text style={styles.label}>Summary</Text>
          <TextInput
            accessibilityLabel="Care event summary"
            maxLength={2000}
            multiline
            onChangeText={setSummary}
            style={styles.summaryInput}
            textAlignVertical="top"
            value={summary}
          />
          {eventType === 'symptom_observation' ? (
            <><Text style={styles.label}>Observed symptoms</Text><SymptomSelector selected={symptoms} onChange={setSymptoms} /></>
          ) : null}
          {eventType === 'medication_taken' || eventType === 'medication_missed' ? (
            <><Text style={styles.label}>Medication — optional</Text><TextInput accessibilityLabel="Medication name" onChangeText={setMedicationName} style={styles.input} value={medicationName} /></>
          ) : null}
          {eventType === 'activity' || eventType === 'sleep_observation' ? (
            <><Text style={styles.label}>{eventType === 'activity' ? 'Duration in minutes' : 'Duration in hours'} — optional</Text><TextInput accessibilityLabel="Duration" keyboardType="decimal-pad" onChangeText={setDuration} style={styles.input} value={duration} /></>
          ) : null}
          {eventType === 'appointment' ? (
            <><Text style={styles.label}>Provider — optional</Text><TextInput accessibilityLabel="Appointment provider" onChangeText={setProvider} style={styles.input} value={provider} /></>
          ) : null}
          {eventType === 'fall' ? (
            <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: injuryObserved }} onPress={() => setInjuryObserved((value) => !value)} style={styles.checkbox}>
              <Ionicons name={injuryObserved ? 'checkbox' : 'square-outline'} size={25} color={colors.primary} />
              <Text style={styles.checkboxText}>An injury was observed</Text>
            </Pressable>
          ) : null}
          <Text style={styles.help}>This creates a separate care record. It does not change or reinterpret the chat message.</Text>
          {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
          <Pressable accessibilityRole="button" disabled={saving} onPress={() => void confirm()} style={[styles.confirm, saving && styles.disabled]}>
            {saving ? <ActivityIndicator color={colors.surface} /> : <Text style={styles.confirmText}>Confirm and add to care record</Text>}
          </Pressable>
        </ScrollView>
      </SafeAreaView>
    </Modal>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', borderBottomWidth: 1, borderBottomColor: colors.border, paddingHorizontal: 20, paddingVertical: 14 },
  headerCopy: { flex: 1 },
  eyebrow: { color: colors.primary, fontSize: 11, fontWeight: '800', letterSpacing: 1, textTransform: 'uppercase' },
  title: { color: colors.ink, fontSize: 27, fontWeight: '800', marginTop: 3 },
  close: { alignItems: 'center', justifyContent: 'center', width: 48, height: 48, borderRadius: 16, backgroundColor: colors.surface },
  content: { padding: 20, paddingBottom: 40 },
  notice: { color: colors.warning, fontSize: 14, lineHeight: 21, padding: 14, borderRadius: 14, backgroundColor: '#FFF4E5' },
  label: { color: colors.ink, fontSize: 14, fontWeight: '800', marginTop: 18, marginBottom: 9 },
  types: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  typeButton: { minHeight: 46, paddingHorizontal: 13, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
  typeSelected: { backgroundColor: colors.primarySoft, borderColor: colors.primary },
  typeText: { color: colors.muted, fontSize: 13, fontWeight: '700' },
  typeTextSelected: { color: colors.primary },
  input: { minHeight: 52, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, color: colors.ink, fontSize: 15, paddingHorizontal: 14 },
  summaryInput: { minHeight: 104, borderRadius: 15, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, color: colors.ink, fontSize: 16, padding: 14 },
  checkbox: { minHeight: 54, flexDirection: 'row', gap: 10, alignItems: 'center', marginTop: 18 },
  checkboxText: { color: colors.ink, fontSize: 15, fontWeight: '600' },
  help: { color: colors.muted, fontSize: 13, lineHeight: 19, marginTop: 22 },
  error: { color: colors.error, fontSize: 14, marginTop: 14 },
  confirm: { minHeight: 56, borderRadius: 16, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center', marginTop: 18 },
  confirmText: { color: colors.surface, fontSize: 16, fontWeight: '800' },
  disabled: { opacity: 0.6 },
});
