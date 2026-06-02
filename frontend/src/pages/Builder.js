import React, { useEffect, useState } from "react";
import { Outlet, NavLink, useLocation, Link } from "react-router-dom";
import { LayoutDashboard, Store, DollarSign, BarChart3, AlertTriangle } from "lucide-react";
import api from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { PageHeader, Empty, Stat } from "../components/UI";

function Tab({ to, icon: Icon, label }) {
  return (
    <NavLink to={to} end className={({ isActive }) =>
      `chip ${isActive ? "chip-emerald" : "chip-muted"}`}
      style={{ padding: "8px 14px", borderRadius: 10, fontWeight: 500 }}
      data-testid={`builder-tab-${label.toLowerCase()}`}
    >
      <Icon size={13} style={{ verticalAlign: -2 }} /> {label}
    </NavLink>
  );
}

export function BuilderShell() {
  const { user } = useAuth();
  const loc = useLocation();
  const isBuilder = user?.role === "builder" || user?.role === "admin";
  if (!isBuilder) {
    return (
      <div className="page" data-testid="builder-not-authorized">
        <Empty title="Builder access only" hint="Switch to a builder account or contact admin." />
      </div>
    );
  }
  return (
    <div className="page" data-testid="builder-shell">
      <PageHeader
        title="Builder Hub"
        subtitle="Your earnings, sales, performance, and trust signals — in one place."
      />
      <div className="row gap-2 mb-6" data-testid="builder-tabs" style={{ flexWrap: "wrap" }}>
        <Tab to="/builder" icon={LayoutDashboard} label="Overview" />
        <Tab to="/builder/solutions" icon={Store} label="Solutions" />
        <Tab to="/builder/sales" icon={BarChart3} label="Sales" />
        <Tab to="/builder/earnings" icon={DollarSign} label="Earnings" />
        <Tab to="/builder/stats" icon={BarChart3} label="Stats" />
      </div>
      <Outlet key={loc.pathname} />
    </div>
  );
}

