import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Loader2, Receipt, Star, MessageSquare } from "lucide-react";
import api from "../lib/api";
import { PageHeader, Empty } from "../components/UI";
import { useAuth } from "../context/AuthContext";
import { toast } from "sonner";

const STATES = ["initiated", "funded", "in_progress", "delivered", "released", "reviewed"];
const STATE_COLOR = { initiated: "chip-muted", funded: "chip", in_progress: "chip-amber", delivered: "chip-amber", released: "chip-emerald", reviewed: "chip-emerald", disputed: "chip-rose", refunded: "chip-rose" };
const NEXT = { funded: ["in_progress"], in_progress: ["delivered"], delivered: ["released"] };

export function TransactionList() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => { api.get("/transactions/me").then(r => setItems(r.data.items)).finally(() => setLoading(false)); }, []);
  return (
    <div className="page" data-testid="transactions-page">
      <PageHeader title="Transactions" subtitle="Escrow-protected purchases. # SIMULATED state machine, real ledger." />
      <span className="banner-sim mb-6" style={{ display: "inline-block" }}>SIMULATED escrow — buyer + builder drive state transitions; Stripe payout deferred</span>
      <div className="mt-6">
      {loading ? <Loader2 size={20} /> : items.length === 0 ? <Empty title="No transactions yet" /> : (
        <div className="col gap-3">
          {items.map(t => (
            <Link to={`/transactions/${t.id}`} key={t.id} className="card row-between" data-testid={`tx-row-${t.id}`}>
              <div className="col flex-1">
                <span style={{ fontWeight: 500 }}>{t.solution_title}</span>
                <span className="dim" style={{ fontSize: 12 }}>{t.builder_name} · {new Date(t.created_at).toLocaleDateString()}</span>
              </div>
              <span className="chip chip-emerald">${t.amount_usd.toLocaleString()}</span>
              <span className={`chip ${STATE_COLOR[t.status] || ""}`}>{t.status.replace("_", " ")}</span>
            </Link>
          ))}
        </div>
      )}
      </div>
    </div>
  );
}

export function TransactionDetail() {
  const { id } = useParams();
  const { user } = useAuth();
  const [tx, setTx] = useState(null);
  const [reviewing, setReviewing] = useState(false);
  const [rating, setRating] = useState(5);
  const [comment, setComment] = useState("");

  const load = () => api.get(`/transactions/${id}`).then(r => setTx(r.data));
  useEffect(() => { load(); }, [id]);

  const advance = async (next) => {
    try { const r = await api.post(`/transactions/${id}/advance`, { next_state: next }); setTx(r.data); toast.success(`Now ${next.replace("_"," ")}`); }
    catch (e) { toast.error(e?.response?.data?.detail?.error || "Cannot advance"); }
  };
  const review = async () => {
    try { await api.post(`/transactions/${id}/review`, { rating, comment }); toast.success("Review posted"); setReviewing(false); load(); }
    catch (e) { toast.error(e?.response?.data?.detail?.error || "Could not post review"); }
  };

  if (!tx) return <div className="page"><Loader2 size={20} /></div>;
  const idx = STATES.indexOf(tx.status);
  const canReview = tx.status === "released" && tx.buyer_id === user?.id;
  return (
    <div className="page" data-testid="transaction-detail">
      <div className="row gap-3 mb-4">
        <Receipt size={16} />
        <span className="mono dim" style={{ fontSize: 12 }}>{id.slice(0,8)}</span>
        <span className={`chip ${STATE_COLOR[tx.status]}`}>{tx.status.replace("_"," ")}</span>
        {tx.simulated_checkout ? <span className="banner-sim">simulated stripe</span> : null}
        {tx.match_integrity === "verified_top1" ? <span className="chip chip-emerald">match #1 verified</span> : null}
      </div>
      <div className="h1 mb-2">{tx.solution_title}</div>
      <p className="muted">{tx.buyer_name} → {tx.builder_name} · ${tx.amount_usd.toLocaleString()}</p>

      <div className="card mt-8">
        <div className="h3 mb-4">Escrow progress</div>
        <div className="row gap-3" data-testid="state-pipeline">
          {STATES.map((st, i) => (
            <div key={st} className="col" style={{ flex: 1 }}>
              <div style={{ height: 4, background: i <= idx ? "linear-gradient(90deg, var(--violet), var(--cyan))" : "rgba(255,255,255,0.06)", borderRadius: 4 }} />
              <span className="dim mono" style={{ fontSize: 10.5, marginTop: 6, textTransform: "uppercase" }}>{st.replace("_"," ")}</span>
            </div>
          ))}
        </div>
        <div className="row gap-3 mt-6">
          {(NEXT[tx.status] || []).map(n => (
            <button key={n} className="btn" onClick={() => advance(n)} data-testid={`advance-${n}-btn`}>Advance → {n.replace("_"," ")}</button>
          ))}
          {canReview && !reviewing && <button className="btn btn-secondary" onClick={() => setReviewing(true)} data-testid="leave-review-btn"><Star size={14} /> Leave review</button>}
          <Link to={`/messages?builder=${tx.builder_id}`} className="btn btn-secondary"><MessageSquare size={14} /> Message</Link>
        </div>
        {reviewing && (
          <div className="card-tight card mt-6" style={{ background: "rgba(8,9,18,0.6)" }}>
            <div className="row gap-2 mb-2">
              {[1,2,3,4,5].map(n => <Star key={n} size={20} onClick={() => setRating(n)} style={{ cursor: "pointer", color: n <= rating ? "var(--amber)" : "var(--text-dim)" }} fill={n <= rating ? "currentColor" : "none"} />)}
            </div>
            <textarea className="textarea" placeholder="How was your experience?" value={comment} onChange={e => setComment(e.target.value)} data-testid="review-comment-input" />
            <button className="btn mt-3" onClick={review} data-testid="submit-review-btn">Post review</button>
          </div>
        )}
      </div>

      <div className="card mt-6">
        <div className="h3 mb-4">History</div>
        <div className="col gap-3">
          {(tx.state_history || []).map((h, i) => (
            <div key={i} className="row gap-3" style={{ fontSize: 13 }}>
              <span className="dim mono" style={{ fontSize: 11 }}>{new Date(h.at).toLocaleString()}</span>
              <span className={`chip ${STATE_COLOR[h.state] || ""}`}>{h.state}</span>
              <span className="dim">by {h.by}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
