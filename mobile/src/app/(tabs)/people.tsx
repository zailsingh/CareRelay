import { Ionicons } from '@expo/vector-icons';
import { useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ProfileSelector } from '@/components/ProfileSelector';
import { api, CareMembership } from '@/lib/api';
import { useAuth } from '@/providers/AuthProvider';
import { useCareProfiles } from '@/providers/CareProfileProvider';
import { colors } from '@/theme/colors';

export default function PeopleScreen() {
  const { token } = useAuth();
  const { activeProfile, refreshProfiles } = useCareProfiles();
  const [members, setMembers] = useState<CareMembership[]>([]);
  const [timezone, setTimezone] = useState('UTC');
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setTimezone(activeProfile?.timezone ?? 'UTC');
    if (!token || !activeProfile) {
      setMembers([]);
      return;
    }
    let current = true;
    setLoading(true);
    api.members(token, activeProfile.id)
      .then((result) => current && setMembers(result))
      .catch((cause) => current && setError(cause instanceof Error ? cause.message : 'Unable to load people.'))
      .finally(() => current && setLoading(false));
    return () => { current = false; };
  }, [token, activeProfile]);

  const updateProfile = async (payload: { subject_user_id?: string | null; timezone?: string }) => {
    if (!token || !activeProfile) return;
    setSaving(true);
    setError(null);
    try {
      await api.updateProfile(token, activeProfile.id, payload);
      await refreshProfiles();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to update this care profile.');
    } finally {
      setSaving(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe} edges={['top']}>
      <ScrollView contentContainerStyle={styles.content}>
        <Text style={styles.brand}>CareRelay</Text>
        <Text style={styles.title} accessibilityRole="header">People</Text>
        <Text style={styles.subtitle}>The care circle and the person this profile is about.</Text>
        <ProfileSelector />
        {loading ? <ActivityIndicator color={colors.primary} style={styles.loader} /> : null}
        {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}

        {activeProfile ? (
          <>
            <View style={styles.card}>
              <Text style={styles.eyebrow}>Profile subject</Text>
              <Text style={styles.cardTitle}>Who is receiving care?</Text>
              <Text style={styles.body}>This identity controls who may create a self-reported “How I feel” check-in. Their membership role can still be admin, family, carer, or cared person.</Text>
              {members.map((member) => {
                const selected = member.user_id === activeProfile.subject_user_id;
                return (
                  <Pressable
                    key={member.id}
                    accessibilityRole="button"
                    accessibilityState={{ selected, disabled: activeProfile.role !== 'admin' || saving }}
                    disabled={activeProfile.role !== 'admin' || saving}
                    onPress={() => updateProfile({ subject_user_id: member.user_id })}
                    style={[styles.member, selected && styles.subjectMember]}
                  >
                    <View style={styles.avatar}><Text style={styles.avatarText}>{member.display_name.charAt(0).toUpperCase()}</Text></View>
                    <View style={styles.memberCopy}>
                      <Text style={styles.memberName}>{member.display_name}</Text>
                      <Text style={styles.memberRole}>{member.role.replace('_', ' ')}</Text>
                    </View>
                    {selected ? <View style={styles.subjectBadge}><Text style={styles.subjectText}>Profile subject</Text></View> : null}
                  </Pressable>
                );
              })}
              {!activeProfile.subject_user_id ? <Text style={styles.warning}>No profile subject has been selected.</Text> : null}
            </View>

            <View style={styles.card}>
              <Text style={styles.eyebrow}>Local time</Text>
              <Text style={styles.cardTitle}>Profile timezone</Text>
              <Text style={styles.body}>Daily wellbeing summaries use this IANA timezone, including daylight-saving changes.</Text>
              <TextInput
                accessibilityLabel="Care profile timezone"
                autoCapitalize="none"
                editable={activeProfile.role === 'admin'}
                onChangeText={setTimezone}
                placeholder="Australia/Melbourne"
                placeholderTextColor={colors.muted}
                style={[styles.input, activeProfile.role !== 'admin' && styles.readOnly]}
                value={timezone}
              />
              {activeProfile.role === 'admin' ? (
                <Pressable accessibilityRole="button" disabled={saving} onPress={() => updateProfile({ timezone: timezone.trim() })} style={[styles.save, saving && styles.disabled]}>
                  {saving ? <ActivityIndicator color={colors.surface} /> : <><Ionicons name="checkmark" size={19} color={colors.surface} /><Text style={styles.saveText}>Save timezone</Text></>}
                </Pressable>
              ) : <Text style={styles.readOnlyNote}>Only a profile administrator can change these settings.</Text>}
            </View>
          </>
        ) : null}
      </ScrollView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  content: { paddingHorizontal: 20, paddingTop: 14, paddingBottom: 120, gap: 16 },
  brand: { color: colors.primary, fontSize: 18, fontWeight: '800' },
  title: { color: colors.ink, fontSize: 32, fontWeight: '800', letterSpacing: -0.8, marginTop: -2 },
  subtitle: { color: colors.muted, fontSize: 15, lineHeight: 21, marginTop: -10 },
  loader: { marginTop: 30 },
  error: { color: colors.error, fontSize: 14 },
  card: { backgroundColor: colors.surface, borderRadius: 22, borderWidth: 1, borderColor: colors.border, padding: 19 },
  eyebrow: { color: colors.primary, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1 },
  cardTitle: { color: colors.ink, fontSize: 21, fontWeight: '800', marginTop: 7 },
  body: { color: colors.muted, fontSize: 14, lineHeight: 21, marginTop: 7, marginBottom: 10 },
  member: { minHeight: 66, borderRadius: 16, borderWidth: 1, borderColor: colors.border, flexDirection: 'row', alignItems: 'center', padding: 10, marginTop: 9 },
  subjectMember: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  avatar: { width: 42, height: 42, borderRadius: 14, backgroundColor: colors.background, alignItems: 'center', justifyContent: 'center' },
  avatarText: { color: colors.primary, fontSize: 17, fontWeight: '800' },
  memberCopy: { flex: 1, marginLeft: 11 },
  memberName: { color: colors.ink, fontSize: 15, fontWeight: '700' },
  memberRole: { color: colors.muted, fontSize: 12, textTransform: 'capitalize', marginTop: 2 },
  subjectBadge: { borderRadius: 99, backgroundColor: colors.surface, paddingHorizontal: 9, paddingVertical: 5 },
  subjectText: { color: colors.primary, fontSize: 10, fontWeight: '800' },
  warning: { color: colors.warning, fontSize: 13, fontWeight: '700', marginTop: 12 },
  input: { minHeight: 52, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, color: colors.ink, fontSize: 16, paddingHorizontal: 14, marginTop: 10 },
  readOnly: { backgroundColor: colors.background },
  save: { minHeight: 52, borderRadius: 15, flexDirection: 'row', gap: 7, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary, marginTop: 12 },
  saveText: { color: colors.surface, fontSize: 15, fontWeight: '800' },
  disabled: { opacity: 0.6 },
  readOnlyNote: { color: colors.muted, fontSize: 12, marginTop: 10 },
});

