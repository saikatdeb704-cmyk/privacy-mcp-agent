import React from 'react';
import { AlertTriangle } from 'lucide-react';

export default function GuardrailModal({ data, onApprove, onReject }) {
  if (!data) return null;

  return (
    <div className="modal-backdrop">
      <div className="guardrail-dialog" onClick={(e) => e.stopPropagation()}>
        {/* Header */}
        <div className="guardrail-dialog-header">
          <div className="guardrail-dialog-icon">
            <AlertTriangle size={22} />
          </div>
          <div>
            <div className="guardrail-dialog-title">⚠ Execution Halted</div>
            <div className="guardrail-dialog-subtitle">
              High-Risk Operation — Human Approval Required
            </div>
          </div>
        </div>

        {/* Body */}
        <div className="guardrail-dialog-body">
          <p>
            The agent is attempting a <strong>potentially destructive action</strong> on{' '}
            <strong>{data.server}</strong>. This operation has been classified as{' '}
            <span className="text-danger fw-600">HIGH RISK</span> by the HITL Guardrail Engine.
          </p>
          <p>
            Review the payload below and choose whether to approve or reject this execution.
          </p>

          <div className="guardrail-label">Target MCP Server → Tool</div>
          <div className="guardrail-code-block" style={{ color: 'var(--accent)', marginBottom: '1rem' }}>
            {data.server} → {data.tool}
          </div>

          <div className="guardrail-label">Exact Action Payload</div>
          <div className="guardrail-code-block" style={{ whiteSpace: 'pre-wrap' }}>
            {data.payload}
          </div>
        </div>

        {/* Actions */}
        <div className="guardrail-dialog-actions">
          <button id="guardrail-reject-btn" className="btn btn-ghost" onClick={onReject}>
            ✕ Reject Action
          </button>
          <button id="guardrail-approve-btn" className="btn btn-danger" onClick={onApprove}>
            ⚡ Approve Execution
          </button>
        </div>
      </div>
    </div>
  );
}
