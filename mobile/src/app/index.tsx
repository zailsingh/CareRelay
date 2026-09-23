import { Href, Redirect } from 'expo-router';

import { LoadingScreen } from '@/components/LoadingScreen';
import { useAuth } from '@/providers/AuthProvider';
import { useCareProfiles } from '@/providers/CareProfileProvider';

export default function Index() {
  const { token, loading } = useAuth();
  const { profiles, loading: profilesLoading } = useCareProfiles();
  if (loading || (token && profilesLoading)) return <LoadingScreen />;
  if (!token) return <Redirect href="/sign-in" />;
  return <Redirect href={(profiles.length ? '/(tabs)' : '/onboarding') as Href} />;
}
