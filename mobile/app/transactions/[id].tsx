import React, { useEffect, useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, ScrollView, StyleSheet, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter, Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api';
import { useAuth } from '../../src/auth';
import { Chip } from '../../src/components/UI';
import { colors, radius } from '../../src/theme';

const STATES = ['initiated', 'funded', 'in_progress', 'delivered', 'released', 'reviewed'];
const NEXT: Record<string, string[]> = { funded: ['in_progress'], in_progress: ['delivered'], delivered: ['released'] };

export default function TransactionDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const { user } = useAuth();
  const router = useRouter();
  const [tx, setTx] = useState<any>(null);
  const [reviewing, setReviewing] = useState(false);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState('');

  const load = () => api.get(`/transactions/${id}`).then(r => setTx(r.data));
  useEffect(() => { load(); }, [id]);

  const advance = async (next: string) => {
    try { const r = await api.post(`/transactions/${id}/advance`, { next_state: next }); setTx(r.data); } catch {}
  };
  const review = async () => {
    try { await api.post(`/transactions/${id}/review`, { rating, comment }); setReviewing(false); load(); } catch {}
  };

  if (!tx) return <SafeAreaView style={s.safe}><Stack.Screen options={{ headerShown: false }} /><View style={s.center}><ActivityIndicator size="large" color={colors.violet} /></View></SafeAreaView>;
  const idx = STATES.indexOf(tx.status);
  const canReview = tx.status === 'released' && tx.buyer_id === user?.id;

  return (
    <SafeAreaView style={s.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView contentContainerStyle={s.content}>
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn}><Ionicons name="arrow-back" size={20} color={colors.text} /><Text style={s.backText}>Back</Text></TouchableOpacity>

        <View testID="transaction-detail">
          <View style={s.row}>
            <Ionicons name="receipt" size={16} color={colors.textMuted} />
            <Text style={s.mono}>{id?.slice(0, 8)}</Text>
            <Chip text={tx.status.replace('_', ' ')} variant={tx.status === 'released' || tx.status === 'reviewed' ? 'emerald' : 'amber'} />
          </View>
          <Text style={s.h1}>{tx.solution_title}</Text>
          <Text style={s.muted}>{tx.buyer_name} → {tx.builder_name} · ${tx.amount_usd?.toLocaleString()}</Text>

          {/* Pipeline */}
          <View style={s.card}>
            <Text style={s.h3}>Escrow progress</Text>
            <View testID="state-pipeline" style={s.pipeline}>
              {STATES.map((st, i) => (
                <View key={st} style={{ flex: 1 }}>
                  <View style={[s.pipeBar, i <= idx && s.pipeBarActive]} />
                  <Text style={s.pipeLabel}>{st.replace('_', ' ')}</Text>
                </View>
              ))}
            </View>
            <View style={[s.row, { marginTop: 16, flexWrap: 'wrap' }]}>
              {(NEXT[tx.status] || []).map((n: string) => (
                <TouchableOpacity key={n} testID={`advance-${n}-btn`} style={s.btn} onPress={() => advance(n)}>
                  <Text style={s.btnText}>→ {n.replace('_', ' ')}</Text>
                </TouchableOpacity>
              ))}
              {canReview && !reviewing && (
                <TouchableOpacity testID="leave-review-btn" style={s.btnSec} onPress={() => setReviewing(true)}>
                  <Text style={s.btnSecText}>Leave review</Text>
                </TouchableOpacity>
              )}
            </View>
            {reviewing && (
              <View style={[s.card, { marginTop: 16, backgroundColor: 'rgba(8,9,18,0.6)' }]}>
                <View style={s.row}>
                  {[1, 2, 3, 4, 5].map(n => (
                    <TouchableOpacity key={n} onPress={() => setRating(n)}>
                      <Ionicons name={n <= rating ? 'star' : 'star-outline'} size={24} color={n <= rating ? colors.amber : colors.textDim} />
                    </TouchableOpacity>
                  ))}
                </View>
                <TextInput testID="review-comment-input" style={s.input} placeholder="How was your experience?" placeholderTextColor={colors.textDim} value={comment} onChangeText={setComment} multiline />
                <TouchableOpacity testID="submit-review-btn" style={[s.btn, { marginTop: 10 }]} onPress={review}>
                  <Text style={s.btnText}>Post review</Text>
                </TouchableOpacity>
              </View>
            )}
          </View>

          {/* History */}
          <View style={s.card}>
            <Text style={s.h3}>History</Text>
            {(tx.state_history || []).map((h: any, i: number) => (
              <View key={i} style={[s.row, { marginBottom: 8 }]}>
                <Text style={s.mono}>{new Date(h.at).toLocaleString()}</Text>
                <Chip text={h.state} variant={h.state === 'released' ? 'emerald' : 'muted'} />
                <Text style={s.dim}>by {h.by}</Text>
              </View>
            ))}
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg0 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  content: { padding: 20, paddingBottom: 40 },
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 16 },
  backText: { color: colors.text, fontSize: 14 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 8 },
  h1: { fontSize: 28, fontWeight: '600', color: colors.text, marginBottom: 4 },
  muted: { fontSize: 14, color: colors.textMuted, marginBottom: 24 },
  mono: { fontSize: 11, color: colors.textDim, fontFamily: 'monospace' },
  dim: { fontSize: 12, color: colors.textDim },
  card: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, padding: 18, marginBottom: 16 },
  h3: { fontSize: 18, fontWeight: '600', color: colors.text, marginBottom: 12 },
  pipeline: { flexDirection: 'row', gap: 4 },
  pipeBar: { height: 4, backgroundColor: 'rgba(255,255,255,0.06)', borderRadius: 4 },
  pipeBarActive: { backgroundColor: colors.violet },
  pipeLabel: { fontSize: 9, color: colors.textDim, marginTop: 4, textTransform: 'uppercase' },
  btn: { backgroundColor: colors.violet, borderRadius: radius.md, paddingVertical: 10, paddingHorizontal: 16 },
  btnText: { color: colors.white, fontWeight: '500', fontSize: 13 },
  btnSec: { borderWidth: 1, borderColor: colors.borderStrong, borderRadius: radius.md, paddingVertical: 10, paddingHorizontal: 16 },
  btnSecText: { color: colors.text, fontWeight: '500', fontSize: 13 },
  input: { backgroundColor: 'rgba(10,12,26,0.65)', borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: 12, color: colors.text, fontSize: 14, minHeight: 80, textAlignVertical: 'top', marginTop: 10 },
});
