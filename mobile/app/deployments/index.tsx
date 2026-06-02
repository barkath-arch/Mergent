import React, { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView, StyleSheet, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api';
import { PageHeader, Empty, Chip } from '../../src/components/UI';
import { colors, radius } from '../../src/theme';

export default function DeploymentsScreen() {
  const router = useRouter();
  const [items, setItems] = useState<any[] | null>(null);

  const load = () => api.get('/deployments').then(r => setItems(r.data.items)).catch(() => {});
  useEffect(() => { load(); }, []);

  return (
    <SafeAreaView style={s.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView contentContainerStyle={s.content}>
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn}><Ionicons name="arrow-back" size={20} color={colors.text} /><Text style={s.backText}>Back</Text></TouchableOpacity>
        <PageHeader title="Deployments" subtitle="Streaming logs · real-time state." />
        <View testID="deployments-page">
          {items === null ? <ActivityIndicator size="large" color={colors.violet} /> : items.length === 0 ? <Empty title="No deployments yet" /> :
            items.map(d => (
              <TouchableOpacity key={d.id} testID={`deployment-row-${d.id}`} style={s.card} onPress={() => router.push(`/deployments/${d.id}` as any)}>
                <View style={s.rowBetween}>
                  <View style={[s.row, { flex: 1 }]}>
                    <Ionicons name="rocket" size={16} color={d.status === 'live' ? colors.emerald : colors.violet2} />
                    <View style={{ flex: 1 }}>
                      <Text style={s.title}>{d.solution_title}</Text>
                      <Text style={s.mono}>{d.current_version} · {d.environment}</Text>
                    </View>
                  </View>
                  <Chip text={d.status} variant={d.status === 'live' ? 'emerald' : d.status === 'failed' ? 'rose' : 'amber'} />
                </View>
              </TouchableOpacity>
            ))
          }
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg0 },
  content: { padding: 20, paddingBottom: 40 },
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 16 },
  backText: { color: colors.text, fontSize: 14 },
  card: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, padding: 16, marginBottom: 10 },
  rowBetween: { flexDirection: 'row', alignItems: 'center' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  title: { fontWeight: '500', color: colors.text },
  mono: { fontSize: 11, color: colors.textDim, fontFamily: 'monospace', marginTop: 2 },
});
