import React, { useEffect, useState } from "react";
import api from "../lib/api";
import { SolutionCard, PageHeader, Empty } from "../components/UI";

export default function Saved() {
  const [items, setItems] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    api.get("/me/saved?limit=50")
      .then(r => setItems(r.data.items || []))
      .finally(() => setLoading(false));
  }, []);

  function handleSavedChange(solId, saved) {
    if (!saved) setItems(prev => prev.filter(i => i.solution_id !== solId));
  }

  return (
    <div className="page" data-testid="saved-page">
      <PageHeader
        title="Saved solutions"
        subtitle={`${items.length} item${items.length === 1 ? "" : "s"} bookmarked for later.`}
      />
      {loading ? (
        <div className="card" style={{ padding: 40, textAlign: "center" }}>Loading…</div>
      ) : items.length === 0 ? (
        <Empty title="Nothing saved yet" hint="Tap the bookmark on any solution card to add it here." />
      ) : (
        <div className="grid grid-3" data-testid="saved-grid">
          {items.map(item => (
            <SolutionCard
              key={item.id}
              s={item.solution}
              initialSaved
              onSavedChange={handleSavedChange}
            />
          ))}
        </div>
      )}
    </div>
  );
}
