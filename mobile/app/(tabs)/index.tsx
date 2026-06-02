import React, { useEffect, useState } from 'react';
import { View, Text, TextInput, TouchableOpacity, ScrollView, StyleSheet, ActivityIndicator } from 'react-native';
import { SafeAreaView } from 'react-native-safe-area-context';
import { useRouter } from 'expo-router';
import { Ionicons } from '@expo/vector-icons';
import api, { WS_BASE } from '../../src/api';
import { useAuth } from '../../src/auth';
import { SolutionCard, RequirementRow, Stat, PageHeader } from '../../src/components/UI';
import { colors, spacing, radius, font } from '../../src/theme';

const AGENTS = ['IntakeAgent','RequirementParserAgent','EmbeddingAgent','SemanticSearchAgent','ContextCompressionAgent','RankingAgent'];

export default function DiscoverTab() {
  const { user } = useAuth();
  const router = useRouter();
  const [overview, setOverview] = useState<any>(null);
  const [trending, setTrending] = useState<any[]>([]);
  const [reqs, setReqs] = useState<any[]>([]);
  const [matchText, setMatchText] = useState('We are a textile manufacturer in Surat needing an inventory + ERP system that handles fabric SKUs, batch dyeing, and supplier POs');
  const [steps, setSteps] = useState<any[]>([]);
  const [result, setResult] = useState<any>(null);
  const [running, setRunning] = useState(false);
  const [runId, setRunId] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([
      api.get('/marketplace/overview'),
      api.get('/marketplace/trending?limit=6'),
      api.get('/marketplace/requirements/recent?limit=4'),
    ]).then(([o, t, r]) => {
      setOverview(o.data); setTrending(t.data.items); setReqs(r.data.items);
    }).catch(() => {});
  }, []);

  const startMatch = async () => {
    if (!matchText.trim() || matchText.trim().length < 5) return;
    setRunning(true); setSteps([]); setResult(null);
    try {
      const r = await api.post('/match', { requirement_text: matchText });
      const rid = r.data.run_id; setRunId(rid);
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

  const seenAgents = new Map();
  steps.forEach(s => seenAgents.set(s.agent, s));

  return (
    <SafeAreaView style={s.safe} edges={['top']}>
      <ScrollView style={s.scroll} contentContainerStyle={s.content}>
        <PageHeader
          title={`Welcome, ${user?.name?.split(' ')[0] || 'there'}`}
          subtitle="Discover production-ready software solutions."
          right={
            <TouchableOpacity testID="dashboard-browse-btn" style={s.browseBtn} onPress={() => router.push('/(tabs)/marketplace')}>
              <Text style={s.browseBtnText}>Browse all</Text>
              <Ionicons name="arrow-forward" size={14} color={colors.text} />
            </TouchableOpacity>
          }
        />

        {/* AI Match hero */}
        <View testID="ai-match-hero" style={s.matchStage}>
          <View style={s.matchHeader}>
            <Ionicons name="sparkles" size={18} color={colors.violet2} />
            <Text style={s.matchTitle}>AI Match</Text>
            <View style={s.chip}><Text style={s.chipTxt}>6 agents · ~10-15s</Text></View>
          </View>
          <TextInput
            testID="ai-match-input"
            style={s.textarea}
            value={matchText}
            onChangeText={setMatchText}
            placeholder="Describe the software you need…"
            placeholderTextColor={colors.textDim}
            multiline
          />
          <View style={s.matchFooter}>
            <Text style={s.charCount}>{matchText.length}/8000</Text>
            <TouchableOpacity
              testID="ai-match-run-btn"
              style={[s.runBtn, (running || matchText.trim().length < 5) && { opacity: 0.5 }]}
              onPress={startMatch}
              disabled={running || matchText.trim().length < 5}
            >
              {running ? <ActivityIndicator size="small" color={colors.white} /> : (
                <>
                  <Text style={s.runBtnText}>Run match</Text>
                  <Ionicons name="arrow-forward" size={14} color={colors.white} />
                </>
              )}
            </TouchableOpacity>
          </View>

          {(steps.length > 0 || running) && (
            <View style={s.stepsGrid}>
              {AGENTS.map(agent => {
                const last = seenAgents.get(agent);
                const status = last?.status || 'pending';
                return (
                  <View key={agent} testID={`match-step-${agent}`} style={[s.stepPill, status === 'running' && s.stepRunning, status === 'completed' && s.stepCompleted]}>
                    <View style={[s.stepDot, status === 'running' && { backgroundColor: colors.violet2 }, status === 'completed' && { backgroundColor: colors.emerald }]} />
                    <View style={{ flex: 1 }}>
                      <Text style={s.stepName}>{agent.replace('Agent', '')}</Text>
                      <Text style={s.stepMeta}>
                        {last?.execution_ms != null ? `${last.execution_ms}ms` : status}
                        {last?.provider_used ? ` · ${last.provider_used.split(':')[0]}` : ''}
                      </Text>
                    </View>
                  </View>
                );
              })}
            </View>
          )}

          {result?.result?.length > 0 && (
            <View style={{ marginTop: 24 }}>
              <View style={[s.rowBetween, { marginBottom: 12 }]}>
                <Text style={s.sectionTitle}>Top matches</Text>
                <TouchableOpacity testID="view-full-match-btn" onPress={() => router.push('/ai-match' as any)}>
                  <Text style={s.linkDim}>View full report →</Text>
                </TouchableOpacity>
              </View>
              {result.result.slice(0, 3).map((m: any, i: number) => {
                const sol = trending.find(t => t.id === m.solutionId);
                return (
                  <TouchableOpacity key={m.solutionId} testID={`match-result-${i}`} style={s.resultCard} onPress={() => router.push(`/solutions/${m.solutionId}` as any)}>
                    <View style={s.row}>
                      <View style={s.rankBadge}><Text style={s.rankText}>{i + 1}</Text></View>
                      <View style={{ flex: 1 }}>
                        <Text style={s.resultName} numberOfLines={1}>{sol?.title || m.solutionId.slice(0, 12)}</Text>
                        <Text style={s.dim}>{sol?.builder_name}</Text>
                      </View>
                      <View style={s.chip}><Text style={s.chipTxt}>{m.score}</Text></View>
                    </View>
                    <View style={s.scoreBar}><View style={[s.scoreBarFill, { width: `${m.score}%` }]} /></View>
                    <Text style={s.resultExplanation} numberOfLines={2}>{m.explanation?.slice(0, 140)}…</Text>
                  </TouchableOpacity>
                );
              })}
            </View>
          )}
        </View>

        {/* Stats */}
        {overview && (
          <View testID="dashboard-stats" style={s.statsGrid}>
            <Stat label="Solutions" value={overview.solutions} delta={`+${overview.activity_24h?.new_solutions || 0} today`} />
            <Stat label="Builders" value={overview.builders} />
            <Stat label="Active escrows" value={overview.active_transactions} />
            <Stat label="GMV" value={`$${overview.gmv_released_usd?.toLocaleString?.() || 0}`} delta="live ledger" />
          </View>
        )}

        {/* Trending solutions */}
        <View style={{ marginTop: 32 }}>
          <View style={[s.rowBetween, { marginBottom: 16 }]}>
            <View style={s.row}>
              <Ionicons name="trending-up" size={18} color={colors.violet2} />
              <Text style={s.sectionTitle}>Trending solutions</Text>
            </View>
          </View>
          <View testID="trending-grid">
            {trending.map(sol => <SolutionCard key={sol.id} s={sol} />)}
          </View>
        </View>

        {/* Recent requirements */}
        <View style={{ marginTop: 32, marginBottom: 32 }}>
          <View style={[s.rowBetween, { marginBottom: 16 }]}>
            <View style={s.row}>
              <Ionicons name="pulse" size={18} color={colors.cyan} />
              <Text style={s.sectionTitle}>Recent requirements</Text>
            </View>
            <TouchableOpacity onPress={() => router.push('/requirements/new' as any)}>
              <Text style={s.linkDim}>Post one →</Text>
            </TouchableOpacity>
          </View>
          <View testID="recent-requirements">
            {reqs.map(r => <RequirementRow key={r.id} r={r} />)}
          </View>
        </View>
      </ScrollView>
    </SafeAreaView>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg0 },
  scroll: { flex: 1 },
  content: { padding: 20 },
  browseBtn: { flexDirection: 'row', alignItems: 'center', gap: 6, borderWidth: 1, borderColor: colors.borderStrong, borderRadius: radius.md, paddingVertical: 8, paddingHorizontal: 14 },
  browseBtnText: { color: colors.text, fontSize: 13, fontWeight: '500' },
  matchStage: { backgroundColor: 'rgba(139,92,246,0.08)', borderWidth: 1, borderColor: 'rgba(139,92,246,0.34)', borderRadius: radius.xl, padding: 20, marginBottom: 24 },
  matchHeader: { flexDirection: 'row', alignItems: 'center', gap: 10, marginBottom: 16 },
  matchTitle: { fontSize: 22, fontWeight: '600', color: colors.text },
  chip: { backgroundColor: 'rgba(139,92,246,0.12)', borderWidth: 1, borderColor: 'rgba(139,92,246,0.28)', borderRadius: radius.full, paddingHorizontal: 10, paddingVertical: 3 },
  chipTxt: { fontSize: 11.5, fontWeight: '500', color: colors.violet2 },
  textarea: { backgroundColor: 'rgba(4,5,12,0.55)', borderWidth: 1, borderColor: colors.border, borderRadius: radius.md, padding: 14, color: colors.text, fontSize: 14, minHeight: 90, textAlignVertical: 'top' },
  matchFooter: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center', marginTop: 16 },
  charCount: { fontSize: 12, color: colors.textDim },
  runBtn: { backgroundColor: colors.violet, borderRadius: radius.md, paddingVertical: 10, paddingHorizontal: 16, flexDirection: 'row', alignItems: 'center', gap: 6 },
  runBtnText: { color: colors.white, fontWeight: '500', fontSize: 13.5 },
  stepsGrid: { marginTop: 20, gap: 8 },
  stepPill: { flexDirection: 'row', alignItems: 'center', gap: 10, padding: 10, backgroundColor: 'rgba(8,9,18,0.55)', borderWidth: 1, borderColor: colors.border, borderRadius: radius.md },
  stepRunning: { borderColor: 'rgba(139,92,246,0.55)', backgroundColor: 'rgba(139,92,246,0.1)' },
  stepCompleted: { borderColor: 'rgba(74,222,128,0.35)' },
  stepDot: { width: 8, height: 8, borderRadius: 4, backgroundColor: colors.textDim },
  stepName: { fontSize: 12, fontWeight: '500', color: colors.text },
  stepMeta: { fontSize: 10.5, color: colors.textDim, fontFamily: 'monospace' },
  rowBetween: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  row: { flexDirection: 'row', alignItems: 'center', gap: 8 },
  sectionTitle: { fontSize: 18, fontWeight: '600', color: colors.text },
  linkDim: { fontSize: 12, color: colors.textDim },
  resultCard: { backgroundColor: colors.surface, borderWidth: 1, borderColor: colors.border, borderRadius: radius.lg, padding: 16, marginBottom: 10 },
  rankBadge: { width: 28, height: 28, borderRadius: 8, backgroundColor: colors.violet, alignItems: 'center', justifyContent: 'center' },
  rankText: { color: colors.white, fontSize: 12, fontWeight: '600' },
  resultName: { fontWeight: '500', color: colors.text },
  dim: { fontSize: 11, color: colors.textDim },
  scoreBar: { height: 4, backgroundColor: 'rgba(255,255,255,0.06)', borderRadius: radius.full, overflow: 'hidden', marginTop: 8 },
  scoreBarFill: { height: '100%', backgroundColor: colors.violet },
  resultExplanation: { fontSize: 12.5, color: colors.textDim, marginTop: 8 },
  statsGrid: { flexDirection: 'row', flexWrap: 'wrap', gap: 10 },
});
