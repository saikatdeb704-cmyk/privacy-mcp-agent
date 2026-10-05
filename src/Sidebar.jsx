import React from 'react';
import { ShieldCheck, Cpu, Terminal, Database, Server, WifiOff, Download } from 'lucide-react';

const SERVER_ICONS = { 'filesystem-mcp': Terminal, 'sqlite-mcp': Database };
const RECOMMENDED = ['llama3.2', 'qwen2.5'];

const formatSize = (bytes) => (bytes ? `${(bytes / 1e9).toFixed(1)} GB` : '');

export default function Sidebar({ health, backendOnline, activeModel, onModelChange }) {
  const models = health?.ollama?.models ?? [];
  const ollamaOnline = !!health?.ollama?.online;
  const servers = health?.servers ?? [];

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="sidebar-logo-icon">
          <ShieldCheck size={20} />
        </div>
        <div>
          <div className="sidebar-logo-text">Privacy MCP Agent</div>
          <div style={{ fontSize: '0.6rem', color: 'var(--text-muted)', marginTop: '1px' }}>
            v1.0 · {backendOnline ? 'Orchestrator online' : 'Orchestrator offline'}
          </div>
        </div>
      </div>

      {/* SLM Runtime */}
      <div className="sidebar-section">
        <div className="sidebar-section-title">
          SLM Runtime · Ollama {ollamaOnline ? '●' : '○'}
        </div>
        {models.length > 0 ? (
          models.map((m) => {
            const isActive = activeModel === m.name;
            return (
              <div
                key={m.name}
                id={`model-${m.name.replace(/[^a-z0-9]/gi, '-')}`}
                className={`sidebar-item ${isActive ? 'active' : ''}`}
                onClick={() => onModelChange(m.name)}
              >
                <div className="sidebar-item-icon"><Cpu size={16} /></div>
                <div className="sidebar-item-label">
                  <div style={{ fontSize: '0.82rem' }}>{m.name}</div>
                  <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)', marginTop: '1px' }}>
                    {formatSize(m.size)} · local
                  </div>
                </div>
                <div className={`status-indicator ${isActive ? 'online' : 'offline'}`} />
              </div>
            );
          })
        ) : (
          RECOMMENDED.map((name) => (
            <div key={name} className="sidebar-item" title={`Run: ollama pull ${name}`}>
              <div className="sidebar-item-icon"><Download size={16} /></div>
              <div className="sidebar-item-label">
                <div style={{ fontSize: '0.82rem' }}>{name}</div>
                <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)', marginTop: '1px' }}>
                  ollama pull {name}
                </div>
              </div>
              <div className="status-indicator offline" />
            </div>
          ))
        )}
      </div>

      {/* MCP Servers */}
      <div className="sidebar-section">
        <div className="sidebar-section-title">MCP Servers</div>
        {servers.length === 0 && (
          <div className="sidebar-item">
            <div className="sidebar-item-icon"><Server size={16} /></div>
            <div className="sidebar-item-label">Waiting for orchestrator…</div>
            <div className="status-indicator offline" />
          </div>
        )}
        {servers.map((s) => {
          const Icon = SERVER_ICONS[s.name] || Server;
          return (
            <div key={s.name} className="sidebar-item" title={s.error || s.tools.map((t) => `${t.name} (${t.risk})`).join('\n')}>
              <div className="sidebar-item-icon"><Icon size={16} /></div>
              <div className="sidebar-item-label">
                <div style={{ fontSize: '0.82rem' }}>{s.name}</div>
                <div style={{ fontSize: '0.62rem', color: 'var(--text-muted)', marginTop: '1px' }}>
                  {s.online ? `${s.tools.length} tools · stdio` : 'failed to start'}
                </div>
              </div>
              <div className={`status-indicator ${s.online ? 'online' : 'offline'}`} />
            </div>
          );
        })}
      </div>

      <div className="sidebar-footer">
        <div className="air-gapped-badge">
          <WifiOff size={14} />
          100% Local Execution
        </div>
        <div style={{ marginTop: '0.75rem', fontSize: '0.65rem', color: 'var(--text-muted)', lineHeight: 1.5 }}>
          Inference runs in Ollama on this machine. Tools run as local MCP subprocesses. No cloud API calls.
        </div>
      </div>
    </aside>
  );
}
