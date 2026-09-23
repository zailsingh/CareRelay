import { fireEvent, render, screen, waitFor } from '@testing-library/react-native';
import { Alert } from 'react-native';

import PeopleScreen from '@/app/(tabs)/people';
import { api, CareInvitation, CareMembership } from '@/lib/api';
import { useAuth } from '@/providers/AuthProvider';
import { useCareProfiles } from '@/providers/CareProfileProvider';

jest.mock('expo-router', () => ({ useLocalSearchParams: () => ({}) }));
jest.mock('@expo/vector-icons', () => ({ Ionicons: () => null }));
jest.mock('react-native-safe-area-context', () => ({
  SafeAreaView: ({ children }: { children: React.ReactNode }) => children,
}));
jest.mock('@/components/ProfileSelector', () => ({ ProfileSelector: () => null }));
jest.mock('@/lib/api', () => ({
  api: {
    members: jest.fn(),
    invitations: jest.fn(),
    createInvitation: jest.fn(),
    resendInvitation: jest.fn(),
    revokeInvitation: jest.fn(),
    updateMemberRole: jest.fn(),
    removeMember: jest.fn(),
    updateProfile: jest.fn(),
  },
}));
jest.mock('@/providers/AuthProvider', () => ({ useAuth: jest.fn() }));
jest.mock('@/providers/CareProfileProvider', () => ({ useCareProfiles: jest.fn() }));

const owner: CareMembership = {
  id: 'membership-owner',
  user_id: 'user-owner',
  display_name: 'Alex',
  email: 'alex@example.com',
  role: 'admin',
  created_at: '2026-09-23T00:00:00Z',
};
const family: CareMembership = {
  id: 'membership-family',
  user_id: 'user-family',
  display_name: 'Jane',
  email: 'jane@example.com',
  role: 'family',
  created_at: '2026-09-23T00:00:00Z',
};
const pending: CareInvitation = {
  id: 'invite-1',
  care_profile_id: 'profile-1',
  invited_email: 'deepika@example.com',
  intended_role: 'family',
  is_subject_invite: true,
  status: 'pending',
  expires_at: '2026-09-30T00:00:00Z',
  accepted_at: null,
  email_sent_at: null,
  delivery_status: 'failed',
  accept_url: null,
  created_at: '2026-09-23T00:00:00Z',
};

describe('People care circle', () => {
  const refreshProfiles = jest.fn(async () => undefined);

  beforeEach(() => {
    jest.clearAllMocks();
    jest.spyOn(Alert, 'alert').mockImplementation(jest.fn());
    jest.mocked(useAuth).mockReturnValue({
      token: 'access-token',
      user: { id: 'user-owner', email: 'alex@example.com', display_name: 'Alex', created_at: 'now' },
      loading: false,
      initializationError: null,
      retryInitialization: jest.fn(),
      signIn: jest.fn(),
      signInWithApple: jest.fn(),
      signOut: jest.fn(),
      deleteAccount: jest.fn(),
    });
    jest.mocked(useCareProfiles).mockReturnValue({
      profiles: [],
      activeProfile: {
        id: 'profile-1',
        name: 'Deepika',
        role: 'admin',
        subject_user_id: null,
        timezone: 'Australia/Melbourne',
        created_at: 'now',
      },
      loading: false,
      error: null,
      wellbeingRevision: 0,
      careEventRevision: 0,
      setActiveProfileId: jest.fn(),
      createProfile: jest.fn(),
      refreshProfiles,
      notifyWellbeingChanged: jest.fn(),
      notifyCareEventChanged: jest.fn(),
    });
    jest.mocked(api.members).mockResolvedValue([owner, family]);
    jest.mocked(api.invitations).mockResolvedValue([pending]);
  });

  it('shows subject, member, pending, and failed-email states', async () => {
    render(<PeopleScreen />);
    await waitFor(() => expect(screen.getByText('Invitation pending')).toBeTruthy());
    expect(screen.getByText('Email delivery failed')).toBeTruthy();
    expect(screen.getByText('Alex')).toBeTruthy();
    expect(screen.getByText('Jane')).toBeTruthy();
  });

  it.each([
    ['family', 'family', false],
    ['carer', 'carer', false],
    ['subject', 'family', true],
  ] as const)('creates a %s invitation', async (kind, role, isSubject) => {
    const created = {
      ...pending,
      id: `invite-${kind}`,
      invited_email: `${kind}@example.com`,
      intended_role: role,
      is_subject_invite: isSubject,
      delivery_status: 'sent' as const,
    };
    jest.mocked(api.createInvitation).mockResolvedValue(created);
    render(<PeopleScreen />);
    await waitFor(() => expect(api.members).toHaveBeenCalled());
    fireEvent.press(screen.getByText('Invite'));
    fireEvent.press(screen.getByLabelText(`Invite as ${kind}`));
    fireEvent.changeText(screen.getByLabelText('Invitation email'), `${kind}@example.com`);
    fireEvent.press(screen.getByText('Send invitation'));
    await waitFor(() => expect(api.createInvitation).toHaveBeenCalledWith(
      'access-token',
      'profile-1',
      {
        invited_email: `${kind}@example.com`,
        intended_role: role,
        is_subject_invite: isSubject,
      },
    ));
  });

  it('resends and revokes a pending invitation', async () => {
    jest.mocked(api.resendInvitation).mockResolvedValue({ ...pending, delivery_status: 'sent' });
    jest.mocked(api.revokeInvitation).mockResolvedValue(undefined);
    render(<PeopleScreen />);
    await waitFor(() => expect(screen.getByText('Invitation pending')).toBeTruthy());
    fireEvent.press(screen.getByLabelText('Resend invitation to deepika@example.com'));
    await waitFor(() => expect(api.resendInvitation).toHaveBeenCalledWith(
      'access-token', 'profile-1', 'invite-1',
    ));
    fireEvent.press(screen.getByLabelText('Revoke invitation to deepika@example.com'));
    await waitFor(() => expect(api.revokeInvitation).toHaveBeenCalledWith(
      'access-token', 'profile-1', 'invite-1',
    ));
  });

  it('changes member role and surfaces final-admin protection', async () => {
    jest.mocked(api.updateMemberRole)
      .mockResolvedValueOnce({ ...family, role: 'carer' })
      .mockRejectedValueOnce(new Error('Transfer administration before changing the final administrator'));
    render(<PeopleScreen />);
    await waitFor(() => expect(screen.getByText('Jane')).toBeTruthy());
    fireEvent.press(screen.getByLabelText('Change Jane role to carer'));
    await waitFor(() => expect(api.updateMemberRole).toHaveBeenCalledWith(
      'access-token', 'profile-1', 'membership-family', 'carer',
    ));
    fireEvent.press(screen.getByLabelText('Change Alex role to family'));
    await waitFor(() => expect(screen.getByRole('alert')).toHaveTextContent(
      /transfer administration/i,
    ));
  });

  it('confirms member removal before calling the API', async () => {
    jest.mocked(api.removeMember).mockResolvedValue(undefined);
    const alert = jest.spyOn(Alert, 'alert').mockImplementation((title, message, buttons) => {
      buttons?.find((button) => button.text === 'Remove')?.onPress?.();
    });
    render(<PeopleScreen />);
    await waitFor(() => expect(screen.getByText('Jane')).toBeTruthy());
    fireEvent.press(screen.getByLabelText('Remove Jane'));
    await waitFor(() => expect(api.removeMember).toHaveBeenCalledWith(
      'access-token', 'profile-1', 'membership-family',
    ));
    expect(alert).toHaveBeenCalled();
  });
});
