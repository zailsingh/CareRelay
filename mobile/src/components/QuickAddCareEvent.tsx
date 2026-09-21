import { Ionicons } from '@expo/vector-icons';
import { useState } from 'react';
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

import {
  api,
  careEventLabels,
  careEventTypes,
  CareEventType,
  SymptomKind,
} from '@/lib/api';
import { useAuth } from '@/providers/AuthProvider';
import { useCareProfiles } from '@/providers/CareProfileProvider';
import { colors } from '@/theme/colors';
import { SymptomSelector } from './SymptomSelector';

type Details = {
  symptoms: SymptomKind[];
  medicationName: string;
  duration: string;
  provider: string;
  injuryObserved: boolean;
};

export function buildEventMetadata(
  eventType: CareEventType,
  details: Details,
): Record<string, unknown> {
  if (eventType === 'symptom_observation') return { symptoms: details.symptoms };
  if (eventType === 'medication_taken' || eventType === 'medication_missed') {
    return details.medicationName.trim()
      ? { medication_name: details.medicationName.trim() }
      : {};
  }
  if (eventType === 'activity') {
    const minutes = Number.parseInt(details.duration, 10);
    return Number.isFinite(minutes) ? { duration_minutes: minutes } : {};
  }
  if (eventType === 'sleep_observation') {
    const hours = Number.parseFloat(details.duration);
    return Number.isFinite(hours) ? { duration_hours: hours } : {};
  }
  if (eventType === 'appointment') {
    return details.provider.trim() ? { provider: details.provider.trim() } : {};
  }
  if (eventType === 'fall') return { injury_observed: details.injuryObserved };
  return {};
}

export function QuickAddCareEvent() {
  const { token } = useAuth();
  const { activeProfile, notifyCareEventChanged } = useCareProfiles();
  const [visible, setVisible] = useState(false);
  const [eventType, setEventType] = useState<CareEventType>('family_observation');
  const [summary, setSummary] = useState('');
  const [symptoms, setSymptoms] = useState<SymptomKind[]>([]);
  const [medicationName, setMedicationName] = useState('');
  const [duration, setDuration] = useState('');
  const [provider, setProvider] = useState('');
  const [injuryObserved, setInjuryObserved] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!activeProfile || !['admin', 'family', 'carer'].includes(activeProfile.role)) return null;

  const reset = () => {
    setSummary('');
    setSymptoms([]);
    setMedicationName('');
    setDuration('');
    setProvider('');
    setInjuryObserved(false);
    setError(null);
  };

  const close = () => {
    if (!saving) {
      setVisible(false);
      reset();
    }
  };

  const save = async () => {
    if (!token || !summary.trim()) {
      setError('Add a short factual summary.');
      return;
    }
    setSaving(true);
    setError(null);
    try {
      await api.createCareEvent(token, activeProfile.id, {
        event_type: eventType,
        occurred_at: new Date().toISOString(),
        summary: summary.trim(),
        metadata: buildEventMetadata(eventType, {
          symptoms,
          medicationName,
          duration,
          provider,
          injuryObserved,
        }),
      });
      notifyCareEventChanged();
      setVisible(false);
      reset();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to save this care event.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <>
      <Pressable accessibilityRole="button" onPress={() => setVisible(true)} style={styles.openButton}>
        <Ionicons name="add" size={23} color={colors.surface} />
        <Text style={styles.openText}>Quick add</Text>
      </Pressable>
      <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={close}>
        <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
          <View style={styles.modalHeader}>
            <View>
              <Text style={styles.eyebrow}>Care record</Text>
              <Text style={styles.title}>Quick add</Text>
            </View>
            <Pressable accessibilityRole="button" accessibilityLabel="Close quick add" onPress={close} style={styles.close}>
              <Ionicons name="close" size={24} color={colors.ink} />
            </Pressable>
          </View>
          <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
            <Text style={styles.label}>What happened?</Text>
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
                    <Text style={[styles.typeText, selected && styles.typeTextSelected]}>{careEventLabels[type]}</Text>
                  </Pressable>
                );
              })}
            </View>

            <Text style={styles.label}>Short factual summary</Text>
            <TextInput
              accessibilityLabel="Care event summary"
              multiline
              maxLength={2000}
              onChangeText={setSummary}
              placeholder="What did you observe?"
              placeholderTextColor={colors.muted}
              style={styles.summaryInput}
              textAlignVertical="top"
              value={summary}
            />

            {eventType === 'symptom_observation' ? (
              <><Text style={styles.label}>Observed symptoms</Text><SymptomSelector selected={symptoms} onChange={setSymptoms} /></>
            ) : null}
            {(eventType === 'medication_taken' || eventType === 'medication_missed') ? (
              <><Text style={styles.label}>Medication — optional</Text><TextInput accessibilityLabel="Medication name" value={medicationName} onChangeText={setMedicationName} style={styles.input} /></>
            ) : null}
            {(eventType === 'activity' || eventType === 'sleep_observation') ? (
              <><Text style={styles.label}>{eventType === 'activity' ? 'Duration in minutes' : 'Duration in hours'} — optional</Text><TextInput accessibilityLabel="Duration" keyboardType="decimal-pad" value={duration} onChangeText={setDuration} style={styles.input} /></>
            ) : null}
            {eventType === 'appointment' ? (
              <><Text style={styles.label}>Provider — optional</Text><TextInput accessibilityLabel="Appointment provider" value={provider} onChangeText={setProvider} style={styles.input} /></>
            ) : null}
            {eventType === 'fall' ? (
              <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: injuryObserved }} onPress={() => setInjuryObserved((value) => !value)} style={styles.checkbox}>
                <Ionicons name={injuryObserved ? 'checkbox' : 'square-outline'} size={25} color={colors.primary} />
                <Text style={styles.checkboxText}>An injury was observed</Text>
              </Pressable>
            ) : null}
            <Text style={styles.help}>This records an observation. It does not change anyone’s self-reported wellbeing score.</Text>
            {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
            <Pressable accessibilityRole="button" disabled={saving} onPress={save} style={[styles.save, saving && styles.disabled]}>
              {saving ? <ActivityIndicator color={colors.surface} /> : <Text style={styles.saveText}>Add to care record</Text>}
            </Pressable>
          </ScrollView>
        </SafeAreaView>
      </Modal>
    </>
  );
}

