import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, ScrollView, StyleSheet, KeyboardAvoidingView, Platform, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter, Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api from '../../src/api';
import { useAuth } from '../../src/auth';
import { PageHeader } from '../../src/components/UI';
import { colors, radius } from '../../src/theme';

export default function SettingsScreen() {
  const { user, refreshMe } = useAuth();
  const router = useRouter();
  const [name, setName] = useState(user?.name || '');
  const [headline, setHeadline] = useState('');
  const [bio, setBio] = useState('');
  const [skills, setSkills] = useState('');
  const [company, setCompany] = useState('');
  const [saving, setSaving] = useState(false);

  if (!user) return null;
  const isBuilder = user.role === 'builder';

  const save = async () => {
    setSaving(true);
    try {
      const payload: any = { name };
      if (isBuilder) {
        if (headline) payload.headline = headline;
        if (bio) payload.bio = bio;
        if (skills) payload.skills = skills.split(',').map(s => s.trim()).filter(Boolean);
      } else {
        if (company) payload.company = company;
      }
      await api.patch('/me', payload);
      refreshMe();
    } catch {}
    finally { setSaving(false); }
  };

  return (
    <SafeAreaView style={s.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={{ flex: 1 }}>
        <ScrollView contentContainerStyle={s.content} keyboardShouldPersistTaps="handled">
          <TouchableOpacity onPress={() => router.back()} style={s.backBtn}><Ionicons name="arrow-back" size={20} color={colors.text} /><Text style={s.backText}>Back</Text></TouchableOpacity>

          <View testID="settings-page">
            <PageHeader title="Settings" subtitle={`Signed in as ${user.email} (${user.role})`} />
            <View style={s.card}>
              <Text style={s.label}>DISPLAY NAME</Text>
              <TextInput testID="settings-name-input" style={s.input} value={name} onChangeText={setName} placeholderTextColor={colors.textDim} />

              {isBuilder ? (
                <>
                  <Text style={[s.label, { marginTop: 16 }]}>HEADLINE</Text>
                  <TextInput testID="settings-headline-input" style={s.input} value={headline} onChangeText={setHeadline} placeholder="One-liner about what you build" placeholderTextColor={colors.textDim} />
                  <Text style={[s.label, { marginTop: 16 }]}>BIO</Text>
                  <TextInput testID="settings-bio-input" style={[s.input, { minHeight: 100, textAlignVertical: 'top' }]} value={bio} onChangeText={setBio} placeholder="Your story." placeholderTextColor={colors.textDim} multiline />
                  <Text style={[s.label, { marginTop: 16 }]}>SKILLS (comma-separated)</Text>
                  <TextInput testID="settings-skills-input" style={s.input} value={skills} onChangeText={setSkills} placeholder="Python, React, Postgres" placeholderTextColor={colors.textDim} />
                </>
              ) : (
                <>
                  <Text style={[s.label, { marginTop: 16 }]}>COMPANY</Text>
                  <TextInput testID="settings-company-input" style={s.input} value={company} onChangeText={setCompany} placeholder="Your company name" placeholderTextColor={colors.textDim} />
                </>
              )}

              <TouchableOpacity testID="settings-save-btn" style={[s.btn, saving && { opacity: 0.5 }]} onPress={save} disabled={saving}>
                {saving ? <ActivityIndicator size="small" color={colors.white} /> : <Text style={s.btnText}>Save</Text>}
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
  btn: { backgroundColor: colors.violet, borderRadius: radius.md, paddingVertical: 14, alignItems: 'center', marginTop: 24 },
  btnText: { color: colors.white, fontWeight: '500', fontSize: 15 },
});
