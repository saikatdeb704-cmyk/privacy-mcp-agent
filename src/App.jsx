import React, { useState, useRef, useEffect, useCallback, useMemo } from 'react';
import {
  Send,
  Bot,
  User,
  Server,
  Code2,
  PanelRightOpen,
  PanelRightClose,
  ShieldCheck,
  Clock,
  Zap,
  CheckCircle2,
  XCircle,
  Activity,
  AlertTriangle,
  RotateCcw,
} from 'lucide-react';
import Sidebar from './Sidebar';
import MonitorPanel from './MonitorPanel';
import GuardrailModal from './GuardrailModal';
import { getHealth, sendChat, sendApproval, resetSession } from './api';

/* ═══════════════════════════════════════════════════════
   HELPERS
   ═══════════════════════════════════════════════════════ */
const now = () =>
  new Date().toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit', second: '2-digit', hour12: false });

const newSessionId = () =>
  (crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(16).slice(2)}`);

const shortArgs = (args) => {
  const s = JSON.stringify(args ?? {});
  return s.length > 140 ? `${s.slice(0, 140)}…` : s;
};

/** Minimal, safe markdown: **bold**, `code`, and line breaks. */
function RichText({ text }) {
  return text.split('\n').map((line, i) => {
    const parts = line.split(/(\*\*.*?\*\*|`[^`]+`)/g);
    return (
      <React.Fragment key={i}>
        {i > 0 && <br />}
        {parts.map((p, j) => {
          if (p.startsWith('**') && p.endsWith('**') && p.length > 4) return <strong key={j}>{p.slice(2, -2)}</strong>;
          if (p.startsWith('`') && p.endsWith('`') && p.length > 2) return <code key={j} className="inline-code">{p.slice(1, -1)}</code>;
          return p;
        })}
      </React.Fragment>
    );
  });
}

const EXAMPLE_QUERIES = [
  'List the files in my workspace',
  'Which 3 regions had the highest revenue in Q3 2024?',
  'Search my notes for budget',
  'Summarize reports/Q3_summary.md',
  'Give every Engineering employee a 5% raise',
];

/* ═══════════════════════════════════════════════════════
   APP COMPONENT
   ═══════════════════════════════════════════════════════ */
