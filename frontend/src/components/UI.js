import React from "react";
import { Link } from "react-router-dom";

export function SolutionCard({ s, rank }) {
  return (
    <Link to={`/solutions/${s.id}`} className="card fade-in result-card" data-testid={`solution-card-${s.id}`}>
      <div className="row gap-3">
        {rank ? <div className="result-rank">{rank}</div> : null}
        <div className="col flex-1" style={{ minWidth: 0 }}>
          <div className="h3" style={{ overflow: "hidden", textOverflow: "ellipsis", whiteSpace: "nowrap" }} data-testid={`solution-title-${s.id}`}>{s.title}</div>
          <div className="dim" style={{ fontSize: 12 }}>{s.builder_name}</div>
        </div>
        <span className="chip chip-muted">{s.category}</span>
      </div>
      <p className="body" style={{ marginTop: 4, color: "var(--text-muted)" }}>{s.tagline}</p>
      <div className="row-between mt-2">
        <span className="row gap-2">
          <span className="chip chip-emerald" data-testid={`solution-price-${s.id}`}>${s.price_usd?.toLocaleString?.() ?? s.price_usd}</span>
          {s.builder_rating ? <span className="chip">★ {s.builder_rating?.toFixed?.(1) ?? s.builder_rating}</span> : null}
        </span>
        <span className="dim mono" style={{ fontSize: 11 }}>{s.clients_count || 0} clients</span>
      </div>
    </Link>
  );
}

export function RequirementRow({ r }) {
  return (
    <div className="card card-tight fade-in" data-testid={`requirement-row-${r.id}`}>
      <div className="row-between">
        <span style={{ fontWeight: 500, fontSize: 13.5 }}>{r.title}</span>
        {r.budget_usd ? <span className="chip chip-emerald">${r.budget_usd.toLocaleString()}</span> : <span className="chip chip-muted">No budget</span>}
      </div>
      <p className="body dim" style={{ marginTop: 4, lineHeight: 1.5 }}>{r.summary}</p>
      <div className="row-between mt-2">
        <span className="chip chip-muted">{r.category}</span>
        <span className="dim mono" style={{ fontSize: 11 }}>{r.match_count || 0} matches</span>
      </div>
    </div>
  );
}

export function Stat({ label, value, delta, deltaDir }) {
  return (
    <div className="card stat" data-testid={`stat-${label.toLowerCase().replace(/\s+/g, "-")}`}>
      <span className="stat-label">{label}</span>
      <span className="stat-value">{value}</span>
      {delta ? <span className={`stat-delta ${deltaDir || "up"}`}>{delta}</span> : null}
    </div>
  );
}

export function Empty({ title = "Nothing here yet", hint = null }) {
  return (
    <div className="card" style={{ textAlign: "center", padding: 56 }} data-testid="empty-state">
      <div style={{ fontSize: 16, fontWeight: 500 }}>{title}</div>
      {hint ? <div className="dim mt-2" style={{ fontSize: 13 }}>{hint}</div> : null}
    </div>
  );
}

export function PageHeader({ title, subtitle, right = null }) {
  return (
    <div className="row-between mb-6" data-testid="page-header">
      <div className="col">
        <span className="h1">{title}</span>
        {subtitle ? <span className="muted mt-2" style={{ fontSize: 14 }}>{subtitle}</span> : null}
      </div>
      {right}
    </div>
  );
}
