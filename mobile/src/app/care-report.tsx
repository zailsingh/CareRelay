import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useMemo, useState } from 'react';
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
import Svg, { Circle } from 'react-native-svg';

import { ProfileSelector } from '@/components/ProfileSelector';
import { WellbeingChart } from '@/components/WellbeingChart';
import {
  api,
  CareReport,
  ReportEvidence,
  ReportRequest,
} from '@/lib/api';
import { addCalendarDays, dateInTimezone, formatCheckinTime } from '@/lib/dates';
import { shareCareReport } from '@/lib/reports';
import { useAuth } from '@/providers/AuthProvider';
import { useCareProfiles } from '@/providers/CareProfileProvider';
import { colors } from '@/theme/colors';

const choices: Array<{ value: ReportRequest['period']; label: string }> = [
  { value: '7d', label: '7 days' },
  { value: '30d', label: '30 days' },
  { value: '90d', label: '90 days' },
  { value: 'custom', label: 'Custom' },
];

export default function CareReportScreen() {
  const router = useRouter();
  const { token } = useAuth();
  const { activeProfile } = useCareProfiles();
  const today = activeProfile
    ? dateInTimezone(new Date(), activeProfile.timezone)
    : new Date().toISOString().slice(0, 10);
  const [period, setPeriod] = useState<ReportRequest['period']>('30d');
  const [startDate, setStartDate] = useState(addCalendarDays(today, -29));
  const [endDate, setEndDate] = useState(today);
  const [report, setReport] = useState<CareReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [sharing, setSharing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [evidence, setEvidence] = useState<ReportEvidence[] | null>(null);

  const payload = useMemo<ReportRequest>(() => period === 'custom'
    ? { period, start_date: startDate, end_date: endDate }
    : { period }, [period, startDate, endDate]);

  const generate = async () => {
    if (!token || !activeProfile) return;
    setLoading(true);
    setError(null);
    try {
      setReport(await api.reportPreview(token, activeProfile.id, payload));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to prepare the report.');
    } finally {
      setLoading(false);
    }
  };

  const share = async () => {
    if (!token || !activeProfile) return;
    setSharing(true);
    setError(null);
    try {
      await shareCareReport(token, activeProfile.id, activeProfile.name, payload);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to share the PDF.');
    } finally {
      setSharing(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top', 'bottom']}>
      <ScrollView contentContainerStyle={styles.content}>
        <View style={styles.header}>
          <Pressable accessibilityRole="button" accessibilityLabel="Back" onPress={() => router.back()} style={styles.iconButton}>
            <Ionicons name="chevron-back" size={24} color={colors.ink} />
          </Pressable>
          <View style={styles.headerCopy}>
            <Text style={styles.brand}>CareRelay</Text>
            <Text accessibilityRole="header" style={styles.title}>Prepare for appointment</Text>
          </View>
        </View>
        <Text style={styles.subtitle}>A factual, evidence-backed summary of information recorded in CareRelay.</Text>
        <ProfileSelector />

        <View style={styles.card}>
          <Text style={styles.eyebrow}>REPORT PERIOD</Text>
          <View style={styles.periodRow}>
            {choices.map((choice) => (
              <Pressable
                key={choice.value}
                accessibilityRole="button"
                accessibilityState={{ selected: period === choice.value }}
                onPress={() => setPeriod(choice.value)}
                style={[styles.periodChoice, period === choice.value && styles.periodSelected]}
              >
                <Text style={[styles.periodText, period === choice.value && styles.periodTextSelected]}>{choice.label}</Text>
              </Pressable>
            ))}
          </View>
          {period === 'custom' ? (
            <View style={styles.dateRow}>
              <DateField label="Start date" value={startDate} onChange={setStartDate} />
              <DateField label="End date" value={endDate} onChange={setEndDate} />
            </View>
          ) : null}
          <Pressable
            accessibilityRole="button"
            accessibilityState={{ disabled: loading || !activeProfile }}
            disabled={loading || !activeProfile}
            onPress={generate}
            style={[styles.primaryButton, (loading || !activeProfile) && styles.disabled]}
          >
            {loading ? <ActivityIndicator color={colors.surface} /> : <Text style={styles.primaryText}>Generate report</Text>}
          </Pressable>
        </View>

        {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
        {report ? <ReportView report={report} onEvidence={setEvidence} /> : (
          !loading ? <View style={styles.empty}><Ionicons name="document-text-outline" size={34} color={colors.primary} /><Text style={styles.emptyTitle}>Ready when you are</Text><Text style={styles.emptyBody}>Choose a period to prepare a care summary for an appointment or family review.</Text></View> : null
        )}
        {report ? (
          <Pressable accessibilityRole="button" disabled={sharing} onPress={share} style={styles.shareButton}>
            {sharing ? <ActivityIndicator color={colors.primary} /> : <><Ionicons name="share-outline" size={20} color={colors.primary} /><Text style={styles.shareText}>Export and share PDF</Text></>}
          </Pressable>
        ) : null}
      </ScrollView>
      <EvidenceModal evidence={evidence} onClose={() => setEvidence(null)} />
    </SafeAreaView>
  );
}

function ReportView({ report, onEvidence }: { report: CareReport; onEvidence: (items: ReportEvidence[]) => void }) {
  return <View style={styles.report}>
    <View style={styles.reportHeader}><Text style={styles.eyebrow}>CARE RELAY SUMMARY</Text><Text style={styles.reportName}>{report.care_profile.subject_display_name}</Text><Text style={styles.periodLabel}>{report.period.start_date} – {report.period.end_date} · {report.period.timezone}</Text></View>
    <View style={styles.card}><Text style={styles.sectionTitle}>Summary</Text><Text style={styles.narrative}>{report.narrative_summary}</Text></View>
    <ExpandableSection title="Self-reported wellbeing" count={report.wellbeing.checkin_count}>
      {report.wellbeing.average === null ? <EmptySection text="No self-reported wellbeing check-ins were recorded during this period." /> : <><View style={styles.visualRow}><WellbeingDonut average={report.wellbeing.average} /><View style={styles.visualCopy}><Text style={styles.average}>{report.wellbeing.average} / 100</Text><Text style={styles.averageLabel}>Average self-reported wellbeing</Text><Text style={styles.detail}>{report.wellbeing.checkin_count} check-ins · range {report.wellbeing.minimum}–{report.wellbeing.maximum}</Text></View></View><WellbeingChart days={report.wellbeing.daily_averages} /><Text style={styles.detail}>{report.wellbeing.trend_statement}</Text><EvidenceButton onPress={() => onEvidence(report.wellbeing.evidence)} /></>}
    </ExpandableSection>
    <ExpandableSection title="Recorded symptoms" count={report.symptoms.length}>
      {report.symptoms.length ? report.symptoms.map((item) => <View key={item.kind} style={styles.symptomRow}><View style={styles.flex}><Text style={styles.itemTitle}>{item.label}</Text><View style={styles.barTrack}><View style={[styles.bar, { width: `${Math.min(100, item.recorded_count * 20)}%` }]} /></View></View><Text style={styles.count}>{item.recorded_count}</Text><Pressable accessibilityLabel={`Show evidence for ${item.label}`} onPress={() => onEvidence(item.evidence)}><Ionicons name="document-text-outline" size={20} color={colors.primary} /></Pressable></View>) : <EmptySection text="No symptoms were recorded during this period." />}
    </ExpandableSection>
    <ExpandableSection title="Care events" count={report.care_events.total_count}>
      <View style={styles.metricRow}><Metric label="Falls" value={report.falls.count} /><Metric label="Activity" value={report.care_events.activity_count} /><Metric label="Sleep" value={report.care_events.sleep_count} /></View>
      {report.care_events.items.map((item) => <View key={`${item.occurred_at}-${item.summary}`} style={styles.listItem}><Text style={styles.itemTitle}>{item.event_type.replaceAll('_', ' ')}</Text><Text style={styles.detail}>{item.summary}</Text><Text style={styles.itemMeta}>{formatCheckinTime(item.occurred_at)} · recorded by {item.entered_by}</Text><EvidenceButton onPress={() => onEvidence(item.evidence)} /></View>)}
      {!report.care_events.items.length ? <EmptySection text="No confirmed care events were recorded during this period." /> : null}
    </ExpandableSection>
    <ExpandableSection title="Medication record" count={report.medications.expected_scheduled_doses}>
      <View style={styles.medicationGrid}><Metric label="Taken" value={report.medications.taken} /><Metric label="Missed" value={report.medications.missed} /><Metric label="Skipped" value={report.medications.skipped} /><Metric label="No record" value={report.medications.not_recorded} /></View>
      <Text style={styles.noRecord}>No record is not counted as missed.</Text>
      {report.medications.evidence.length ? <EvidenceButton onPress={() => onEvidence(report.medications.evidence)} /> : null}
    </ExpandableSection>
    <ExpandableSection title="Appointments / notes" count={report.appointments.length}>
      {report.appointments.map((item) => <View key={`${item.occurred_at}-${item.summary}`} style={styles.listItem}><Text style={styles.itemTitle}>{item.summary}</Text><Text style={styles.detail}>{[item.provider, item.location].filter(Boolean).join(' · ')}</Text><Text style={styles.itemMeta}>{formatCheckinTime(item.occurred_at)}</Text><EvidenceButton onPress={() => onEvidence(item.evidence)} /></View>)}
      {!report.appointments.length ? <EmptySection text="No appointments were recorded during this period." /> : null}
    </ExpandableSection>
    <ExpandableSection title="Points to discuss" count={report.points_to_discuss.length}>{report.points_to_discuss.length ? report.points_to_discuss.map((item) => <Text key={item} style={styles.point}>• {item}</Text>) : <EmptySection text="No additional recorded points were identified." />}</ExpandableSection>
    <Text style={styles.disclaimer}>{report.disclaimer}</Text>
  </View>;
}

function ExpandableSection({ title, count, children }: { title: string; count: number; children: React.ReactNode }) {
  const [expanded, setExpanded] = useState(true);
  return <View style={styles.card}><Pressable accessibilityRole="button" accessibilityState={{ expanded }} onPress={() => setExpanded((value) => !value)} style={styles.sectionHeader}><View><Text style={styles.sectionTitle}>{title}</Text><Text style={styles.sectionCount}>{count} recorded</Text></View><Ionicons name={expanded ? 'chevron-up' : 'chevron-down'} size={21} color={colors.muted} /></Pressable>{expanded ? <View style={styles.sectionBody}>{children}</View> : null}</View>;
}

function DateField({ label, value, onChange }: { label: string; value: string; onChange: (value: string) => void }) {
  return <View style={styles.dateField}><Text style={styles.fieldLabel}>{label}</Text><TextInput accessibilityLabel={label} autoCapitalize="none" value={value} onChangeText={onChange} placeholder="YYYY-MM-DD" style={styles.input} /></View>;
}

function Metric({ label, value }: { label: string; value: number }) {
  return <View style={styles.metric}><Text style={styles.metricValue}>{value}</Text><Text style={styles.metricLabel}>{label}</Text></View>;
}

function WellbeingDonut({ average }: { average: number }) {
  const radius = 43; const circumference = 2 * Math.PI * radius;
  return <View accessible accessibilityLabel={`Average self-reported wellbeing ${average} out of 100`}><Svg width={108} height={108} viewBox="0 0 108 108"><Circle cx={54} cy={54} r={radius} stroke={colors.border} strokeWidth={10} fill="none" /><Circle cx={54} cy={54} r={radius} stroke={colors.primary} strokeWidth={10} fill="none" strokeLinecap="round" strokeDasharray={`${circumference}`} strokeDashoffset={circumference * (1 - average / 100)} rotation={-90} origin="54 54" /></Svg></View>;
}

function EvidenceButton({ onPress }: { onPress: () => void }) {
  return <Pressable accessibilityRole="button" onPress={onPress} style={styles.evidenceButton}><Ionicons name="document-text-outline" size={17} color={colors.primary} /><Text style={styles.evidenceText}>Show evidence</Text></Pressable>;
}

function EmptySection({ text }: { text: string }) { return <Text style={styles.emptySection}>{text}</Text>; }

function EvidenceModal({ evidence, onClose }: { evidence: ReportEvidence[] | null; onClose: () => void }) {
  const router = useRouter();
  const open = (item: ReportEvidence) => {
    if (item.record_type === 'medication' || item.record_type === 'medication_dose') {
      onClose(); router.push({ pathname: '/medications', params: { evidenceType: item.record_type, recordId: item.record_id } });
    }
  };
  return <Modal visible={evidence !== null} animationType="slide" onRequestClose={onClose}><SafeAreaView style={styles.safe}><View style={styles.modalHeader}><View><Text style={styles.eyebrow}>SOURCE RECORDS</Text><Text style={styles.modalTitle}>Report evidence</Text></View><Pressable accessibilityLabel="Close evidence" onPress={onClose} style={styles.iconButton}><Ionicons name="close" size={23} color={colors.ink} /></Pressable></View><ScrollView contentContainerStyle={styles.evidenceList}>{evidence?.map((item) => { const navigable = item.record_type.startsWith('medication'); return <Pressable key={`${item.record_type}-${item.record_id}`} accessibilityRole={navigable ? 'button' : undefined} onPress={() => navigable && open(item)} style={styles.evidenceCard}><Text style={styles.evidenceKind}>{item.record_type.replaceAll('_', ' ')}</Text><Text style={styles.itemTitle}>{item.label}</Text><Text style={styles.itemMeta}>{formatCheckinTime(item.occurred_at)}</Text>{navigable ? <Text style={styles.openRecord}>Open exact record →</Text> : null}</Pressable>; })}</ScrollView></SafeAreaView></Modal>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background }, content: { padding: 20, paddingBottom: 80, gap: 16 }, header: { flexDirection: 'row', alignItems: 'center', gap: 12 }, headerCopy: { flex: 1 }, iconButton: { width: 48, height: 48, borderRadius: 16, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border }, brand: { color: colors.primary, fontSize: 14, fontWeight: '800' }, title: { color: colors.ink, fontSize: 27, fontWeight: '800', marginTop: 2 }, subtitle: { color: colors.muted, fontSize: 15, lineHeight: 22 }, card: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: 21, padding: 18 }, eyebrow: { color: colors.primary, fontSize: 11, fontWeight: '800', letterSpacing: 1 }, periodRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginTop: 14 }, periodChoice: { paddingHorizontal: 14, paddingVertical: 10, borderRadius: 14, borderWidth: 1, borderColor: colors.border }, periodSelected: { backgroundColor: colors.primary, borderColor: colors.primary }, periodText: { color: colors.ink, fontWeight: '700' }, periodTextSelected: { color: colors.surface }, dateRow: { flexDirection: 'row', gap: 10, marginTop: 14 }, dateField: { flex: 1 }, fieldLabel: { color: colors.ink, fontSize: 12, fontWeight: '700' }, input: { minHeight: 48, borderWidth: 1, borderColor: colors.border, borderRadius: 13, color: colors.ink, paddingHorizontal: 11, marginTop: 6 }, primaryButton: { minHeight: 52, borderRadius: 15, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary, marginTop: 16 }, primaryText: { color: colors.surface, fontSize: 16, fontWeight: '800' }, disabled: { opacity: 0.5 }, error: { color: colors.error, fontSize: 14 }, empty: { alignItems: 'center', padding: 30, borderRadius: 20, backgroundColor: colors.primarySoft }, emptyTitle: { color: colors.ink, fontSize: 19, fontWeight: '800', marginTop: 10 }, emptyBody: { color: colors.muted, textAlign: 'center', lineHeight: 20, marginTop: 5 }, report: { gap: 14 }, reportHeader: { padding: 4 }, reportName: { color: colors.ink, fontSize: 25, fontWeight: '800', marginTop: 5 }, periodLabel: { color: colors.muted, marginTop: 4 }, sectionTitle: { color: colors.ink, fontSize: 19, fontWeight: '800' }, narrative: { color: colors.ink, fontSize: 15, lineHeight: 23, marginTop: 10 }, sectionHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' }, sectionCount: { color: colors.muted, fontSize: 12, marginTop: 2 }, sectionBody: { marginTop: 15 }, visualRow: { flexDirection: 'row', alignItems: 'center' }, visualCopy: { flex: 1, marginLeft: 10 }, average: { color: colors.ink, fontSize: 26, fontWeight: '800' }, averageLabel: { color: colors.primary, fontSize: 13, fontWeight: '800' }, detail: { color: colors.muted, lineHeight: 20, marginTop: 5 }, symptomRow: { flexDirection: 'row', alignItems: 'center', gap: 12, marginBottom: 15 }, flex: { flex: 1 }, itemTitle: { color: colors.ink, fontSize: 15, fontWeight: '700', textTransform: 'capitalize' }, barTrack: { height: 7, borderRadius: 4, backgroundColor: colors.border, marginTop: 7 }, bar: { height: 7, borderRadius: 4, backgroundColor: colors.primary }, count: { color: colors.ink, fontSize: 18, fontWeight: '800' }, metricRow: { flexDirection: 'row', gap: 8 }, medicationGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 }, metric: { flexGrow: 1, minWidth: 68, backgroundColor: colors.primarySoft, borderRadius: 15, padding: 12 }, metricValue: { color: colors.primary, fontSize: 23, fontWeight: '800' }, metricLabel: { color: colors.ink, fontSize: 11, marginTop: 2 }, noRecord: { color: colors.muted, fontSize: 12, marginTop: 10 }, listItem: { borderTopWidth: 1, borderTopColor: colors.border, paddingTop: 12, marginTop: 12 }, itemMeta: { color: colors.muted, fontSize: 12, marginTop: 5 }, evidenceButton: { flexDirection: 'row', alignItems: 'center', gap: 6, alignSelf: 'flex-start', marginTop: 10 }, evidenceText: { color: colors.primary, fontWeight: '800', fontSize: 13 }, emptySection: { color: colors.muted, lineHeight: 21 }, point: { color: colors.ink, lineHeight: 22, marginBottom: 7 }, disclaimer: { color: colors.muted, fontSize: 12, lineHeight: 18, paddingHorizontal: 8 }, shareButton: { minHeight: 54, borderRadius: 16, flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', borderWidth: 1, borderColor: colors.primary, backgroundColor: colors.surface }, shareText: { color: colors.primary, fontSize: 16, fontWeight: '800' }, modalHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 20, borderBottomWidth: 1, borderBottomColor: colors.border }, modalTitle: { color: colors.ink, fontSize: 25, fontWeight: '800', marginTop: 3 }, evidenceList: { padding: 20, gap: 12 }, evidenceCard: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: 17, padding: 16 }, evidenceKind: { color: colors.primary, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', marginBottom: 7 }, openRecord: { color: colors.primary, fontWeight: '800', marginTop: 9 },
});