export default function App() {
  const [sessionId, setSessionId] = useState(newSessionId);
  const [messages, setMessages] = useState([]);
  const [input, setInput] = useState('');
  const [isThinking, setIsThinking] = useState(false);
  const [health, setHealth] = useState(null);
  const [backendError, setBackendError] = useState(null);
  const [activeModel, setActiveModel] = useState(() => localStorage.getItem('agent-model') || '');
  const [showMonitor, setShowMonitor] = useState(true);
  const [monitorLogs, setMonitorLogs] = useState([]);
  const [guardrailData, setGuardrailData] = useState(null);
  const [toast, setToast] = useState(null);

  const shownEventsRef = useRef(0);
  const messagesEndRef = useRef(null);
  const textareaRef = useRef(null);

  /* ── Health polling ── */
  const refreshHealth = useCallback(async () => {
    try {
      const h = await getHealth();
      setHealth(h);
      setBackendError(null);
      setActiveModel((current) => {
        const names = h.ollama.models.map((m) => m.name);
        if (current && names.includes(current)) return current;
        const preferred = names.find((n) => n.startsWith(h.ollama.default_model)) || names[0] || h.ollama.default_model;
        return preferred;
      });
    } catch (e) {
      setBackendError(e.message);
    }
  }, []);

  useEffect(() => {
    refreshHealth();
    const t = setInterval(refreshHealth, 8000);
    return () => clearInterval(t);
  }, [refreshHealth]);

  useEffect(() => {
    if (activeModel) localStorage.setItem('agent-model', activeModel);
  }, [activeModel]);

  /* ── Scroll + textarea autosize ── */
  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, [messages, isThinking]);

  useEffect(() => {
    const el = textareaRef.current;
    if (el) {
      el.style.height = 'auto';
      el.style.height = Math.min(el.scrollHeight, 120) + 'px';
    }
  }, [input]);

  const flashToast = useCallback((message) => {
    setToast(message);
    setTimeout(() => setToast(null), 2500);
  }, []);

  /* ── Stats ── */
  const stats = useMemo(() => {
    const done = monitorLogs.filter((l) => l.latencyMs != null);
    return {
      totalCalls: monitorLogs.length,
      autoApproved: monitorLogs.filter((l) => l.status === 'auto').length,
      blocked: monitorLogs.filter((l) => l.status === 'denied').length,
      avgLatency: done.length ? `${Math.round(done.reduce((s, l) => s + l.latencyMs, 0) / done.length)}ms` : '—',
    };
  }, [monitorLogs]);

  /* ═══════════════════════════════════════════════════════
     Handle an orchestrator response (chat or approval)
     ═══════════════════════════════════════════════════════ */
  const handleAgentResponse = useCallback((resp) => {
    const fresh = resp.events.slice(shownEventsRef.current);
    shownEventsRef.current = resp.events.length;

    // Monitor log: resolve pending entries, append the rest
    setMonitorLogs((prev) => {
      let logs = [...prev];
      for (const ev of fresh) {
        const entry = {
          toolName: `${ev.server} → ${ev.tool}`,
          timestamp: now(),
          detail: ev.status === 'denied' ? `DENIED: ${shortArgs(ev.arguments)}` : shortArgs(ev.arguments),
          risk: ev.risk,
          status: ev.status,
          latency: `${ev.latency_ms}ms`,
          latencyMs: ev.status === 'denied' ? null : ev.latency_ms,
        };
        const pendingIdx = logs.findIndex((l) => l.status === 'pending');
        if ((ev.status === 'approved' || ev.status === 'denied') && pendingIdx !== -1) {
          logs[pendingIdx] = { ...logs[pendingIdx], ...entry };
        } else {
          logs.push({ id: `${Date.now()}-${Math.random()}`, ...entry });
        }
      }
      if (resp.status === 'approval_required') {
        logs.push({
          id: resp.approval.id,
          toolName: `${resp.approval.server} → ${resp.approval.tool}`,
          timestamp: now(),
          detail: `HALTED: ${shortArgs(resp.approval.arguments)}`,
          risk: 'HIGH',
          status: 'pending',
          latency: null,
          latencyMs: null,
        });
      }
      return logs;
    });

    if (fresh.some((e) => e.risk === 'MEDIUM' && e.status === 'auto')) {
      flashToast('Auto-executed read-only database query');
    }

    if (fresh.length || resp.status === 'complete') {
      setMessages((prev) => [
        ...prev,
        {
          id: `${Date.now()}-${Math.random()}`,
          role: 'agent',
          content: resp.status === 'complete' ? resp.reply : '',
          tools: fresh,
          timestamp: now(),
        },
      ]);
    }

    if (resp.status === 'approval_required') {
      setGuardrailData({
        id: resp.approval.id,
        server: resp.approval.server,
        tool: resp.approval.tool,
        payload: `${resp.approval.tool}(${JSON.stringify(resp.approval.arguments, null, 2)})`,
      });
    }
  }, [flashToast]);

  const pushError = useCallback((message) => {
    setMessages((prev) => [
      ...prev,
      { id: `${Date.now()}-err`, role: 'agent', content: `⚠️ ${message}`, error: true, timestamp: now() },
    ]);
  }, []);

  /* ── Send ── */
  const handleSend = useCallback(async (queryOverride) => {
    const query = (typeof queryOverride === 'string' ? queryOverride : input).trim();
    if (!query || isThinking || guardrailData) return;

    setMessages((prev) => [...prev, { id: `${Date.now()}-u`, role: 'user', content: query, timestamp: now() }]);
    setInput('');
    setIsThinking(true);
    shownEventsRef.current = 0;

    try {
      handleAgentResponse(await sendChat(sessionId, query, activeModel));
    } catch (e) {
      pushError(e.message);
      refreshHealth();
    } finally {
      setIsThinking(false);
    }
  }, [input, isThinking, guardrailData, sessionId, activeModel, handleAgentResponse, pushError, refreshHealth]);

  /* ── Guardrail decision ── */
  const decide = useCallback(async (approved) => {
    if (!guardrailData) return;
    const { id } = guardrailData;
    setGuardrailData(null);
    setIsThinking(true);
    try {
      handleAgentResponse(await sendApproval(sessionId, id, approved));
    } catch (e) {
      pushError(e.message);
    } finally {
      setIsThinking(false);
    }
  }, [guardrailData, sessionId, handleAgentResponse, pushError]);

  const handleNewChat = useCallback(async () => {
    try { await resetSession(sessionId); } catch { /* backend may be offline */ }
    setSessionId(newSessionId());
    setMessages([]);
    setMonitorLogs([]);
    setGuardrailData(null);
  }, [sessionId]);

  const handleKeyDown = useCallback((e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSend();
    }
  }, [handleSend]);

  /* ── Setup status ── */
  const ollamaOnline = health?.ollama?.online;
  const hasModels = (health?.ollama?.models?.length ?? 0) > 0;
  const setupIssue = backendError
    ? { title: 'Orchestrator offline', text: 'Start the backend: run start.ps1 (or python backend/main.py).' }
    : health && !ollamaOnline
      ? { title: 'Ollama is not running', text: 'Open the Ollama app from the Start menu, or run: ollama serve' }
      : health && !hasModels
        ? { title: 'No local model installed', text: 'Download one in a terminal: ollama pull llama3.2' }
        : null;
  const ready = health && !setupIssue;
  const onlineServers = health?.servers?.filter((s) => s.online) ?? [];

  /* ═══════════════════════════════════════════════════════
     RENDER
     ═══════════════════════════════════════════════════════ */
  return (
    <div className="app-shell">
      <Sidebar
        health={health}
        backendOnline={!backendError && !!health}
        activeModel={activeModel}
        onModelChange={setActiveModel}
      />

      <main className="main-panel">
        <header className="panel-header">
          <div className="panel-header-left">
            <Server size={18} color="var(--accent)" />
            <span className="panel-header-title">Local Host Orchestrator</span>
            <span className="header-badge accent">MCP</span>
            <span className={`header-badge ${ready ? 'success' : 'warning'}`}>
              {ready ? 'HITL Active' : 'Setup needed'}
            </span>
          </div>
          <div className="panel-header-actions">
            <button id="new-chat-btn" className="icon-btn" onClick={handleNewChat} title="New conversation">
              <RotateCcw size={17} />
            </button>
            <button
              id="toggle-monitor-btn"
              className={`icon-btn ${showMonitor ? 'active' : ''}`}
              onClick={() => setShowMonitor((p) => !p)}
              title="Toggle Tool Monitor"
            >
              {showMonitor ? <PanelRightClose size={18} /> : <PanelRightOpen size={18} />}
            </button>
          </div>
        </header>

        {toast && (
          <div className="toast-bar">
            <Activity size={14} color="var(--warning)" />
            {toast}
          </div>
        )}

        {setupIssue && (
          <div className="setup-banner" role="alert">
            <AlertTriangle size={16} />
            <div>
              <strong>{setupIssue.title}.</strong> {setupIssue.text}
            </div>
          </div>
        )}

        <div className="messages-container">
          {messages.length === 0 && !isThinking && (
            <div className="welcome-hero">
              <div className="welcome-icon">
                <ShieldCheck size={32} />
              </div>
              <h1 className="welcome-title">Privacy-Preserving AI Agent</h1>
              <p className="welcome-subtitle">
                A local Small Language Model that works with your files and databases through the
                Model Context Protocol. Nothing leaves this computer, and every risky action waits
                for your approval.
              </p>

              <div className="arch-grid" style={{ maxWidth: 500, width: '100%', marginTop: '0.5rem' }}>
                <div className="arch-card">
                  <div className="arch-card-title">
                    <Zap size={12} color="var(--accent)" /> Local LLM Runtime
                  </div>
                  <ul className="arch-card-list">
                    {hasModels
                      ? health.ollama.models.slice(0, 3).map((m) => <li key={m.name}>{m.name}</li>)
                      : <li>{ollamaOnline ? 'No models pulled yet' : 'Ollama offline'}</li>}
                  </ul>
                </div>
                <div className="arch-card">
                  <div className="arch-card-title">
                    <Server size={12} color="var(--accent)" /> MCP Servers
                  </div>
                  <ul className="arch-card-list">
                    {onlineServers.length
                      ? onlineServers.map((s) => <li key={s.name}>{s.name} · {s.tools.length} tools</li>)
                      : <li>Not connected</li>}
                  </ul>
                </div>
              </div>

              <div className="welcome-chips">
                {EXAMPLE_QUERIES.map((q) => (
                  <button key={q} className="welcome-chip" onClick={() => handleSend(q)} disabled={!ready}>
                    {q}
                  </button>
                ))}
              </div>
            </div>
          )}

          {messages.map((msg) => (
            <div key={msg.id} className={`message-row ${msg.role}`}>
              <div className={`msg-avatar ${msg.role}`}>
                {msg.role === 'agent' ? <Bot size={18} /> : <User size={18} />}
              </div>
              <div className="msg-body">
                {msg.tools?.map((t, i) => (
                  <div key={i} className="tool-card">
                    <div className="tool-card-header">
                      <div className="tool-card-name">
                        <Code2 size={13} />
                        {t.server} → {t.tool}
                      </div>
                      <span className={`risk-badge ${t.risk.toLowerCase()}`}>{t.risk}</span>
                    </div>
                    <div className="tool-card-args">{shortArgs(t.arguments)}</div>
                    <div className="tool-card-body">{t.output}</div>
                    <div className="tool-card-footer">
                      <Clock size={10} />
                      {t.latency_ms}ms
                      <span style={{ marginLeft: 'auto', display: 'inline-flex', alignItems: 'center', gap: 4 }}>
                        {t.status === 'denied' ? (
                          <><XCircle size={10} color="var(--danger)" /> rejected</>
                        ) : (
                          <><CheckCircle2 size={10} color={t.error ? 'var(--danger)' : 'var(--success)'} />
                            {t.status === 'approved' ? 'approved & executed' : t.error ? 'error' : 'executed'}</>
                        )}
                      </span>
                    </div>
                  </div>
                ))}

                {msg.content && (
                  <div className={`msg-bubble ${msg.error ? 'error' : ''}`}>
                    <RichText text={msg.content} />
                  </div>
                )}

                <div className="msg-timestamp">{msg.timestamp}</div>
              </div>
            </div>
          ))}

          {isThinking && (
            <div className="message-row agent">
              <div className="msg-avatar agent">
                <Bot size={18} />
              </div>
              <div className="msg-body">
                <div className="thinking-dots">
                  <span /><span /><span />
                </div>
              </div>
            </div>
          )}

          <div ref={messagesEndRef} />
        </div>

        <div className="chat-input-area">
          <div className="chat-input-box">
            <textarea
              id="chat-input"
              ref={textareaRef}
              rows={1}
              placeholder={ready ? 'Ask about your files or database…' : 'Finish setup to start chatting…'}
              value={input}
              onChange={(e) => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
            />
            <button
              id="send-btn"
              className="send-btn"
              onClick={() => handleSend()}
              disabled={!input.trim() || isThinking || !!guardrailData}
            >
              <Send size={17} />
            </button>
          </div>
          <div className="chat-hint">
            Enter to send · Shift+Enter for new line · Model: {activeModel || '—'}
          </div>
        </div>
      </main>

      {showMonitor && <MonitorPanel logs={monitorLogs} stats={stats} />}

      {guardrailData && (
        <GuardrailModal data={guardrailData} onApprove={() => decide(true)} onReject={() => decide(false)} />
      )}
    </div>
  );
}
