import { Ionicons } from '@expo/vector-icons';
import { Redirect, Tabs } from 'expo-router';
import { ColorValue } from 'react-native';

import { LoadingScreen } from '@/components/LoadingScreen';
import { useAuth } from '@/providers/AuthProvider';
import { colors } from '@/theme/colors';

type IconName = React.ComponentProps<typeof Ionicons>['name'];

function tabIcon(name: IconName) {
  return ({ color, size }: { color: ColorValue; size: number }) => (
    <Ionicons name={name} color={color} size={size} />
  );
}

export default function TabLayout() {
  const { token, loading } = useAuth();
  if (loading) return <LoadingScreen />;
  if (!token) return <Redirect href="/sign-in" />;

  return (
    <Tabs
      screenOptions={{
        headerShown: false,
        tabBarActiveTintColor: colors.primary,
        tabBarInactiveTintColor: colors.muted,
        tabBarLabelStyle: { fontSize: 11, fontWeight: '600' },
        tabBarStyle: { height: 84, paddingTop: 8, paddingBottom: 22, borderTopColor: colors.border, backgroundColor: colors.surface },
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Overview', tabBarIcon: tabIcon('home-outline') }} />
      <Tabs.Screen name="timeline" options={{ title: 'Timeline', tabBarIcon: tabIcon('time-outline') }} />
      <Tabs.Screen name="chat" options={{ title: 'Chat', tabBarIcon: tabIcon('chatbubble-outline') }} />
      <Tabs.Screen name="ask-ai" options={{ title: 'Ask AI', tabBarIcon: tabIcon('sparkles-outline') }} />
      <Tabs.Screen name="people" options={{ title: 'People', tabBarIcon: tabIcon('people-outline') }} />
    </Tabs>
  );
}
