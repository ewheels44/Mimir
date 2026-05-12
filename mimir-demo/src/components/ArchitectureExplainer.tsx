import { useState, useCallback } from 'react';
import { architectureLayers, ArchitectureLayer, CodeExample, DependencyTrace } from '../data/architecture_explainer';

interface ArchitectureExplainerProps {
  plainEnglish?: boolean;
}

/* ─── Sub-components ───────────────────────────────────────────────────────── */

function CodeBlock({ example, plainEnglish }: { example: CodeExample; plainEnglish: boolean }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(example.code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [example.code]);

  return (
    <div className="code-example">
      <div className="code-example-header">
        <span className="code-example-title">{example.title}</span>
        <span className="code-example-file">{example.file}:{example.line}</span>
        <button
          className="code-copy-btn"
          onClick={handleCopy}
          title="Copy code"
        >
          {copied ? '✅' : '📋'}
        </button>
      </div>
      <pre className="code-block">
        <code>{example.code}</code>
      </pre>
      <p className="code-explanation">
        {plainEnglish ? example.plainExplanation : example.explanation}
      </p>
    </div>
  );
}

function DependencyTraceView({ trace }: { trace: DependencyTrace }) {
  const arrowColor = trace.type === 'imports' ? '#3b82f6' : trace.type === 'calls' ? '#10b981' : '#f59e0b';

  return (
    <div className="dep-trace" style={{ '--arrow-color': arrowColor } as React.CSSProperties}>
      <span className="dep-source">{trace.from}</span>
      <span className="dep-arrow" style={{ borderColor: `transparent transparent transparent ${arrowColor}` }}>
        {'⟶'}
      </span>
      <span className="dep-target">{trace.to}</span>
      <span className="dep-type" style={{ backgroundColor: `${arrowColor}20`, color: arrowColor }}>
        {trace.type}
      </span>
      <span className="dep-line">L{trace.line}</span>
    </div>
  );
}

