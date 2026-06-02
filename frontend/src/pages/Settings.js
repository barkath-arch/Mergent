import React, { useState } from "react";
import { toast } from "sonner";
import api from "../lib/api";
import { PageHeader } from "../components/UI";
import { useAuth } from "../context/AuthContext";

export default function Settings() {
  const { user, refreshMe } = useAuth();
  const [name, setName] = useState(user?.name || "");
  const [headline, setHeadline] = useState("");
  const [bio, setBio] = useState("");
  const [skills, setSkills] = useState("");
  const [company, setCompany] = useState("");
  const [saving, setSaving] = useState(false);

  if (!user) return null;
  const isBuilder = user.role === "builder";

  const save = async (e) => {
    e.preventDefault(); setSaving(true);
    try {
      const payload = { name };
      if (isBuilder) {
        if (headline) payload.headline = headline;
        if (bio) payload.bio = bio;
        if (skills) payload.skills = skills.split(",").map(s => s.trim()).filter(Boolean);
      } else {
        if (company) payload.company = company;
      }
      await api.patch("/me", payload);
      toast.success("Saved");
      refreshMe();
    } catch { toast.error("Save failed"); }
    finally { setSaving(false); }
  };

  return (
    <div className="page page-narrow" data-testid="settings-page">
      <PageHeader title="Settings" subtitle={`Signed in as ${user.email} (${user.role})`} />
      <form onSubmit={save} className="card">
        <label className="dim mono mb-2">Display name</label>
        <input className="input" value={name} onChange={e => setName(e.target.value)} data-testid="settings-name-input" />
        {isBuilder ? (
          <>
            <label className="dim mono mt-4 mb-2">Headline</label>
            <input className="input" value={headline} onChange={e => setHeadline(e.target.value)} placeholder="One-liner about what you build" data-testid="settings-headline-input" />
            <label className="dim mono mt-4 mb-2">Bio</label>
            <textarea className="textarea" value={bio} onChange={e => setBio(e.target.value)} placeholder="Your story." data-testid="settings-bio-input" />
            <label className="dim mono mt-4 mb-2">Skills (comma-separated)</label>
            <input className="input" value={skills} onChange={e => setSkills(e.target.value)} placeholder="Python, React, Postgres" data-testid="settings-skills-input" />
          </>
        ) : (
          <>
            <label className="dim mono mt-4 mb-2">Company</label>
            <input className="input" value={company} onChange={e => setCompany(e.target.value)} placeholder="Your company name" data-testid="settings-company-input" />
          </>
        )}
        <button className="btn mt-6" disabled={saving} data-testid="settings-save-btn">{saving ? "Saving…" : "Save"}</button>
      </form>
    </div>
  );
}
