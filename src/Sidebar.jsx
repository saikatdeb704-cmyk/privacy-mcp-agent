import React from 'react';
import { ShieldCheck, Cpu, Terminal, Database, Server, Cloud, Wifi, WifiOff, Lock, Globe } from 'lucide-react';

const SERVER_ICONS = { 'filesystem-mcp': Terminal, 'sqlite-mcp': Database };
const formatSize = (bytes) => (bytes ? `${(bytes / 1e9).toFixed(1)} GB` : '');

export default function Sidebar({ health, backendOnline, mode, activeEngine, localModel, onLocalModelChange }) {
  const cloud = health?.cloud;
  const local = health?.local;
  const servers = health?.servers ?? [];
  const usingLocal = activeEngine === 'local';

  const cloudStatus = !cloud?.configured
    ? { text: 'No API key configured', cls: 'offline' }
    : !health?.internet
      ? { text: 'No internet connection', cls: 'warning' }
      : { text: 'Connected', cls: 'online' };

  const localStatus = health?.hosted
    ? { text: 'Available on your PC only', cls: 'offline' }
    : local?.ready
      ? { text: `${local.models.length} model${local.models.length > 1 ? 's' : ''} installed`, cls: 'online' }
      : { text: local?.error || 'Not running', cls: 'offline' };

  return (
    <aside className="sidebar">
      <div className="sidebar-logo">
        <div className="sidebar-logo-icon">
          <ShieldCheck size={20} />
        </div>
        <div>
          <div className="sidebar-logo-text">Privacy MCP Agent</div>
          <div className="sidebar-logo-sub">
            <span className={`dot ${backendOnline ? 'online' : 'offline'}`} />
            {backendOnline ? 'Agent server online' : 'Agent server offline'}
          </div>
        </div>
      </div>

      {/* Engines */}
      <div className="sidebar-section">
        <div className="sidebar-section-title">AI Engines</div>

        <div className={`engine-card ${activeEngine === 'cloud' ? 'active' : ''} ${mode === 'local' ? 'dimmed' : ''}`}>
          <div className="engine-card-head">
            <div className="engine-card-icon cloud"><Cloud size={15} /></div>
            <div className="engine-card-title">
              <div>Online · {cloud?.provider || 'Cloud'}</div>
              <div className="engine-card-sub">{cloud?.model || 'not configured'}</div>
            </div>
            {activeEngine === 'cloud' && <span className="engine-active-tag">in use</span>}
          </div>
          <div className={`engine-status ${cloudStatus.cls}`}>
            {health?.internet ? <Wifi size={11} /> : <WifiOff size={11} />}
            {cloudStatus.text}
          </div>
        </div>

        <div className={`engine-card ${usingLocal ? 'active' : ''} ${mode === 'online' ? 'dimmed' : ''}`}>
          <div className="engine-card-head">
            <div className="engine-card-icon local"><Cpu size={15} /></div>
            <div className="engine-card-title">
              <div>Local · Ollama</div>
              <div className="engine-card-sub">{localModel || 'no model'}</div>
            </div>
            {usingLocal && <span className="engine-active-tag">in use</span>}
          </div>
          <div className={`engine-status ${localStatus.cls}`}>
            <Lock size={11} />
            {localStatus.text}
          </div>
          {local?.models?.length > 1 && (
            <div className="engine-models">
              {local.models.map((m) => (
                <button
                  key={m.name}
                  id={`model-${m.name.replace(/[^a-z0-9]/gi, '-')}`}
                  className={`engine-model ${localModel === m.name ? 'active' : ''}`}
                  onClick={() => onLocalModelChange(m.name)}
                  title={formatSize(m.size)}
                >
                  {m.name.replace(':latest', '')}
                </button>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* MCP Servers */}
      <div className="sidebar-section">
        <div className="sidebar-section-title">MCP Servers</div>
        {servers.length === 0 && (
          <div className="sidebar-item">
            <div className="sidebar-item-icon"><Server size={16} /></div>
            <div className="sidebar-item-label">Waiting for agent server…</div>
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
                <div className="engine-card-sub">
                  {s.online ? `${s.tools.length} tools · stdio` : 'failed to start'}
                </div>
              </div>
              <div className={`status-indicator ${s.online ? 'online' : 'offline'}`} />
            </div>
          );
        })}
      </div>

      <div className="sidebar-footer">
        <div className={`privacy-badge ${usingLocal ? 'local' : 'cloud'}`}>
          {usingLocal ? <Lock size={14} /> : <Globe size={14} />}
          {usingLocal ? 'Private · on-device' : activeEngine === 'cloud' ? 'Online · cloud model' : 'No engine available'}
        </div>
        <div className="sidebar-footnote">
          {usingLocal
            ? 'Prompts and data never leave this machine. Tools run as local MCP subprocesses.'
            : 'Prompts and tool results are sent to the cloud model. Tools still run on the agent server. Switch to Local for full privacy.'}
        </div>
      </div>
    </aside>
  );
}
