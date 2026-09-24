import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';

import InvitationScreen from '@/app/invite/[token]';
import OnboardingScreen from '@/app/onboarding';
import SignInScreen from '@/app/sign-in';
import { api } from '@/lib/api';
import { useAuth } from '@/providers/AuthProvider';
import { useCareProfiles } from '@/providers/CareProfileProvider';

const mockReplace = jest.fn();
const mockSearchParams = jest.fn(() => ({}));
const mockAppleSignIn = jest.fn();
const mockRandomBytes = jest.fn(async (_count?: number) => new Uint8Array([1, 2, 255]));
const mockDigest = jest.fn(async (_algorithm?: unknown, _value?: unknown) => 'hashed-nonce');

jest.mock('expo-router', () => {
  const { Text } = require('react-native');
  return {
    Redirect: ({ href }: { href: unknown }) => <Text>redirect:{JSON.stringify(href)}</Text>,
    router: { replace: (...args: unknown[]) => mockReplace(...args) },
    useLocalSearchParams: () => mockSearchParams(),
  };
});

jest.mock('expo-apple-authentication', () => {
  const { Pressable, Text } = require('react-native');
  return {
    AppleAuthenticationButton: ({ onPress }: { onPress: () => void }) => (
      <Pressable accessibilityRole="button" onPress={onPress}><Text>Continue with Apple</Text></Pressable>
    ),
    AppleAuthenticationButtonStyle: { BLACK: 'black' },
    AppleAuthenticationButtonType: { CONTINUE: 'continue' },
    AppleAuthenticationScope: { FULL_NAME: 'full-name', EMAIL: 'email' },
    signInAsync: (...args: unknown[]) => mockAppleSignIn(...args),
  };
});

jest.mock('expo-crypto', () => ({
  CryptoDigestAlgorithm: { SHA256: 'SHA-256' },
  digestStringAsync: (algorithm: unknown, value: unknown) => mockDigest(algorithm, value),
  getRandomBytesAsync: (count: number) => mockRandomBytes(count),
  randomUUID: () => 'state-123',
}));

jest.mock('@expo/vector-icons', () => ({ Ionicons: () => null }));
jest.mock('react-native-safe-area-context', () => ({
  SafeAreaView: ({ children }: { children: React.ReactNode }) => children,
}));
jest.mock('@/lib/api', () => ({
  api: { acceptInvitation: jest.fn() },
}));
jest.mock('@/providers/AuthProvider', () => ({ useAuth: jest.fn() }));
jest.mock('@/providers/CareProfileProvider', () => ({ useCareProfiles: jest.fn() }));

const baseAuth = {
  token: null,
  user: null,
  loading: false,
  initializationError: null,
  retryInitialization: jest.fn(),
  signIn: jest.fn(),
  signInWithApple: jest.fn(),
  signOut: jest.fn(),
  deleteAccount: jest.fn(),
};