// ---------- Overview ----------
export function BuilderOverview() {
  const { user } = useAuth();
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    api.get("/me/overview").then(r => setData(r.data)).finally(() => setLoading(false));
  }, []);
  if (loading) return <div className="card" style={{ padding: 40, textAlign: "center" }}>Loading…</div>;
  if (!data) return <Empty title="No data" />;
  return (
    <div className="col gap-6" data-testid="builder-overview">
      <div className="grid grid-4">
        <Stat label="Revenue 7d" value={`$${data.revenue_7d.amount_usd.toLocaleString()}`} delta={`${data.revenue_7d.count} tx`} deltaDir="up" />
        <Stat label="Revenue 30d" value={`$${data.revenue_30d.amount_usd.toLocaleString()}`} delta={`${data.revenue_30d.count} tx`} deltaDir="up" />
        <Stat label="Solutions" value={data.solutions_count} />
        <Stat label="Trust score" value={data.trust_score ? data.trust_score.toFixed(1) : "—"} delta={data.review_count ? `${data.review_count} reviews` : null} />
      </div>

      <div className="card" data-testid="simulated-banner-payout" style={{ borderColor: "rgba(251,191,36,.35)" }}>
        <div className="row gap-3" style={{ alignItems: "flex-start" }}>
          <AlertTriangle size={16} style={{ color: "#fbbf24", marginTop: 2 }} />
          <div className="col">
            <span style={{ fontWeight: 500 }}>Payouts are SIMULATED in this environment</span>
            <span className="dim" style={{ fontSize: 12.5 }}>
              Stripe Connect payouts are stubbed for Phase 6 — Phase 10 will wire real bank transfers. Funds you see in “Earnings” are correctly accounted in the ledger.
            </span>
          </div>
        </div>
      </div>

      <div className="card" data-testid="builder-trust-card">
        <div className="row-between">
          <div className="h3">Trust components</div>
          <Link to={`/builders/${user?.id || ""}`} className="dim" style={{ fontSize: 12 }}>View public profile</Link>
        </div>
        {data.trust_score_components ? (
          <div className="grid grid-3 mt-4">
            {Object.entries(data.trust_score_components).map(([k, v]) => (
              <div key={k} className="card card-tight" data-testid={`trust-comp-${k}`}>
                <div className="dim" style={{ fontSize: 11.5, textTransform: "uppercase", letterSpacing: ".08em" }}>{k.replace(/_/g, " ")}</div>
                <div className="stat-value" style={{ fontSize: 22 }}>{typeof v === "number" ? v.toFixed(1) : v}</div>
              </div>
            ))}
          </div>
        ) : <div className="dim mt-2">Trust score not yet computed.</div>}
      </div>

      <div className="card" data-testid="builder-activity-card">
        <div className="h3">Recent activity</div>
        <div className="col gap-2 mt-4">
          {(data.activity || []).length === 0 ? (
            <div className="dim">No activity yet.</div>
          ) : data.activity.map((a, i) => (
            <div key={i} className="row-between card card-tight" data-testid={`activity-row-${i}`}>
              <div className="col" style={{ minWidth: 0 }}>
                <span style={{ fontSize: 13.5 }}>
                  {a.type === "review" ? `★ ${a.rating} review from ${a.buyer_name}` :
                    `${a.solution_title || "Transaction"} — ${a.status}`}
                </span>
                <span className="dim" style={{ fontSize: 11.5 }}>{a.snippet || (a.amount_usd ? `$${a.amount_usd.toLocaleString()}` : "")}</span>
              </div>
              <span className="dim mono" style={{ fontSize: 11 }}>{new Date(a.ts).toLocaleString()}</span>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------- Solutions ----------
export function BuilderSolutions() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);
  useEffect(() => {
    api.get("/me/solutions").then(r => setItems(r.data.items || [])).finally(() => setLoading(false));
  }, []);
  if (loading) return <div className="card" style={{ padding: 40, textAlign: "center" }}>Loading…</div>;
  if (items.length === 0) return <Empty title="No solutions yet" hint="Publish your first solution to start earning." />;
  return (
    <div className="grid grid-2" data-testid="builder-solutions-grid">
      {items.map(s => (
        <Link key={s.id} to={`/solutions/${s.id}`} className="card fade-in" data-testid={`builder-solution-${s.id}`}>
          <div className="row-between">
            <div className="h3">{s.title}</div>
            <span className="chip chip-muted">v{s.version || 1}</span>
          </div>
          <div className="dim" style={{ fontSize: 12.5 }}>{s.tagline}</div>
          <div className="row gap-2 mt-2">
            <span className="chip chip-emerald">${(s.price_usd || 0).toLocaleString()}</span>
            <span className="chip chip-muted">{s.category}</span>
            {s.is_fork ? <span className="chip" style={{ background: "rgba(196,181,253,.18)" }}>fork</span> : null}
          </div>
          <div className="row-between mt-4 dim" style={{ fontSize: 11.5 }}>
            <span>{s.clients_count || 0} clients</span>
            <span>{s.fork_children_count || 0} forks</span>
          </div>
        </Link>
      ))}
    </div>
  );
}

// ---------- Sales ----------
export function BuilderSales() {
  const [data, setData] = useState(null);
  const [days, setDays] = useState(30);
  useEffect(() => { api.get(`/me/sales?days=${days}`).then(r => setData(r.data)); }, [days]);
  if (!data) return <div className="card" style={{ padding: 40, textAlign: "center" }}>Loading…</div>;
  const max = Math.max(1, ...(data.sparkline || []).map(p => p.amount_usd));
  return (
    <div className="col gap-6" data-testid="builder-sales">
      <div className="card">
        <div className="row-between">
          <div className="h3">Sales over last {days} days</div>
          <select className="input" style={{ maxWidth: 140 }} value={days} onChange={e => setDays(parseInt(e.target.value))} data-testid="sales-days-select">
            <option value={7}>7 days</option><option value={30}>30 days</option><option value={90}>90 days</option>
          </select>
        </div>
        <div className="row gap-1 mt-4" style={{ alignItems: "flex-end", height: 120 }} data-testid="sales-sparkline">
          {(data.sparkline || []).map((p, i) => (
            <div key={i} title={`${p.date}: $${p.amount_usd.toLocaleString()}`} style={{
              flex: 1, background: "linear-gradient(180deg, rgba(196,181,253,.85), rgba(196,181,253,.25))",
              height: `${Math.max(2, (p.amount_usd / max) * 100)}%`, borderRadius: 4, minWidth: 4,
            }} />
          ))}
        </div>
      </div>
      <div className="card">
        <div className="h3">Recent sales</div>
        <div className="col gap-1 mt-4">
          {(data.items || []).slice(0, 30).map(t => (
            <Link to={`/transactions/${t.id}`} key={t.id} className="row-between card card-tight" data-testid={`sale-row-${t.id}`}>
              <div className="col" style={{ minWidth: 0 }}>
                <span style={{ fontSize: 13.5 }}>{t.solution_title}</span>
                <span className="dim" style={{ fontSize: 11.5 }}>{t.buyer_name}</span>
              </div>
              <div className="row gap-3">
                <span className="chip chip-muted">{t.status}</span>
                <span className="mono" style={{ fontWeight: 500 }}>${t.amount_usd?.toLocaleString()}</span>
              </div>
            </Link>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------- Earnings ----------
export function BuilderEarnings() {
  const [data, setData] = useState(null);
  useEffect(() => { api.get("/me/earnings").then(r => setData(r.data)); }, []);
  if (!data) return <div className="card" style={{ padding: 40, textAlign: "center" }}>Loading…</div>;
  return (
    <div className="col gap-6" data-testid="builder-earnings">
      <div className="grid grid-3">
        <Stat label="Ledger balance" value={`$${data.ledger_balance_usd.toLocaleString()}`} />
        <Stat label="YTD released" value={`$${data.ytd.amount_usd.toLocaleString()}`} delta={`${data.ytd.count} tx`} deltaDir="up" />
        <Stat label="Lifetime" value={`$${data.lifetime.amount_usd.toLocaleString()}`} delta={`${data.lifetime.count} tx`} deltaDir="up" />
      </div>
      <div className="card" data-testid="payout-status-card" style={{ borderColor: "rgba(251,191,36,.35)" }}>
        <div className="row gap-3" style={{ alignItems: "flex-start" }}>
          <AlertTriangle size={16} style={{ color: "#fbbf24", marginTop: 2 }} />
          <div className="col">
            <span style={{ fontWeight: 500 }}>Payouts: {data.payout_provider_status.toUpperCase()}</span>
            <span className="dim" style={{ fontSize: 12.5 }}>
              Stripe Connect bank-transfer payouts are stubbed for Phase 6. Ledger accounting is real — when Phase 10 wires Connect, withdrawals will draw from this balance.
            </span>
          </div>
        </div>
      </div>
      <div className="card">
        <div className="h3">Released-tx ledger</div>
        <div className="col gap-1 mt-4">
          {(data.ledger || []).map((row, i) => (
            <div key={i} className="row-between card card-tight" data-testid={`ledger-row-${i}`}>
              <div className="col"><span style={{ fontSize: 13.5 }}>{row.solution_title}</span><span className="dim" style={{ fontSize: 11.5 }}>{row.buyer_name}</span></div>
              <div className="row gap-3"><span className="dim mono" style={{ fontSize: 11 }}>{row.released_at ? new Date(row.released_at).toLocaleDateString() : "—"}</span><span className="mono" style={{ fontWeight: 500 }}>+${row.amount_usd.toLocaleString()}</span></div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

// ---------- Stats ----------
export function BuilderStats() {
  const [data, setData] = useState(null);
  useEffect(() => { api.get("/me/stats").then(r => setData(r.data)); }, []);
  if (!data) return <div className="card" style={{ padding: 40, textAlign: "center" }}>Loading…</div>;
  return (
    <div className="card" data-testid="builder-stats">
      <div className="h3">Per-solution performance</div>
      <div className="col gap-1 mt-4">
        <div className="row-between dim" style={{ fontSize: 11.5, padding: "6px 12px", textTransform: "uppercase", letterSpacing: ".08em" }}>
          <span style={{ flex: 2 }}>Solution</span><span style={{ flex: 1 }}>Reviews</span><span style={{ flex: 1 }}>Clients</span><span style={{ flex: 1 }}>GMV</span><span style={{ flex: 1 }}>Forks</span>
        </div>
        {(data.solutions || []).map(s => (
          <Link key={s.id} to={`/solutions/${s.id}`} className="row card card-tight" data-testid={`stats-row-${s.id}`}>
            <span style={{ flex: 2 }}>{s.title}</span>
            <span style={{ flex: 1 }}>{s.reviews_count}</span>
            <span style={{ flex: 1 }}>{s.clients_count}</span>
            <span style={{ flex: 1, fontFamily: "monospace" }}>${s.gmv_released_usd.toLocaleString()}</span>
            <span style={{ flex: 1 }}>{s.fork_children_count}</span>
          </Link>
        ))}
      </div>
    </div>
  );
}
