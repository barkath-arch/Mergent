import React, { useEffect, useState } from "react";
import { toast } from "sonner";
import { Save, Bell, Mail } from "lucide-react";
import api from "../lib/api";
import { PageHeader } from "../components/UI";

const CATEGORY_LABELS = {
  messages: "Direct messages",
  transactions: "Purchases & sales",
  deployments: "Deployment status",
  reviews: "Reviews you receive",
  system: "Account & system",
};

const DIGEST_OPTIONS = [
  ["realtime", "Send each email instantly"],
  ["daily", "Daily digest"],
  ["weekly", "Weekly digest"],
  ["off", "Off — no marketing emails"],
];

export default function NotificationSettings() {
  const [prefs, setPrefs] = useState(null);
  const [saving, setSaving] = useState(false);

  useEffect(() => { api.get("/notification-preferences").then(r => setPrefs(r.data)); }, []);

  if (!prefs) return <div className="card" style={{ padding: 40, textAlign: "center" }}>Loading…</div>;

  function setChannel(k, v) {
    setPrefs({ ...prefs, channels: { ...prefs.channels, [k]: v } });
  }
  function setCategory(cat, ch, v) {
    setPrefs({
      ...prefs,
      categories: {
        ...prefs.categories,
        [cat]: { ...(prefs.categories[cat] || {}), [ch]: v },
      },
    });
  }

  async function save() {
    setSaving(true);
    try {
      const r = await api.patch("/notification-preferences", {
        channels: prefs.channels,
        categories: prefs.categories,
        email_digest: prefs.email_digest,
      });
      setPrefs(r.data);
      toast.success("Preferences saved");
    } catch (e) {
      toast.error("Could not save");
    } finally { setSaving(false); }
  }

  return (
    <div className="page" data-testid="notification-settings-page">
      <PageHeader
        title="Notification preferences"
        subtitle="Choose how and when Mergent reaches you."
        right={
          <button className="btn btn-secondary" onClick={save} disabled={saving} data-testid="prefs-save-btn">
            <Save size={14} /> {saving ? "Saving…" : "Save"}
          </button>
        }
      />

      <div className="card" data-testid="channels-card">
        <div className="h3">Channels</div>
        <div className="dim mt-2" style={{ fontSize: 12.5 }}>Master switches — turn off a channel and we'll respect that for every category below.</div>
        <div className="col gap-2 mt-4">
          {[["in_app", "In-app notifications", Bell],
            ["email", "Email", Mail]].map(([k, label, Icon]) => (
            <label key={k} className="row-between card card-tight" style={{ cursor: "pointer" }} data-testid={`channel-${k}`}>
              <span className="row gap-3"><Icon size={14} /> {label}</span>
              <input type="checkbox" checked={!!prefs.channels?.[k]} onChange={e => setChannel(k, e.target.checked)} data-testid={`channel-${k}-input`} />
            </label>
          ))}
        </div>
      </div>

      <div className="card mt-6" data-testid="categories-card">
        <div className="h3">Per-category settings</div>
        <div className="col gap-1 mt-4">
          <div className="row dim" style={{ fontSize: 11.5, padding: "6px 12px", textTransform: "uppercase", letterSpacing: ".08em" }}>
            <span style={{ flex: 2 }}>Category</span><span style={{ flex: 1, textAlign: "center" }}>In-app</span><span style={{ flex: 1, textAlign: "center" }}>Email</span>
          </div>
          {Object.entries(prefs.categories || {}).map(([cat, cfg]) => (
            <div key={cat} className="row card card-tight" data-testid={`category-row-${cat}`}>
              <span style={{ flex: 2 }}>{CATEGORY_LABELS[cat] || cat}</span>
              <span style={{ flex: 1, textAlign: "center" }}>
                <input type="checkbox" checked={!!cfg.in_app} onChange={e => setCategory(cat, "in_app", e.target.checked)} data-testid={`cat-${cat}-in_app`} />
              </span>
              <span style={{ flex: 1, textAlign: "center" }}>
                <input type="checkbox" checked={!!cfg.email} onChange={e => setCategory(cat, "email", e.target.checked)} data-testid={`cat-${cat}-email`} />
              </span>
            </div>
          ))}
        </div>
      </div>

      <div className="card mt-6" data-testid="digest-card">
        <div className="h3">Email digest</div>
        <select className="input mt-3" value={prefs.email_digest || "realtime"}
          onChange={e => setPrefs({ ...prefs, email_digest: e.target.value })}
          data-testid="digest-select"
          style={{ maxWidth: 320 }}>
          {DIGEST_OPTIONS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}
        </select>
        <div className="dim mt-2" style={{ fontSize: 12 }}>
          Digest applies to bulk categories (marketing, recommendations). Critical events (security, transactions) always go realtime regardless of this setting.
        </div>
      </div>
    </div>
  );
}