const styles = StyleSheet.create({
  openButton: { minHeight: 50, borderRadius: 15, backgroundColor: colors.primary, flexDirection: 'row', gap: 7, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 17 },
  openText: { color: colors.surface, fontSize: 15, fontWeight: '800' },
  safe: { flex: 1, backgroundColor: colors.background },
  modalHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 20, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.border },
  eyebrow: { color: colors.primary, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1 },
  title: { color: colors.ink, fontSize: 27, fontWeight: '800' },
  close: { width: 48, height: 48, borderRadius: 16, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
  content: { padding: 20, paddingBottom: 40 },
  label: { color: colors.ink, fontSize: 14, fontWeight: '800', marginTop: 18, marginBottom: 9 },
  types: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  typeButton: { minHeight: 46, paddingHorizontal: 13, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' },
  typeSelected: { backgroundColor: colors.primarySoft, borderColor: colors.primary },
  typeText: { color: colors.muted, fontSize: 13, fontWeight: '700' },
  typeTextSelected: { color: colors.primary },
  summaryInput: { minHeight: 104, borderRadius: 15, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, color: colors.ink, fontSize: 16, padding: 14 },
  input: { minHeight: 52, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, color: colors.ink, fontSize: 16, paddingHorizontal: 14 },
  checkbox: { minHeight: 54, flexDirection: 'row', gap: 10, alignItems: 'center', marginTop: 18 },
  checkboxText: { color: colors.ink, fontSize: 15, fontWeight: '600' },
  help: { color: colors.muted, fontSize: 13, lineHeight: 19, marginTop: 22 },
  error: { color: colors.error, fontSize: 14, marginTop: 14 },
  save: { minHeight: 56, borderRadius: 16, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center', marginTop: 18 },
  saveText: { color: colors.surface, fontSize: 16, fontWeight: '800' },
  disabled: { opacity: 0.6 },
});

