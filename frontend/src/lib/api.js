/* MERGENT V1 — global API client. Access token in-memory, refresh cookie httpOnly. */
import axios from "axios";

// We honour REACT_APP_BACKEND_URL, but if the live origin differs (e.g. the
// preview ingress 307'd us from preview→internal.preview), prefer the live
// origin so XHRs stay same-origin and credentials flow without Cloudflare's
// preflight CORS interception.
const ENV_BACKEND = process.env.REACT_APP_BACKEND_URL || "";
const LIVE_ORIGIN = typeof window !== "undefined" ? window.location.origin : "";
const BACKEND = LIVE_ORIGIN && (LIVE_ORIGIN.endsWith(".emergentagent.com") || LIVE_ORIGIN.endsWith(".emergent.host")) ? LIVE_ORIGIN : ENV_BACKEND;
export const API_BASE = `${BACKEND}/api`;
export const WS_BASE = BACKEND.replace(/^http/i, "ws") + "/api/ws";

let _accessToken = null;
const listeners = new Set();

export function setAccessToken(t) {
  _accessToken = t;
  listeners.forEach((l) => l(t));
}
export function getAccessToken() { return _accessToken; }
export function onAuthChange(cb) { listeners.add(cb); return () => listeners.delete(cb); }

const api = axios.create({ baseURL: API_BASE, withCredentials: true, timeout: 30000 });

api.interceptors.request.use((cfg) => {
  if (_accessToken) cfg.headers.Authorization = `Bearer ${_accessToken}`;
  return cfg;
});

let refreshing = null;
api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const orig = err?.config || {};
    if (err?.response?.status === 401 && !orig._retried && !orig.url?.includes("/auth/")) {
      orig._retried = true;
      try {
        if (!refreshing) {
          refreshing = axios.post(`${API_BASE}/auth/refresh`, {}, { withCredentials: true }).finally(() => { refreshing = null; });
        }
        const res = await refreshing;
        setAccessToken(res.data.access_token);
        orig.headers = { ...(orig.headers || {}), Authorization: `Bearer ${res.data.access_token}` };
        return axios(orig);
      } catch (_) { /* fall through */ }
    }
    return Promise.reject(err);
  }
);

export default api;
