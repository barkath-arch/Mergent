import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, KeyboardAvoidingView, Platform, ScrollView, ActivityIndicator } from 'react-native';
import { useRouter, Link } from 'expo-router';
import { useAuth } from '../../src/auth';
import { colors, spacing, radius, font } from '../../src/theme';

export default function LoginScreen() {
  const { login } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState('rohit@mergent.demo');
  const [password, setPassword] = useState('Demo!Pass123');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');

  const submit = async () => {
    setLoading(true); setError('');
    try {
      await login(email, password);
      router.replace('/(tabs)' as any);
    } catch (err: any) {
      setError(err?.response?.data?.detail?.error || 'Login failed');
    } finally { setLoading(false); }
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={s.flex}>
      <ScrollView contentContainerStyle={s.container} keyboardShouldPersistTaps="handled">
        <View testID="login-page" style={s.card}>
          <View style={s.brandRow}>
            <View style={s.brandMark} />
            <Text style={s.brandName}>Mergent</Text>
          </View>
          <Text style={s.title}>Welcome back</Text>
          <Text style={s.subtitle}>Sign in to access the marketplace and AI match.</Text>

          <Text style={s.label}>EMAIL</Text>
          <TextInput
            testID="login-email-input"
            style={s.input}
            value={email}
            onChangeText={setEmail}
            keyboardType="email-address"
            autoCapitalize="none"
            placeholderTextColor={colors.textDim}
          />

          <Text style={[s.label, { marginTop: 16 }]}>PASSWORD</Text>
          <TextInput
            testID="login-password-input"
            style={s.input}
            value={password}
            onChangeText={setPassword}
            secureTextEntry
            placeholderTextColor={colors.textDim}
          />

          {error ? <View style={s.errorChip}><Text style={s.errorText}>{error}</Text></View> : null}

          <TouchableOpacity testID="login-submit-btn" style={[s.btn, loading && { opacity: 0.5 }]} onPress={submit} disabled={loading} activeOpacity={0.7}>
            {loading ? <ActivityIndicator color={colors.white} size="small" /> : <Text style={s.btnText}>Sign in</Text>}
          </TouchableOpacity>

          <View style={s.divider} />
          <View style={s.linksRow}>
            <Link href="/(auth)/forgot" asChild>
              <TouchableOpacity testID="login-forgot-link"><Text style={s.linkDim}>Forgot password?</Text></TouchableOpacity>
            </Link>
            <Link href="/(auth)/register" asChild>
              <TouchableOpacity testID="login-register-link"><Text style={s.linkMuted}>Create an account →</Text></TouchableOpacity>
            </Link>
          </View>
          <Text style={s.demoText}>
            Demo buyer: rohit@mergent.demo / Demo!Pass123{'\n'}
            Demo builder: aman@mergent.demo / Demo!Pass123
          </Text>
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
  input: { backgroundColor: 'rgba(10,12,26,0.65)', borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: 14, paddingVertical: 12, color: colors.text, fontSize: 14 },
  errorChip: { backgroundColor: 'rgba(251,113,133,0.1)', borderWidth: 1, borderColor: 'rgba(251,113,133,0.3)', borderRadius: radius.full, paddingHorizontal: 12, paddingVertical: 6, marginTop: 16, alignSelf: 'flex-start' },
  errorText: { color: colors.rose, fontSize: 12 },
  btn: { backgroundColor: colors.violet, borderRadius: radius.md, paddingVertical: 14, alignItems: 'center', marginTop: 24 },
  btnText: { color: colors.white, fontWeight: '500', fontSize: 15 },
  divider: { height: 1, backgroundColor: colors.border, marginVertical: 16 },
  linksRow: { flexDirection: 'row', justifyContent: 'space-between' },
  linkDim: { color: colors.textDim, fontSize: 12.5 },
  linkMuted: { color: colors.textMuted, fontSize: 12.5 },
  demoText: { color: colors.textDim, fontSize: 11.5, textAlign: 'center', marginTop: 24, lineHeight: 18 },
});
