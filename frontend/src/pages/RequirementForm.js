import React, { useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import api from "../lib/api";
import { PageHeader } from "../components/UI";

const CATEGORIES = ["Inventory Management", "CRM", "HR System", "Project Management", "E-commerce", "Finance", "Analytics", "Marketing", "Operations", "Other"];

export default function RequirementForm() {
  const nav = useNavigate();
  const [f, setF] = useState({ title: "", description: "", category: "Inventory Management", budget_usd: "", timeline: "flexible", tags: "" });
  const [loading, setLoading] = useState(false);

  const submit = async (e) => {
    e.preventDefault(); setLoading(true);
    try {
      await api.post("/requirements", {
        title: f.title,
        description: f.description,
        category: f.category,
        budget_usd: f.budget_usd ? Number(f.budget_usd) : null,
        timeline: f.timeline,
        tags: f.tags.split(",").map(t => t.trim()).filter(Boolean),
      });
      toast.success("Requirement posted");
      nav("/");
    } catch (e) { toast.error(e?.response?.data?.detail?.error || "Failed to post"); }
    finally { setLoading(false); }
  };

  return (
    <div className="page page-narrow" data-testid="requirement-form-page">
      <PageHeader title="Post a requirement" subtitle="Tell builders what you need. Better descriptions → better matches." />
      <form onSubmit={submit} className="card">
        <label className="dim mono mb-2">Title</label>
        <input className="input" required minLength={4} value={f.title} onChange={e => setF({ ...f, title: e.target.value })} placeholder="e.g., Multi-tenant ERP for textile factory" data-testid="req-title-input" />
        <label className="dim mono mt-4 mb-2">Detailed description</label>
        <textarea className="textarea" required minLength={20} maxLength={6000} value={f.description} onChange={e => setF({ ...f, description: e.target.value })} placeholder="The more specific, the better the AI match." data-testid="req-description-input" />
        <div className="row gap-3 mt-4">
          <div className="col flex-1">
            <label className="dim mono mb-2">Category</label>
            <select className="input" value={f.category} onChange={e => setF({ ...f, category: e.target.value })} data-testid="req-category-select">
              {CATEGORIES.map(c => <option key={c}>{c}</option>)}
            </select>
          </div>
          <div className="col flex-1">
            <label className="dim mono mb-2">Budget USD</label>
            <input className="input" type="number" min={0} value={f.budget_usd} onChange={e => setF({ ...f, budget_usd: e.target.value })} placeholder="optional" data-testid="req-budget-input" />
          </div>
          <div className="col flex-1">
            <label className="dim mono mb-2">Timeline</label>
            <input className="input" value={f.timeline} onChange={e => setF({ ...f, timeline: e.target.value })} placeholder="e.g., Q1 2026" data-testid="req-timeline-input" />
          </div>
        </div>
        <label className="dim mono mt-4 mb-2">Tags (comma-separated)</label>
        <input className="input" value={f.tags} onChange={e => setF({ ...f, tags: e.target.value })} placeholder="multi-tenant, compliance" data-testid="req-tags-input" />
        <button className="btn mt-6" disabled={loading} data-testid="req-submit-btn">{loading ? "Posting…" : "Post requirement"}</button>
      </form>
    </div>
  );
}
