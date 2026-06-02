import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, ScrollView, StyleSheet, KeyboardAvoidingView, Platform, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api';
import { PageHeader } from '../../src/components/UI';
import { colors, radius } from '../../src/theme';

const CATEGORIES = ['Inventory Management', 'CRM', 'HR System', 'Project Management', 'E-commerce', 'Finance', 'Analytics', 'Marketing', 'Operations', 'Other'];

export default function RequirementFormScreen() {
  const router = useRouter();
  const [f, setF] = useState({ title: '', description: '', category: 'Inventory Management', budget_usd: '', timeline: 'flexible', tags: '' });
  const [loading, setLoading] = useState(false);

  const submit = async () => {
    setLoading(true);
    try {
      await api.post('/requirements', {
        title: f.title, description: f.description, category: f.category,
        budget_usd: f.budget_usd ? Number(f.budget_usd) : null,
        timeline: f.timeline,
        tags: f.tags.split(',').map(t => t.trim()).filter(Boolean),
      });
      router.back();
    } catch {}
    finally { setLoading(false); }
  };

  return (
    <SafeAreaView style={s.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
          <TouchableOpacity onPress={() => router.back()} style={s.backBtn}><Ionicons name="arrow-back" size={20} color={colors.text} /><Text style={s.backText}>Back</Text></TouchableOpacity>

          <View testID="requirement-form-page">
            <PageHeader title="Post a requirement" subtitle="Better descriptions → better matches." />
            <View style={s.card}>
              <Text style={s.label}>TITLE</Text>
              <TextInput testID="req-title-input" style={s.input} value={f.title} onChangeText={v => setF({ ...f, title: v })} placeholder="e.g., Multi-tenant ERP for textile factory" placeholderTextColor={colors.textDim} />

              <Text style={[s.label, { marginTop: 16 }]}>DETAILED DESCRIPTION</Text>
              <TextInput testID="req-description-input" style={[s.input, { minHeight: 110, textAlignVertical: 'top' }]} value={f.description} onChangeText={v => setF({ ...f, description: v })} placeholder="The more specific, the better." placeholderTextColor={colors.textDim} multiline />

              <Text style={[s.label, { marginTop: 16 }]}>CATEGORY</Text>
              <ScrollView horizontal showsHorizontalScrollIndicator={false}>
                {CATEGORIES.map(c => (
                  <TouchableOpacity key={c} testID={`req-category-${c}`} style={[s.catChip, f.category === c && s.catChipActive]} onPress={() => setF({ ...f, category: c })}>
                    <Text style={[s.catChipText, f.category === c && s.catChipTextActive]}>{c}</Text>
                  </TouchableOpacity>
                ))}
              </ScrollView>

              <Text style={[s.label, { marginTop: 16 }]}>BUDGET USD</Text>
              <TextInput testID="req-budget-input" style={s.input} value={f.budget_usd} onChangeText={v => setF({ ...f, budget_usd: v })} placeholder="optional" placeholderTextColor={colors.textDim} keyboardType="numeric" />

              <Text style={[s.label, { marginTop: 16 }]}>TIMELINE</Text>
              <TextInput testID="req-timeline-input" style={s.input} value={f.timeline} onChangeText={v => setF({ ...f, timeline: v })} placeholder="e.g., Q1 2026" placeholderTextColor={colors.textDim} />

              <Text style={[s.label, { marginTop: 16 }]}>TAGS (comma-separated)</Text>
              <TextInput testID="req-tags-input" style={s.input} value={f.tags} onChangeText={v => setF({ ...f, tags: v })} placeholder="multi-tenant, compliance" placeholderTextColor={colors.textDim} />

              <TouchableOpacity testID="req-submit-btn" style={[s.btn, loading && { opacity: 0.5 }]} onPress={submit} disabled={loading}>
                {loading ? <ActivityIndicator size="small" color={colors.white} /> : <Text style={s.btnText}>Post requirement</Text>}
              </TouchableOpacity>
            </View>
          </View>
        </ScrollView>
      </KeyboardAvoidingView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg0 },
  content: { padding: 20, paddingBottom: 40 },
  backBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, marginBottom: 16 },
  backText: { color: colors.text, fontSize: 14 },
  card: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, padding: 20 },
  label: { fontSize: 11, color: colors.textDim, fontFamily: 'monospace', letterSpacing: 1, marginBottom: 8 },
  input: { backgroundColor: 'rgba(10,12,26,0.65)', borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: 14, paddingVertical: 12, color: colors.text, fontSize: 14 },
  catChip: { paddingHorizontal: 12, paddingVertical: 6, borderRadius: 999, backgroundColor: 'rgba(255,255,255,0.04)', borderWidth: 1, borderColor: colors.border, marginRight: 8 },
  catChipActive: { backgroundColor: 'rgba(139,92,246,0.12)', borderColor: 'rgba(139,92,246,0.28)' },
  catChipText: { fontSize: 12, color: colors.textMuted },
  catChipTextActive: { color: colors.violet2 },
  btn: { backgroundColor: colors.violet, borderRadius: radius.md, paddingVertical: 14, alignItems: 'center', marginTop: 24 },
  btnText: { color: colors.white, fontWeight: '500', fontSize: 15 },
});
