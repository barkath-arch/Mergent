import axios from 'axios';
import * as SecureStore from 'expo-secure-store';

const BACKEND = process.env.EXPO_PUBLIC_BACKEND_URL || '';
export const API_BASE = `${BACKEND}/api`;
export const WS_BASE = BACKEND.replace(/^http/i, 'ws') + '/api/ws';

let _accessToken: string | null = null;
const listeners = new Set<(t: string | null) => void>();

export function setAccessToken(t: string | null) {
  _accessToken = t;
  if (t) SecureStore.setItemAsync('access_token', t).catch(() => {});
  else SecureStore.deleteItemAsync('access_token').catch(() => {});
  listeners.forEach((l) => l(t));
}

export function getAccessToken() {
  return _accessToken;
}

export function onAuthChange(cb: (t: string | null) => void) {
  listeners.add(cb);
  return () => { listeners.delete(cb); };
}

export async function restoreToken() {
  try {
    const t = await SecureStore.getItemAsync('access_token');
    if (t) _accessToken = t;
    return t;
  } catch {
    return null;
  }
}

const api = axios.create({ baseURL: API_BASE, timeout: 30000 });

api.interceptors.request.use((cfg) => {
  if (_accessToken) cfg.headers.Authorization = `Bearer ${_accessToken}`;
  return cfg;
});

let refreshing: Promise<any> | null = null;
api.interceptors.response.use(
  (r) => r,
  async (err) => {
    const orig = err?.config || {};
    if (err?.response?.status === 401 && !orig._retried && !orig.url?.includes('/auth/')) {
      orig._retried = true;
      try {
        if (!refreshing) {
          refreshing = axios
            .post(`${API_BASE}/auth/refresh`, {}, {
              headers: _accessToken ? { Authorization: `Bearer ${_accessToken}` } : {},
            })
            .finally(() => { refreshing = null; });
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
