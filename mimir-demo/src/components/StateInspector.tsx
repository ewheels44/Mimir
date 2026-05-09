import { Database, TrendingUp, AlertCircle, Sparkles } from 'lucide-react';
import { FlowStep } from '../data/flows';

interface StateInspectorProps {
  step: FlowStep;
  stepIndex: number;
  totalSteps: number;
  flowColor: string;
}

export function StateInspector({ step, stepIndex, totalSteps, flowColor }: StateInspectorProps) {
  const entries = Object.entries(step.state);

  const getTypeColor = (type: string) => {
    switch (type) {
      case 'string': return '#10b981';
      case 'number': return '#f59e0b';
      case 'boolean': return '#3b82f6';
      case 'array': return '#ec4899';
      case 'object': return '#8b5cf6';
      default: return '#a0a0b0';
    }
  };

  const getTypeIcon = (type: string) => {
    switch (type) {
      case 'string': return '🔤';
      case 'number': return '🔢';
      case 'boolean': return '🔲';
      case 'array': return '📦';
      case 'object': return '📋';
      default: return '📌';
    }
  };

  const formatValue = (value: string | number | boolean) => {
    if (typeof value === 'boolean') {
      return value ? '✅ true' : '❌ false';
    }
    return String(value);
  };

  return (
    <div className="state-inspector" role="complementary" aria-label="State inspector">
      {/* Header */}
      <div className="state-header">
        <h3>
          <span className="state-icon-wrapper" style={{ backgroundColor: `${flowColor}20` }}>
            <Database size={18} style={{ color: flowColor }} />
          </span>
          State Inspector
        </h3>
        <div className="state-progress">
          <span className="state-step-indicator" style={{ color: flowColor }}>
            Step {stepIndex + 1}
          </span>
          <span className="state-step-sep">/</span>
          <span className="state-total">{totalSteps}</span>
          <div className="state-mini-progress">
            <div
              className="state-mini-fill"
              style={{
                width: `${((stepIndex + 1) / totalSteps) * 100}%`,
                backgroundColor: flowColor,
              }}
            />
          </div>
        </div>
      </div>

      {/* Stats Summary */}
      <div className="state-stats-row">
        <div className="state-stat-card">
          <Sparkles size={14} style={{ color: '#f59e0b' }} />
          <span className="state-stat-value">{entries.length}</span>
          <span className="state-stat-label">Variables</span>
        </div>
        <div className="state-stat-card">
          <TrendingUp size={14} style={{ color: '#10b981' }} />
          <span className="state-stat-value">{entries.filter(([, v]) => v.type === 'number').length}</span>
          <span className="state-stat-label">Numbers</span>
        </div>
        <div className="state-stat-card">
          <AlertCircle size={14} style={{ color: '#ef4444' }} />
          <span className="state-stat-value">{entries.filter(([, v]) => v.type === 'boolean').length}</span>
          <span className="state-stat-label">Booleans</span>
        </div>
      </div>

      {/* State Panel */}
      <div className="state-panel">
        {entries.map(([key, data], index) => (
          <div
            key={key}
            className="state-item"
            style={{
              animation: `stateFadeIn 0.4s ease ${index * 0.08}s both`,
              '--state-accent': getTypeColor(data.type),
            } as React.CSSProperties}
          >
            <div className="state-item-left">
              <span className="state-type-icon">{getTypeIcon(data.type)}</span>
              <span className="state-key">{key}</span>
            </div>
            <div className="state-item-right">
              <span
                className={`state-value state-value-${data.type}`}
                title={typeof data.value === 'string' ? data.value : String(data.value)}
              >
                {formatValue(data.value)}
              </span>
              <span className="state-type-badge" style={{ color: getTypeColor(data.type) }}>
                {data.type}
              </span>
            </div>
          </div>
        ))}
      </div>

      {/* Legend */}
      <div className="state-legend">
        <span className="legend-item">
          <span className="legend-dot" style={{ backgroundColor: '#10b981' }} /> string
        </span>
        <span className="legend-item">
          <span className="legend-dot" style={{ backgroundColor: '#f59e0b' }} /> number
        </span>
        <span className="legend-item">
          <span className="legend-dot" style={{ backgroundColor: '#3b82f6' }} /> boolean
        </span>
        <span className="legend-item">
          <span className="legend-dot" style={{ backgroundColor: '#ec4899' }} /> array
        </span>
        <span className="legend-item">
          <span className="legend-dot" style={{ backgroundColor: '#8b5cf6' }} /> object
        </span>
      </div>
    </div>
  );
}