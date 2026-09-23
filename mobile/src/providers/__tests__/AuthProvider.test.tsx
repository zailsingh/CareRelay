import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { PropsWithChildren } from 'react';
import { Text } from 'react-native';

import * as SecureStore from 'expo-secure-store';

import { api } from '@/lib/api';
import { AuthProvider, useAuth } from '@/providers/AuthProvider';

jest.mock('@/lib/api', () => ({
  api: {
    me: jest.fn(),
    devLogin: jest.fn(),
  },
}));

function Probe() {
  const { loading, token, initializationError, retryInitialization } = useAuth();
  return (
    <>
      <Text>{loading ? 'loading' : 'ready'}</Text>
      <Text>{token ?? 'signed-out'}</Text>
      {initializationError ? <Text>{initializationError}</Text> : null}
      <Text onPress={retryInitialization}>retry</Text>
    </>
  );
}

function renderProvider() {
  return render(
    <AuthProvider>
      <Probe />
    </AuthProvider>,
  );
}

describe('AuthProvider startup', () => {
  beforeEach(() => {
    jest.clearAllMocks();
    jest.mocked(SecureStore.getItemAsync).mockResolvedValue(null);
  });

  it('reaches a signed-out initial render without contacting the backend', async () => {
    renderProvider();

    await waitFor(() => expect(screen.getByText('ready')).toBeTruthy());
    expect(screen.getByText('signed-out')).toBeTruthy();
    expect(api.me).not.toHaveBeenCalled();
  });

  it('shows a recoverable state when restoring a stored session fails', async () => {
    jest.mocked(SecureStore.getItemAsync).mockResolvedValue('expired-token');
    jest.mocked(api.me)
      .mockRejectedValueOnce(new Error('Network request failed'))
      .mockResolvedValueOnce({
        id: 'user-1',
        email: 'alex@example.com',
        display_name: 'Alex',
        created_at: '2026-09-22T00:00:00Z',
      });
    renderProvider();

    await waitFor(() => expect(screen.getByText(/could not restore your session/i)).toBeTruthy());
    expect(screen.getByText('ready')).toBeTruthy();
    expect(SecureStore.deleteItemAsync).not.toHaveBeenCalled();

    fireEvent.press(screen.getByText('retry'));
    await waitFor(() => expect(api.me).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(screen.getByText('expired-token')).toBeTruthy());
    expect(screen.queryByText(/could not restore your session/i)).toBeNull();
  });
});
