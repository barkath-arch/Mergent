import React, { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView, StyleSheet, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api';
import { PageHeader, Empty, Chip } from '../../src/components/UI';
import { colors, radius } from '../../src/theme';

const STATE_VARIANT: Record<string, 'default' | 'emerald' | 'amber' | 'rose' | 'muted'> = { initiated: 'muted', funded: 'default', in_progress: 'amber', delivered: 'amber', released: 'emerald', reviewed: 'emerald', disputed: 'rose', refunded: 'rose' };

export default function TransactionsScreen() {
  const router = useRouter();
  const [items, setItems] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => { api.get('/transactions/me').then(r => setItems(r.data.items)).finally(() => setLoading(false)); }, []);

  return (
    <SafeAreaView style={s.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView contentContainerStyle={s.content}>
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn}><Ionicons name="arrow-back" size={20} color={colors.text} /><Text style={s.backText}>Back</Text></TouchableOpacity>
        <PageHeader title="Transactions" subtitle="Escrow-protected purchases." />
        <View testID="transactions-page">
          {loading ? <ActivityIndicator size="large" color={colors.violet} /> : items.length === 0 ? <Empty title="No transactions yet" /> :
            items.map(t => (
              <TouchableOpacity key={t.id} testID={`tx-row-${t.id}`} style={s.card} onPress={() => router.push(`/transactions/${t.id}` as any)}>
                <View style={s.rowBetween}>
                  <View style={{ flex: 1 }}>
                    <Text style={s.title}>{t.solution_title}</Text>
                    <Text style={s.dim}>{t.builder_name} · {new Date(t.created_at).toLocaleDateString()}</Text>
                  </View>
                  <Chip text={`$${t.amount_usd?.toLocaleString()}`} variant="emerald" />
                  <View style={{ marginLeft: 6 }}><Chip text={t.status.replace('_', ' ')} variant={STATE_VARIANT[t.status] || 'muted'} /></View>
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
  title: { fontWeight: '500', color: colors.text },
  dim: { fontSize: 12, color: colors.textDim, marginTop: 2 },
});
