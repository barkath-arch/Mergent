import React, { useEffect, useRef, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { Bell, Check, Settings as Cog } from "lucide-react";
import api from "../lib/api";

/** Notification dropdown anchored under the topbar bell.
 *  - polls unread-count every 30s
 *  - lazy-loads list on open
 *  - mark-all-read + per-row navigation
 */
export default function NotificationCenter() {
  const [open, setOpen] = useState(false);
  const [items, setItems] = useState([]);
  const [unread, setUnread] = useState(0);
  const [loading, setLoading] = useState(false);
  const ref = useRef(null);
  const nav = useNavigate();

  // Initial + polling unread count.
  useEffect(() => {
    let mounted = true;
    const fetchCount = () =>
      api.get("/notifications/unread-count")
        .then(r => mounted && setUnread(r.data.unread_total || 0))
        .catch(() => {});
    fetchCount();
    const t = setInterval(fetchCount, 30000);
    return () => { mounted = false; clearInterval(t); };
  }, []);

  // Close on outside click.
  useEffect(() => {
    function onDoc(e) { if (ref.current && !ref.current.contains(e.target)) setOpen(false); }
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, []);

  async function openDropdown() {
    setOpen(v => !v);
    if (open) return;
    setLoading(true);
    try {
      const r = await api.get("/notifications?limit=20");
      setItems(r.data.items || []);
      setUnread(r.data.unread_total || 0);
    } finally { setLoading(false); }
  }

  async function markAllRead() {
    await api.post("/notifications/read", { mark_all: true });
    setItems(items.map(i => ({ ...i, read: true })));
    setUnread(0);
  }

  async function openItem(n) {
    if (!n.read) {
      await api.post("/notifications/read", { ids: [n.id] }).catch(() => {});
      setItems(items.map(i => i.id === n.id ? { ...i, read: true } : i));
      setUnread(Math.max(0, unread - 1));
    }
    setOpen(false);
    if (n.link) nav(n.link);
  }

  return (
    <div ref={ref} style={{ position: "relative" }} data-testid="notification-center">
      <button
        className="btn-ghost"
        style={{ position: "relative", padding: 8, borderRadius: 10 }}
        title="Notifications"
        onClick={openDropdown}
        data-testid="topbar-bell-btn"
      >
        <Bell size={16} />
        {unread > 0 ? (
          <span data-testid="bell-unread-dot" style={{
            position: "absolute", top: 2, right: 2, minWidth: 16, height: 16,
            padding: "0 4px", borderRadius: 8, background: "var(--rose, #f87171)",
            color: "white", fontSize: 10, lineHeight: "16px", fontWeight: 600,
          }}>{unread > 99 ? "99+" : unread}</span>
        ) : null}
      </button>

      {open ? (
        <div className="card" data-testid="notification-dropdown" style={{
          position: "absolute", right: 0, top: "calc(100% + 8px)",
          width: 380, maxHeight: 480, overflow: "auto", zIndex: 50,
          boxShadow: "0 20px 60px rgba(0,0,0,.45)", padding: 0,
        }}>
          <div className="row-between" style={{ padding: "12px 14px", borderBottom: "1px solid var(--border)" }}>
            <span style={{ fontSize: 13, fontWeight: 600 }}>Notifications</span>
            <div className="row gap-2">
              <button className="btn-ghost" style={{ padding: 6, fontSize: 12 }} onClick={markAllRead} disabled={unread === 0} data-testid="notif-mark-all-read">
                <Check size={12} /> Mark all
              </button>
              <Link to="/settings/notifications" onClick={() => setOpen(false)} className="btn-ghost" style={{ padding: 6 }} title="Preferences" data-testid="notif-prefs-link">
                <Cog size={12} />
              </Link>
            </div>
          </div>
          {loading ? <div style={{ padding: 32, textAlign: "center" }} className="dim">Loading…</div>
            : items.length === 0 ? <div style={{ padding: 32, textAlign: "center" }} className="dim">You're all caught up.</div>
              : items.map(n => (
                <button
                  key={n.id}
                  onClick={() => openItem(n)}
                  className="col"
                  data-testid={`notif-row-${n.id}`}
                  style={{
                    width: "100%", textAlign: "left", padding: "10px 14px",
                    background: n.read ? "transparent" : "rgba(196,181,253,.08)",
                    borderBottom: "1px solid var(--border)", cursor: "pointer",
                  }}
                >
                  <div className="row-between"><span style={{ fontSize: 13, fontWeight: 500 }}>{n.title}</span>
                    {!n.read ? <span style={{ width: 6, height: 6, borderRadius: 3, background: "var(--accent, #c4b5fd)" }} /> : null}
                  </div>
                  <span className="dim" style={{ fontSize: 11.5, marginTop: 2 }}>{n.body}</span>
                  <span className="dim mono" style={{ fontSize: 10.5, marginTop: 4 }}>{new Date(n.created_at).toLocaleString()}</span>
                </button>
              ))}
        </div>
      ) : null}
    </div>
  );
}
