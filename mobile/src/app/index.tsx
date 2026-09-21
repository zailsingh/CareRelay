import { Redirect } from 'expo-router';

import { LoadingScreen } from '@/components/LoadingScreen';
import { useAuth } from '@/providers/AuthProvider';

export default function Index() {
  const { token, loading } = useAuth();
  if (loading) return <LoadingScreen />;
  return <Redirect href={token ? '/(tabs)' : '/sign-in'} />;
}

