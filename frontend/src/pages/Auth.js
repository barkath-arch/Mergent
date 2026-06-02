import React, { useState } from "react";
import { Link, useNavigate, useLocation } from "react-router-dom";
import { ArrowRight, Loader2 } from "lucide-react";
import { useAuth } from "../context/AuthContext";
import { toast } from "sonner";
import api from "../lib/api";

export function Login() {
  const { login } = useAuth();
  const nav = useNavigate();
  const loc = useLocation();
  const next = new URLSearchParams(loc.search).get("next") || "/";
  const [email, setEmail] = useState("rohit@mergent.demo");
  const [password, setPassword] = useState("Demo!Pass123");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault();
    setLoading(true); setError("");
    try { await login(email, password); toast.success("Welcome back"); nav(next); }
    catch (err) { setError(err?.response?.data?.detail?.error || "Login failed"); }
    finally { setLoading(false); }
  };

  return (
    <div className="auth-shell" data-testid="login-page">
      <form onSubmit={submit} className="card card-elevated auth-card fade-in">
        <div className="row gap-3 mb-6">
          <div className="brand-mark" />
          <span className="h2">Mergent</span>
        </div>
        <div className="h1 mb-2" style={{ fontSize: 26 }}>Welcome back</div>
        <p className="muted mb-6" style={{ fontSize: 13.5 }}>Sign in to access the marketplace and AI match.</p>
        <label className="dim mono mb-2" style={{ fontSize: 11, letterSpacing: ".08em", textTransform: "uppercase" }}>Email</label>
        <input className="input" type="email" value={email} onChange={e => setEmail(e.target.value)} required data-testid="login-email-input" />
        <label className="dim mono mt-4 mb-2" style={{ fontSize: 11, letterSpacing: ".08em", textTransform: "uppercase" }}>Password</label>
        <input className="input" type="password" value={password} onChange={e => setPassword(e.target.value)} required data-testid="login-password-input" />
        {error ? <div className="chip chip-rose mt-4" data-testid="login-error">{error}</div> : null}
        <button type="submit" className="btn mt-6" style={{ width: "100%", justifyContent: "center" }} disabled={loading} data-testid="login-submit-btn">
          {loading ? <Loader2 size={14} /> : <>Sign in <ArrowRight size={14} /></>}
        </button>
        <div className="divider" />
        <div className="row-between" style={{ fontSize: 12.5 }}>
          <Link to="/auth/forgot" className="dim" data-testid="login-forgot-link">Forgot password?</Link>
          <Link to="/auth/register" className="muted" data-testid="login-register-link">Create an account →</Link>
        </div>
        <div className="dim mt-6" style={{ fontSize: 11.5, textAlign: "center", lineHeight: 1.7 }}>
          Demo buyer: <code>rohit@mergent.demo</code> / <code>Demo!Pass123</code><br />
          Demo builder: <code>aman@mergent.demo</code> / <code>Demo!Pass123</code>
        </div>
      </form>
    </div>
  );
}

export function Register() {
  const { register } = useAuth();
  const nav = useNavigate();
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "buyer" });
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const submit = async (e) => {
    e.preventDefault(); setLoading(true); setError("");
    try { await register(form); toast.success("Account created"); nav("/"); }
    catch (err) { setError(err?.response?.data?.detail?.error || "Registration failed"); }
    finally { setLoading(false); }
  };

  return (
    <div className="auth-shell" data-testid="register-page">
      <form onSubmit={submit} className="card card-elevated auth-card fade-in">
        <div className="row gap-3 mb-6"><div className="brand-mark" /><span className="h2">Mergent</span></div>
        <div className="h1 mb-2" style={{ fontSize: 26 }}>Create account</div>
        <p className="muted mb-6" style={{ fontSize: 13.5 }}>Join as a buyer or builder.</p>

        <label className="dim mono mb-2" style={{ fontSize: 11, letterSpacing: ".08em", textTransform: "uppercase" }}>I'm a…</label>
        <div className="row gap-3 mb-4">
          {["buyer", "builder"].map(r => (
            <button type="button" key={r}
              className="card card-tight"
              style={{ flex: 1, cursor: "pointer", textAlign: "center", borderColor: form.role === r ? "var(--violet-2)" : undefined, background: form.role === r ? "rgba(139,92,246,0.1)" : undefined }}
              onClick={() => setForm({ ...form, role: r })}
              data-testid={`register-role-${r}`}>
              <div style={{ fontWeight: 500, fontSize: 13.5, textTransform: "capitalize" }}>{r}</div>
              <div className="dim" style={{ fontSize: 11, marginTop: 2 }}>{r === "buyer" ? "Find & acquire software" : "Sell solutions you've built"}</div>
            </button>
          ))}
        </div>
        <input className="input mt-3" placeholder="Full name" value={form.name} onChange={e => setForm({ ...form, name: e.target.value })} required data-testid="register-name-input" />
        <input className="input mt-3" type="email" placeholder="you@company.com" value={form.email} onChange={e => setForm({ ...form, email: e.target.value })} required data-testid="register-email-input" />
        <input className="input mt-3" type="password" placeholder="Password (min 8)" minLength={8} value={form.password} onChange={e => setForm({ ...form, password: e.target.value })} required data-testid="register-password-input" />
        {error ? <div className="chip chip-rose mt-4" data-testid="register-error">{error}</div> : null}
        <button className="btn mt-6" style={{ width: "100%", justifyContent: "center" }} disabled={loading} data-testid="register-submit-btn">
          {loading ? <Loader2 size={14} /> : "Create account"}
        </button>
        <div className="divider" />
        <div className="muted" style={{ fontSize: 12.5, textAlign: "center" }}>Already have an account? <Link to="/auth/login" data-testid="register-login-link">Sign in</Link></div>
      </form>
    </div>
  );
}

export function Forgot() {
  const [email, setEmail] = useState("");
  const [sent, setSent] = useState(false);
  const submit = async (e) => {
    e.preventDefault();
    try { await api.post("/auth/forgot-password", { email }); } catch {}
    setSent(true);
  };
  return (
    <div className="auth-shell" data-testid="forgot-page">
      <form onSubmit={submit} className="card card-elevated auth-card">
        <div className="h2 mb-4">Reset password</div>
        {sent ? (
          <p className="muted">If an account exists for <code>{email}</code>, we've logged a reset link to the server console.</p>
        ) : (
          <>
            <p className="muted mb-4" style={{ fontSize: 13.5 }}>Enter your email and we'll send a reset link.</p>
            <input className="input" type="email" value={email} onChange={e => setEmail(e.target.value)} required data-testid="forgot-email-input" />
            <button className="btn mt-4" style={{ width: "100%", justifyContent: "center" }} data-testid="forgot-submit-btn">Send reset link</button>
          </>
        )}
        <div className="divider" />
        <Link to="/auth/login" className="dim" style={{ fontSize: 12.5 }}>← Back to sign in</Link>
      </form>
    </div>
  );
}
