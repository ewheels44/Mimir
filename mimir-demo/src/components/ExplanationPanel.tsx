import { Lightbulb, AlertTriangle, CheckCircle, Info } from 'lucide-react';
import { FlowStep } from '../data/flows';

interface ExplanationPanelProps {
  step: FlowStep;
  flowColor: string;
  stepIndex: number;
  totalSteps: number;
}

export function ExplanationPanel({ step, flowColor, stepIndex, totalSteps }: ExplanationPanelProps) {
  return (
    <div className="explanation-panel" role="region" aria-label="Step explanation">
      {/* Header with step label */}
      <div className="explanation-header" style={{ borderLeftColor: flowColor }}>
        <div className="explanation-header-content">
          <h3>{step.label}</h3>
          {step.sublabel && <span className="explanation-sublabel" style={{ color: flowColor }}>{step.sublabel}</span>}
        </div>
        <div className="explanation-badge" style={{ backgroundColor: `${flowColor}20`, color: flowColor }}>
          {step.icon}
        </div>
      </div>

      <div className="explanation-body">
        {/* What Happens */}
        <div className="explanation-section">
          <div className="section-icon" style={{ backgroundColor: `${flowColor}15` }}>
            <Info size={16} style={{ color: flowColor }} />
          </div>
          <div className="section-content">
            <h4 style={{ color: flowColor }}>What Happens</h4>
            <p className="explanation-text">{step.explanation}</p>
          </div>
        </div>

        {/* Why This Decision */}
        <div className="explanation-section">
          <div className="section-icon" style={{ backgroundColor: 'rgba(139, 92, 246, 0.12)' }}>
            <Lightbulb size={16} style={{ color: '#8b5cf6' }} />
          </div>
          <div className="section-content">
            <h4 style={{ color: '#8b5cf6' }}>Design Rationale</h4>
            <p className="explanation-text">{step.rationale}</p>
          </div>
        </div>

        {/* Key Metrics */}
        <div className="explanation-section">
          <div className="section-icon" style={{ backgroundColor: 'rgba(16, 185, 129, 0.12)' }}>
            <CheckCircle size={16} style={{ color: '#10b981' }} />
          </div>
          <div className="section-content">
            <h4 style={{ color: '#10b981' }}>Key Metrics</h4>
            <div className="metrics-grid">
              <div className="metric-item" style={{ animationDelay: '0.1s' }}>
                <span className="metric-label">Performance</span>
                <span className="metric-value" style={{ color: flowColor }}>{step.timing || 'N/A'}</span>
              </div>
              <div className="metric-item" style={{ animationDelay: '0.2s' }}>
                <span className="metric-label">State Size</span>
                <span className="metric-value">{Object.keys(step.state).length} vars</span>
              </div>
              <div className="metric-item" style={{ animationDelay: '0.3s' }}>
                <span className="metric-label">Step</span>
                <span className="metric-value">{stepIndex + 1}/{totalSteps}</span>
              </div>
            </div>
          </div>
        </div>

        {/* Risk Flags */}
        <div className="explanation-section">
          <div className="section-icon" style={{ backgroundColor: 'rgba(239, 68, 68, 0.1)' }}>
            <AlertTriangle size={16} style={{ color: '#ef4444' }} />
          </div>
          <div className="section-content">
            <h4 style={{ color: '#ef4444' }}>Risk Considerations</h4>
            <ul className="risk-list">
              {getRisksForStep(step)}
            </ul>
          </div>
        </div>
      </div>

      {/* Step metadata bar */}
      <div className="explanation-footer">
        <span className="step-id">Step ID: {step.id}</span>
        <span className="step-tags">
          {Object.keys(step.state).length > 0 && (
            <span className="tag" style={{ backgroundColor: `${flowColor}20`, color: flowColor }}>
              {Object.keys(step.state).length} state variables
            </span>
          )}
          {step.inputs && step.inputs.length > 0 && (
            <span className="tag" style={{ backgroundColor: 'rgba(99, 102, 241, 0.2)' }}>
              {step.inputs.length} inputs
            </span>
          )}
          {step.outputs && step.outputs.length > 0 && (
            <span className="tag" style={{ backgroundColor: 'rgba(16, 185, 129, 0.2)' }}>
              {step.outputs.length} outputs
            </span>
          )}
        </span>
      </div>
    </div>
  );
}

function getRisksForStep(step: FlowStep): JSX.Element[] {
  const risks: string[] = [];
  const stateKeys = Object.keys(step.state);

  if (stateKeys.includes('has_index') || stateKeys.includes('cache_hit')) {
    risks.push('Boolean dependency — if false, flow may bypass or fail');
  }
  if (stateKeys.includes('failure_count') || stateKeys.includes('circuit_state')) {
    risks.push('Circuit breaker state must be monitored to prevent cascading failures');
  }
  if (stateKeys.some(k => step.state[k].type === 'array' && k.includes('vector'))) {
    risks.push('High-dimensional vectors require consistent embedding model versions');
  }
  if (stateKeys.includes('results_truncated')) {
    risks.push('Truncation may discard relevant context');
  }
  if (!risks.length) {
    risks.push('Standard step — no elevated risk detected');
  }

  return risks.map((r, i) => <li key={i}>{r}</li>);
}