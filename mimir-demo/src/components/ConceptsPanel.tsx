import { useState } from 'react';
import { conceptQuickIndex, concepts, type Concept } from '../data/concepts';
import { allFlows } from '../data/flows';

interface ConceptsPanelProps {
  activeFlowId: string;
}

export function ConceptsPanel({ activeFlowId }: ConceptsPanelProps) {
  const [searchTerm, setSearchTerm] = useState('');
  const [expandedId, setExpandedId] = useState<string | null>(null);

  // Show concepts relevant to the active flow, or all if on index page
  const flowConceptIds = conceptQuickIndex[activeFlowId] || concepts.map(c => c.id);
  const filteredConcepts = concepts.filter(c => {
    if (!flowConceptIds.includes(c.id)) return false;
    if (!searchTerm) return true;
    return (
      c.title.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.shortSummary.toLowerCase().includes(searchTerm.toLowerCase()) ||
      c.explanation.toLowerCase().includes(searchTerm.toLowerCase())
    );
  });

  return (
    <div className="concepts-panel" role="complementary" aria-label="Concept glossary">
      {/* Header */}
      <div className="concepts-header">
        <h3>
          <span className="concepts-icon">📚</span>
          Concept Glossary
        </h3>
        <span className="concepts-count">{filteredConcepts.length} concepts</span>
      </div>

      {/* Flow context badge */}
      {activeFlowId !== 'index' && (
        <div className="flow-context-badge">
          Showing concepts for: <strong>{allFlows.find(f => f.id === activeFlowId)?.title || 'All'}</strong>
        </div>
      )}

      {/* Search */}
      <div className="concepts-search">
        <input
          type="text"
          placeholder="Search concepts..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="concepts-search-input"
        />
        {searchTerm && (
          <button
            className="concepts-search-clear"
            onClick={() => setSearchTerm('')}
            title="Clear search"
          >
            ✕
          </button>
        )}
      </div>

      {/* Concept cards */}
      <div className="concepts-list">
        {filteredConcepts.length === 0 ? (
          <div className="concepts-empty">
            🤔 No concepts match "<strong>{searchTerm}</strong>"
          </div>
        ) : (
          filteredConcepts.map((concept) => (
            <ConceptCard
              key={concept.id}
              concept={concept}
              isExpanded={expandedId === concept.id}
              onToggle={() => setExpandedId(expandedId === concept.id ? null : concept.id)}
            />
          ))
        )}
      </div>

      {/* Legend at the bottom */}
      <div className="concepts-legend">
        <div className="legend-item">
          <span className="legend-badge tech">TECH</span>
          <span className="legend-label">Technical explanation</span>
        </div>
        <div className="legend-item">
          <span className="legend-badge eli5">ELI5</span>
          <span className="legend-label">Plain English analogy</span>
        </div>
      </div>
    </div>
  );
}

function ConceptCard({
  concept,
  isExpanded,
  onToggle,
}: {
  concept: Concept;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  return (
    <div
      className={`concept-card ${isExpanded ? 'expanded' : ''}`}
      style={{ '--card-accent': concept.icon === '🗄️' ? '#3b82f6' : '#8b5cf6' } as React.CSSProperties}
    >
      {/* Clickable header */}
      <div className="concept-header" onClick={onToggle}>
        <span className="concept-icon">{concept.icon}</span>
        <div className="concept-title-area">
          <span className="concept-title">{concept.title}</span>
          <span className="concept-summary">{concept.shortSummary}</span>
        </div>
        <span className={`concept-chevron ${isExpanded ? 'open' : ''}`}>▼</span>
      </div>

      {/* Expanded content */}
      {isExpanded && (
        <div className="concept-body">
          {/* Technical explanation */}
          <div className="concept-section">
            <div className="concept-section-header tech">
              <span className="section-badge">TECH</span>
              <span>Technical Explanation</span>
            </div>
            <p className="concept-text">{concept.explanation}</p>
          </div>

          {/* Plain English */}
          <div className="concept-section">
            <div className="concept-section-header eli5">
              <span className="section-badge eli5">ELI5</span>
              <span>Explain Like I'm 5</span>
            </div>
            <p className="concept-text eli5-text">{concept.plainEnglish}</p>
          </div>

          {/* Examples */}
          {concept.examples && concept.examples.length > 0 && (
            <div className="concept-section">
              <div className="concept-section-header">
                <span>🔮 Real-World Analogies</span>
              </div>
              <ul className="concept-examples">
                {concept.examples.map((ex, i) => (
                  <li key={i}>{ex}</li>
                ))}
              </ul>
            </div>
          )}

          {/* Related flows */}
          <div className="concept-related">
            <span className="related-label">Used in:</span>
            <div className="related-flows">
              {concept.relatedFlows.map((flowId) => {
                const flow = allFlows.find((f) => f.id === flowId);
                return flow ? (
                  <span key={flowId} className="related-flow-tag" style={{ backgroundColor: `${flow.color}20`, color: flow.color }}>
                    {flow.icon} {flow.title.split(' ').slice(0, 2).join(' ')}
                  </span>
                ) : null;
              })}
            </div>
          </div>
        </div>
      )}
    </div>
  );
}