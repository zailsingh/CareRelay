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
import Svg, { Circle } from 'react-native-svg';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ProfileSelector } from '@/components/ProfileSelector';
import { WellbeingChart } from '@/components/WellbeingChart';
import { api, AskEvidence, AskResponse } from '@/lib/api';
import { evidenceKindLabel, wellbeingDisclaimer } from '@/lib/ask';
import { formatCheckinTime } from '@/lib/dates';
import { useAuth } from '@/providers/AuthProvider';
import { useCareProfiles } from '@/providers/CareProfileProvider';
import { colors } from '@/theme/colors';

const examples = [
  'How has Mum been feeling over the last 7 days?',
  'Was this week better than last week?',
  'What symptoms have been reported most often?',
  'Have there been any falls recently?',
];

type SessionAnswer = { question: string; result: AskResponse };

export default function AskAiScreen() {
  const { token } = useAuth();
  const { activeProfile } = useCareProfiles();
  const [question, setQuestion] = useState('');
  const [history, setHistory] = useState<SessionAnswer[]>([]);
  const [evidence, setEvidence] = useState<AskEvidence[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (suggested?: string) => {
    const value = (suggested ?? question).trim();
    if (!token || !activeProfile || !value || loading) return;
    setQuestion(value);
    setLoading(true);
    setError(null);
    try {
      const result = await api.ask(token, activeProfile.id, value);
      setHistory((current) => [{ question: value, result }, ...current]);
      setQuestion('');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Ask CareRelay is unavailable.');
    } finally {
      setLoading(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <Text style={styles.brand}>CareRelay</Text>
        <Text accessibilityRole="header" style={styles.title}>Ask CareRelay</Text>
        <Text style={styles.subtitle}>Answers are grounded in this profile’s confirmed care data.</Text>
        <ProfileSelector />

        <View style={styles.composerCard}>
          <TextInput
            accessibilityLabel="Question for CareRelay"
            maxLength={1000}
            multiline
            onChangeText={setQuestion}
            placeholder="Ask about recorded wellbeing, symptoms, or care events"
            placeholderTextColor={colors.muted}
            style={styles.input}
            value={question}
          />
          <Pressable accessibilityRole="button" disabled={!question.trim() || loading || !activeProfile} onPress={() => void submit()} style={[styles.askButton, (!question.trim() || loading || !activeProfile) && styles.disabled]}>
            {loading ? <ActivityIndicator color={colors.surface} /> : <><Ionicons name="sparkles" size={18} color={colors.surface} /><Text style={styles.askText}>Ask</Text></>}
          </Pressable>
        </View>
        <Text style={styles.exampleLabel}>Try asking</Text>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.examples}>
          {examples.map((example) => <Pressable key={example} accessibilityRole="button" onPress={() => void submit(example)} style={styles.example}><Text style={styles.exampleText}>{example}</Text></Pressable>)}
        </ScrollView>
        {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
        {!loading && history.length === 0 ? <View style={styles.empty}><Ionicons name="shield-checkmark-outline" size={32} color={colors.primary} /><Text style={styles.emptyTitle}>Evidence before explanation</Text><Text style={styles.emptyBody}>Statistics are calculated by CareRelay. AI summarizes them without diagnosing or changing the care record.</Text></View> : null}
        {history.map((entry, index) => <AnswerCard key={`${entry.question}-${index}`} entry={entry} onEvidence={setEvidence} />)}
      </ScrollView>
      <EvidenceModal evidence={evidence} onClose={() => setEvidence(null)} />
    </SafeAreaView>
  );
}

function AnswerCard({ entry, onEvidence }: { entry: SessionAnswer; onEvidence: (items: AskEvidence[]) => void }) {
  const visual = entry.result.visualization;
  return (
    <View style={styles.answerCard}>
      <Text style={styles.question}>{entry.question}</Text>
      <Text style={styles.period}>{entry.result.period.description} · {entry.result.period.timezone}</Text>
      {visual ? <><View style={styles.visualRow}><Donut score={visual.average} /><View style={styles.visualCopy}><Text style={styles.average}>{visual.average} / 100</Text><Text style={styles.averageLabel}>Average self-reported wellbeing</Text><Text style={styles.clinicalNote}>{wellbeingDisclaimer}</Text></View></View><WellbeingChart days={visual.daily_averages} /></> : null}
      <Text style={styles.answer}>{entry.result.answer}</Text>
      <Pressable accessibilityRole="button" disabled={entry.result.evidence.length === 0} onPress={() => onEvidence(entry.result.evidence)} style={[styles.evidenceButton, entry.result.evidence.length === 0 && styles.disabled]}>
        <Ionicons name="document-text-outline" size={18} color={colors.primary} />
        <Text style={styles.evidenceText}>{entry.result.evidence.length ? `Show evidence (${entry.result.evidence.length})` : 'No supporting records'}</Text>
      </Pressable>
    </View>
  );
}

function Donut({ score }: { score: number }) {
  const radius = 46;
  const circumference = 2 * Math.PI * radius;
  return <View accessible accessibilityLabel={`Average self-reported wellbeing ${score} out of 100`}><Svg width={112} height={112} viewBox="0 0 112 112"><Circle cx={56} cy={56} r={radius} stroke={colors.border} strokeWidth={10} fill="none" /><Circle cx={56} cy={56} r={radius} stroke={colors.primary} strokeWidth={10} fill="none" strokeLinecap="round" strokeDasharray={`${circumference}`} strokeDashoffset={circumference * (1 - score / 100)} rotation={-90} origin="56, 56" /></Svg></View>;
}

function EvidenceModal({ evidence, onClose }: { evidence: AskEvidence[] | null; onClose: () => void }) {
  return <Modal visible={evidence !== null} animationType="slide" presentationStyle="pageSheet" onRequestClose={onClose}><SafeAreaView style={styles.safe} edges={['top', 'bottom']}><View style={styles.modalHeader}><View><Text style={styles.brand}>Ask CareRelay</Text><Text style={styles.modalTitle}>Supporting records</Text></View><Pressable accessibilityRole="button" accessibilityLabel="Close evidence" onPress={onClose} style={styles.close}><Ionicons name="close" size={24} color={colors.ink} /></Pressable></View><ScrollView contentContainerStyle={styles.evidenceList}>{evidence?.map((item) => <View key={`${item.record_type}-${item.record_id}`} style={styles.evidenceCard}><Text style={styles.evidenceKind}>{evidenceKindLabel(item.record_type)}</Text><Text style={styles.evidenceLabel}>{item.label}</Text><Text style={styles.evidenceTime}>{formatCheckinTime(item.occurred_at)}</Text></View>)}</ScrollView></SafeAreaView></Modal>;
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background }, content: { paddingHorizontal: 20, paddingTop: 14, paddingBottom: 120 }, brand: { color: colors.primary, fontSize: 18, fontWeight: '800' }, title: { color: colors.ink, fontSize: 32, fontWeight: '800', marginTop: 9 }, subtitle: { color: colors.muted, fontSize: 15, lineHeight: 21, marginTop: 7 }, composerCard: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: 20, padding: 12, marginTop: 20 }, input: { minHeight: 88, color: colors.ink, fontSize: 16, lineHeight: 22, textAlignVertical: 'top', padding: 5 }, askButton: { minHeight: 50, borderRadius: 15, backgroundColor: colors.primary, flexDirection: 'row', gap: 7, alignItems: 'center', justifyContent: 'center' }, askText: { color: colors.surface, fontSize: 16, fontWeight: '800' }, disabled: { opacity: 0.45 }, exampleLabel: { color: colors.ink, fontSize: 13, fontWeight: '800', marginTop: 18 }, examples: { gap: 9, paddingVertical: 10 }, example: { width: 210, minHeight: 62, borderRadius: 15, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, justifyContent: 'center', padding: 12 }, exampleText: { color: colors.primary, fontSize: 13, lineHeight: 18, fontWeight: '700' }, error: { color: colors.error, marginTop: 12 }, empty: { alignItems: 'center', padding: 28, marginTop: 18 }, emptyTitle: { color: colors.ink, fontSize: 19, fontWeight: '800', marginTop: 10 }, emptyBody: { color: colors.muted, fontSize: 14, lineHeight: 21, textAlign: 'center', marginTop: 6 }, answerCard: { borderRadius: 21, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 18, marginTop: 18 }, question: { color: colors.ink, fontSize: 17, lineHeight: 23, fontWeight: '800' }, period: { color: colors.muted, fontSize: 12, marginTop: 5 }, visualRow: { flexDirection: 'row', alignItems: 'center', marginTop: 17 }, visualCopy: { flex: 1, marginLeft: 12 }, average: { color: colors.ink, fontSize: 28, fontWeight: '800' }, averageLabel: { color: colors.primary, fontSize: 13, fontWeight: '800', marginTop: 2 }, clinicalNote: { color: colors.muted, fontSize: 11, lineHeight: 16, marginTop: 5 }, answer: { color: colors.ink, fontSize: 16, lineHeight: 24, marginTop: 15 }, evidenceButton: { minHeight: 48, flexDirection: 'row', gap: 8, alignItems: 'center', justifyContent: 'center', borderRadius: 14, backgroundColor: colors.primarySoft, marginTop: 16 }, evidenceText: { color: colors.primary, fontSize: 14, fontWeight: '800' }, modalHeader: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', padding: 20, borderBottomWidth: 1, borderBottomColor: colors.border }, modalTitle: { color: colors.ink, fontSize: 26, fontWeight: '800', marginTop: 4 }, close: { width: 48, height: 48, borderRadius: 16, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center' }, evidenceList: { padding: 20, gap: 12 }, evidenceCard: { padding: 16, borderRadius: 17, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface }, evidenceKind: { color: colors.primary, fontSize: 11, fontWeight: '800', letterSpacing: 0.8 }, evidenceLabel: { color: colors.ink, fontSize: 16, lineHeight: 22, marginTop: 7 }, evidenceTime: { color: colors.muted, fontSize: 12, marginTop: 7 },
});
