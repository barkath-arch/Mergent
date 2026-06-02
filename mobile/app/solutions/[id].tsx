import React, { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView, StyleSheet, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter, Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api';
import { useAuth } from '../../src/auth';
import { Chip } from '../../src/components/UI';
import { colors, radius } from '../../src/theme';

export default function SolutionDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const { user } = useAuth();
  const [s, setS] = useState<any>(null);
  const [loading, setLoading] = useState(true);
  const [buying, setBuying] = useState(false);

  useEffect(() => {
    setLoading(true);
    api.get(`/solutions/${id}`).then(r => setS(r.data)).finally(() => setLoading(false));
  }, [id]);

  const startMessage = async () => {
    if (!s) return;
    try {
      const r = await api.post('/conversations', { recipient_id: s.builder_id, initial_message: `Hi ${s.builder_name}, I'm interested in ${s.title}.` });
      router.push('/(tabs)/messages' as any);
    } catch {}
  };

  const checkout = async () => {
    setBuying(true);
    try {
      const r = await api.post('/checkout/session', { solution_id: s.id });
      if (r.data.simulated) {
        router.push(`/transactions/${r.data.transaction_id}` as any);
      }
    } catch {}
    finally { setBuying(false); }
  };

  if (loading) return <SafeAreaView style={st.safe}><Stack.Screen options={{ headerShown: false }} /><View style={st.center}><ActivityIndicator size="large" color={colors.violet} /></View></SafeAreaView>;
  if (!s) return <SafeAreaView style={st.safe}><Stack.Screen options={{ headerShown: false }} /><View style={st.center}><Text style={st.text}>Solution not found.</Text></View></SafeAreaView>;

  return (
    <SafeAreaView style={st.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView contentContainerStyle={st.content}>
        <TouchableOpacity onPress={() => router.back()} style={st.backBtn}><Ionicons name="arrow-back" size={20} color={colors.text} /><Text style={st.backText}>Back</Text></TouchableOpacity>

        <View testID={`solution-detail-${s.id}`}>
          <View style={st.chipRow}>
            <Chip text={s.category} />
            <Chip text={s.license_model} variant="muted" />
            <Chip text={s.deployment_maturity} variant="emerald" />
          </View>
          <Text testID="solution-title" style={st.h1}>{s.title}</Text>
          <Text style={st.tagline}>{s.tagline}</Text>

          {/* Purchase card */}
          <View testID="purchase-card" style={st.purchaseCard}>
            <Text style={st.priceLabel}>PRICE</Text>
            <Text style={st.price}>${s.price_usd?.toLocaleString?.()}</Text>
            <Text style={st.priceSub}>{s.license_model}</Text>
            <View style={st.divider} />
            <View style={st.escrowRow}>
              <Ionicons name="shield-checkmark" size={16} color={colors.emerald} />
              <Text style={st.escrowText}>Escrow protected · refundable until release</Text>
            </View>
            <TouchableOpacity testID="purchase-btn" style={st.buyBtn} onPress={checkout} disabled={buying}>
              {buying ? <ActivityIndicator size="small" color={colors.white} /> : <><Ionicons name="cart" size={14} color={colors.white} /><Text style={st.buyBtnText}>Acquire with escrow</Text></>}
            </TouchableOpacity>
            <TouchableOpacity testID="message-builder-btn" style={st.msgBtn} onPress={startMessage}>
              <Ionicons name="chatbubble" size={14} color={colors.text} /><Text style={st.msgBtnText}>Message builder</Text>
            </TouchableOpacity>
            <View testID="simulated-banner" style={st.simBanner}><Text style={st.simText}>SIMULATED escrow</Text></View>
          </View>

          {/* About */}
          <View style={st.card}>
            <Text style={st.h3}>About this solution</Text>
            <Text style={st.body}>{s.description}</Text>
            {s.tech_stack?.length > 0 && (
              <View style={{ marginTop: 16 }}>
                <Text style={st.label}>TECH STACK</Text>
                <View style={st.chipRow}>{s.tech_stack.map((t: string) => <Chip key={t} text={t} variant="muted" />)}</View>
              </View>
            )}
          </View>

          {/* Builder */}
          {s.builder && (
            <TouchableOpacity testID="builder-card" style={st.card} onPress={() => router.push(`/builders/${s.builder.id}` as any)}>
              <View style={st.row}>
                <View style={st.avatar}><Text style={st.avatarText}>{(s.builder.name || '?')[0]}</Text></View>
                <View style={{ flex: 1 }}>
                  <Text style={st.builderName}>{s.builder.name}</Text>
                  <Text style={st.dim}>{s.builder.headline}</Text>
                </View>
                {s.builder.verified ? <Chip text="verified" /> : null}
              </View>
              <View style={[st.row, { marginTop: 12 }]}>
                <Text style={st.mono}>★ {s.builder.rating?.toFixed?.(1) || '—'}</Text>
                <Text style={st.mono}>{s.builder.review_count} reviews</Text>
              </View>
            </TouchableOpacity>
          )}

          {/* Reviews */}
          <View testID="solution-reviews" style={st.card}>
            <Text style={st.h3}>Reviews ({s.reviews?.length || 0})</Text>
            {(s.reviews || []).length === 0 ? <Text style={st.dim}>No reviews yet.</Text> :
              s.reviews.map((r: any) => (
                <View key={r.id} style={st.reviewItem}>
                  <View style={st.row}>
                    <View style={[st.avatar, { width: 28, height: 28 }]}><Text style={[st.avatarText, { fontSize: 12 }]}>{(r.buyer_name || '?')[0]}</Text></View>
                    <Text style={st.reviewerName}>{r.buyer_name}</Text>
                    <View style={{ flex: 1 }} />
                    <Text style={{ color: colors.amber, fontSize: 12 }}>{'★'.repeat(r.rating)}</Text>
                  </View>
                  <Text style={[st.dim, { marginTop: 4 }]}>{r.comment}</Text>
                </View>
              ))
            }
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg0 },
  center: { flex: 1, justifyContent: 'center', alignItems: 'center' },
  content: { padding: 20, paddingBottom: 40 },
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 16 },
  backText: { color: colors.text, fontSize: 14 },
  chipRow: { flexDirection: 'row', flexWrap: 'wrap', gap: 8, marginBottom: 12 },
  h1: { fontSize: 28, fontWeight: '600', color: colors.text, marginBottom: 6 },
  tagline: { fontSize: 16, color: colors.textMuted, marginBottom: 24 },
  purchaseCard: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, padding: 20, marginBottom: 16 },
  priceLabel: { fontSize: 11, color: colors.textDim, fontFamily: 'monospace', letterSpacing: 1 },
  price: { fontSize: 34, fontWeight: '600', color: colors.text, marginTop: 4 },
  priceSub: { fontSize: 12, color: colors.textDim, marginTop: 2 },
  divider: { height: 1, backgroundColor: colors.border, marginVertical: 14 },
  escrowRow: { flexDirection: 'row', alignItems: 'center', gap: 8, marginBottom: 16 },
  escrowText: { fontSize: 12, color: colors.textDim },
  buyBtn: { backgroundColor: colors.violet, borderRadius: radius.md, paddingVertical: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8 },
  buyBtnText: { color: colors.white, fontWeight: '500', fontSize: 14 },
  msgBtn: { borderWidth: 1, borderColor: colors.borderStrong, borderRadius: radius.md, paddingVertical: 14, flexDirection: 'row', alignItems: 'center', justifyContent: 'center', gap: 8, marginTop: 10 },
  msgBtnText: { color: colors.text, fontWeight: '500', fontSize: 14 },
  simBanner: { marginTop: 12, paddingHorizontal: 9, paddingVertical: 4, borderWidth: 1, borderStyle: 'dashed', borderColor: 'rgba(251,191,36,0.5)', borderRadius: 6, backgroundColor: 'rgba(251,191,36,0.1)', alignSelf: 'flex-start' },
  simText: { color: colors.amber, fontSize: 10.5, fontWeight: '500', letterSpacing: 0.5 },
  card: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, padding: 18, marginBottom: 16 },
  h3: { fontSize: 18, fontWeight: '600', color: colors.text, marginBottom: 12 },
  body: { fontSize: 14, color: colors.text, lineHeight: 22 },
  label: { fontSize: 11, color: colors.textDim, fontFamily: 'monospace', letterSpacing: 1, marginBottom: 8 },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  avatar: { width: 36, height: 36, borderRadius: 18, backgroundColor: colors.violet, alignItems: 'center', justifyContent: 'center' },
  avatarText: { color: colors.white, fontWeight: '600', fontSize: 14 },
  builderName: { fontWeight: '500', color: colors.text },
  dim: { fontSize: 12, color: colors.textDim },
  mono: { fontSize: 11.5, color: colors.textDim, fontFamily: 'monospace' },
  text: { color: colors.text, fontSize: 16 },
  reviewItem: { borderBottomWidth: 1, borderBottomColor: colors.border, paddingBottom: 14, marginBottom: 14 },
  reviewerName: { fontWeight: '500', fontSize: 13, color: colors.text },
});
