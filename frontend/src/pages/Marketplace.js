import React, { useEffect, useState } from "react";
import { useSearchParams } from "react-router-dom";
import api from "../lib/api";
import { SolutionCard, PageHeader, Empty } from "../components/UI";
import { Filter, Loader2 } from "lucide-react";

const CATEGORIES = ["All", "Inventory Management", "CRM", "HR System", "Project Management", "E-commerce", "Finance", "Analytics", "Marketing", "Operations"];
const SORTS = [["trust", "Most trusted"], ["recent", "Newest"], ["price_asc", "Price ↑"], ["price_desc", "Price ↓"], ["rating", "Top rated"]];

export default function Marketplace() {
  const [params, setParams] = useSearchParams();
  const [items, setItems] = useState([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const q = params.get("q") || "";
  const category = params.get("category") || "All";
  const sort = params.get("sort") || "trust";

  useEffect(() => {
    setLoading(true);
    const qs = new URLSearchParams();
    if (q) qs.set("q", q);
    if (category && category !== "All") qs.set("category", category);
    qs.set("sort", sort);
    qs.set("limit", "30");
    api.get(`/marketplace/search?${qs}`)
      .then(r => { setItems(r.data.items); setTotal(r.data.total); })
      .finally(() => setLoading(false));
  }, [q, category, sort]);

  const setParam = (k, v) => {
    const p = new URLSearchParams(params);
    if (v && v !== "All") p.set(k, v); else p.delete(k);
    setParams(p);
  };

  return (
    <div className="page" data-testid="marketplace-page">
      <PageHeader title="Marketplace" subtitle={`${total.toLocaleString()} production-ready solutions from builders worldwide`} />

      <div className="card card-tight mb-6" data-testid="marketplace-filters">
        <div className="row gap-3" style={{ flexWrap: "wrap" }}>
          <input className="input" style={{ flex: "1 1 240px", maxWidth: 360 }} placeholder="Search…" value={q} onChange={e => setParam("q", e.target.value)} data-testid="marketplace-search-input" />
          <select className="input" style={{ maxWidth: 200 }} value={category} onChange={e => setParam("category", e.target.value)} data-testid="marketplace-category-select">
            {CATEGORIES.map(c => <option key={c}>{c}</option>)}
          </select>
          <select className="input" style={{ maxWidth: 180 }} value={sort} onChange={e => setParam("sort", e.target.value)} data-testid="marketplace-sort-select">
            {SORTS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
          </select>
          <span className="dim mono" style={{ alignSelf: "center", fontSize: 11.5 }}><Filter size={12} style={{ verticalAlign: -2 }} /> {items.length} of {total}</span>
        </div>
      </div>

      {loading ? (
        <div className="card" style={{ textAlign: "center", padding: 56 }}><Loader2 size={20} /></div>
      ) : items.length === 0 ? (
        <Empty title="No matches" hint="Try a different category or search term." />
      ) : (
        <div className="grid grid-3" data-testid="marketplace-grid">
          {items.map(s => <SolutionCard key={s.id} s={s} />)}
        </div>
      )}
    </div>
  );
}