function LayerSection({ layer, isOpen, onToggle, plainEnglish }: { layer: ArchitectureLayer; isOpen: boolean; onToggle: () => void; plainEnglish: boolean }) {
  return (
    <div className={`layer-section ${isOpen ? 'layer-open' : ''}`}>
      {/* Layer Header */}
      <button
        className="layer-header"
        onClick={onToggle}
        style={{ borderLeftColor: layer.color }}
      >
        <span className="layer-icon" style={{ color: layer.color }}>{layer.icon}</span>
        <div className="layer-header-text">
          <h3 style={{ color: layer.color }}>{layer.label}</h3>
          <span className="layer-subtitle">{plainEnglish ? layer.plainOverview : layer.overview}</span>
        </div>
        <span className={`layer-chevron ${isOpen ? 'open' : ''}`}>▼</span>
      </button>

      {/* Expanded Content */}
      {isOpen && (
        <div className="layer-content">
          {/* Sequence Flow */}
          {layer.sequence.length > 0 && (
            <div className="sequence-section">
              <h4 className="section-label">🗺️ How It Flows</h4>
              <div className="sequence-steps">
                {layer.sequence.map((step, i) => (
                  <div key={i} className="sequence-step">
                    <div className="step-number" style={{ backgroundColor: layer.color }}>
                      {i + 1}
                    </div>
                    <div className="step-details">
                      <span className="step-module">{step.module}</span>
                      <span className="step-action">
                        {plainEnglish ? step.plainAction : step.action}
                      </span>
                      <div className="step-io">
                        {step.inputs.length > 0 && (
                          <span className="io-tag in">
                            📥 {step.inputs.join(', ')}
                          </span>
                        )}
                        {step.outputs.length > 0 && (
                          <span className="io-tag out">
                            📤 {step.outputs.join(', ')}
                          </span>
                        )}
                      </div>
                    </div>
                  </div>
                ))}
              </div>
            </div>
          )}

          {/* Modules */}
          <div className="modules-section">
            <h4 className="section-label">🔧 Key Modules</h4>
            {layer.modules.map((mod, mi) => (
              <div key={mi} className="module-card">
                <div className="module-header">
                  <span className="module-name">{mod.title}</span>
                  <span className="module-file">📄 {mod.file}</span>
                </div>
                <p className="module-desc">
                  {plainEnglish ? mod.plainDescription : mod.description}
                </p>

                {/* Key Exports */}
                {mod.keyExports.length > 0 && (
                  <div className="module-exports">
                    <span className="export-label">Exports:</span>
                    {mod.keyExports.map((exp, ei) => (
                      <span key={ei} className="export-tag">{exp}</span>
                    ))}
                  </div>
                )}

                {/* Code Examples */}
                {mod.codeExamples.map((ex, ei) => (
                  <CodeBlock key={ei} example={ex} plainEnglish={plainEnglish} />
                ))}

                {/* Dependency Traces */}
                {mod.dependencyTraces.length > 0 && (
                  <div className="dep-traces">
                    <span className="dep-label">🔗 Dependencies:</span>
                    {mod.dependencyTraces.map((dt, di) => (
                      <DependencyTraceView key={di} trace={dt} />
                    ))}
                  </div>
                )}
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

/* ─── Main Component ───────────────────────────────────────────────────────── */

export function ArchitectureExplainer({ plainEnglish = false }: ArchitectureExplainerProps) {
  const [openLayers, setOpenLayers] = useState<Set<string>>(new Set());
  const [searchTerm, setSearchTerm] = useState('');

  const toggleLayer = useCallback((layerId: string) => {
    setOpenLayers(prev => {
      const next = new Set(prev);
      if (next.has(layerId)) {
        next.delete(layerId);
      } else {
        next.add(layerId);
      }
      return next;
    });
  }, []);

  const filteredLayers = architectureLayers.filter(layer => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return (
      layer.label.toLowerCase().includes(term) ||
      layer.modules.some(m =>
        m.title.toLowerCase().includes(term) ||
        m.description.toLowerCase().includes(term) ||
        m.plainDescription.toLowerCase().includes(term) ||
        m.codeExamples.some(ex =>
          ex.title.toLowerCase().includes(term) ||
          ex.code.toLowerCase().includes(term)
        )
      )
    );
  });

  return (
    <div className="architecture-explainer">
      {/* Search Bar */}
      <div className="explainer-search">
        <input
          type="text"
          placeholder="Search modules, code examples, dependencies..."
          value={searchTerm}
          onChange={(e) => setSearchTerm(e.target.value)}
          className="explainer-search-input"
        />
        <span className="explainer-search-count">
          {filteredLayers.length} / {architectureLayers.length} layers shown
        </span>
      </div>

      {/* Layer Sections */}
      <div className="layers-list">
        {filteredLayers.map(layer => (
          <LayerSection
            key={layer.id}
            layer={layer}
            isOpen={openLayers.has(layer.id)}
            onToggle={() => toggleLayer(layer.id)}
            plainEnglish={plainEnglish}
          />
        ))}
      </div>

      {/* Cross-Cutting Features */}
      <div className="cross-cutting-section">
        <h4 className="section-label">🌐 Cross-Cutting Features</h4>
        <div className="cross-cutting-grid">
          {[
            {
              title: 'Shared Indexes',
              file: 'shared_index.py',
              icon: '🌐',
              color: '#8b5cf6',
              description: 'Multiple projects can query pre-built indexes from a central location. Results are merged by score with TaggedNode attribution.',
              plainDesc: 'A shared library catalog that multiple projects can tap into.',
            },
            {
              title: 'SDK Docs Cache',
              file: 'sdk_cache.py',
              icon: '📚',
              color: '#ec4899',
              description: 'TTL-based cache (7-day default) for SDK docs fetched from Context7 API. Eliminates repeated API calls.',
              plainDesc: 'Remembers fetched docs so they don\'t need to be downloaded again.',
            },
            {
              title: 'Cost Metrics',
              file: 'metrics.py',
              icon: '📊',
              color: '#f59e0b',
              description: 'JSONL-based tracking of every query. Tracks tokens per component (embedding, LLM input/output) and calculates real costs vs. traditional baseline.',
              plainDesc: 'A receipt showing how much each search and query costs.',
            },
          ].map((feature, i) => (
            <div key={i} className="cross-cutting-card" style={{ borderTopColor: feature.color }}>
              <span className="cc-icon" style={{ color: feature.color }}>{feature.icon}</span>
              <span className="cc-title" style={{ color: feature.color }}>{feature.title}</span>
              <span className="cc-file">📄 {feature.file}</span>
              <p className="cc-desc">{plainEnglish ? feature.plainDesc : feature.description}</p>
            </div>
          ))}
        </div>
      </div>

      {/* File Dependency Map */}
      <div className="dep-map-section">
        <h4 className="section-label">🗺️ File Dependency Map</h4>
        <div className="dep-map-list">
          {[
            { file: 'config.py', importedBy: ['indexing.py', 'openspace_bridge.py', 'sdk_cache.py', 'shared_index.py', 'metrics.py', 'mcp_server_llamaindex.py'] },
            { file: 'indexing.py', imports: ['config.py'], importedBy: ['watcher.py', 'mcp_server_llamaindex.py'] },
            { file: 'knowledge_graph.py', imports: ['config.py', 'indexing.py'], importedBy: ['watcher.py'] },
            { file: 'openspace_bridge.py', imports: ['config.py'], importedBy: ['mcp_server_llamaindex.py'] },
            { file: 'mcp_server_llamaindex.py', imports: ['config.py', 'indexing.py', 'knowledge_graph.py', 'openspace_bridge.py', 'sdk_cache.py', 'shared_index.py', 'metrics.py', 'watcher.py'], importedBy: [] },
            { file: 'watcher.py', imports: ['indexing.py', 'knowledge_graph.py', 'config.py'], importedBy: ['mcp_server_llamaindex.py'] },
          ].map((dep, i) => (
            <div key={i} className="dep-map-row">
              <span className="dep-file">{dep.file}</span>
              {dep.imports && dep.imports.length > 0 && (
                <span className="dep-arrows">
                  {dep.imports.map((imp, j) => (
                    <span key={j} className="dep-import">← {imp}</span>
                  ))}
                </span>
              )}
              {dep.importedBy.length > 0 && (
                <span className="dep-arrows">
                  {dep.importedBy.map((parent, j) => (
                    <span key={j} className="dep-usedby">→ {parent}</span>
                  ))}
                </span>
              )}
            </div>
          ))}
        </div>
        <div className="dep-map-legend">
          <span className="dep-legend-item">← imports</span>
          <span className="dep-legend-item">→ imported by</span>
        </div>
      </div>
    </div>
  );
}