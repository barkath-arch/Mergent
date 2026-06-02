import React, { useState, useEffect } from 'react';
import { View, Text, TextInput, TouchableOpacity, ScrollView, StyleSheet, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api, { WS_BASE } from '../../src/api';
import { PageHeader } from '../../src/components/UI';
import { colors, radius } from '../../src/theme';

const AGENTS = ['IntakeAgent','RequirementParserAgent','EmbeddingAgent','SemanticSearchAgent','ContextCompressionAgent','RankingAgent'];

export default function AIMatchTab() {
  const router = useRouter();
  const [text, setText] = useState('');
  const [steps, setSteps] = useState<any[]>([]);
  const [result, setResult] = useState<any>(null);
  const [running, setRunning] = useState(false);
  const [solutionsById, setSolutionsById] = useState<Record<string, any>>({});

  useEffect(() => {
    if (result?.result?.length) {
      const ids = result.result.map((r: any) => r.solutionId);
      Promise.all(ids.map((id: string) => api.get(`/solutions/${id}`).catch(() => null))).then(rs => {
        const map: Record<string, any> = {};
        rs.forEach((r: any) => { if (r?.data) map[r.data.id] = r.data; });
        setSolutionsById(map);
      });
    }
  }, [result]);

  const run = async () => {
    if (text.trim().length < 5) return;
    setRunning(true); setSteps([]); setResult(null);
    try {
      const r = await api.post('/match', { requirement_text: text });
      const rid = r.data.run_id;
      const ws = new WebSocket(`${WS_BASE}/match/${rid}`);
      ws.onmessage = (e: any) => {
        try {
          const m = JSON.parse(e.data);
          if (m.type === 'agent_step') setSteps(prev => [...prev, m]);
          if (m.type === 'run_completed') {
            api.get(`/match/${rid}`).then(rr => setResult(rr.data)).finally(() => setRunning(false));
            ws.close();
          }
          if (m.type === 'run_failed') { setRunning(false); ws.close(); }
        } catch {}
      };
      ws.onerror = () => setRunning(false);
    } catch { setRunning(false); }
  };

  const byAgent = new Map();
  steps.forEach(s => byAgent.set(s.agent, s));

  return (
    <SafeAreaView style={st.safe} edges={['top']}>
      <ScrollView style={st.scroll} contentContainerStyle={st.content}>
        <PageHeader title="AI Match" subtitle="6-agent orchestration · semantic search · real-time stream" />

        <View testID="ai-match-page" style={st.matchStage}>
          <TextInput
            testID="ai-match-textarea"
            style={st.textarea}
            placeholder="Describe what you need…"
            placeholderTextColor={colors.textDim}
            value={text}
            onChangeText={setText}
            multiline
          />
          <View style={st.footer}>
            <Text style={st.charCount}>{text.length}/8000</Text>
            <TouchableOpacity
              testID="ai-match-submit"
              style={[st.runBtn, (running || text.trim().length < 5) && { opacity: 0.5 }]}
              onPress={run}
              disabled={running || text.trim().length < 5}
            >
              {running ? <ActivityIndicator size="small" color={colors.white} /> : (
                <><Text style={st.runBtnText}>Run match</Text><Ionicons name="arrow-forward" size={14} color={colors.white} /></>
              )}
            </TouchableOpacity>
          </View>

          {(steps.length > 0 || running) && (
            <View style={st.stepsGrid}>
              {AGENTS.map(a => {
                const ev = byAgent.get(a);
                const status = ev?.status || 'pending';
                return (
                  <View key={a} testID={`page-match-step-${a}`} style={[st.stepPill, status === 'running' && st.stepRunning, status === 'completed' && st.stepDone]}>
                    <View style={[st.dot, status === 'running' && { backgroundColor: colors.violet2 }, status === 'completed' && { backgroundColor: colors.emerald }]} />
                    <View style={{ flex: 1 }}>
                      <Text style={st.stepName}>{a.replace('Agent', '')}</Text>
                      <Text style={st.stepMeta}>{ev?.execution_ms != null ? `${ev.execution_ms}ms` : status}{ev?.provider_used ? ` · ${ev.provider_used.split(':')[0]}` : ''}</Text>
                    </View>
                  </View>
                );
              })}
            </View>
          )}
        </View>

        {result?.result?.length > 0 && (
          <View>
            <View style={[st.rowBetween, { marginBottom: 12, marginTop: 24 }]}>
              <Text style={st.h2}>Ranked matches</Text>
              <Text style={st.mono}>{result.total_execution_ms}ms · {result.total_tokens} tokens</Text>
            </View>
            <View testID="ai-match-results">
              {result.result.map((m: any, i: number) => {
                const sol = solutionsById[m.solutionId];
                return (
                  <View key={m.solutionId} testID={`ai-match-result-${i}`} style={st.resultCard}>
                    <View style={st.row}>
                      <View style={st.rankBadge}><Text style={st.rankText}>{i + 1}</Text></View>
                      <View style={{ flex: 1 }}>
                        <Text style={st.resultTitle} numberOfLines={1}>{sol?.title || m.solutionId.slice(0, 12)}</Text>
                        <Text style={st.dim}>{sol?.builder_name}</Text>
                      </View>
                      <View style={st.chip}><Text style={st.chipTxt}>{m.score}</Text></View>
                    </View>
                    <View style={st.scoreBar}><View style={[st.scoreBarFill, { width: `${m.score}%` }]} /></View>
                    <Text style={st.explanation}>{m.explanation}</Text>
                    <TouchableOpacity testID={`view-solution-${i}`} style={st.viewBtn} onPress={() => router.push(`/solutions/${m.solutionId}` as any)}>
                      <Text style={st.viewBtnText}>View & acquire →</Text>
                    </TouchableOpacity>
                  </View>
                );
              })}
            </View>
          </View>
        )}
      </ScrollView>
    </SafeAreaView>
  );
}

const st = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg0 },
  scroll: { flex: 1 },
  content: { padding: 20, paddingBottom: 40 },
  matchStage: { backgroundColor: 'rgba(139,92,246,0.08)', borderWidth: 1, borderColor: 'rgba(139,92,246,0.34)', borderRadius: radius.xl, padding: 20 },
  textarea: { backgroundColor: 'rgba(4,5,12,0.55)', borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: 14, color: colors.text, fontSize: 14, minHeight: 110, textAlignVertical: 'top' },
  footer: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 16 },
  charCount: { fontSize: 12, color: colors.textDim, fontFamily: 'monospace' },
  runBtn: { backgroundColor: colors.violet, borderRadius: radius.md, paddingVertical: 10, paddingHorizontal: 16, flexDirection: 'row', alignItems: 'center', gap: 6 },
  runBtnText: { color: colors.white, fontWeight: '500', fontSize: 13.5 },
  stepsGrid: { marginTop: 20, gap: 8 },
  stepPill: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 10, backgroundColor: 'rgba(8,9,18,0.55)', borderWidth: 1, borderColor: colors.border, borderRadius: radius.md },
  stepRunning: { borderColor: 'rgba(139,92,246,0.55)', backgroundColor: 'rgba(139,92,246,0.1)' },
  stepDone: { borderColor: 'rgba(74,222,128,0.35)' },
  dot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.textDim },
  stepName: { fontSize: 12, fontWeight: '500', color: colors.text },
  stepMeta: { fontSize: 10.5, color: colors.textDim, fontFamily: 'monospace' },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 10 },
  h2: { fontSize: 22, fontWeight: '600', color: colors.text },
  mono: { fontSize: 11.5, color: colors.textDim, fontFamily: 'monospace' },
  resultCard: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, padding: 16, marginBottom: 12 },
  rankBadge: { width: 28, height: 28, borderRadius: 8, backgroundColor: colors.violet, alignItems: 'center', justifyContent: 'center' },
  rankText: { color: colors.white, fontSize: 12, fontWeight: '600' },
  resultTitle: { fontWeight: '500', color: colors.text },
  dim: { fontSize: 11, color: colors.textDim },
  chip: { backgroundColor: 'rgba(139,92,246,0.12)', borderWidth: 1, borderColor: 'rgba(139,92,246,0.28)', borderRadius: radius.full, paddingHorizontal: 10, paddingVertical: 3 },
  chipTxt: { fontSize: 11.5, fontWeight: '500', color: colors.violet2 },
  scoreBar: { height: 4, backgroundColor: 'rgba(255,255,255,0.06)', borderRadius: radius.full, overflow: 'hidden', marginTop: 8 },
  scoreBarFill: { height: '100%', backgroundColor: colors.violet },
  explanation: { fontSize: 12.5, color: colors.textDim, marginTop: 8, lineHeight: 18 },
  viewBtn: { borderWidth: 1, borderColor: colors.borderStrong, borderRadius: radius.md, paddingVertical: 10, alignItems: 'center', marginTop: 12 },
  viewBtnText: { color: colors.text, fontWeight: '500', fontSize: 13 },
});
