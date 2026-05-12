import { Database, TrendingUp, AlertCircle, Sparkles } from 'lucide-react';
import { FlowStep } from '../data/flows';

interface StateInspectorProps {
  step: FlowStep;
  stepIndex: number;
  totalSteps: number;
  flowColor: string;
  plainEnglish?: boolean;
}

function getPlainKey(key: string): string {
  const map: Record<string, string> = {
    'has_index': 'Index exists?',
    'source_files': 'Indexed files',
    'document_count': 'Total documents',
    'project_root': 'Project folder',
    'index_freshness': 'Last updated',
    'thought_process': 'Thinking',
    'tool_selected': 'Tool chosen',
    'args': 'Parameters',
    'reasoning': 'Why this tool?',
    'neighbors_found': 'Connected nodes found',
    'top_connections': 'Key connections',
    'conversation_messages': 'Messages so far',
    'current_loop': 'Current loop',
    'needs_more_info': 'Need more info?',
    'has_answer': 'Has answer?',
    'sources_cited': 'Sources cited',
    'confidence': 'Confidence',
    'total_tokens_used': 'Tokens used',
    'loops_completed': 'Loops done',
    'nodes_explored': 'Nodes explored',
    'failure_count': 'Failures so far',
    'threshold': 'Failure limit',
    'circuit_state': 'Circuit state',
    'reset_after': 'Reset after',
    'cache_max_size': 'Max cached answers',
    'ttl_seconds': 'Cache freshness (seconds)',
    'cache_hit': 'Found in cache?',
    'current_size': 'Cached answers now',
    'new_vectors_inserted': 'New vectors added',
    'total_vectors_in_store': 'Total vectors',
    'storage_size': 'Storage size',
    'persisted_to_disk': 'Saved to disk?',
    'last_updated': 'Last saved',
    'indexed_files': 'Total files indexed',
    'model': 'Model used',
    'dimensions': 'Vector size',
    'embeddings_generated': 'Embeddings created',
    'api_cost': 'API cost',
    'query_vector': 'Query vector',
    'candidates_scanned': 'Vectors scanned',
    'similarity_scores': 'Relevance scores',
    'retrieved_docs': 'Documents found',
    'similarity_threshold': 'Minimum relevance',
    'context_length': 'Context size',
    'sources': 'Source files',
    'format': 'Output format',
    'token_budget': 'Token budget',
    'query': 'User query',
    'results_count': 'Results returned',
    'freshness_score': 'Freshness score',
    'freshness_label': 'Freshness label',
    'blocked_patterns_found': 'Secrets found',
    'redacted_content': 'Redactions made',
    'safe_results': 'Safe results',
    'filtered_out_files': 'Blocked files',
    'results_truncated': 'Results trimmed',
    'context_ready': 'Context prepared?',
    'max_context_tokens': 'Max context tokens',
    'prompt_tokens': 'Prompt tokens',
    'completion_tokens': 'Completion tokens',
    'total_latency': 'Total time',
  };
  return map[key] || key;
}

export function StateInspector({ step, stepIndex, totalSteps, flowColor, plainEnglish = false }: StateInspectorProps) {
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
        {entries.map(([key, data], index) => {
          const plainKey = plainEnglish ? getPlainKey(key) : key;
          return (
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
                <span className="state-key">{plainKey}</span>
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
          );
        })}
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