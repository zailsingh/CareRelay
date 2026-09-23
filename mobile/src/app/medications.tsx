import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
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
  Medication,
  MedicationDose,
  MedicationDoseOccurrence,
  MedicationSchedule,
} from '@/lib/api';
import { dateInTimezone } from '@/lib/dates';
import {
  doseStatusLabel,
  formatMedicationClock,
  medicationScheduleSummary,
  scheduleSummary,
} from '@/lib/medications';
import { useAuth } from '@/providers/AuthProvider';
import { useCareProfiles } from '@/providers/CareProfileProvider';
import { colors } from '@/theme/colors';

const dayLabels = ['M', 'T', 'W', 'T', 'F', 'S', 'S'];
type DoseStatus = 'taken' | 'missed' | 'skipped';

export default function MedicationsScreen() {
  const router = useRouter();
  const params = useLocalSearchParams<{ evidenceType?: string; recordId?: string }>();
  const { token, user } = useAuth();
  const { activeProfile, notifyCareEventChanged } = useCareProfiles();
  const [medications, setMedications] = useState<Medication[]>([]);
  const [todayDoses, setTodayDoses] = useState<MedicationDoseOccurrence[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<Medication | MedicationDose | null>(null);
  const [medicationEditor, setMedicationEditor] = useState<Medication | 'new' | null>(null);
  const [scheduleEditor, setScheduleEditor] = useState<{
    medication: Medication;
    schedule?: MedicationSchedule;
  } | null>(null);
  const [doseEditor, setDoseEditor] = useState<{
    medication: Medication;
    occurrence?: MedicationDoseOccurrence;
    status: DoseStatus;
  } | null>(null);

  const canManage = !!activeProfile && ['admin', 'family', 'carer'].includes(activeProfile.role);
  const canRecord = canManage || activeProfile?.subject_user_id === user?.id;

  const load = useCallback(async () => {
    if (!token || !activeProfile) {
      setMedications([]);
      setTodayDoses([]);
      return;
    }
    setLoading(true);
    try {
      const today = dateInTimezone(new Date(), activeProfile.timezone);
      const [plans, doses] = await Promise.all([
        api.medications(token, activeProfile.id),
        api.medicationDoses(token, activeProfile.id, today, today),
      ]);
      setMedications(plans);
      setTodayDoses(doses);
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load medications.');
    } finally {
      setLoading(false);
    }
  }, [token, activeProfile]);

  useEffect(() => { void load(); }, [load]);

  useEffect(() => {
    if (!token || !activeProfile || !params.evidenceType || !params.recordId) return;
    const request = params.evidenceType === 'medication_dose'
      ? api.medicationDose(token, activeProfile.id, params.recordId)
      : params.evidenceType === 'medication'
        ? api.medication(token, activeProfile.id, params.recordId)
        : null;
    request?.then(setEvidence).catch((cause) => {
      setError(cause instanceof Error ? cause.message : 'Unable to open evidence.');
    });
  }, [token, activeProfile, params.evidenceType, params.recordId]);

  const activeMedications = useMemo(
    () => medications.filter((item) => item.active),
    [medications],
  );

  const deactivate = (medication: Medication) => Alert.alert(
    'Deactivate medication?',
    `${medication.name} will stop generating expected doses. Existing dose history stays intact.`,
    [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Deactivate', style: 'destructive', onPress: () => {
          if (!token || !activeProfile) return;
          void api.deactivateMedication(token, activeProfile.id, medication.id)
            .then(load)
            .catch((cause) => setError(cause instanceof Error ? cause.message : 'Unable to deactivate.'));
        },
      },
    ],
  );

  const removeSchedule = (medication: Medication, schedule: MedicationSchedule) => Alert.alert(
    'Remove schedule?',
    'Existing dose history will remain available.',
    [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Remove', style: 'destructive', onPress: () => {
          if (!token || !activeProfile) return;
          void api.removeMedicationSchedule(token, activeProfile.id, medication.id, schedule.id)
            .then(load)
            .catch((cause) => setError(cause instanceof Error ? cause.message : 'Unable to remove schedule.'));
        },
      },
    ],
  );

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.header}>
          <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={() => router.back()} style={styles.iconButton}>
            <Ionicons name="chevron-back" size={24} color={colors.ink} />
          </Pressable>
          <View style={styles.headerCopy}>
            <Text style={styles.brand}>CareRelay</Text>
            <Text accessibilityRole="header" style={styles.title}>Medications</Text>
          </View>
          {canManage ? <Pressable accessibilityRole="button" accessibilityLabel="Add medication" onPress={() => setMedicationEditor('new')} style={styles.iconButton}><Ionicons name="add" size={25} color={colors.primary} /></Pressable> : <View style={styles.iconSpacer} />}
        </View>
        <Text style={styles.subtitle}>Factual medication plans and dose records for {activeProfile?.name ?? 'the selected profile'}.</Text>
        <Text style={styles.safety}>CareRelay does not recommend doses or medication changes.</Text>

        {evidence ? <EvidenceBanner evidence={evidence} onClose={() => setEvidence(null)} /> : null}
        {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
        {loading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> : null}

        <Text style={styles.sectionLabel}>TODAY</Text>
        {!loading && todayDoses.length === 0 ? <EmptyCard text="No scheduled doses today." /> : null}
        {todayDoses.map((dose) => {
          const medication = medications.find((item) => item.id === dose.medication_id);
          if (!medication) return null;
          return <DoseCard key={dose.occurrence_key} dose={dose} canRecord={!!canRecord} onRecord={(doseStatus) => setDoseEditor({ medication, occurrence: dose, status: doseStatus })} />;
        })}

        <View style={styles.sectionRow}>
          <Text style={styles.sectionLabel}>MEDICATIONS</Text>
          <Text style={styles.count}>{activeMedications.length} active</Text>
        </View>
        {!loading && medications.length === 0 ? <EmptyCard text="No medications have been entered." /> : null}
        {medications.map((medication) => (
          <View key={medication.id} style={[styles.card, !medication.active && styles.inactiveCard]}>
            <View style={styles.cardHeader}>
              <View style={styles.flex}>
                <Text style={styles.medicationName}>{medication.name}{medication.strength_text ? ` ${medication.strength_text}` : ''}</Text>
                <Text style={styles.scheduleText}>{medicationScheduleSummary(medication)}</Text>
              </View>
              <Text style={[styles.statePill, !medication.active && styles.inactivePill]}>{medication.active ? 'ACTIVE' : 'INACTIVE'}</Text>
            </View>
            {medication.instructions_text ? <Text style={styles.instructions}>{medication.instructions_text}</Text> : null}
            {medication.schedules.filter((item) => item.active).map((schedule) => (
              <View key={schedule.id} style={styles.scheduleRow}>
                <Text style={styles.scheduleItem}>{scheduleSummary(schedule)}</Text>
                {canManage ? <View style={styles.inlineActions}><Pressable onPress={() => setScheduleEditor({ medication, schedule })}><Text style={styles.link}>Edit</Text></Pressable><Pressable onPress={() => removeSchedule(medication, schedule)}><Text style={styles.removeLink}>Remove</Text></Pressable></View> : null}
              </View>
            ))}
            {medication.active && medication.schedule_type === 'as_needed' && canRecord ? <Pressable accessibilityRole="button" onPress={() => setDoseEditor({ medication, status: 'taken' })} style={styles.secondaryButton}><Text style={styles.secondaryText}>Record as-needed dose taken</Text></Pressable> : null}
            {canManage ? <View style={styles.cardActions}><Pressable onPress={() => setMedicationEditor(medication)}><Text style={styles.link}>Edit medication</Text></Pressable>{medication.active && medication.schedule_type === 'scheduled' ? <Pressable onPress={() => setScheduleEditor({ medication })}><Text style={styles.link}>Add schedule</Text></Pressable> : null}{medication.active ? <Pressable onPress={() => deactivate(medication)}><Text style={styles.removeLink}>Deactivate</Text></Pressable> : null}</View> : null}
          </View>
        ))}
      </ScrollView>

      <MedicationEditor visible={medicationEditor} token={token} profileId={activeProfile?.id} onClose={() => setMedicationEditor(null)} onSaved={async () => { setMedicationEditor(null); await load(); }} />
      <ScheduleEditor visible={scheduleEditor} token={token} profileId={activeProfile?.id} onClose={() => setScheduleEditor(null)} onSaved={async () => { setScheduleEditor(null); await load(); }} />
      <DoseEditor visible={doseEditor} token={token} profileId={activeProfile?.id} onClose={() => setDoseEditor(null)} onSaved={async () => { setDoseEditor(null); notifyCareEventChanged(); await load(); }} />
    </SafeAreaView>
  );
}

