import React, { useEffect, useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView, StyleSheet, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter, Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api';
import { SolutionCard, Chip, Empty } from '../../src/components/UI';
import { colors, radius } from '../../src/theme';

export default function BuilderDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<any>(null);

  useEffect(() => { api.get(`/builders/${id}`).then(r => setData(r.data)).catch(() => {}); }, [id]);

  if (!data) return <SafeAreaView style={s.safe}><Stack.Screen options={{ headerShown: false }} /><View style={s.center}><ActivityIndicator size="large" color={colors.violet} /></View></SafeAreaView>;
  const b = data.builder;

  return (
    <SafeAreaView style={s.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView contentContainerStyle={s.content}>
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn}><Ionicons name="arrow-back" size={20} color={colors.text} /><Text style={s.backText}>Back</Text></TouchableOpacity>

        <View testID={`builder-detail-${id}`}>
          <View style={s.headerRow}>
            <View style={s.bigAvatar}><Text style={s.bigAvatarText}>{b.name[0]}</Text></View>
            <View style={{ flex: 1 }}>
              <Text style={s.h1}>{b.name}</Text>
              <Text style={s.muted}>{b.headline}</Text>
              <View style={[s.row, { marginTop: 8 }]}>
                <Chip text={`★ ${b.rating?.toFixed?.(1) || '—'}`} />
                <Chip text={`${b.review_count} reviews`} variant="muted" />
                <Chip text={`${b.solutions_count} solutions`} variant="muted" />
              </View>
            </View>
          </View>

          <View style={s.card}>
            <Text style={s.h3}>About</Text>
            <Text style={s.body}>{b.bio || '—'}</Text>
            {b.skills?.length > 0 && (
              <View style={[s.row, { marginTop: 12, flexWrap: 'wrap' }]}>
                {b.skills.map((sk: string) => <Chip key={sk} text={sk} variant="muted" />)}
              </View>
            )}
          </View>

          <Text style={[s.h3, { marginBottom: 12 }]}>Solutions by {b.name.split(' ')[0]}</Text>
          {data.solutions.length === 0 ? <Empty title="No solutions yet" /> : (
            <View testID="builder-solutions">{data.solutions.map((sol: any) => <SolutionCard key={sol.id} s={sol} />)}</View>
          )}
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
  headerRow: { flexDirection: 'row', gap: 16, marginBottom: 24 },
  bigAvatar: { width: 64, height: 64, borderRadius: 32, backgroundColor: colors.violet, alignItems: 'center', justifyContent: 'center' },
  bigAvatarText: { color: colors.white, fontWeight: '600', fontSize: 22 },
  h1: { fontSize: 28, fontWeight: '600', color: colors.text },
  muted: { fontSize: 14, color: colors.textMuted },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  card: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, padding: 18, marginBottom: 24 },
  h3: { fontSize: 18, fontWeight: '600', color: colors.text, marginBottom: 8 },
  body: { fontSize: 14, color: colors.text, lineHeight: 22 },
});
