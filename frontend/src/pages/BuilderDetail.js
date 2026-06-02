import React, { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import { Loader2, Star, ShieldCheck } from "lucide-react";
import api from "../lib/api";
import { SolutionCard, PageHeader, Empty } from "../components/UI";

export default function BuilderDetail() {
  const { id } = useParams();
  const [data, setData] = useState(null);
  useEffect(() => { api.get(`/builders/${id}`).then(r => setData(r.data)); }, [id]);
  if (!data) return <div className="page"><Loader2 size={20} /></div>;
  const b = data.builder;
  return (
    <div className="page" data-testid={`builder-detail-${id}`}>
      <div className="row gap-4 mb-6">
        <div className="avatar" style={{ width: 64, height: 64, fontSize: 22 }}>{b.name[0]}</div>
        <div className="col flex-1">
          <div className="h1" style={{ fontSize: 32 }}>{b.name}</div>
          <p className="muted">{b.headline}</p>
          <div className="row gap-3 mt-2">
            <span className="chip">★ {b.rating?.toFixed?.(1) || "—"}</span>
            <span className="chip chip-muted">{b.review_count} reviews</span>
            <span className="chip chip-muted">{b.solutions_count} solutions</span>
            {b.verified ? <span className="chip chip-emerald"><ShieldCheck size={12} /> verified</span> : null}
          </div>
        </div>
        <Link to={`/messages?builder=${id}`} className="btn">Message {b.name.split(" ")[0]}</Link>
      </div>

      <div className="card mb-6">
        <div className="h3 mb-2">About</div>
        <p className="body" style={{ lineHeight: 1.75 }}>{b.bio || "—"}</p>
        {b.skills?.length > 0 && (
          <div className="row gap-2 mt-4" style={{ flexWrap: "wrap" }}>
            {b.skills.map(s => <span key={s} className="chip chip-muted">{s}</span>)}
          </div>
        )}
      </div>

      <div className="h2 mb-4">Solutions by {b.name.split(" ")[0]}</div>
      {data.solutions.length === 0 ? <Empty title="No solutions yet" /> : (
        <div className="grid grid-3" data-testid="builder-solutions">
          {data.solutions.map(s => <SolutionCard key={s.id} s={s} />)}
        </div>
      )}
    </div>
  );
}
