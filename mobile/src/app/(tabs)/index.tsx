import { Ionicons } from '@expo/vector-icons';
import { useRouter } from 'expo-router';
import { useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ProfileSelector } from '@/components/ProfileSelector';
import { ScoreControl } from '@/components/ScoreControl';
import { SymptomSelector } from '@/components/SymptomSelector';
import { WellbeingChart } from '@/components/WellbeingChart';
import { api, SymptomKind, WellbeingCheckin, WellbeingSummary } from '@/lib/api';
import { addCalendarDays, dateInTimezone } from '@/lib/dates';
import { useAuth } from '@/providers/AuthProvider';
import { useCareProfiles } from '@/providers/CareProfileProvider';
import { colors } from '@/theme/colors';

export default function OverviewScreen() {
  const router = useRouter();
  const { token, user, signOut } = useAuth();
  const {
    activeProfile,
    profiles,
    loading: profilesLoading,
    error: profilesError,
    createProfile,
    wellbeingRevision,
    notifyWellbeingChanged,
  } = useCareProfiles();
  const [profileName, setProfileName] = useState('');
  const [latest, setLatest] = useState<WellbeingCheckin | null>(null);
  const [summary, setSummary] = useState<WellbeingSummary | null>(null);
  const [score, setScore] = useState(50);
  const [symptoms, setSymptoms] = useState<SymptomKind[]>([]);
  const [note, setNote] = useState('');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    if (!token || !activeProfile) {
      setLatest(null);
      setSummary(null);
      return;
    }
    let current = true;
    const endDate = dateInTimezone(new Date(), activeProfile.timezone);
    const startDate = addCalendarDays(endDate, -6);
    setLoading(true);
    Promise.all([
      api.checkins(token, activeProfile.id, 1),
      api.wellbeingSummary(token, activeProfile.id, startDate, endDate),
    ])
      .then(([checkins, result]) => {
        if (!current) return;
        setLatest(checkins[0] ?? null);
        setSummary(result);
        setError(null);
      })
      .catch((cause) => current && setError(cause instanceof Error ? cause.message : 'Unable to load wellbeing.'))
      .finally(() => current && setLoading(false));
    return () => { current = false; };
  }, [token, activeProfile, wellbeingRevision]);

  const handleCreateProfile = async () => {
    if (!profileName.trim()) return;
    try {
      await createProfile(profileName.trim());
      setProfileName('');
      setError(null);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to create care profile.');
    }
  };

  const saveCheckin = async () => {
    if (!token || !activeProfile || saving) return;
    setSaving(true);
    setSaved(false);
    setError(null);
    try {
      const created = await api.createCheckin(token, activeProfile.id, {
        score,
        occurred_at: new Date().toISOString(),
        symptoms,
        note: note.trim() || null,
      });
      setLatest(created);
      setSymptoms([]);
      setNote('');
      setSaved(true);
      notifyWellbeingChanged();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to save the check-in.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.topRow}>
          <View>
            <Text style={styles.brand}>CareRelay</Text>
            <Text style={styles.greeting}>Hello, {user?.display_name ?? 'there'}</Text>
          </View>
          <Pressable accessibilityRole="button" accessibilityLabel="Sign out" onPress={signOut} style={styles.signOut}>
            <Ionicons name="log-out-outline" size={22} color={colors.primary} />
          </Pressable>
        </View>

        <ProfileSelector />
        {profilesLoading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> : null}
        {profilesError ? <Text accessibilityRole="alert" style={styles.error}>{profilesError}</Text> : null}
        {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}

        {activeProfile ? (
          <Pressable accessibilityRole="button" onPress={() => router.push('/medications')} style={styles.medicationLink}>
            <View style={styles.medicationIcon}><Ionicons name="medical-outline" size={23} color={colors.primary} /></View>
            <View style={styles.medicationCopy}><Text style={styles.medicationTitle}>Medications</Text><Text style={styles.medicationBody}>Today's expected doses and medication plans</Text></View>
            <Ionicons name="chevron-forward" size={21} color={colors.muted} />
          </Pressable>
        ) : null}

        {!profilesLoading && profiles.length === 0 ? (
          <View style={styles.card}>
            <Ionicons name="heart-outline" size={30} color={colors.primary} />
            <Text style={styles.cardTitle}>Create your first care profile</Text>
            <Text style={styles.body}>A care profile is the private space shared by a family and care team.</Text>
            <TextInput
              accessibilityLabel="Care profile name"
              placeholder="Who are you caring for?"
              placeholderTextColor={colors.muted}
              value={profileName}
              onChangeText={setProfileName}
              style={styles.input}
            />
            <Pressable accessibilityRole="button" onPress={handleCreateProfile} style={styles.primaryButton}>
              <Text style={styles.primaryButtonText}>Create care profile</Text>
            </Pressable>
          </View>
        ) : null}

        {activeProfile ? (
          <>
            <View style={[styles.card, styles.currentCard]}>
              <View>
                <Text style={styles.eyebrow}>Current wellbeing</Text>
                <Text style={styles.howIFeel}>How I feel</Text>
                <Text style={styles.subjective}>Self-reported and subjective</Text>
              </View>
              {loading && !latest ? <ActivityIndicator color={colors.primary} /> : (
                <View style={styles.scoreReadout}>
                  <Text style={styles.currentScore}>{latest?.score ?? '—'}</Text>
                  <Text style={styles.currentOutOf}>/ 100</Text>
                </View>
              )}
            </View>

            {activeProfile.subject_user_id === user?.id ? (
              <View style={styles.card}>
                <Text style={styles.eyebrow}>New self report</Text>
                <Text style={styles.cardTitle}>How do you feel right now?</Text>
                <Text style={styles.body}>Choose the number that feels right to you. CareRelay will never infer or change it.</Text>
                <ScoreControl value={score} onChange={setScore} />
                <Text style={styles.fieldLabel}>Symptoms or positives — optional</Text>
                <SymptomSelector selected={symptoms} onChange={setSymptoms} />
                <Text style={styles.fieldLabel}>Note — optional</Text>
                <TextInput
                  accessibilityLabel="Optional wellbeing note"
                  multiline
                  maxLength={2000}
                  onChangeText={setNote}
                  placeholder="Anything you want your care circle to know?"
                  placeholderTextColor={colors.muted}
                  style={[styles.input, styles.noteInput]}
                  textAlignVertical="top"
                  value={note}
                />
                {saved ? <Text accessibilityRole="alert" style={styles.success}>Check-in saved to the timeline.</Text> : null}
                <Pressable
                  accessibilityRole="button"
                  accessibilityState={{ disabled: saving }}
                  disabled={saving}
                  onPress={saveCheckin}
                  style={({ pressed }) => [styles.primaryButton, pressed && styles.primaryPressed, saving && styles.disabled]}
                >
                  {saving ? <ActivityIndicator color={colors.surface} /> : <Text style={styles.primaryButtonText}>Save check-in</Text>}
                </Pressable>
              </View>
            ) : (
              <View style={styles.viewOnly}>
                <Ionicons name="eye-outline" size={22} color={colors.primary} />
                <Text style={styles.viewOnlyText}>{activeProfile.subject_user_id ? 'You can view self reports. Only the person this profile is about can record how they feel.' : 'An administrator needs to choose who this care profile is about before self reports can be recorded.'}</Text>
              </View>
            )}

            <View style={styles.card}>
              <Text style={styles.eyebrow}>Last 7 days</Text>
              <Text style={styles.cardTitle}>Wellbeing overview</Text>
              <View style={styles.statsRow}>
                <View style={styles.stat}>
                  <Text style={styles.statValue}>{summary?.average_score ?? '—'}</Text>
                  <Text style={styles.statLabel}>Average / 100</Text>
                </View>
                <View style={styles.statDivider} />
                <View style={styles.stat}>
                  <Text style={styles.statValue}>{summary?.checkin_count ?? 0}</Text>
                  <Text style={styles.statLabel}>Check-ins</Text>
                </View>
              </View>
              {summary ? <WellbeingChart days={summary.daily_averages} /> : <ActivityIndicator color={colors.primary} style={styles.loader} />}
              <Text style={styles.disclaimer}>These are averages of self-reported wellbeing, not clinical conclusions.</Text>
            </View>
          </>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  content: { paddingHorizontal: 20, paddingTop: 12, paddingBottom: 120, gap: 16 },
  topRow: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginBottom: 2 },
  brand: { color: colors.primary, fontSize: 20, fontWeight: '800' },
  greeting: { color: colors.ink, fontSize: 14, marginTop: 2 },
  signOut: { width: 48, height: 48, borderRadius: 16, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, alignItems: 'center', justifyContent: 'center' },
  loader: { marginVertical: 18 },
  error: { color: colors.error, fontSize: 14 },
  card: { backgroundColor: colors.surface, borderRadius: 22, borderWidth: 1, borderColor: colors.border, padding: 20 },
  currentCard: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', marginTop: 2 },
  eyebrow: { color: colors.primary, fontSize: 12, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1 },
  howIFeel: { color: colors.ink, fontSize: 21, fontWeight: '800', marginTop: 7 },
  subjective: { color: colors.muted, fontSize: 12, marginTop: 3 },
  scoreReadout: { alignItems: 'baseline', flexDirection: 'row' },
  currentScore: { color: colors.primary, fontSize: 44, fontWeight: '800', letterSpacing: -1.5 },
  currentOutOf: { color: colors.muted, fontSize: 15, marginLeft: 4 },
  cardTitle: { color: colors.ink, fontSize: 21, fontWeight: '800', marginTop: 7 },
  body: { color: colors.muted, fontSize: 15, lineHeight: 22, marginTop: 7 },
  fieldLabel: { color: colors.ink, fontSize: 14, fontWeight: '700', marginTop: 24 },
  input: { minHeight: 52, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, color: colors.ink, paddingHorizontal: 15, fontSize: 16, marginTop: 16 },
  noteInput: { minHeight: 96, paddingTop: 14 },
  primaryButton: { minHeight: 54, borderRadius: 15, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary, marginTop: 14 },
  primaryPressed: { backgroundColor: colors.primaryPressed },
  primaryButtonText: { color: colors.surface, fontSize: 16, fontWeight: '800' },
  disabled: { opacity: 0.6 },
  success: { color: colors.primary, fontSize: 14, fontWeight: '700', marginTop: 14 },
  viewOnly: { minHeight: 64, flexDirection: 'row', alignItems: 'center', gap: 12, padding: 16, borderRadius: 18, backgroundColor: colors.primarySoft },
  viewOnlyText: { flex: 1, color: colors.ink, fontSize: 14, lineHeight: 20 },
  statsRow: { flexDirection: 'row', marginTop: 20, marginBottom: 4 },
  stat: { flex: 1 },
  statDivider: { width: 1, backgroundColor: colors.border, marginHorizontal: 16 },
  statValue: { color: colors.ink, fontSize: 28, fontWeight: '800' },
  statLabel: { color: colors.muted, fontSize: 12, marginTop: 3 },
  disclaimer: { color: colors.muted, fontSize: 12, lineHeight: 17, marginTop: 2 },
  medicationLink: { minHeight: 72, flexDirection: 'row', alignItems: 'center', gap: 12, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: 19, padding: 14 },
  medicationIcon: { width: 44, height: 44, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primarySoft },
  medicationCopy: { flex: 1 },
  medicationTitle: { color: colors.ink, fontSize: 16, fontWeight: '800' },
  medicationBody: { color: colors.muted, fontSize: 12, marginTop: 3 },
});
