import React, { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Sparkles, ArrowRight, Loader2 } from "lucide-react";
import api, { WS_BASE } from "../lib/api";
import { PageHeader, SolutionCard } from "../components/UI";

const AGENTS = ["IntakeAgent","RequirementParserAgent","EmbeddingAgent","SemanticSearchAgent","ContextCompressionAgent","RankingAgent"];

export default function AIMatch() {
  const [params, setParams] = useSearchParams();
  const initialRun = params.get("run");
  const [text, setText] = useState("");
  const [steps, setSteps] = useState([]);
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [solutionsById, setSolutionsById] = useState({});

  useEffect(() => {
    if (initialRun) {
      api.get(`/match/${initialRun}/trace`).then(r => {
        const trace = r.data;
        const stepEvents = (trace.steps || []).map(s => ({ ...s, ts: s.ended_at || s.started_at }));
        setSteps(stepEvents);
        if (trace.status === "completed") api.get(`/match/${initialRun}`).then(rr => setResult(rr.data));
      }).catch(() => {});
    }
  }, [initialRun]);

  useEffect(() => {
    if (result?.result?.length) {
      const ids = result.result.map(r => r.solutionId);
      Promise.all(ids.map(id => api.get(`/solutions/${id}`).catch(() => null))).then(rs => {
        const map = {};
        rs.forEach(r => { if (r?.data) map[r.data.id] = r.data; });
        setSolutionsById(map);
      });
    }
  }, [result]);

  const run = async () => {
    if (text.trim().length < 5) return;
    setRunning(true); setSteps([]); setResult(null);
    try {
      const r = await api.post("/match", { requirement_text: text });
      const rid = r.data.run_id;
      setParams(p => { p.set("run", rid); return p; });
      const ws = new WebSocket(`${WS_BASE}/match/${rid}`);
      ws.onmessage = (e) => {
        try {
          const m = JSON.parse(e.data);
          if (m.type === "agent_step") setSteps(prev => [...prev, m]);
          if (m.type === "run_completed") {
            api.get(`/match/${rid}`).then(rr => setResult(rr.data)).finally(() => setRunning(false));
            ws.close();
          }
          if (m.type === "run_failed") { setRunning(false); ws.close(); }
        } catch {}
      };
      ws.onerror = () => setRunning(false);
    } catch { setRunning(false); }
  };

  const byAgent = new Map();
  steps.forEach(s => byAgent.set(s.agent, s));

  return (
    <div className="page" data-testid="ai-match-page">
      <PageHeader title="AI Match" subtitle="6-agent orchestration · semantic search · real-time stream" />
      <div className="match-stage">
        <textarea className="textarea" placeholder="Describe what you need…" value={text} onChange={e => setText(e.target.value)} style={{ minHeight: 110 }} data-testid="ai-match-textarea" />
        <div className="row-between mt-4">
          <span className="dim mono">{text.length}/8000</span>
          <button className="btn" disabled={running || text.trim().length < 5} onClick={run} data-testid="ai-match-submit">
            {running ? <><Loader2 size={14} /> Matching…</> : <>Run match <ArrowRight size={14} /></>}
          </button>
        </div>
        {(steps.length > 0 || running) && (
          <div className="grid grid-3 mt-6" style={{ gap: 10 }}>
            {AGENTS.map(a => {
              const ev = byAgent.get(a);
              const status = ev?.status || "pending";
              return (
                <div key={a} className={`match-step ${status}`} data-testid={`page-match-step-${a}`}>
                  <span className="match-step-dot" />
                  <div className="col" style={{ minWidth: 0 }}>
                    <span style={{ fontSize: 12, fontWeight: 500 }}>{a.replace("Agent","")}</span>
                    <span className="dim mono" style={{ fontSize: 10.5 }}>
                      {ev?.execution_ms != null ? `${ev.execution_ms}ms` : status}
                      {ev?.provider_used ? ` · ${ev.provider_used.split(":")[0]}` : ""}
                    </span>
                  </div>
                </div>
              );
            })}
          </div>
        )}
      </div>

      {result?.result?.length > 0 && (
        <>
          <div className="row-between mb-4 mt-8">
            <span className="h2">Ranked matches</span>
            <span className="dim mono" style={{ fontSize: 11.5 }}>{result.total_execution_ms}ms · {result.total_tokens} tokens · {result.providers_used?.join(", ")}</span>
          </div>
          <div className="grid grid-3" data-testid="ai-match-results">
            {result.result.map((m, i) => {
              const s = solutionsById[m.solutionId];
              return (
                <div key={m.solutionId} className="card fade-in" data-testid={`ai-match-result-${i}`}>
                  <div className="row gap-3">
                    <div className="result-rank">{i + 1}</div>
                    <div className="col flex-1" style={{ minWidth: 0 }}>
                      <span style={{ fontWeight: 500 }}>{s?.title || m.solutionId.slice(0, 12)}</span>
                      <span className="dim" style={{ fontSize: 11 }}>{s?.builder_name}</span>
                    </div>
                    <span className="chip">{m.score}</span>
                  </div>
                  <div className="score-bar mt-2"><div className="score-bar-fill" style={{ width: `${m.score}%` }} /></div>
                  <p className="body dim mt-2" style={{ fontSize: 12.5 }}>{m.explanation}</p>
                  <a href={`/solutions/${m.solutionId}?run=${result.run_id}`} className="btn btn-secondary mt-3" style={{ width: "100%", justifyContent: "center" }} data-testid={`view-solution-${i}`}>
                    View & acquire →
                  </a>
                </div>
              );
            })}
          </div>
        </>
      )}
    </div>
  );
}
