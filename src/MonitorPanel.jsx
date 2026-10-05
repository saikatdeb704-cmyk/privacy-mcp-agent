import React, { useRef, useEffect } from 'react';
import { Activity, Clock, Zap, CheckCircle2, XCircle, Shield } from 'lucide-react';

export default function MonitorPanel({ logs, stats }) {
  const scrollRef = useRef(null);

  useEffect(() => {
    if (scrollRef.current) {
      scrollRef.current.scrollTop = scrollRef.current.scrollHeight;
    }
  }, [logs]);

  return (
    <div className="monitor-panel">
      <div className="monitor-header">
        <Activity size={16} color="var(--accent)" />
        <div className="monitor-header-title">Tool Call Monitor</div>
        <div className="monitor-header-count">{logs.length} events</div>
      </div>

      <div className="monitor-scroll" ref={scrollRef}>
        {logs.length === 0 ? (
          <div style={{
            textAlign: 'center',
            padding: '2rem 1rem',
            color: 'var(--text-muted)',
            fontSize: '0.78rem'
          }}>
            <Shield size={28} style={{ marginBottom: '0.75rem', opacity: 0.3 }} />
            <div>No MCP calls yet.</div>
            <div style={{ marginTop: '0.25rem' }}>Events will appear here as the agent executes tool calls.</div>
          </div>
        ) : (
          logs.map((log) => (
            <div key={log.id} className="log-entry">
              <div className="log-entry-header">
                <div className="log-entry-tool">{log.toolName}</div>
                <div className="log-entry-time">{log.timestamp}</div>
              </div>
              <div className="log-entry-detail">{log.detail}</div>
              <div className="log-entry-meta">
                <span
                  className="log-meta-tag"
                  style={{
                    background: log.risk === 'LOW' ? 'var(--success-muted)' : log.risk === 'MEDIUM' ? 'var(--warning-muted)' : 'var(--danger-muted)',
                    color: log.risk === 'LOW' ? 'var(--success)' : log.risk === 'MEDIUM' ? 'var(--warning)' : 'var(--danger)',
                  }}
                >
                  {log.risk}
                </span>
                <span
                  className="log-meta-tag"
                  style={{
                    background: log.status === 'approved' ? 'var(--success-muted)' : log.status === 'denied' ? 'var(--danger-muted)' : log.status === 'pending' ? 'var(--warning-muted)' : 'var(--info-muted)',
                    color: log.status === 'approved' ? 'var(--success)' : log.status === 'denied' ? 'var(--danger)' : log.status === 'pending' ? 'var(--warning)' : 'var(--info)',
                  }}
                >
                  {log.status === 'approved' ? '✓ approved' : log.status === 'denied' ? '✕ denied' : log.status === 'pending' ? '⏸ awaiting approval' : '⟳ auto'}
                </span>
                {log.latency && (
                  <span className="log-meta-tag" style={{ background: 'var(--bg-panel)', color: 'var(--text-muted)' }}>
                    {log.latency}
                  </span>
                )}
              </div>
            </div>
          ))
        )}
      </div>

      <div className="monitor-stats">
        <div className="monitor-stat">
          <div className="monitor-stat-value">{stats.totalCalls}</div>
          <div className="monitor-stat-label">Total Calls</div>
        </div>
        <div className="monitor-stat">
          <div className="monitor-stat-value" style={{ color: 'var(--success)' }}>{stats.autoApproved}</div>
          <div className="monitor-stat-label">Auto-Approved</div>
        </div>
        <div className="monitor-stat">
          <div className="monitor-stat-value" style={{ color: 'var(--danger)' }}>{stats.blocked}</div>
          <div className="monitor-stat-label">Blocked</div>
        </div>
        <div className="monitor-stat">
          <div className="monitor-stat-value" style={{ color: 'var(--warning)' }}>{stats.avgLatency}</div>
          <div className="monitor-stat-label">Avg Latency</div>
        </div>
      </div>
    </div>
  );
}
