import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Text } from 'react-native';

import Index from '@/app/index';
import RootLayout from '@/app/_layout';
import SignInScreen from '@/app/sign-in';
import { useAuth } from '@/providers/AuthProvider';
import { useCareProfiles } from '@/providers/CareProfileProvider';

const mockStack = jest.fn(() => <Text>router-stack</Text>);
const mockRedirect = jest.fn(({ href }: { href: string }) => <Text>redirect:{href}</Text>);

jest.mock('expo-router', () => ({
  Stack: () => mockStack(),
  Redirect: (props: { href: string }) => mockRedirect(props),
  useLocalSearchParams: () => ({}),
  router: { replace: jest.fn() },
}));

jest.mock('@expo/vector-icons', () => ({
  Ionicons: () => null,
}));

jest.mock('react-native-safe-area-context', () => ({
  SafeAreaProvider: ({ children }: { children: React.ReactNode }) => children,
  SafeAreaView: ({ children }: { children: React.ReactNode }) => children,
}));

jest.mock('@/providers/AuthProvider', () => ({
  AuthProvider: ({ children }: { children: React.ReactNode }) => children,
  useAuth: jest.fn(),
}));

jest.mock('@/providers/CareProfileProvider', () => ({
  CareProfileProvider: ({ children }: { children: React.ReactNode }) => children,
  useCareProfiles: jest.fn(),
}));

describe('app startup', () => {
  beforeEach(() => {
    jest.clearAllMocks();
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

  it('initializes the root layout and navigation stack', () => {
    render(<RootLayout />);

    expect(screen.getByText('router-stack')).toBeTruthy();
    expect(mockStack).toHaveBeenCalledTimes(1);
  });

  it('shows a visible loading shell while auth initializes', () => {
    jest.mocked(useAuth).mockReturnValue({ loading: true } as ReturnType<typeof useAuth>);

    render(<Index />);

    expect(screen.getByText('Loading CareRelay…')).toBeTruthy();
    expect(mockRedirect).not.toHaveBeenCalled();
  });

  it('initializes signed-out navigation without a backend', () => {
    jest.mocked(useAuth).mockReturnValue({ loading: false, token: null } as ReturnType<typeof useAuth>);

    render(<Index />);

    expect(screen.getByText('redirect:/sign-in')).toBeTruthy();
  });

  it('sends a first-time authenticated user to onboarding', () => {
    jest.mocked(useAuth).mockReturnValue({
      loading: false,
      token: 'access-token',
    } as ReturnType<typeof useAuth>);
    render(<Index />);
    expect(screen.getByText('redirect:/onboarding')).toBeTruthy();
  });

  it('sends a returning member directly into the app', () => {
    jest.mocked(useAuth).mockReturnValue({
      loading: false,
      token: 'access-token',
    } as ReturnType<typeof useAuth>);
    jest.mocked(useCareProfiles).mockReturnValue({
      ...jest.mocked(useCareProfiles)(),
      profiles: [{
        id: 'profile-1',
        name: 'Deepika',
        role: 'admin',
        subject_user_id: null,
        timezone: 'Australia/Melbourne',
        created_at: 'now',
      }],
      loading: false,
    });
    render(<Index />);
    expect(screen.getByText('redirect:/(tabs)')).toBeTruthy();
  });

  it('shows a recoverable auth initialization failure', () => {
    const retryInitialization = jest.fn();
    jest.mocked(useAuth).mockReturnValue({
      loading: false,
      token: null,
      user: null,
      initializationError: 'We could not restore your session. Check your connection and try again.',
      retryInitialization,
      signIn: jest.fn(),
      signInWithApple: jest.fn(),
      signOut: jest.fn(),
      deleteAccount: jest.fn(),
    });

    render(<SignInScreen />);

    expect(screen.getByRole('alert')).toHaveTextContent(/could not restore your session/i);
    fireEvent.press(screen.getByText('Try again'));
    expect(retryInitialization).toHaveBeenCalledTimes(1);
  });

  it('keeps the sign-in shell visible when the backend is unavailable', async () => {
    const signIn = jest.fn().mockRejectedValue(new Error('Network request failed'));
    jest.mocked(useAuth).mockReturnValue({
      loading: false,
      token: null,
      user: null,
      initializationError: null,
      retryInitialization: jest.fn(),
      signIn,
      signInWithApple: jest.fn(),
      signOut: jest.fn(),
      deleteAccount: jest.fn(),
    });

    render(<SignInScreen />);
    fireEvent.press(screen.getByText('Continue with DEV login'));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Network request failed'));
    expect(screen.getByText('Welcome to CareRelay')).toBeTruthy();
  });
});
