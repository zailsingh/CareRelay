import { Ionicons } from '@expo/vector-icons';
import { useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  ActivityIndicator,
  Alert,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';

import { ProfileSelector } from '@/components/ProfileSelector';
import { api, CareInvitation, CareMembership } from '@/lib/api';
import { useAuth } from '@/providers/AuthProvider';
import { useCareProfiles } from '@/providers/CareProfileProvider';
import { colors } from '@/theme/colors';

type InviteKind = 'subject' | 'family' | 'carer';
type EditableRole = 'admin' | 'family' | 'carer';

export default function PeopleScreen() {
  const params = useLocalSearchParams<{ invite?: string | string[] }>();
  const { token, user, deleteAccount } = useAuth();
  const { activeProfile, refreshProfiles } = useCareProfiles();
  const [members, setMembers] = useState<CareMembership[]>([]);
  const [invitations, setInvitations] = useState<CareInvitation[]>([]);
  const [timezone, setTimezone] = useState('UTC');
  const [inviteEmail, setInviteEmail] = useState('');
  const [inviteKind, setInviteKind] = useState<InviteKind>('family');
  const [showInvite, setShowInvite] = useState(false);
  const [loading, setLoading] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const isAdmin = activeProfile?.role === 'admin';

  const loadPeople = useCallback(async () => {
    if (!token || !activeProfile) {
      setMembers([]);
      setInvitations([]);
      return;
    }
    setLoading(true);
    setError(null);
    try {
      const [memberRows, inviteRows] = await Promise.all([
        api.members(token, activeProfile.id),
        activeProfile.role === 'admin'
          ? api.invitations(token, activeProfile.id)
          : Promise.resolve([]),
      ]);
      setMembers(memberRows);
      setInvitations(inviteRows);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to load people.');
    } finally {
      setLoading(false);
    }
  }, [token, activeProfile]);

  useEffect(() => {
    setTimezone(activeProfile?.timezone ?? 'UTC');
    void loadPeople();
  }, [activeProfile, loadPeople]);

  useEffect(() => {
    const requested = Array.isArray(params.invite) ? params.invite[0] : params.invite;
    if (requested === 'subject' || requested === 'family' || requested === 'carer') {
      setInviteKind(requested);
      setShowInvite(true);
    }
  }, [params.invite]);

  const run = async (action: () => Promise<void>) => {
    setSaving(true);
    setError(null);
    try {
      await action();
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : 'Unable to update the care circle.');
    } finally {
      setSaving(false);
    }
  };

  const updateProfile = (payload: { subject_user_id?: string | null; timezone?: string }) => run(async () => {
    if (!token || !activeProfile) return;
    await api.updateProfile(token, activeProfile.id, payload);
    await refreshProfiles();
  });

  const sendInvite = async () => {
    if (!token || !activeProfile || !inviteEmail.trim()) {
      setError('Enter the invitation email address.');
      return;
    }
    await run(async () => {
      const invitation = await api.createInvitation(token, activeProfile.id, {
        invited_email: inviteEmail.trim(),
        intended_role: inviteKind === 'carer' ? 'carer' : 'family',
        is_subject_invite: inviteKind === 'subject',
      });
      setInvitations((current) => [invitation, ...current]);
      setInviteEmail('');
      setShowInvite(false);
      if (invitation.delivery_status === 'failed') {
        setError('Invitation created, but email delivery failed. You can resend it below.');
      }
    });
  };

  const resend = (invitation: CareInvitation) => run(async () => {
    if (!token || !activeProfile) return;
    const replacement = await api.resendInvitation(token, activeProfile.id, invitation.id);
    setInvitations((current) => current.map((item) =>
      item.id === replacement.id ? replacement : item,
    ));
  });

  const revoke = (invitation: CareInvitation) => run(async () => {
    if (!token || !activeProfile) return;
    await api.revokeInvitation(token, activeProfile.id, invitation.id);
    await loadPeople();
  });

  const changeRole = (member: CareMembership, role: EditableRole) => run(async () => {
    if (!token || !activeProfile) return;
    const updated = await api.updateMemberRole(token, activeProfile.id, member.id, role);
    setMembers((current) => current.map((item) => item.id === updated.id ? updated : item));
    await refreshProfiles();
  });

  const removeMember = (member: CareMembership) => {
    Alert.alert('Remove from care circle?', `${member.display_name} will lose access to this profile.`, [
      { text: 'Cancel', style: 'cancel' },
      {
        text: 'Remove',
        style: 'destructive',
        onPress: () => void run(async () => {
          if (!token || !activeProfile) return;
          await api.removeMember(token, activeProfile.id, member.id);
          setMembers((current) => current.filter((item) => item.id !== member.id));
          await refreshProfiles();
        }),
      },
    ]);
  };

  const requestDeletion = () => {
    Alert.alert(
      'Delete CareRelay account?',
      'Shared care history is retained. If you are the only admin, transfer administration first.',
      [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Delete account', style: 'destructive', onPress: () => void run(deleteAccount) },
      ],
    );
  };

  const subjectInvitation = useMemo(
    () => invitations.find((item) => item.is_subject_invite && item.status === 'pending'),
    [invitations],
  );
  const subjectStatus = activeProfile?.subject_user_id
    ? 'Account linked'
    : subjectInvitation
      ? 'Invitation pending'
      : 'Not invited';

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
              <Text style={styles.eyebrow}>Person this profile is about</Text>
              <Text style={styles.cardTitle}>{activeProfile.name}</Text>
              <Text style={[styles.status, subjectStatus === 'Account linked' && styles.linked]}>{subjectStatus}</Text>
              {!activeProfile.subject_user_id && isAdmin ? (
                <Pressable
                  accessibilityRole="button"
                  onPress={() => { setInviteKind('subject'); setShowInvite(true); }}
                  style={styles.secondary}
                >
                  <Text style={styles.secondaryText}>Invite {activeProfile.name} to CareRelay</Text>
                </Pressable>
              ) : null}
              {activeProfile.subject_user_id ? members.map((member) => {
                const selected = member.user_id === activeProfile.subject_user_id;
                return selected ? <MemberRow key={member.id} member={member} subject /> : null;
              }) : null}
            </View>

            <View style={styles.card}>
              <View style={styles.cardHeader}>
                <View>
                  <Text style={styles.eyebrow}>Care circle</Text>
                  <Text style={styles.cardTitle}>Members</Text>
                </View>
                {isAdmin ? (
                  <Pressable accessibilityRole="button" onPress={() => setShowInvite((value) => !value)} style={styles.smallButton}>
                    <Ionicons name="person-add" size={17} color={colors.surface} />
                    <Text style={styles.smallButtonText}>Invite</Text>
                  </Pressable>
                ) : null}
              </View>
              {showInvite ? (
                <View style={styles.inviteForm}>
                  <TextInput
                    accessibilityLabel="Invitation email"
                    autoCapitalize="none"
                    keyboardType="email-address"
                    onChangeText={setInviteEmail}
                    placeholder="person@example.com"
                    placeholderTextColor={colors.muted}
                    style={styles.input}
                    value={inviteEmail}
                  />
                  <View style={styles.roleRow}>
                    {(['subject', 'family', 'carer'] as InviteKind[]).map((kind) => (
                      <Pressable
                        key={kind}
                        accessibilityLabel={`Invite as ${kind}`}
                        accessibilityRole="radio"
                        accessibilityState={{ checked: inviteKind === kind }}
                        onPress={() => setInviteKind(kind)}
                        style={[styles.roleChoice, inviteKind === kind && styles.roleChoiceSelected]}
                      >
                        <Text style={[styles.roleText, inviteKind === kind && styles.roleTextSelected]}>{kind}</Text>
                      </Pressable>
                    ))}
                  </View>
                  <Pressable accessibilityRole="button" disabled={saving} onPress={() => void sendInvite()} style={styles.save}>
                    {saving ? <ActivityIndicator color={colors.surface} /> : <Text style={styles.saveText}>Send invitation</Text>}
                  </Pressable>
                </View>
              ) : null}
              {members.map((member) => (
                <View key={member.id} style={styles.memberBlock}>
                  <MemberRow member={member} subject={member.user_id === activeProfile.subject_user_id} />
                  {isAdmin ? (
                    <View style={styles.memberActions}>
                      {(['admin', 'family', 'carer'] as EditableRole[]).map((role) => (
                        <Pressable
                          key={role}
                          accessibilityLabel={`Change ${member.display_name} role to ${role}`}
                          accessibilityRole="button"
                          disabled={saving || member.role === role}
                          onPress={() => void changeRole(member, role)}
                        >
                          <Text style={[styles.textAction, member.role === role && styles.activeRole]}>{role}</Text>
                        </Pressable>
                      ))}
                      <Pressable
                        accessibilityLabel={`Remove ${member.display_name}`}
                        accessibilityRole="button"
                        disabled={saving}
                        onPress={() => removeMember(member)}
                      >
                        <Text style={styles.remove}>Remove</Text>
                      </Pressable>
                    </View>
                  ) : null}
                </View>
              ))}
            </View>

            {isAdmin ? (
              <View style={styles.card}>
                <Text style={styles.eyebrow}>Invitations</Text>
                <Text style={styles.cardTitle}>Invitation activity</Text>
                {!invitations.length ? <Text style={styles.body}>No invitations yet.</Text> : null}
                {invitations.map((invitation) => (
                  <View key={invitation.id} style={styles.invitation}>
                    <View style={styles.invitationCopy}>
                      <Text style={styles.memberName}>{invitation.invited_email}</Text>
                      <Text style={styles.memberRole}>
                        {invitation.is_subject_invite ? 'profile subject' : invitation.intended_role} · {invitation.status}
                      </Text>
                      {invitation.delivery_status === 'failed' ? <Text style={styles.deliveryFailed}>Email delivery failed</Text> : null}
                    </View>
                    {invitation.status === 'pending' ? (
                      <View style={styles.invitationActions}>
                        <Pressable
                          accessibilityLabel={`Resend invitation to ${invitation.invited_email}`}
                          accessibilityRole="button"
                          disabled={saving}
                          onPress={() => void resend(invitation)}
                        >
                          <Text style={styles.textAction}>Resend</Text>
                        </Pressable>
                        <Pressable
                          accessibilityLabel={`Revoke invitation to ${invitation.invited_email}`}
                          accessibilityRole="button"
                          disabled={saving}
                          onPress={() => void revoke(invitation)}
                        >
                          <Text style={styles.remove}>Revoke</Text>
                        </Pressable>
                      </View>
                    ) : null}
                  </View>
                ))}
              </View>
            ) : null}

            <View style={styles.card}>
              <Text style={styles.eyebrow}>Local time</Text>
              <Text style={styles.cardTitle}>Profile timezone</Text>
              <TextInput
                accessibilityLabel="Care profile timezone"
                autoCapitalize="none"
                editable={isAdmin}
                onChangeText={setTimezone}
                placeholder="Australia/Melbourne"
                placeholderTextColor={colors.muted}
                style={[styles.input, !isAdmin && styles.readOnly]}
                value={timezone}
              />
              {isAdmin ? (
                <Pressable accessibilityRole="button" disabled={saving} onPress={() => void updateProfile({ timezone: timezone.trim() })} style={styles.save}>
                  <Text style={styles.saveText}>Save timezone</Text>
                </Pressable>
              ) : null}
            </View>
          </>
        ) : null}

        <Pressable accessibilityRole="button" onPress={requestDeletion} style={styles.deleteAccount}>
          <Text style={styles.remove}>Delete my CareRelay account</Text>
        </Pressable>
        <Text style={styles.signedIn}>Signed in as {user?.display_name}</Text>
      </ScrollView>
    </SafeAreaView>
  );
}

