import React, { useEffect, useRef, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Rocket, Play, Loader2, RotateCcw, Repeat } from "lucide-react";
import api, { WS_BASE, getAccessToken } from "../lib/api";
import { PageHeader, Empty } from "../components/UI";
import { toast } from "sonner";

export function DeploymentList() {
  const [items, setItems] = useState(null);
  const [creating, setCreating] = useState(false);
  const load = () => api.get("/deployments").then(r => setItems(r.data.items));
  useEffect(() => { load(); }, []);

  const start = async () => {
    setCreating(true);
    try {
      const sols = (await api.get("/marketplace/search?limit=1")).data.items;
      const r = await api.post("/deployments", { solution_id: sols[0].id });
      toast.success(`Deployment started: ${r.data.solution_title}`);
      load();
    } catch (e) { toast.error("Could not start"); } finally { setCreating(false); }
  };

  return (
    <div className="page" data-testid="deployments-page">
      <PageHeader
        title="Deployments"
        subtitle="7-step state machine · streaming logs. # SIMULATED real-state, sim-infra."
        right={<button className="btn" onClick={start} disabled={creating} data-testid="new-deployment-btn">{creating ? <Loader2 size={14} /> : <><Play size={14}/> Quick deploy</>}</button>}
      />
      <span className="banner-sim mb-6" style={{ display: "inline-block" }}>SIMULATED deployment infra — logs streamed, no real container provisioned</span>
      <div className="mt-6">
      {items === null ? <Loader2 size={20} /> : items.length === 0 ? <Empty title="No deployments yet" hint="Start one with the button above" /> :
        <div className="col gap-3">
          {items.map(d => (
            <Link to={`/deployments/${d.id}`} key={d.id} className="card row-between" data-testid={`deployment-row-${d.id}`}>
              <div className="row gap-3 flex-1">
                <Rocket size={16} style={{ color: d.status === "live" ? "var(--emerald)" : "var(--violet-2)" }} />
                <div className="col">
                  <span style={{ fontWeight: 500 }}>{d.solution_title}</span>
                  <span className="dim mono" style={{ fontSize: 11 }}>{d.current_version} · {d.environment}</span>
                </div>
              </div>
              <span className={`chip ${d.status === "live" ? "chip-emerald" : d.status === "failed" ? "chip-rose" : "chip-amber"}`}>{d.status}</span>
            </Link>
          ))}
        </div>
      }
      </div>
    </div>
  );
}

export function DeploymentDetail() {
  const { id } = useParams();
  const [d, setD] = useState(null);
  const [logs, setLogs] = useState([]);
  const logRef = useRef(null);

  useEffect(() => {
    api.get(`/deployments/${id}`).then(r => { setD(r.data); setLogs(r.data.logs || []); });
    const url = `${WS_BASE}/deployments/${id}?token=${getAccessToken()}`;
    let ws;
    try {
      ws = new WebSocket(url);
      ws.onmessage = (e) => {
        try {
          const m = JSON.parse(e.data);
          if (m.type === "log") setLogs(prev => [...prev, m]);
          if (m.type === "state") setD(prev => prev ? { ...prev, status: m.state } : prev);
          if (m.type === "completed") api.get(`/deployments/${id}`).then(r => setD(r.data));
        } catch {}
      };
    } catch {}
    return () => { try { ws?.close(); } catch {} };
  }, [id]);

  useEffect(() => { logRef.current?.scrollTo(0, 1e6); }, [logs]);

  const act = async (action) => {
    try { await api.post(`/deployments/${id}/action`, { action }); toast.success(`${action} triggered`); }
    catch (e) { toast.error(e?.response?.data?.detail?.error || "Failed"); }
  };

  if (!d) return <div className="page"><Loader2 size={20} /></div>;
  return (
    <div className="page" data-testid={`deployment-detail-${id}`}>
      <div className="row gap-3 mb-4">
        <Rocket size={20} style={{ color: d.status === "live" ? "var(--emerald)" : "var(--violet-2)" }} />
        <span className={`chip ${d.status === "live" ? "chip-emerald" : "chip-amber"}`}>{d.status}</span>
        <span className="mono dim" style={{ fontSize: 12 }}>{d.current_version}</span>
        <span className="banner-sim">simulated infra</span>
      </div>
      <div className="h1 mb-2">{d.solution_title}</div>
      <div className="row gap-3 mt-6">
        <button className="btn btn-secondary" onClick={() => act("redeploy")} data-testid="redeploy-btn"><Repeat size={14} /> Redeploy</button>
        <button className="btn btn-secondary" onClick={() => act("rollback")} disabled={(d.versions?.length || 0) < 2} data-testid="rollback-btn"><RotateCcw size={14}/> Rollback</button>
      </div>
      <div className="grid mt-8" style={{ gridTemplateColumns: "1fr 320px", gap: 24 }}>
        <div className="card">
          <div className="h3 mb-4">Log stream</div>
          <div className="log-stream" ref={logRef} data-testid="log-stream">
            {logs.map((l, i) => (
              <div key={i} className="log-row">
                <span className="log-ts">{new Date(l.ts).toLocaleTimeString()}</span>
                <span className={`log-level ${l.level}`}>{l.level}</span>
                <span>{l.msg}</span>
              </div>
            ))}
          </div>
        </div>
        <div className="card">
          <div className="h3 mb-4">Versions</div>
          <div className="col gap-3">
            {(d.versions || []).slice().reverse().map(v => (
              <div key={v.version} className="row-between">
                <span className="mono" style={{ fontSize: 12 }}>{v.version}</span>
                <span className="dim" style={{ fontSize: 11 }}>{new Date(v.deployed_at).toLocaleDateString()}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}
