import { Ionicons } from '@expo/vector-icons';
import * as AppleAuthentication from 'expo-apple-authentication';
import * as Crypto from 'expo-crypto';
import { Href, Redirect, router, useLocalSearchParams } from 'expo-router';
import { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { LoadingScreen } from '@/components/LoadingScreen';
import { useAuth } from '@/providers/AuthProvider';
import { colors } from '@/theme/colors';

export default function SignInScreen() {
  const {
    token,
    loading,
    initializationError,
    retryInitialization,
    signIn,
    signInWithApple,
  } = useAuth();
  const { inviteToken } = useLocalSearchParams<{ inviteToken?: string | string[] }>();
  const [email, setEmail] = useState('alex@example.com');
  const [displayName, setDisplayName] = useState('Alex');
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const devLoginEnabled = process.env.EXPO_PUBLIC_APP_ENV !== 'production';
  const pendingInvite = Array.isArray(inviteToken) ? inviteToken[0] : inviteToken;
  const nextPath = pendingInvite ? `/invite/${encodeURIComponent(pendingInvite)}` : '/';

  if (loading) return <LoadingScreen />;
  if (token) return <Redirect href="/(tabs)" />;

  const submit = async () => {
    if (!email.trim() || !displayName.trim()) {
      setError('Enter your name and email address.');
      return;
    }
    setSubmitting(true);
    setError(null);
    try {
      await signIn(email, displayName);
      router.replace(nextPath as Href);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to sign in.');
    } finally {
      setSubmitting(false);
    }
  };

  const appleSignIn = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const rawNonce = Array.from(await Crypto.getRandomBytesAsync(32), (byte) =>
        byte.toString(16).padStart(2, '0'),
      ).join('');
      const state = Crypto.randomUUID();
      const hashedNonce = await Crypto.digestStringAsync(
        Crypto.CryptoDigestAlgorithm.SHA256,
        rawNonce,
      );
      const credential = await AppleAuthentication.signInAsync({
        requestedScopes: [
          AppleAuthentication.AppleAuthenticationScope.FULL_NAME,
          AppleAuthentication.AppleAuthenticationScope.EMAIL,
        ],
        nonce: hashedNonce,
        state,
      });
      if (credential.state !== state || !credential.identityToken) {
        throw new Error('Apple Sign-In could not be verified. Please try again.');
      }
      const displayName = [credential.fullName?.givenName, credential.fullName?.familyName]
        .filter(Boolean)
        .join(' ');
      await signInWithApple(credential.identityToken, rawNonce, displayName || undefined);
      router.replace(nextPath as Href);
    } catch (cause) {
      if ((cause as { code?: string }).code !== 'ERR_REQUEST_CANCELED') {
        setError(cause instanceof Error ? cause.message : 'Unable to sign in with Apple.');
      }
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <SafeAreaView style={styles.safe}>
      <KeyboardAvoidingView style={styles.page} behavior={Platform.OS === 'ios' ? 'padding' : undefined}>
        <View style={styles.mark}><Ionicons name="heart" size={30} color={colors.surface} /></View>
        <Text style={styles.eyebrow}>Care, understood</Text>
        <Text style={styles.title}>Welcome to CareRelay</Text>
        <Text style={styles.subtitle}>A calm, shared place for families supporting someone they care about.</Text>

        <View style={styles.form}>
          {Platform.OS === 'ios' ? (
            <AppleAuthentication.AppleAuthenticationButton
              accessibilityLabel="Continue with Apple"
              buttonStyle={AppleAuthentication.AppleAuthenticationButtonStyle.BLACK}
              buttonType={AppleAuthentication.AppleAuthenticationButtonType.CONTINUE}
              cornerRadius={14}
              onPress={() => void appleSignIn()}
              style={styles.nativeAppleButton}
            />
          ) : null}
          {devLoginEnabled ? (
            <>
              <Text style={styles.devHeading}>Development sign-in</Text>
          <Text style={styles.label}>Your name</Text>
          <TextInput
            accessibilityLabel="Your name"
            autoComplete="name"
            value={displayName}
            onChangeText={setDisplayName}
            style={styles.input}
          />
          <Text style={styles.label}>Email</Text>
          <TextInput
            accessibilityLabel="Email"
            autoCapitalize="none"
            autoComplete="email"
            keyboardType="email-address"
            value={email}
            onChangeText={setEmail}
            style={styles.input}
          />
          {initializationError ? (
            <View>
              <Text accessibilityRole="alert" style={styles.error}>{initializationError}</Text>
              <Pressable accessibilityRole="button" onPress={retryInitialization}>
                <Text style={styles.retry}>Try again</Text>
              </Pressable>
            </View>
          ) : null}
          {error ? <Text accessibilityRole="alert" style={styles.error}>{error}</Text> : null}
          <Pressable
            accessibilityRole="button"
            disabled={submitting}
            onPress={submit}
            style={({ pressed }) => [styles.button, pressed && styles.buttonPressed, submitting && styles.disabled]}
          >
            {submitting ? <ActivityIndicator color={colors.surface} /> : <Text style={styles.buttonText}>Continue with DEV login</Text>}
          </Pressable>
            </>
          ) : null}
          {Platform.OS !== 'ios' ? (
            <Text style={styles.note}>Sign in with Apple is available in the iOS app.</Text>
          ) : null}
        </View>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const styles = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.background },
  page: { flex: 1, justifyContent: 'center', paddingHorizontal: 28, paddingVertical: 24 },
  mark: { width: 56, height: 56, borderRadius: 18, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary, marginBottom: 24 },
  eyebrow: { color: colors.primary, fontSize: 14, fontWeight: '700', letterSpacing: 1.2, textTransform: 'uppercase' },
  title: { color: colors.ink, fontSize: 36, lineHeight: 42, fontWeight: '800', letterSpacing: -1, marginTop: 8 },
  subtitle: { color: colors.muted, fontSize: 17, lineHeight: 25, marginTop: 12 },
  form: { marginTop: 32 },
  nativeAppleButton: { width: '100%', height: 54, marginBottom: 22 },
  devHeading: { color: colors.muted, fontSize: 12, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1, marginBottom: 16 },
  label: { color: colors.ink, fontSize: 14, fontWeight: '700', marginBottom: 8 },
  input: { minHeight: 52, borderRadius: 14, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, color: colors.ink, paddingHorizontal: 16, fontSize: 16, marginBottom: 18 },
  error: { color: colors.error, fontSize: 14, marginBottom: 12 },
  retry: { color: colors.primary, fontSize: 14, fontWeight: '700', marginBottom: 12 },
  button: { minHeight: 54, borderRadius: 14, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary },
  buttonPressed: { backgroundColor: colors.primaryPressed },
  disabled: { opacity: 0.65 },
  buttonText: { color: colors.surface, fontSize: 16, fontWeight: '700' },
  note: { color: colors.muted, fontSize: 12, lineHeight: 17, textAlign: 'center', marginTop: 10 },
});
