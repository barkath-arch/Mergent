import React, { useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, StyleSheet, KeyboardAvoidingView, Platform, ScrollView } from 'react-native';
import { Link } from 'expo-router';
import api from '../../src/api';
import { colors, radius } from '../../src/theme';

export default function ForgotScreen() {
  const [email, setEmail] = useState('');
  const [sent, setSent] = useState(false);

  const submit = async () => {
    try { await api.post('/auth/forgot-password', { email }); } catch {}
    setSent(true);
  };

  return (
    <KeyboardAvoidingView behavior={Platform.OS === 'ios' ? 'padding' : 'height'} style={s.flex}>
      <ScrollView contentContainerStyle={s.container} keyboardShouldPersistTaps="handled">
        <View testID="forgot-page" style={s.card}>
          <Text style={s.title}>Reset password</Text>
          {sent ? (
            <Text style={s.subtitle}>If an account exists for {email}, we've logged a reset link to the server console.</Text>
          ) : (
            <>
              <Text style={[s.subtitle, { marginBottom: 16 }]}>Enter your email and we'll send a reset link.</Text>
              <TextInput testID="forgot-email-input" style={s.input} value={email} onChangeText={setEmail} keyboardType="email-address" autoCapitalize="none" placeholderTextColor={colors.textDim} placeholder="Email" />
              <TouchableOpacity testID="forgot-submit-btn" style={s.btn} onPress={submit} activeOpacity={0.7}>
                <Text style={s.btnText}>Send reset link</Text>
              </TouchableOpacity>
            </>
          )}
          <View style={s.divider} />
          <Link href="/(auth)/login" asChild>
            <TouchableOpacity><Text style={s.linkDim}>← Back to sign in</Text></TouchableOpacity>
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
  title: { fontSize: 22, fontWeight: '600', color: colors.text, marginBottom: 16 },
  subtitle: { fontSize: 13.5, color: colors.textMuted },
  input: { backgroundColor: 'rgba(10,12,26,0.65)', borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, paddingHorizontal: 14, paddingVertical: 12, color: colors.text, fontSize: 14 },
  btn: { backgroundColor: colors.violet, borderRadius: radius.md, paddingVertical: 14, alignItems: 'center', marginTop: 16 },
  btnText: { color: colors.white, fontWeight: '500', fontSize: 15 },
  divider: { height: 1, backgroundColor: colors.border, marginVertical: 16 },
  linkDim: { color: colors.textDim, fontSize: 12.5 },
});