function DoseCard({ dose, canRecord, onRecord }: { dose: MedicationDoseOccurrence; canRecord: boolean; onRecord: (status: DoseStatus) => void }) {
  return <View style={styles.card}><View style={styles.doseTop}><Text style={styles.doseTime}>{formatMedicationClock(dose.scheduled_local_time)}</Text><Text style={[styles.doseStatus, dose.status === 'missed' && styles.missed]}>{doseStatusLabel(dose)}</Text></View><Text style={styles.medicationName}>{dose.medication_name}{dose.medication_strength ? ` ${dose.medication_strength}` : ''}</Text>{dose.dose_record ? <Text style={styles.recordedBy}>Recorded by {dose.dose_record.recorded_by.display_name} · {new Date(dose.dose_record.recorded_at).toLocaleTimeString([], { hour: 'numeric', minute: '2-digit' })}</Text> : canRecord && dose.due_state !== 'upcoming' ? <View style={styles.doseActions}>{(['taken', 'missed', 'skipped'] as DoseStatus[]).map((status) => <Pressable key={status} accessibilityRole="button" onPress={() => onRecord(status)} style={styles.doseButton}><Text style={styles.doseButtonText}>{status === 'skipped' ? 'Skip' : status.charAt(0).toUpperCase() + status.slice(1)}</Text></Pressable>)}</View> : null}</View>;
}

