import { Redirect, router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { api } from '@/lib/api';
import { useAuth } from '@/providers/AuthProvider';
import { useCareProfiles } from '@/providers/CareProfileProvider';
import { colors } from '@/theme/colors';

export default function InvitationScreen() {
  const params = useLocalSearchParams<{ token?: string | string[] }>();
  const invitationToken = Array.isArray(params.token) ? params.token[0] : params.token;
  const { token: accessToken, loading } = useAuth();
  const { refreshProfiles } = useCareProfiles();
  const [accepting, setAccepting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (loading) return null;
  if (!invitationToken) return <Redirect href="/" />;
  if (!accessToken) {
    return <Redirect href={{ pathname: '/sign-in', params: { inviteToken: invitationToken } }} />;
  }

  const accept = async () => {
    setAccepting(true);
    setError(null);
    try {
      await api.acceptInvitation(accessToken, invitationToken);
      await refreshProfiles();
      router.replace('/(tabs)');
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to accept this invitation.');
    } finally {
      setAccepting(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <View style={styles.card}>
        <Text style={styles.eyebrow}>CareRelay invitation</Text>
        <Text style={styles.title}>Join this care circle?</Text>
        <Text style={styles.body}>
          Your signed-in CareRelay account will be added only after you explicitly accept.
        </Text>
        {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
        <Pressable
          accessibilityRole="button"
          disabled={accepting}
          onPress={() => void accept()}
          style={[styles.button, accepting && styles.disabled]}
        >
          {accepting ? <ActivityIndicator color={colors.surface} /> : <Text style={styles.buttonText}>Accept invitation</Text>}
        </Pressable>
      </View>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background, justifyContent: 'center', padding: 24 },
  card: { borderRadius: 24, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, padding: 24 },
  eyebrow: { color: colors.primary, fontSize: 12, fontWeight: '800', letterSpacing: 1, textTransform: 'uppercase' },
  title: { color: colors.ink, fontSize: 30, fontWeight: '800', marginTop: 8 },
  body: { color: colors.muted, fontSize: 15, lineHeight: 23, marginTop: 12 },
  error: { color: colors.error, fontSize: 14, marginTop: 18 },
  button: { minHeight: 54, borderRadius: 14, backgroundColor: colors.primary, alignItems: 'center', justifyContent: 'center', marginTop: 24 },
  buttonText: { color: colors.surface, fontSize: 16, fontWeight: '800' },
  disabled: { opacity: 0.6 },
});
