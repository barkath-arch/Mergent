import React, { useEffect, useState } from "react";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import {
  LayoutDashboard, Store, Sparkles, MessageSquare, Receipt, Rocket,
  Settings, LogOut, Search, User2, Plus, Bookmark, Hammer,
} from "lucide-react";
import { useAuth } from "../context/AuthContext";
import api, { WS_BASE, getAccessToken } from "../lib/api";
import NotificationCenter from "./NotificationCenter";

function NavItem({ to, icon: Icon, label, badge }) {
  return (
    <NavLink to={to} end={to === "/"} className={({ isActive }) => `nav-item ${isActive ? "active" : ""}`} data-testid={`nav-${label.toLowerCase().replace(/\s+/g, "-")}`}>
      <Icon size={16} strokeWidth={1.8} />
      <span>{label}</span>
      {badge ? <span className="nav-badge" data-testid={`nav-badge-${label.toLowerCase()}`}>{badge}</span> : null}
    </NavLink>
  );
}

export default function Layout() {
  const { user, logout } = useAuth();
  const nav = useNavigate();
  const [unread, setUnread] = useState(0);
  const isBuilder = user?.role === "builder" || user?.role === "admin";

  useEffect(() => {
    if (!user) return;
    const token = getAccessToken();
    if (!token) return;
    const url = `${WS_BASE}/conversations/${user.id}?token=${token}`;
    let ws;
    let cancelled = false;
    try {
      ws = new WebSocket(url);
      ws.onmessage = (e) => {
        try {
          const m = JSON.parse(e.data);
          if (m.type === "unread_count") setUnread(m.total_unread || 0);
        } catch {}
      };
    } catch {}
    api.get("/messaging/unread-count").then(r => !cancelled && setUnread(r.data.total_unread || 0)).catch(() => {});
    return () => { cancelled = true; try { ws?.close(); } catch {} };
  }, [user]);

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand" data-testid="brand">
          <div className="brand-mark" />
          <span className="brand-name">Mergent</span>
          <span className="brand-tag">V1</span>
        </div>

        <div className="nav-group">
          <NavItem to="/" icon={LayoutDashboard} label="Discover" />
          <NavItem to="/marketplace" icon={Store} label="Marketplace" />
          <NavItem to="/ai-match" icon={Sparkles} label="AI Match" />
          <NavItem to="/messages" icon={MessageSquare} label="Messages" badge={unread > 0 ? unread : null} />
          <NavItem to="/transactions" icon={Receipt} label="Transactions" />
          <NavItem to="/deployments" icon={Rocket} label="Deployments" />
          <NavItem to="/saved" icon={Bookmark} label="Saved" />
        </div>

        {isBuilder ? (
          <>
            <div className="nav-label">Builder</div>
            <div className="nav-group">
              <NavItem to="/builder" icon={Hammer} label="Builder Hub" />
            </div>
          </>
        ) : null}

        <div className="nav-label">Account</div>
        <div className="nav-group">
          <NavItem to="/settings" icon={Settings} label="Settings" />
        </div>

        <div style={{ position: "absolute", bottom: 16, left: 16, right: 16 }}>
          <div className="card card-tight" style={{ padding: 10 }}>
            <div className="row gap-3">
              <div className="avatar" data-testid="sidebar-user-avatar">{(user?.name || "?").slice(0, 1).toUpperCase()}</div>
              <div className="col" style={{ minWidth: 0 }}>
                <span style={{ fontSize: 12.5, fontWeight: 500, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }} data-testid="sidebar-user-name">{user?.name || "Guest"}</span>
                <span className="dim" style={{ fontSize: 11, textTransform: "uppercase", letterSpacing: ".08em" }}>{user?.role}</span>
              </div>
              <button className="btn-ghost" style={{ padding: 6, borderRadius: 8 }} onClick={async () => { await logout(); nav("/auth/login"); }} title="Logout" data-testid="sidebar-logout-btn">
                <LogOut size={14} />
              </button>
            </div>
          </div>
        </div>
      </aside>

      <main className="main">
        <div className="topbar">
          <div className="topbar-search">
            <Search size={15} />
            <input placeholder="Search solutions, builders, requirements…" data-testid="topbar-search-input"
              onKeyDown={(e) => { if (e.key === "Enter" && e.target.value.trim()) nav(`/marketplace?q=${encodeURIComponent(e.target.value.trim())}`); }} />
          </div>
          <div style={{ flex: 1 }} />
          <Link to="/requirements/new" className="btn btn-secondary" data-testid="topbar-post-requirement-btn">
            <Plus size={14} /> Post requirement
          </Link>
          <NotificationCenter />
          <div className="avatar" title={user?.email} data-testid="topbar-avatar">{(user?.name || "?").slice(0, 1).toUpperCase()}</div>
        </div>

        <Outlet />
      </main>
    </div>
  );
}
