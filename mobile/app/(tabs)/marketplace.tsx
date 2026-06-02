import React, { useEffect, useState } from 'react';
import { View, Text, TextInput, ScrollView, StyleSheet, ActivityIndicator, TouchableOpacity } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api';
import { SolutionCard, PageHeader, Empty } from '../../src/components/UI';
import { colors, radius } from '../../src/theme';

const CATEGORIES = ['All', 'Inventory Management', 'CRM', 'HR System', 'Project Management', 'E-commerce', 'Finance', 'Analytics'];
const SORTS: [string, string][] = [['trust', 'Most trusted'], ['recent', 'Newest'], ['price_asc', 'Price ↑'], ['price_desc', 'Price ↓'], ['rating', 'Top rated']];

export default function MarketplaceTab() {
  const [items, setItems] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState('');
  const [category, setCategory] = useState('All');
  const [sort, setSort] = useState('trust');

  useEffect(() => {
    setLoading(true);
    const qs = new URLSearchParams();
    if (q) qs.set('q', q);
    if (category && category !== 'All') qs.set('category', category);
    qs.set('sort', sort);
    qs.set('limit', '30');
    api.get(`/marketplace/search?${qs}`)
      .then(r => { setItems(r.data.items); setTotal(r.data.total); })
      .finally(() => setLoading(false));
  }, [q, category, sort]);

  return (
    <SafeAreaView style={s.safe} edges={['top']}>
      <ScrollView style={s.scroll} contentContainerStyle={s.content}>
        <PageHeader title="Marketplace" subtitle={`${total} production-ready solutions`} />

        <View testID="marketplace-filters" style={s.filterCard}>
          <TextInput
            testID="marketplace-search-input"
            style={s.input}
            placeholder="Search…"
            placeholderTextColor={colors.textDim}
            value={q}
            onChangeText={setQ}
          />
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: 10 }}>
            {CATEGORIES.map(c => (
              <TouchableOpacity
                key={c}
                testID={`marketplace-category-${c}`}
                style={[s.catChip, category === c && s.catChipActive]}
                onPress={() => setCategory(c)}
              >
                <Text style={[s.catChipText, category === c && s.catChipTextActive]}>{c}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
          <ScrollView horizontal showsHorizontalScrollIndicator={false} style={{ marginTop: 8 }}>
            {SORTS.map(([v, l]) => (
              <TouchableOpacity
                key={v}
                testID={`marketplace-sort-${v}`}
                style={[s.catChip, sort === v && s.catChipActive]}
                onPress={() => setSort(v)}
              >
                <Text style={[s.catChipText, sort === v && s.catChipTextActive]}>{l}</Text>
              </TouchableOpacity>
            ))}
          </ScrollView>
          <Text style={s.countText}><Ionicons name="filter" size={12} color={colors.textDim} /> {items.length} of {total}</Text>
        </View>

        {loading ? (
          <View style={s.center}><ActivityIndicator size="large" color={colors.violet} /></View>
        ) : items.length === 0 ? (
          <Empty title="No matches" hint="Try a different category or search." />
        ) : (
          <View testID="marketplace-grid">
            {items.map(sol => <SolutionCard key={sol.id} s={sol} />)}
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg0 },
  scroll: { flex: 1 },
  content: { padding: 20, paddingBottom: 40 },
  filterCard: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, padding: 14, marginBottom: 20 },
  input: { backgroundColor: 'rgba(10,12,26,0.65)', borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: 14, paddingVertical: 10, color: colors.text, fontSize: 14 },
  catChip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: radius.full, backgroundColor: 'rgba(255,255,255,0.04)', borderWidth: 1, borderColor: colors.border, marginRight: 8 },
  catChipActive: { backgroundColor: 'rgba(139,92,246,0.12)', borderColor: 'rgba(139,92,246,0.28)' },
  catChipText: { fontSize: 12, color: colors.textMuted },
  catChipTextActive: { color: colors.violet2 },
  countText: { fontSize: 11.5, color: colors.textDim, fontFamily: 'monospace', marginTop: 8 },
  center: { padding: 56, alignItems: 'center' },
});
