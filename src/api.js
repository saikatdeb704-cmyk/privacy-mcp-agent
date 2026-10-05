/**
 * api.js — thin client for the local FastAPI orchestrator.
 * In dev, Vite proxies /api → http://127.0.0.1:8000. In production the
 * backend serves the built UI itself, so relative URLs work everywhere.
 */
const BASE = import.meta.env.VITE_API_URL || '';

async function request(path, options = {}) {
  let res;
  try {
    res = await fetch(`${BASE}${path}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });
  } catch {
    throw new Error('Cannot reach the local orchestrator. Start it with: python backend/main.py');
  }
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.detail || `Request failed (${res.status})`);
  return body;
}

export const getHealth = () => request('/api/health');

export const sendChat = (sessionId, message, model) =>
  request('/api/chat', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, message, model }),
  });

export const sendApproval = (sessionId, approvalId, approved) =>
  request('/api/approve', {
    method: 'POST',
    body: JSON.stringify({ session_id: sessionId, approval_id: approvalId, approved }),
  });

export const resetSession = (sessionId) =>
  request(`/api/reset/${sessionId}`, { method: 'POST' });
