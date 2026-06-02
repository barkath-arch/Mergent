import React, { useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Send, Loader2 } from "lucide-react";
import api, { WS_BASE, getAccessToken } from "../lib/api";
import { useAuth } from "../context/AuthContext";
import { PageHeader, Empty } from "../components/UI";

export default function Messages() {
  const [params, setParams] = useSearchParams();
  const { user } = useAuth();
  const [convs, setConvs] = useState([]);
  const [activeId, setActiveId] = useState(params.get("c"));
  const [messages, setMessages] = useState([]);
  const [text, setText] = useState("");
  const [typing, setTyping] = useState(null);
  const listRef = useRef(null);

  const load = () => api.get("/conversations").then(r => setConvs(r.data.items));
  useEffect(() => { load(); }, []);

  useEffect(() => {
    if (!user) return;
    const url = `${WS_BASE}/conversations/${user.id}?token=${getAccessToken()}`;
    let ws;
    try {
      ws = new WebSocket(url);
      ws.onmessage = (e) => {
        try {
          const m = JSON.parse(e.data);
          if (m.type === "new_message") {
            load();
            if (m.conversation_id === activeId) setMessages(prev => [...prev, m.message]);
          }
          if (m.type === "typing" && m.conversation_id === activeId) {
            setTyping(m.is_typing ? m.user_id : null);
            if (m.is_typing) setTimeout(() => setTyping(null), 2500);
          }
        } catch {}
      };
    } catch {}
    return () => { try { ws?.close(); } catch {} };
  }, [user, activeId]);

  useEffect(() => {
    if (!activeId) return;
    api.get(`/conversations/${activeId}/messages`).then(r => setMessages(r.data.items));
    setParams(p => { p.set("c", activeId); return p; });
  }, [activeId, setParams]);

  useEffect(() => { listRef.current?.scrollTo(0, 1e6); }, [messages]);

  const send = async (e) => {
    e?.preventDefault?.();
    if (!text.trim()) return;
    const t = text.trim(); setText("");
    try {
      const r = await api.post(`/conversations/${activeId}/messages`, { text: t });
      setMessages(prev => [...prev, r.data]);
      load();
    } catch {}
  };

  const onTyping = (v) => {
    setText(v);
    if (activeId) api.post(`/conversations/${activeId}/typing`, { is_typing: true }).catch(() => {});
  };

  const active = convs.find(c => c.id === activeId);
  const otherId = active?.participants?.find(p => p !== user?.id);
  const otherName = active?.participant_names?.[otherId] || "—";

  return (
    <div className="page" data-testid="messages-page">
      <PageHeader title="Messages" subtitle="Coordinate with builders and buyers." />
      <div className="card" style={{ padding: 0, overflow: "hidden", height: "calc(100vh - 280px)", minHeight: 460, display: "grid", gridTemplateColumns: "280px 1fr" }}>
        <aside style={{ borderRight: "1px solid var(--border)", overflowY: "auto" }} data-testid="conversation-list">
          {convs.length === 0 ? <div className="dim" style={{ padding: 18, fontSize: 13 }}>No conversations yet.</div> :
            convs.map(c => {
              const otherUid = c.participants.find(p => p !== user?.id);
              const otherN = c.participant_names?.[otherUid] || "—";
              return (
                <button key={c.id}
                  onClick={() => setActiveId(c.id)}
                  className="nav-item"
                  style={{ width: "100%", textAlign: "left", borderRadius: 0, background: c.id === activeId ? "rgba(139,92,246,0.1)" : "transparent" }}
                  data-testid={`conversation-item-${c.id}`}>
                  <div className="avatar" style={{ width: 30, height: 30, fontSize: 12 }}>{otherN[0]}</div>
                  <div className="col flex-1" style={{ minWidth: 0 }}>
                    <span style={{ fontWeight: 500, fontSize: 13, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{otherN}</span>
                    <span className="dim" style={{ fontSize: 11, whiteSpace: "nowrap", overflow: "hidden", textOverflow: "ellipsis" }}>{c.last_message || "—"}</span>
                  </div>
                  {c.unread_for_me ? <span className="nav-badge">{c.unread_for_me}</span> : null}
                </button>
              );
            })}
        </aside>
        <section style={{ display: "flex", flexDirection: "column", minWidth: 0 }}>
          {!active ? <Empty title="Select a conversation" /> : (
            <>
              <div className="row gap-3" style={{ padding: 16, borderBottom: "1px solid var(--border)" }}>
                <div className="avatar">{otherName[0]}</div>
                <div className="col flex-1">
                  <span style={{ fontWeight: 500 }}>{otherName}</span>
                  {typing && typing !== user?.id ? <span className="dim" style={{ fontSize: 11 }}>typing…</span> : null}
                </div>
              </div>
              <div ref={listRef} style={{ flex: 1, padding: 16, overflowY: "auto" }} data-testid="messages-list">
                {messages.map(m => {
                  const mine = m.sender_id === user?.id;
                  return (
                    <div key={m.id} className="row" style={{ justifyContent: mine ? "flex-end" : "flex-start", marginBottom: 8 }}>
                      <div className={mine ? "card" : "card card-tight"} style={{ maxWidth: "70%", padding: "10px 14px", background: mine ? "linear-gradient(135deg, var(--violet), var(--violet-3))" : undefined, border: mine ? "none" : undefined }}>
                        <div style={{ fontSize: 13.5 }}>{m.text}</div>
                      </div>
                    </div>
                  );
                })}
              </div>
              <form onSubmit={send} className="row gap-3" style={{ padding: 14, borderTop: "1px solid var(--border)" }}>
                <input className="input" placeholder="Type a message…" value={text} onChange={e => onTyping(e.target.value)} data-testid="message-input" />
                <button className="btn" data-testid="send-message-btn"><Send size={14} /></button>
              </form>
            </>
          )}
        </section>
      </div>
    </div>
  );
}
