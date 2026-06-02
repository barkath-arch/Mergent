import React, { useEffect, useState } from "react";
import { useParams, useSearchParams, Link, useNavigate } from "react-router-dom";
import { Star, ShoppingCart, MessageSquare, Rocket, ShieldCheck, Loader2 } from "lucide-react";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { toast } from "sonner";

export default function SolutionDetail() {
  const { id } = useParams();
  const [params] = useSearchParams();
  const run_id = params.get("run") || null;
  const [s, setS] = useState(null);
  const [loading, setLoading] = useState(true);
  const [buyingState, setBuyingState] = useState("idle");
  const { user } = useAuth();
  const nav = useNavigate();

  useEffect(() => {
    setLoading(true);
    api.get(`/solutions/${id}`).then(r => setS(r.data)).finally(() => setLoading(false));
  }, [id]);

  const startMessage = async () => {
    if (!s) return;
    try {
      const r = await api.post("/conversations", { recipient_id: s.builder_id, initial_message: `Hi ${s.builder_name}, I'm interested in ${s.title}.` });
      nav(`/messages?c=${r.data.id}`);
    } catch (e) { toast.error("Could not start conversation"); }
  };

  const checkout = async () => {
    setBuyingState("loading");
    try {
      const r = await api.post("/checkout/session", { solution_id: s.id, run_id });
      const data = r.data;
      if (data.simulated) {
        toast.success("Demo escrow funded — Stripe in test stub mode");
        nav(`/transactions/${data.transaction_id}`);
      } else {
        window.location.href = data.checkout_url;
      }
    } catch (e) {
      const err = e?.response?.data?.detail;
      if (err?.error === "match_integrity_violation") {
        toast.error(`Match integrity: top-1 is ${err.ranked_top.slice(0,12)}, not this one.`);
      } else {
        toast.error(err?.error || "Checkout failed");
      }
    } finally { setBuyingState("idle"); }
  };

  if (loading) return <div className="page"><div className="card" style={{ padding: 56, textAlign: "center" }}><Loader2 size={20} /></div></div>;
  if (!s) return <div className="page"><div className="card">Solution not found.</div></div>;

  return (
    <div className="page" data-testid={`solution-detail-${s.id}`}>
      <div className="row gap-3 mb-4">
        <span className="chip">{s.category}</span>
        <span className="chip chip-muted">{s.license_model}</span>
        <span className="chip chip-emerald">{s.deployment_maturity}</span>
        {run_id ? <span className="banner-sim">via run {run_id.slice(0,8)}</span> : null}
      </div>
      <div className="h1 mb-2" data-testid="solution-title">{s.title}</div>
      <p className="muted" style={{ fontSize: 16, maxWidth: 740 }}>{s.tagline}</p>

      <div className="grid mt-8" style={{ gridTemplateColumns: "2fr 1fr", gap: 24 }}>
        <div>
          <div className="card">
            <div className="h3 mb-4">About this solution</div>
            <p className="body" style={{ lineHeight: 1.75, whiteSpace: "pre-wrap" }}>{s.description}</p>
            {s.tech_stack?.length > 0 && (
              <div className="mt-6">
                <div className="dim mono mb-2" style={{ fontSize: 11, letterSpacing: ".08em", textTransform: "uppercase" }}>Tech stack</div>
                <div className="row gap-2" style={{ flexWrap: "wrap" }}>
                  {s.tech_stack.map(t => <span key={t} className="chip chip-muted">{t}</span>)}
                </div>
              </div>
            )}
          </div>

          <div className="card mt-6" data-testid="solution-reviews">
            <div className="row-between mb-4">
              <span className="h3">Reviews ({s.reviews?.length || 0})</span>
              <span className="chip">★ {s.builder?.rating?.toFixed?.(1) || "—"}</span>
            </div>
            {(s.reviews || []).length === 0 ? (
              <p className="dim" style={{ fontSize: 13 }}>No reviews yet.</p>
            ) : (
              <div className="col gap-4">
                {s.reviews.map(r => (
                  <div key={r.id} style={{ borderBottom: "1px solid var(--border)", paddingBottom: 14 }}>
                    <div className="row gap-3 mb-2">
                      <div className="avatar" style={{ width: 28, height: 28, fontSize: 12 }}>{(r.buyer_name||"?")[0]}</div>
                      <div className="col flex-1"><span style={{ fontWeight: 500, fontSize: 13 }}>{r.buyer_name}</span></div>
                      <div className="row gap-2" style={{ color: "var(--amber)" }}>
                        {Array.from({length: r.rating}, (_, i) => <Star key={i} size={12} fill="currentColor" stroke="none" />)}
                      </div>
                    </div>
                    <p className="body dim" style={{ fontSize: 13 }}>{r.comment}</p>
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>

        <div className="col gap-4">
          <div className="card" data-testid="purchase-card">
            <div className="dim mono mb-2" style={{ fontSize: 11, letterSpacing: ".08em", textTransform: "uppercase" }}>Price</div>
            <div className="h1" style={{ fontSize: 34 }}>${s.price_usd.toLocaleString()}</div>
            <div className="dim mt-1" style={{ fontSize: 12 }}>{s.license_model}</div>
            <div className="divider" />
            <div className="row gap-3 mb-4">
              <ShieldCheck size={16} style={{ color: "var(--emerald)" }} />
              <span className="dim" style={{ fontSize: 12 }}>Escrow protected · refundable until release</span>
            </div>
            <button className="btn" style={{ width: "100%", justifyContent: "center" }} onClick={checkout} disabled={buyingState === "loading"} data-testid="purchase-btn">
              {buyingState === "loading" ? <Loader2 size={14} /> : <><ShoppingCart size={14} /> Acquire with escrow</>}
            </button>
            <button className="btn btn-secondary mt-3" style={{ width: "100%", justifyContent: "center" }} onClick={startMessage} data-testid="message-builder-btn">
              <MessageSquare size={14} /> Message builder
            </button>
            <div className="banner-sim mt-4" data-testid="simulated-banner"># SIMULATED escrow · real-state, sim-infra</div>
          </div>

          {s.builder && (
            <Link to={`/builders/${s.builder.id}`} className="card" data-testid="builder-card">
              <div className="row gap-3">
                <div className="avatar">{(s.builder.name||"?")[0]}</div>
                <div className="col flex-1">
                  <span style={{ fontWeight: 500 }}>{s.builder.name}</span>
                  <span className="dim" style={{ fontSize: 11 }}>{s.builder.headline}</span>
                </div>
                {s.builder.verified ? <span className="chip">verified</span> : null}
              </div>
              <div className="row gap-3 mt-4">
                <span className="dim mono" style={{ fontSize: 11.5 }}>★ {s.builder.rating?.toFixed?.(1) || "—"}</span>
                <span className="dim mono" style={{ fontSize: 11.5 }}>{s.builder.review_count} reviews</span>
              </div>
            </Link>
          )}

          <div className="card card-tight">
            <div className="row gap-3"><Rocket size={14} style={{ color: "var(--violet-2)" }} /><span style={{ fontSize: 12, fontWeight: 500 }}>{s.clients_count || 0} active deployments</span></div>
            <div className="dim mt-1" style={{ fontSize: 11.5 }}>Uptime {s.uptime_pct?.toFixed?.(2) || "—"}% · trust {s.trust_score?.toFixed?.(0) || "—"}</div>
          </div>
        </div>
      </div>
    </div>
  );
}