function EvidenceBanner({ evidence, onClose }: { evidence: Medication | MedicationDose; onClose: () => void }) {
  const isDose = 'recorded_by' in evidence;
  return <View style={styles.evidenceBanner}><View style={styles.flex}><Text style={styles.evidenceEyebrow}>ASK CARERELAY EVIDENCE</Text><Text style={styles.medicationName}>{isDose ? `${evidence.medication_name}${evidence.medication_strength ? ` ${evidence.medication_strength}` : ''}` : `${evidence.name}${evidence.strength_text ? ` ${evidence.strength_text}` : ''}`}</Text><Text style={styles.instructions}>{isDose ? `${evidence.status.toUpperCase()} · scheduled ${formatMedicationClock(evidence.scheduled_local_time)} · recorded by ${evidence.recorded_by.display_name}` : medicationScheduleSummary(evidence)}</Text></View><Pressable accessibilityLabel="Close evidence detail" onPress={onClose}><Ionicons name="close" size={22} color={colors.ink} /></Pressable></View>;
}

function EmptyCard({ text }: { text: string }) {
  return <View style={styles.empty}><Text style={styles.emptyText}>{text}</Text></View>;
}

function MedicationEditor({ visible, token, profileId, onClose, onSaved }: { visible: Medication | 'new' | null; token: string | null; profileId?: string; onClose: () => void; onSaved: () => Promise<void> }) {
  const existing = visible && visible !== 'new' ? visible : null;
  const [name, setName] = useState('');
  const [strength, setStrength] = useState('');
  const [form, setForm] = useState('');
  const [instructions, setInstructions] = useState('');
  const [scheduleType, setScheduleType] = useState<'scheduled' | 'as_needed'>('scheduled');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    setName(existing?.name ?? ''); setStrength(existing?.strength_text ?? ''); setForm(existing?.form ?? ''); setInstructions(existing?.instructions_text ?? ''); setScheduleType(existing?.schedule_type ?? 'scheduled'); setError(null);
  }, [visible, existing]);
  const save = async () => {
    if (!token || !profileId || !name.trim()) return;
    setSaving(true); setError(null);
    try {
      const payload = { name: name.trim(), strength_text: strength.trim() || null, form: form.trim() || null, instructions_text: instructions.trim() || null, schedule_type: scheduleType };
      if (existing) await api.updateMedication(token, profileId, existing.id, payload);
      else await api.createMedication(token, profileId, payload);
      await onSaved();
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to save medication.'); } finally { setSaving(false); }
  };
  return <EditorModal visible={visible !== null} title={existing ? 'Edit medication' : 'Add medication'} onClose={onClose}><Field label="Name" value={name} onChange={setName} placeholder="Metformin" /><Field label="Strength — entered text" value={strength} onChange={setStrength} placeholder="500 mg" /><Field label="Form — optional" value={form} onChange={setForm} placeholder="Tablet" /><Field label="Instructions — entered text" value={instructions} onChange={setInstructions} placeholder="Take with evening meal" multiline /><Text style={styles.fieldLabel}>Schedule type</Text><View style={styles.choiceRow}>{(['scheduled', 'as_needed'] as const).map((choice) => <Pressable key={choice} onPress={() => setScheduleType(choice)} style={[styles.choice, scheduleType === choice && styles.choiceSelected]}><Text style={[styles.choiceText, scheduleType === choice && styles.choiceTextSelected]}>{choice === 'scheduled' ? 'Scheduled' : 'As needed'}</Text></Pressable>)}</View>{error ? <Text style={styles.error}>{error}</Text> : null}<SaveButton label="Save medication" saving={saving} disabled={!name.trim()} onPress={save} /></EditorModal>;
}

