import React, { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Sparkles, TrendingUp, Users, ArrowRight, Loader2, Activity } from "lucide-react";
import api, { WS_BASE, getAccessToken } from "../lib/api";
import { Stat, SolutionCard, RequirementRow, PageHeader } from "../components/UI";
import { useAuth } from "../context/AuthContext";

export default function Discover() {
  const [overview, setOverview] = useState(null);
  const [trending, setTrending] = useState([]);
  const [reqs, setReqs] = useState([]);
  const [matchText, setMatchText] = useState("We are a textile manufacturer in Surat needing an inventory + ERP system that handles fabric SKUs, batch dyeing, and supplier POs");
  const [steps, setSteps] = useState([]);
  const [result, setResult] = useState(null);
  const [running, setRunning] = useState(false);
  const [runId, setRunId] = useState(null);
  const { user } = useAuth();
  const nav = useNavigate();

  useEffect(() => {
    Promise.all([
      api.get("/marketplace/overview"),
      api.get("/marketplace/trending?limit=6"),
      api.get("/marketplace/requirements/recent?limit=4"),
    ]).then(([o, t, r]) => {
      setOverview(o.data); setTrending(t.data.items); setReqs(r.data.items);
    }).catch(() => {});
  }, []);

  const startMatch = async () => {
    if (!matchText.trim() || matchText.trim().length < 5) return;
    setRunning(true); setSteps([]); setResult(null);
    try {
      const r = await api.post("/match", { requirement_text: matchText });
      const rid = r.data.run_id; setRunId(rid);
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
    } catch (err) { setRunning(false); }
  };

  const seenAgents = new Map();
  steps.forEach(s => seenAgents.set(s.agent, s));

  return (
    <div className="page" data-testid="discover-page">
      <PageHeader
        title={`Welcome back, ${user?.name?.split(" ")[0] || "there"}`}
        subtitle="Discover production-ready software solutions, matched semantically to your needs."
        right={<Link to="/marketplace" className="btn btn-secondary" data-testid="dashboard-browse-btn"><span>Browse all</span><ArrowRight size={14} /></Link>}
      />

      {/* AI Match hero stage */}
      <div className="match-stage" data-testid="ai-match-hero">
        <div className="row gap-3 mb-4">
          <Sparkles size={18} style={{ color: "var(--violet-2)" }} />
          <span className="h2" style={{ position: "relative", zIndex: 1 }}>AI Match</span>
          <span className="chip" style={{ position: "relative", zIndex: 1 }}>6 agents · streaming · ~10–15s</span>
        </div>
        <textarea
          className="textarea"
          value={matchText}
          onChange={(e) => setMatchText(e.target.value)}
          placeholder="Describe the software you need…"
          data-testid="ai-match-input"
          style={{ position: "relative", zIndex: 1, background: "rgba(4,5,12,0.55)", minHeight: 90 }}
        />
        <div className="row-between mt-4" style={{ position: "relative", zIndex: 1 }}>
          <span className="dim" style={{ fontSize: 12 }}>{matchText.length}/8000</span>
          <button className="btn" disabled={running || matchText.trim().length < 5} onClick={startMatch} data-testid="ai-match-run-btn">
            {running ? <><Loader2 size={14} className="spin" /> Matching…</> : <>Run match <ArrowRight size={14} /></>}
          </button>
        </div>

        {/* Step pills */}
        {(steps.length > 0 || running) && (
          <div className="grid grid-3 mt-6" style={{ position: "relative", zIndex: 1, gap: 10 }}>
            {["IntakeAgent","RequirementParserAgent","EmbeddingAgent","SemanticSearchAgent","ContextCompressionAgent","RankingAgent"].map((agent) => {
              const last = seenAgents.get(agent);
              const status = last?.status || "pending";
              return (
                <div key={agent} className={`match-step ${status}`} data-testid={`match-step-${agent}`}>
                  <span className="match-step-dot" />
                  <span className="col" style={{ minWidth: 0 }}>
                    <span style={{ fontSize: 12, fontWeight: 500 }}>{agent.replace("Agent","")}</span>
                    <span className="dim mono" style={{ fontSize: 10.5 }}>
                      {last?.execution_ms != null ? `${last.execution_ms}ms` : status}
                      {last?.provider_used ? ` · ${last.provider_used.split(":")[0]}` : ""}
                      {last?.token_usage?.total_tokens ? ` · ${last.token_usage.total_tokens}tok` : ""}
                    </span>
                  </span>
                </div>
              );
            })}
          </div>
        )}

        {result?.result?.length > 0 && (
          <div className="mt-6" style={{ position: "relative", zIndex: 1 }}>
            <div className="row-between mb-4">
              <span className="h3">Top matches</span>
              <Link to={`/ai-match?run=${runId}`} className="btn-ghost dim" style={{ fontSize: 12 }} data-testid="view-full-match-btn">View full report →</Link>
            </div>
            <div className="grid grid-3">
              {result.result.slice(0, 3).map((m, i) => {
                const sol = trending.find(t => t.id === m.solutionId);
                return (
                  <Link key={m.solutionId} to={`/solutions/${m.solutionId}?run=${runId}`} className="card fade-in" data-testid={`match-result-${i}`}>
                    <div className="row gap-3">
                      <div className="result-rank">{i + 1}</div>
                      <div className="col flex-1" style={{ minWidth: 0 }}>
                        <span style={{ fontWeight: 500 }}>{sol?.title || m.solutionId.slice(0, 12)}</span>
                        <span className="dim" style={{ fontSize: 11 }}>{sol?.builder_name}</span>
                      </div>
                      <span className="chip">{m.score}</span>
                    </div>
                    <div className="score-bar mt-2"><div className="score-bar-fill" style={{ width: `${m.score}%` }} /></div>
                    <p className="dim body mt-2" style={{ fontSize: 12.5 }}>{m.explanation?.slice(0, 140)}…</p>
                  </Link>
                );
              })}
            </div>
          </div>
        )}
      </div>

      {/* Stats row */}
      {overview && (
        <div className="grid grid-4 mt-8" data-testid="dashboard-stats">
          <Stat label="Solutions" value={overview.solutions} delta={`+${overview.activity_24h?.new_solutions || 0} today`} />
          <Stat label="Builders" value={overview.builders} />
          <Stat label="Active escrows" value={overview.active_transactions} />
          <Stat label="GMV (released)" value={`$${overview.gmv_released_usd.toLocaleString()}`} delta="live ledger" />
        </div>
      )}

      {/* Trending + Recent requirements */}
      <div className="grid mt-8" style={{ gridTemplateColumns: "2fr 1fr", gap: 24 }}>
        <div>
          <div className="row-between mb-4">
            <span className="h2"><TrendingUp size={18} style={{ verticalAlign: -3, marginRight: 8, color: "var(--violet-2)" }} />Trending solutions</span>
            <Link to="/marketplace" className="dim" style={{ fontSize: 12 }}>See marketplace →</Link>
          </div>
          <div className="grid grid-2" data-testid="trending-grid">
            {trending.map(s => <SolutionCard key={s.id} s={s} />)}
          </div>
        </div>

        <div>
          <div className="row-between mb-4">
            <span className="h2"><Activity size={18} style={{ verticalAlign: -3, marginRight: 8, color: "var(--cyan)" }} />Recent requirements</span>
            <Link to="/requirements/new" className="dim" style={{ fontSize: 12 }}>Post one →</Link>
          </div>
          <div className="col gap-3" data-testid="recent-requirements">
            {reqs.map(r => <RequirementRow key={r.id} r={r} />)}
          </div>
        </div>
      </div>
    </div>
  );
}
