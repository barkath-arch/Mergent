import React from 'react';
import { View, Text, TouchableOpacity, ScrollView, StyleSheet } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import { useAuth } from '../../src/auth';
import { colors, radius } from '../../src/theme';

export default function MoreTab() {
  const router = useRouter();
  const { user, logout } = useAuth();

  const items = [
    { label: 'Transactions', icon: 'receipt-outline' as const, route: '/transactions' },
    { label: 'Deployments', icon: 'rocket-outline' as const, route: '/deployments' },
    { label: 'Post Requirement', icon: 'add-circle-outline' as const, route: '/requirements/new' },
    { label: 'Settings', icon: 'settings-outline' as const, route: '/settings' },
  ];

  return (
    <SafeAreaView style={s.safe} edges={['top']}>
      <ScrollView style={s.scroll} contentContainerStyle={s.content}>
        {/* User card */}
        <View testID="more-user-card" style={s.userCard}>
          <View style={s.avatar}><Text style={s.avatarText}>{(user?.name || '?')[0].toUpperCase()}</Text></View>
          <View style={{ flex: 1 }}>
            <Text testID="more-user-name" style={s.userName}>{user?.name || 'Guest'}</Text>
            <Text style={s.userRole}>{user?.role?.toUpperCase()}</Text>
            <Text style={s.userEmail}>{user?.email}</Text>
          </View>
        </View>

        {/* Menu items */}
        <View style={s.menuCard}>
          {items.map(item => (
            <TouchableOpacity key={item.label} testID={`more-${item.label.toLowerCase().replace(/\s+/g, '-')}-btn`} style={s.menuItem} onPress={() => router.push(item.route as any)} activeOpacity={0.7}>
              <Ionicons name={item.icon} size={20} color={colors.textMuted} />
              <Text style={s.menuLabel}>{item.label}</Text>
              <Ionicons name="chevron-forward" size={16} color={colors.textDim} />
            </TouchableOpacity>
          ))}
        </View>

        {/* Logout */}
        <TouchableOpacity
          testID="more-logout-btn"
          style={s.logoutBtn}
          onPress={async () => { await logout(); router.replace('/(auth)/login' as any); }}
          activeOpacity={0.7}
        >
          <Ionicons name="log-out-outline" size={20} color={colors.rose} />
          <Text style={s.logoutText}>Sign out</Text>
        </TouchableOpacity>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg0 },
  scroll: { flex: 1 },
  content: { padding: 20 },
  userCard: { flexDirection: 'row', alignItems: 'center', gap: 16, backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, padding: 20, marginBottom: 24 },
  avatar: { width: 52, height: 52, borderRadius: 26, backgroundColor: colors.violet, alignItems: 'center', justifyContent: 'center' },
  avatarText: { color: colors.white, fontWeight: '600', fontSize: 20 },
  userName: { fontSize: 18, fontWeight: '600', color: colors.text },
  userRole: { fontSize: 10.5, color: colors.textDim, letterSpacing: 1, marginTop: 2 },
  userEmail: { fontSize: 12, color: colors.textMuted, marginTop: 2 },
  menuCard: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, overflow: 'hidden', marginBottom: 24 },
  menuItem: { flexDirection: 'row', alignItems: 'center', gap: 14, paddingVertical: 16, paddingHorizontal: 18, borderBottomWidth: 1, borderBottomColor: colors.border },
  menuLabel: { flex: 1, fontSize: 15, fontWeight: '500', color: colors.text },
  logoutBtn: { flexDirection: 'row', alignItems: 'center', gap: 10, justifyContent: 'center', paddingVertical: 14, borderWidth: 1, borderColor: 'rgba(251,113,133,0.3)', borderRadius: radius.md, backgroundColor: 'rgba(251,113,133,0.06)' },
  logoutText: { color: colors.rose, fontWeight: '500', fontSize: 15 },
});