function ScheduleEditor({ visible, token, profileId, onClose, onSaved }: { visible: { medication: Medication; schedule?: MedicationSchedule } | null; token: string | null; profileId?: string; onClose: () => void; onSaved: () => Promise<void> }) {
  const [clock, setClock] = useState('08:00');
  const [days, setDays] = useState<number[]>([0, 1, 2, 3, 4, 5, 6]);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { setClock(visible?.schedule?.local_time.slice(0, 5) ?? '08:00'); setDays(visible?.schedule?.days_of_week ?? [0, 1, 2, 3, 4, 5, 6]); setError(null); }, [visible]);
  const validClock = /^([01]\d|2[0-3]):[0-5]\d$/.test(clock);
  const save = async () => {
    if (!visible || !token || !profileId || !validClock || !days.length) return;
    setSaving(true); setError(null);
    try {
      if (visible.schedule) await api.updateMedicationSchedule(token, profileId, visible.medication.id, visible.schedule.id, { local_time: clock, days_of_week: days });
      else await api.createMedicationSchedule(token, profileId, visible.medication.id, { local_time: clock, days_of_week: days });
      await onSaved();
    } catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to save schedule.'); } finally { setSaving(false); }
  };
  return <EditorModal visible={visible !== null} title={visible?.schedule ? 'Edit schedule' : 'Add schedule'} onClose={onClose}><Field label="Local time (24-hour)" value={clock} onChange={setClock} placeholder="08:00" /><Text style={styles.fieldLabel}>Days</Text><View style={styles.dayRow}>{dayLabels.map((label, day) => <Pressable key={`${label}-${day}`} onPress={() => setDays((current) => current.includes(day) ? current.filter((item) => item !== day) : [...current, day].sort())} style={[styles.day, days.includes(day) && styles.daySelected]}><Text style={[styles.dayText, days.includes(day) && styles.dayTextSelected]}>{label}</Text></Pressable>)}</View>{!validClock ? <Text style={styles.error}>Use a local time such as 08:00 or 20:00.</Text> : null}{error ? <Text style={styles.error}>{error}</Text> : null}<SaveButton label="Save schedule" saving={saving} disabled={!validClock || !days.length} onPress={save} /></EditorModal>;
}

