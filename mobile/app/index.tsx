import { useEffect } from 'react';
import { useRouter, useSegments } from 'expo-router';
import { useAuth } from '../src/auth';
import { Loader } from '../src/components/UI';

export default function Index() {
  const { user, loading } = useAuth();
  const router = useRouter();
  const segments = useSegments();

  useEffect(() => {
    if (loading) return;
    if (!user) {
      router.replace('/(auth)/login' as any);
    } else {
      router.replace('/(tabs)' as any);
    }
  }, [user, loading]);

  return <Loader />;
}