describe('production identity and onboarding', () => {
  const originalAppEnv = process.env.EXPO_PUBLIC_APP_ENV;

  beforeEach(() => {
    jest.clearAllMocks();
    delete process.env.EXPO_PUBLIC_APP_ENV;
    mockSearchParams.mockReturnValue({});
    jest.mocked(useAuth).mockReturnValue({ ...baseAuth });
    jest.mocked(useCareProfiles).mockReturnValue({
      profiles: [],
      activeProfile: null,
      loading: false,
      error: null,
      wellbeingRevision: 0,
      careEventRevision: 0,
      setActiveProfileId: jest.fn(),
      createProfile: jest.fn(),
      refreshProfiles: jest.fn(),
      notifyWellbeingChanged: jest.fn(),
      notifyCareEventChanged: jest.fn(),
    });
  });

  afterAll(() => {
    process.env.EXPO_PUBLIC_APP_ENV = originalAppEnv;
  });

  it('shows Apple login and hides DEV login in production', () => {
    process.env.EXPO_PUBLIC_APP_ENV = 'production';
    render(<SignInScreen />);
    expect(screen.getByText('Continue with Apple')).toBeTruthy();
    expect(screen.queryByText('Continue with DEV login')).toBeNull();
  });

  it('shows both Apple and DEV login in development', () => {
    process.env.EXPO_PUBLIC_APP_ENV = 'development';
    render(<SignInScreen />);
    expect(screen.getByText('Continue with Apple')).toBeTruthy();
    expect(screen.getByText('Continue with DEV login')).toBeTruthy();
  });

  it('completes Apple authentication with nonce and state', async () => {
    const signInWithApple = jest.fn().mockResolvedValue(undefined);
    jest.mocked(useAuth).mockReturnValue({ ...baseAuth, signInWithApple });
    mockAppleSignIn.mockResolvedValue({
      state: 'state-123',
      identityToken: 'apple-jwt',
      fullName: { givenName: 'Jane', familyName: 'Doe' },
    });
    render(<SignInScreen />);
    fireEvent.press(screen.getByText('Continue with Apple'));
    await waitFor(() => expect(signInWithApple).toHaveBeenCalledWith(
      'apple-jwt',
      '0102ff',
      'Jane Doe',
    ));
    expect(mockAppleSignIn).toHaveBeenCalledWith(expect.objectContaining({
      nonce: 'hashed-nonce',
      state: 'state-123',
    }));
    expect(mockRandomBytes).toHaveBeenCalledWith(32);
    expect(mockDigest).toHaveBeenCalledWith('SHA-256', '0102ff');
    expect(mockReplace).toHaveBeenCalledWith('/');
  });

  it('shows a useful error when Apple omits the identity token', async () => {
    const signInWithApple = jest.fn();
    jest.mocked(useAuth).mockReturnValue({ ...baseAuth, signInWithApple });
    mockAppleSignIn.mockResolvedValue({
      state: 'state-123',
      identityToken: null,
      fullName: null,
    });
    render(<SignInScreen />);
    fireEvent.press(screen.getByText('Continue with Apple'));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(
      /Apple Sign-In could not be verified/,
    ));
    expect(signInWithApple).not.toHaveBeenCalled();
  });

  it('handles Apple cancellation without displaying an error', async () => {
    mockAppleSignIn.mockRejectedValue({ code: 'ERR_REQUEST_CANCELED' });
    render(<SignInScreen />);
    fireEvent.press(screen.getByText('Continue with Apple'));
    await waitFor(() => expect(mockAppleSignIn).toHaveBeenCalled());
    expect(screen.queryByRole('alert')).toBeNull();
  });

  it('returns to the invitation after Apple authentication', async () => {
    const signInWithApple = jest.fn().mockResolvedValue(undefined);
    mockSearchParams.mockReturnValue({ inviteToken: 'invite/with symbols' });
    jest.mocked(useAuth).mockReturnValue({ ...baseAuth, signInWithApple });
    mockAppleSignIn.mockResolvedValue({
      state: 'state-123',
      identityToken: 'apple-jwt',
      fullName: null,
    });
    render(<SignInScreen />);
    fireEvent.press(screen.getByText('Continue with Apple'));
    await waitFor(() => expect(mockReplace).toHaveBeenCalledWith(
      '/invite/invite%2Fwith%20symbols',
    ));
  });

  it('creates a someone-else profile and offers care-circle invitations', async () => {
    const createProfile = jest.fn().mockResolvedValue({ id: 'profile-1' });
    jest.mocked(useCareProfiles).mockReturnValue({
      ...jest.mocked(useCareProfiles)(),
      createProfile,
    });
    jest.mocked(useAuth).mockReturnValue({
      ...baseAuth,
      user: { id: 'u1', email: null, display_name: 'Alex', created_at: 'now' },
    });
    render(<OnboardingScreen />);
    fireEvent.changeText(screen.getByLabelText('Care profile name'), 'Deepika');
    fireEvent.press(screen.getByText('Create Care Profile'));
    await waitFor(() => expect(createProfile).toHaveBeenCalledWith('Deepika', false));
    expect(screen.getByText('Build your care circle')).toBeTruthy();
    expect(screen.getByText('Invite the person this profile is for')).toBeTruthy();
  });

  it('links self-care onboarding explicitly to the authenticated user', async () => {
    const createProfile = jest.fn().mockResolvedValue({ id: 'profile-1' });
    jest.mocked(useCareProfiles).mockReturnValue({
      ...jest.mocked(useCareProfiles)(),
      createProfile,
    });
    jest.mocked(useAuth).mockReturnValue({
      ...baseAuth,
      user: { id: 'u1', email: null, display_name: 'Alex', created_at: 'now' },
    });
    render(<OnboardingScreen />);
    fireEvent.press(screen.getByText('Me'));
    fireEvent.press(screen.getByText('Create Care Profile'));
    await waitFor(() => expect(createProfile).toHaveBeenCalledWith('Alex', true));
    expect(screen.queryByText('Invite the person this profile is for')).toBeNull();
  });

  it('preserves an invitation through sign-in and accepts it', async () => {
    const refreshProfiles = jest.fn().mockResolvedValue(undefined);
    mockSearchParams.mockReturnValue({ token: 'raw-invite-token' });
    jest.mocked(useAuth).mockReturnValue({ ...baseAuth, token: 'access-token' });
    jest.mocked(useCareProfiles).mockReturnValue({
      ...jest.mocked(useCareProfiles)(),
      refreshProfiles,
    });
    jest.mocked(api.acceptInvitation).mockResolvedValue({
      care_profile_id: 'profile-1',
      membership_id: 'membership-1',
      role: 'family',
      subject_linked: false,
    });
    render(<InvitationScreen />);
    fireEvent.press(screen.getByText('Accept invitation'));
    await waitFor(() => expect(api.acceptInvitation).toHaveBeenCalledWith(
      'access-token',
      'raw-invite-token',
    ));
    expect(refreshProfiles).toHaveBeenCalled();
    expect(mockReplace).toHaveBeenCalledWith('/(tabs)');
  });

  it('returns a signed-out invitee to sign-in with invite intent', () => {
    mockSearchParams.mockReturnValue({ token: 'raw-invite-token' });
    render(<InvitationScreen />);
    expect(screen.getByText(/inviteToken.*raw-invite-token/)).toBeTruthy();
  });

  it('shows an expired invitation error safely', async () => {
    mockSearchParams.mockReturnValue({ token: 'expired-token' });
    jest.mocked(useAuth).mockReturnValue({ ...baseAuth, token: 'access-token' });
    jest.mocked(api.acceptInvitation).mockRejectedValue(new Error('Invitation is no longer valid'));
    render(<InvitationScreen />);
    fireEvent.press(screen.getByText('Accept invitation'));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(
      'Invitation is no longer valid',
    ));
  });
});
