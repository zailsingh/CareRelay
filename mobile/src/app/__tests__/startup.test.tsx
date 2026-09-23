import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Text } from 'react-native';

import Index from '@/app/index';
import RootLayout from '@/app/_layout';
import SignInScreen from '@/app/sign-in';
import { useAuth } from '@/providers/AuthProvider';

const mockStack = jest.fn(() => <Text>router-stack</Text>);
const mockRedirect = jest.fn(({ href }: { href: string }) => <Text>redirect:{href}</Text>);

jest.mock('expo-router', () => ({
  Stack: () => mockStack(),
  Redirect: (props: { href: string }) => mockRedirect(props),
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
}));

describe('app startup', () => {
  beforeEach(() => {
    jest.clearAllMocks();
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

  it('shows a recoverable auth initialization failure', () => {
    const retryInitialization = jest.fn();
    jest.mocked(useAuth).mockReturnValue({
      loading: false,
      token: null,
      user: null,
      initializationError: 'We could not restore your session. Check your connection and try again.',
      retryInitialization,
      signIn: jest.fn(),
      signOut: jest.fn(),
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
      signOut: jest.fn(),
    });

    render(<SignInScreen />);
    fireEvent.press(screen.getByText('Continue with DEV login'));

    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent('Network request failed'));
    expect(screen.getByText('Welcome to CareRelay')).toBeTruthy();
  });
});
