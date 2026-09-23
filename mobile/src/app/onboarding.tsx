import { Ionicons } from '@expo/vector-icons';
import { router } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, TextInput, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { useAuth } from '@/providers/AuthProvider';
import { useCareProfiles } from '@/providers/CareProfileProvider';
import { colors } from '@/theme/colors';

type ProfileFor = 'someone' | 'me';

export default function OnboardingScreen() {
  const { user } = useAuth();
  const { createProfile } = useCareProfiles();
  const [profileFor, setProfileFor] = useState<ProfileFor>('someone');
  const [name, setName] = useState('');
  const [created, setCreated] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    const profileName = (profileFor === 'me' ? name || user?.display_name : name)?.trim();
    if (!profileName) {
      setError('Enter the name for this care profile.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await createProfile(profileName, profileFor === 'me');
      setCreated(true);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to create the care profile.');
    } finally {
      setSubmitting(false);
    }
  };

  const openPeople = (invite?: 'subject' | 'family' | 'carer') => {
    router.replace({ pathname: '/(tabs)/people', params: invite ? { invite } : {} });
  };

  if (created) {
    return (
      <SafeAreaView style={styles.safe}>
        <View style={styles.page}>
          <View style={styles.icon}><Ionicons name="people" size={28} color={colors.surface} /></View>
          <Text style={styles.eyebrow}>Care space created</Text>
          <Text style={styles.title}>Build your care circle</Text>
          <Text style={styles.subtitle}>Invite people now, or continue and do this later from People.</Text>
          {profileFor === 'someone' ? (
            <Action label="Invite the person this profile is for" onPress={() => openPeople('subject')} />
          ) : null}
          <Action label="Invite family member" onPress={() => openPeople('family')} />
          <Action label="Invite carer" onPress={() => openPeople('carer')} />
          <Pressable accessibilityRole="button" onPress={() => router.replace('/(tabs)')} style={styles.skip}>
            <Text style={styles.skipText}>Skip for now</Text>
          </Pressable>
        </View>
      </SafeAreaView>
    );
  }

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.page}>
        <Text style={styles.eyebrow}>Welcome to CareRelay</Text>
        <Text style={styles.title}>Create your first care space</Text>
        <Text style={styles.subtitle}>Who is this care profile for?</Text>
        <View style={styles.choiceRow}>
          <Choice
            label="Someone I care for"
            selected={profileFor === 'someone'}
            onPress={() => setProfileFor('someone')}
          />
          <Choice label="Me" selected={profileFor === 'me'} onPress={() => setProfileFor('me')} />
        </View>
        <Text style={styles.label}>Care profile name</Text>
        <TextInput
          accessibilityLabel="Care profile name"
          autoComplete="name"
          onChangeText={setName}
          placeholder={profileFor === 'me' ? user?.display_name ?? 'Your name' : 'Their name'}
          placeholderTextColor={colors.muted}
          style={styles.input}
          value={name}
        />
        <Text style={styles.note}>
          {profileFor === 'me'
            ? 'Your account will be linked as the person this profile is about.'
            : 'They can be linked securely after accepting a subject invitation.'}
        </Text>
        {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
        <Pressable
          accessibilityRole="button"
          disabled={submitting}
          onPress={() => void submit()}
          style={[styles.primary, submitting && styles.disabled]}
        >
          {submitting ? <ActivityIndicator color={colors.surface} /> : <Text style={styles.primaryText}>Create Care Profile</Text>}
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

function Choice({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="radio"
      accessibilityState={{ checked: selected }}
      onPress={onPress}
      style={[styles.choice, selected && styles.choiceSelected]}
    >
      <Text style={[styles.choiceText, selected && styles.choiceTextSelected]}>{label}</Text>
    </Pressable>
  );
}

function Action({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} style={styles.action}>
      <Text style={styles.actionText}>{label}</Text>
      <Ionicons name="arrow-forward" size={18} color={colors.primary} />
    </Pressable>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  page: { flex: 1, justifyContent: 'center', padding: 26 },
  icon: { width: 54, height: 54, borderRadius: 17, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary, marginBottom: 20 },
  eyebrow: { color: colors.primary, fontSize: 13, fontWeight: '800', letterSpacing: 1, textTransform: 'uppercase' },
  title: { color: colors.ink, fontSize: 34, lineHeight: 40, fontWeight: '800', letterSpacing: -0.8, marginTop: 8 },
  subtitle: { color: colors.muted, fontSize: 17, lineHeight: 25, marginTop: 12, marginBottom: 24 },
  choiceRow: { flexDirection: 'row', gap: 10, marginBottom: 26 },
  choice: { flex: 1, minHeight: 68, borderRadius: 16, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, alignItems: 'center', justifyContent: 'center', paddingHorizontal: 10 },
  choiceSelected: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  choiceText: { color: colors.ink, fontSize: 14, textAlign: 'center', fontWeight: '700' },
  choiceTextSelected: { color: colors.primary },
  label: { color: colors.ink, fontSize: 14, fontWeight: '700', marginBottom: 8 },
  input: { minHeight: 54, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, color: colors.ink, paddingHorizontal: 15, fontSize: 16 },
  note: { color: colors.muted, fontSize: 13, lineHeight: 19, marginTop: 10 },
  error: { color: colors.error, fontSize: 14, marginTop: 12 },
  primary: { minHeight: 54, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary, marginTop: 22 },
  primaryText: { color: colors.surface, fontSize: 16, fontWeight: '800' },
  disabled: { opacity: 0.6 },
  action: { minHeight: 56, borderRadius: 15, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between', paddingHorizontal: 16, marginTop: 10 },
  actionText: { color: colors.ink, fontSize: 15, fontWeight: '700' },
  skip: { alignItems: 'center', padding: 16, marginTop: 8 },
  skipText: { color: colors.primary, fontSize: 15, fontWeight: '800' },
});