function DoseEditor({ visible, token, profileId, onClose, onSaved }: { visible: { medication: Medication; occurrence?: MedicationDoseOccurrence; status: DoseStatus } | null; token: string | null; profileId?: string; onClose: () => void; onSaved: () => Promise<void> }) {
  const [note, setNote] = useState(''); const [saving, setSaving] = useState(false); const [error, setError] = useState<string | null>(null);
  useEffect(() => { setNote(''); setError(null); }, [visible]);
  const save = async () => {
    if (!visible || !token || !profileId) return;
    setSaving(true); setError(null);
    try { await api.recordMedicationDose(token, profileId, { medication_id: visible.medication.id, schedule_id: visible.occurrence?.schedule_id, scheduled_for: visible.occurrence?.scheduled_for ?? new Date().toISOString(), status: visible.status, note: note.trim() || null }); await onSaved(); } catch (cause) { setError(cause instanceof Error ? cause.message : 'Unable to record dose.'); } finally { setSaving(false); }
  };
  return <EditorModal visible={visible !== null} title={`Record ${visible?.status ?? 'dose'}`} onClose={onClose}>{visible ? <><Text style={styles.medicationName}>{visible.medication.name}{visible.medication.strength_text ? ` ${visible.medication.strength_text}` : ''}</Text>{visible.occurrence ? <Text style={styles.instructions}>Scheduled {formatMedicationClock(visible.occurrence.scheduled_local_time)}</Text> : <Text style={styles.instructions}>As-needed dose</Text>}<Field label="Factual note — optional" value={note} onChange={setNote} placeholder="What was recorded?" multiline /><Text style={styles.safety}>This records an outcome only. It does not change the medication plan.</Text></> : null}{error ? <Text style={styles.error}>{error}</Text> : null}<SaveButton label="Confirm dose record" saving={saving} disabled={!visible} onPress={save} /></EditorModal>;
}

function EditorModal({ visible, title, onClose, children }: { visible: boolean; title: string; onClose: () => void; children: React.ReactNode }) {
  return <Modal visible={visible} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}><SafeAreaView style={styles.safe} edges={['top', 'bottom']}><View style={styles.modalHeader}><Text style={styles.modalTitle}>{title}</Text><Pressable accessibilityLabel="Close" onPress={onClose} style={styles.iconButton}><Ionicons name="close" size={24} color={colors.ink} /></Pressable></View><ScrollView contentContainerStyle={styles.modalContent} keyboardShouldPersistTaps="handled">{children}</ScrollView></SafeAreaView></Modal>;
}

function Field({ label, value, onChange, placeholder, multiline = false }: { label: string; value: string; onChange: (value: string) => void; placeholder: string; multiline?: boolean }) {
  return <View><Text style={styles.fieldLabel}>{label}</Text><TextInput accessibilityLabel={label} value={value} onChangeText={onChange} placeholder={placeholder} placeholderTextColor={colors.muted} multiline={multiline} style={[styles.input, multiline && styles.multiline]} /></View>;
}