function MemberRow({ member, subject = false }: { member: CareMembership; subject?: boolean }) {
  return (
    <View style={styles.member}>
      <View style={styles.avatar}><Text style={styles.avatarText}>{member.display_name.charAt(0).toUpperCase()}</Text></View>
      <View style={styles.memberCopy}>
        <Text style={styles.memberName}>{member.display_name}</Text>
        <Text style={styles.memberRole}>{member.role.replace('_', ' ')}</Text>
      </View>
      {subject ? <View style={styles.subjectBadge}><Text style={styles.subjectText}>Profile subject</Text></View> : null}
    </View>
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
  cardHeader: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  eyebrow: { color: colors.primary, fontSize: 11, fontWeight: '800', textTransform: 'uppercase', letterSpacing: 1 },
  cardTitle: { color: colors.ink, fontSize: 21, fontWeight: '800', marginTop: 7 },
  body: { color: colors.muted, fontSize: 14, lineHeight: 21, marginTop: 9 },
  status: { color: colors.warning, fontSize: 13, fontWeight: '800', marginTop: 8 },
  linked: { color: colors.primary },
  secondary: { minHeight: 48, borderRadius: 14, borderWidth: 1, borderColor: colors.primary, alignItems: 'center', justifyContent: 'center', marginTop: 15 },
  secondaryText: { color: colors.primary, fontSize: 14, fontWeight: '800' },
  smallButton: { borderRadius: 12, backgroundColor: colors.primary, paddingHorizontal: 12, paddingVertical: 9, flexDirection: 'row', gap: 6 },
  smallButtonText: { color: colors.surface, fontSize: 13, fontWeight: '800' },
  inviteForm: { borderRadius: 16, backgroundColor: colors.background, padding: 12, marginTop: 16 },
  input: { minHeight: 50, borderRadius: 13, borderWidth: 1, borderColor: colors.border, backgroundColor: colors.surface, color: colors.ink, fontSize: 15, paddingHorizontal: 13, marginTop: 10 },
  roleRow: { flexDirection: 'row', gap: 7, marginTop: 10 },
  roleChoice: { flex: 1, borderRadius: 10, borderWidth: 1, borderColor: colors.border, paddingVertical: 9, alignItems: 'center' },
  roleChoiceSelected: { borderColor: colors.primary, backgroundColor: colors.primarySoft },
  roleText: { color: colors.muted, fontSize: 12, fontWeight: '700', textTransform: 'capitalize' },
  roleTextSelected: { color: colors.primary },
  save: { minHeight: 48, borderRadius: 13, alignItems: 'center', justifyContent: 'center', backgroundColor: colors.primary, marginTop: 11 },
  saveText: { color: colors.surface, fontSize: 14, fontWeight: '800' },
  memberBlock: { borderTopWidth: 1, borderTopColor: colors.border, marginTop: 10, paddingTop: 5 },
  member: { minHeight: 62, flexDirection: 'row', alignItems: 'center', paddingVertical: 8 },
  avatar: { width: 42, height: 42, borderRadius: 14, backgroundColor: colors.background, alignItems: 'center', justifyContent: 'center' },
  avatarText: { color: colors.primary, fontSize: 17, fontWeight: '800' },
  memberCopy: { flex: 1, marginLeft: 11 },
  memberName: { color: colors.ink, fontSize: 15, fontWeight: '700' },
  memberRole: { color: colors.muted, fontSize: 12, textTransform: 'capitalize', marginTop: 2 },
  subjectBadge: { borderRadius: 99, backgroundColor: colors.primarySoft, paddingHorizontal: 9, paddingVertical: 5 },
  subjectText: { color: colors.primary, fontSize: 10, fontWeight: '800' },
  memberActions: { flexDirection: 'row', alignItems: 'center', justifyContent: 'flex-end', gap: 13, paddingBottom: 8 },
  textAction: { color: colors.primary, fontSize: 12, fontWeight: '800', textTransform: 'capitalize' },
  activeRole: { color: colors.muted },
  remove: { color: colors.error, fontSize: 12, fontWeight: '800' },
  invitation: { flexDirection: 'row', alignItems: 'center', borderTopWidth: 1, borderTopColor: colors.border, paddingVertical: 12, marginTop: 8 },
  invitationCopy: { flex: 1 },
  invitationActions: { flexDirection: 'row', gap: 12 },
  deliveryFailed: { color: colors.error, fontSize: 11, fontWeight: '700', marginTop: 3 },
  readOnly: { backgroundColor: colors.background },
  deleteAccount: { alignItems: 'center', padding: 14 },
  signedIn: { color: colors.muted, textAlign: 'center', fontSize: 12, marginTop: -14 },
});
