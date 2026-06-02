import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, KeyboardAvoidingView, Platform, ScrollView, ActivityIndicator } from 'react-native';
import { useRouter, Link } from 'expo-router';
import { useAuth } from '../../src/auth';
import { colors, spacing, radius, font } from '../../src/theme';

export default function RegisterScreen() {
  const { register } = useAuth();
  const router = useRouter();
  const [form, setForm] = useState({ name: '', email: '', password: '', role: 'buyer' });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const submit = async () => {
    setLoading(true); setError('');
    try {
      await register(form);
      router.replace('/(tabs)' as any);
    } catch (err: any) {
      setError(err?.response?.data?.detail?.error || 'Registration failed');
    } finally { setLoading(false); }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={s.flex}>
      <ScrollView contentContainerStyle={s.container} keyboardShouldPersistTaps="handled">
        <View testID="register-page" style={s.card}>
          <View style={s.brandRow}>
            <View style={s.brandMark} />
            <Text style={s.brandName}>Mergent</Text>
          </View>
          <Text style={s.title}>Create account</Text>
          <Text style={s.subtitle}>Join as a buyer or builder.</Text>

          <Text style={s.label}>I'M A…</Text>
          <View style={s.roleRow}>
            {(['buyer', 'builder'] as const).map(r => (
              <TouchableOpacity
                key={r}
                testID={`register-role-${r}`}
                style={[s.roleCard, form.role === r && s.roleActive]}
                onPress={() => setForm({ ...form, role: r })}
                activeOpacity={0.7}
              >
                <Text style={s.roleTitle}>{r.charAt(0).toUpperCase() + r.slice(1)}</Text>
                <Text style={s.roleSub}>{r === 'buyer' ? 'Find & acquire software' : 'Sell solutions you\'ve built'}</Text>
              </TouchableOpacity>
            ))}
          </View>

          <TextInput testID="register-name-input" style={[s.input, { marginTop: 12 }]} placeholder="Full name" placeholderTextColor={colors.textDim} value={form.name} onChangeText={v => setForm({ ...form, name: v })} />
          <TextInput testID="register-email-input" style={[s.input, { marginTop: 12 }]} placeholder="you@company.com" placeholderTextColor={colors.textDim} value={form.email} onChangeText={v => setForm({ ...form, email: v })} keyboardType="email-address" autoCapitalize="none" />
          <TextInput testID="register-password-input" style={[s.input, { marginTop: 12 }]} placeholder="Password (min 8)" placeholderTextColor={colors.textDim} value={form.password} onChangeText={v => setForm({ ...form, password: v })} secureTextEntry />

          {error ? <View style={s.errorChip}><Text style={s.errorText}>{error}</Text></View> : null}

          <TouchableOpacity testID="register-submit-btn" style={[s.btn, loading && { opacity: 0.5 }]} onPress={submit} disabled={loading} activeOpacity={0.7}>
            {loading ? <ActivityIndicator color={colors.white} size="small" /> : <Text style={s.btnText}>Create account</Text>}
          </TouchableOpacity>

          <View style={s.divider} />
          <Link href="/(auth)/login" asChild>
            <TouchableOpacity testID="register-login-link" style={{ alignSelf: 'center' }}>
              <Text style={s.linkMuted}>Already have an account? Sign in</Text>
            </TouchableOpacity>
          </Link>
        </View>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

const s = StyleSheet.create({
  flex: { flex: 1, backgroundColor: colors.bg0 },
  container: { flexGrow: 1, justifyContent: 'center', padding: 24 },
  card: { backgroundColor: colors.surfaceElevated, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, padding: 28 },
  brandRow: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 24 },
  brandMark: { width: 28, height: 28, borderRadius: 8, backgroundColor: colors.violet },
  brandName: { fontSize: 22, fontWeight: '600', color: colors.text },
  title: { fontSize: 26, fontWeight: '600', color: colors.text, marginBottom: 6 },
  subtitle: { fontSize: 13.5, color: colors.textMuted, marginBottom: 24 },
  label: { fontSize: 11, color: colors.textDim, fontFamily: 'monospace', letterSpacing: 1, textTransform: 'uppercase', marginBottom: 8 },
  roleRow: { flexDirection: 'row', gap: 12 },
  roleCard: { flex: 1, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: 14, alignItems: 'center' },
  roleActive: { borderColor: colors.violet2, backgroundColor: 'rgba(139,92,246,0.1)' },
  roleTitle: { fontWeight: '500', fontSize: 13.5, color: colors.text },
  roleSub: { fontSize: 11, color: colors.textDim, marginTop: 2 },
  input: { backgroundColor: 'rgba(10,12,26,0.65)', borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: 14, paddingVertical: 12, color: colors.text, fontSize: 14 },
  errorChip: { backgroundColor: 'rgba(251,113,133,0.1)', borderWidth: 1, borderColor: 'rgba(251,113,133,0.3)', borderRadius: radius.full, paddingHorizontal: 12, paddingVertical: 6, marginTop: 16, alignSelf: 'flex-start' },
  errorText: { color: colors.rose, fontSize: 12 },
  btn: { backgroundColor: colors.violet, borderRadius: radius.md, paddingVertical: 14, alignItems: 'center', marginTop: 24 },
  btnText: { color: colors.white, fontWeight: '500', fontSize: 15 },
  divider: { height: 1, backgroundColor: colors.border, marginVertical: 16 },
  linkMuted: { color: colors.textMuted, fontSize: 12.5 },
});