function SaveButton({ label, saving, disabled, onPress }: { label: string; saving: boolean; disabled: boolean; onPress: () => Promise<void> }) {
  return <Pressable accessibilityRole="button" accessibilityState={{ disabled: disabled || saving }} disabled={disabled || saving} onPress={() => void onPress()} style={[styles.primaryButton, (disabled || saving) && styles.disabled]}>{saving ? <ActivityIndicator color={colors.surface} /> : <Text style={styles.primaryText}>{label}</Text>}</Pressable>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background }, content: { padding: 20, paddingBottom: 80 }, header: { flexDirection: 'row', alignItems: 'center', gap: 12 }, headerCopy: { flex: 1 }, brand: { color: colors.primary, fontSize: 14, fontWeight: '800' }, title: { color: colors.ink, fontSize: 30, fontWeight: '800' }, subtitle: { color: colors.muted, fontSize: 15, lineHeight: 21, marginTop: 12 }, safety: { color: colors.muted, fontSize: 12, lineHeight: 17, marginTop: 8 }, iconButton: { width: 46, height: 46, borderRadius: 15, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border }, iconSpacer: { width: 46 }, loader: { margin: 24 }, error: { color: colors.error, marginTop: 12 }, sectionLabel: { color: colors.primary, fontSize: 12, fontWeight: '800', letterSpacing: 1, marginTop: 26, marginBottom: 8 }, sectionRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }, count: { color: colors.muted, fontSize: 12, marginTop: 18 }, card: { backgroundColor: colors.surface, borderRadius: 19, borderWidth: 1, borderColor: colors.border, padding: 16, marginTop: 10 }, inactiveCard: { opacity: 0.65 }, cardHeader: { flexDirection: 'row', gap: 10, alignItems: 'flex-start' }, flex: { flex: 1 }, medicationName: { color: colors.ink, fontSize: 17, fontWeight: '800' }, scheduleText: { color: colors.primary, fontSize: 13, marginTop: 5 }, statePill: { color: colors.primary, backgroundColor: colors.primarySoft, borderRadius: 99, paddingHorizontal: 9, paddingVertical: 5, fontSize: 10, fontWeight: '800' }, inactivePill: { color: colors.muted }, instructions: { color: colors.muted, fontSize: 13, lineHeight: 19, marginTop: 8 }, scheduleRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', gap: 10, borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 10, marginTop: 10 }, scheduleItem: { color: colors.ink, flex: 1, fontSize: 13 }, inlineActions: { flexDirection: 'row', gap: 12 }, cardActions: { flexDirection: 'row', flexWrap: 'wrap', gap: 18, marginTop: 16 }, link: { color: colors.primary, fontWeight: '800', fontSize: 13 }, removeLink: { color: colors.error, fontWeight: '700', fontSize: 13 }, secondaryButton: { minHeight: 46, borderRadius: 13, backgroundColor: colors.primarySoft, alignItems: 'center', justifyContent: 'center', marginTop: 14 }, secondaryText: { color: colors.primary, fontWeight: '800' }, empty: { backgroundColor: colors.surface, borderRadius: 18, padding: 22, borderWidth: 1, borderColor: colors.border }, emptyText: { color: colors.muted, textAlign: 'center' }, doseTop: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 7 }, doseTime: { color: colors.primary, fontSize: 18, fontWeight: '800' }, doseStatus: { color: colors.primary, fontSize: 12, fontWeight: '800' }, missed: { color: colors.error }, recordedBy: { color: colors.muted, fontSize: 12, marginTop: 8 }, doseActions: { flexDirection: 'row', gap: 8, marginTop: 14 }, doseButton: { flex: 1, minHeight: 42, borderRadius: 12, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primarySoft }, doseButtonText: { color: colors.primary, fontSize: 12, fontWeight: '800' }, evidenceBanner: { flexDirection: 'row', alignItems: 'flex-start', gap: 12, padding: 16, borderRadius: 18, backgroundColor: '#ECE9F5', marginTop: 18 }, evidenceEyebrow: { color: '#5B4A85', fontSize: 10, fontWeight: '800', letterSpacing: 0.8, marginBottom: 5 }, modalHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 20, borderBottomWidth: 1, borderBottomColor: colors.border }, modalTitle: { color: colors.ink, fontSize: 25, fontWeight: '800' }, modalContent: { padding: 20, paddingBottom: 60 }, fieldLabel: { color: colors.ink, fontSize: 13, fontWeight: '800', marginTop: 16, marginBottom: 7 }, input: { minHeight: 50, borderWidth: 1, borderColor: colors.border, borderRadius: 14, backgroundColor: colors.surface, color: colors.ink, paddingHorizontal: 14, fontSize: 16 }, multiline: { minHeight: 92, paddingTop: 13, textAlignVertical: 'top' }, choiceRow: { flexDirection: 'row', gap: 10 }, choice: { flex: 1, minHeight: 46, borderRadius: 13, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' }, choiceSelected: { backgroundColor: colors.primary, borderColor: colors.primary }, choiceText: { color: colors.ink, fontWeight: '700' }, choiceTextSelected: { color: colors.surface }, dayRow: { flexDirection: 'row', justifyContent: 'space-between' }, day: { width: 38, height: 38, borderRadius: 19, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' }, daySelected: { backgroundColor: colors.primary }, dayText: { color: colors.ink, fontWeight: '700' }, dayTextSelected: { color: colors.surface }, primaryButton: { minHeight: 54, borderRadius: 15, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center', marginTop: 24 }, primaryText: { color: colors.surface, fontWeight: '800', fontSize: 16 }, disabled: { opacity: 0.5 },
});
