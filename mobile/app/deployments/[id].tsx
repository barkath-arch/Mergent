import React, { useEffect, useRef, useState } from 'react';
import { View, Text, TouchableOpacity, ScrollView, StyleSheet, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useLocalSearchParams, useRouter, Stack } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api, { WS_BASE, getAccessToken } from '../../src/api';
import { Chip } from '../../src/components/UI';
import { colors, radius } from '../../src/theme';

export default function DeploymentDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const router = useRouter();
  const [d, setD] = useState<any>(null);
  const [logs, setLogs] = useState<any[]>([]);
  const logRef = useRef<ScrollView>(null);

  useEffect(() => {
    api.get(`/deployments/${id}`).then(r => { setD(r.data); setLogs(r.data.logs || []); });
    const url = `${WS_BASE}/deployments/${id}?token=${getAccessToken()}`;
    let ws: WebSocket;
    try {
      ws = new WebSocket(url);
      ws.onmessage = (e: any) => {
        try {
          const m = JSON.parse(e.data);
          if (m.type === 'log') setLogs(prev => [...prev, m]);
          if (m.type === 'state') setD((prev: any) => prev ? { ...prev, status: m.state } : prev);
          if (m.type === 'completed') api.get(`/deployments/${id}`).then(r => setD(r.data));
        } catch {}
      };
    } catch {}
    return () => { try { ws?.close(); } catch {} };
  }, [id]);

  useEffect(() => { logRef.current?.scrollToEnd?.({ animated: true }); }, [logs]);

  const act = async (action: string) => {
    try { await api.post(`/deployments/${id}/action`, { action }); } catch {}
  };

  if (!d) return <SafeAreaView style={s.safe}><Stack.Screen options={{ headerShown: false }} /><View style={s.center}><ActivityIndicator size="large" color={colors.violet} /></View></SafeAreaView>;

  return (
    <SafeAreaView style={s.safe} edges={['top']}>
      <Stack.Screen options={{ headerShown: false }} />
      <ScrollView contentContainerStyle={s.content}>
        <TouchableOpacity onPress={() => router.back()} style={s.backBtn}><Ionicons name="arrow-back" size={20} color={colors.text} /><Text style={s.backText}>Back</Text></TouchableOpacity>

        <View testID={`deployment-detail-${id}`}>
          <View style={s.row}>
            <Ionicons name="rocket" size={20} color={d.status === 'live' ? colors.emerald : colors.violet2} />
            <Chip text={d.status} variant={d.status === 'live' ? 'emerald' : 'amber'} />
            <Text style={s.mono}>{d.current_version}</Text>
          </View>
          <Text style={s.h1}>{d.solution_title}</Text>

          <View style={[s.row, { marginTop: 16 }]}>
            <TouchableOpacity testID="redeploy-btn" style={s.btnSec} onPress={() => act('redeploy')}>
              <Ionicons name="refresh" size={14} color={colors.text} /><Text style={s.btnSecText}>Redeploy</Text>
            </TouchableOpacity>
            <TouchableOpacity testID="rollback-btn" style={s.btnSec} onPress={() => act('rollback')}>
              <Ionicons name="arrow-undo" size={14} color={colors.text} /><Text style={s.btnSecText}>Rollback</Text>
            </TouchableOpacity>
          </View>

          {/* Logs */}
          <View style={[s.card, { marginTop: 20 }]}>
            <Text style={s.h3}>Log stream</Text>
            <ScrollView ref={logRef} style={s.logStream} testID="log-stream">
              {logs.map((l, i) => (
                <View key={i} style={s.logRow}>
                  <Text style={s.logTs}>{new Date(l.ts).toLocaleTimeString()}</Text>
                  <View style={[s.logLevel, l.level === 'info' && s.logInfo, l.level === 'ok' && s.logOk, l.level === 'warn' && s.logWarn, l.level === 'error' && s.logError]}>
                    <Text style={[s.logLevelText, l.level === 'info' && { color: colors.violet2 }, l.level === 'ok' && { color: colors.emerald }, l.level === 'warn' && { color: colors.amber }, l.level === 'error' && { color: colors.rose }]}>{l.level}</Text>
                  </View>
                  <Text style={s.logMsg} numberOfLines={2}>{l.msg}</Text>
                </View>
              ))}
            </ScrollView>
          </View>

          {/* Versions */}
          <View style={s.card}>
            <Text style={s.h3}>Versions</Text>
            {(d.versions || []).slice().reverse().map((v: any) => (
              <View key={v.version} style={[s.rowBetween, { marginBottom: 8 }]}>
                <Text style={s.mono}>{v.version}</Text>
                <Text style={s.dim}>{new Date(v.deployed_at).toLocaleDateString()}</Text>
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
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  h1: { fontSize: 28, fontWeight: '600', color: colors.text, marginTop: 8 },
  mono: { fontSize: 12, color: colors.textDim, fontFamily: 'monospace' },
  dim: { fontSize: 11, color: colors.textDim },
  card: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, padding: 18, marginBottom: 16 },
  h3: { fontSize: 18, fontWeight: '600', color: colors.text, marginBottom: 12 },
  btnSec: { flexDirection: 'row', alignItems: 'center', gap: 6, borderWidth: 1, borderColor: colors.borderStrong, borderRadius: radius.md, paddingVertical: 10, paddingHorizontal: 14 },
  btnSecText: { color: colors.text, fontWeight: '500', fontSize: 13 },
  logStream: { backgroundColor: 'rgba(4,5,12,0.7)', borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: 12, maxHeight: 300 },
  logRow: { flexDirection: 'row', alignItems: 'flex-start', gap: 8, marginBottom: 6 },
  logTs: { fontSize: 10.5, color: colors.textDim, fontFamily: 'monospace' },
  logLevel: { paddingHorizontal: 6, borderRadius: 4 },
  logLevelText: { fontSize: 10.5 },
  logInfo: { backgroundColor: 'rgba(139,92,246,0.18)' },
  logOk: { backgroundColor: 'rgba(74,222,128,0.12)' },
  logWarn: { backgroundColor: 'rgba(251,191,36,0.12)' },
  logError: { backgroundColor: 'rgba(251,113,133,0.16)' },
  logMsg: { flex: 1, fontSize: 12, color: colors.text, fontFamily: 'monospace' },
});
