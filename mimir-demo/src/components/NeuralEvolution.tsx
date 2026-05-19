import { useState, useCallback, useEffect, useRef } from 'react';
import { neuralLayer, neuralCodeExamples, neuralDependencyTraces, neuralAnimations, savingsData } from '../data/neural_evolution';
import { CodeExample, DependencyTrace } from '../data/architecture_explainer';

// ─── Sub-components (follows ArchitectureExplainer pattern) ─────────

function CodeBlock({ example, plainEnglish }: { example: CodeExample; plainEnglish: boolean }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(example.code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [example.code]);

  return (
    <div className="code-example" style={{ animation: `fadeIn 500ms cubic-bezier(0.16, 1, 0.3, 1)` }}>
      <div className="code-example-header">
        <span className="code-example-title">{example.title}</span>
        <span className="code-example-file">{example.file}:{example.line}</span>
        <button className="code-copy-btn" onClick={handleCopy} title="Copy code">
          {copied ? '✅' : '📋'}
        </button>
      </div>
      <pre className="code-block"><code>{example.code}</code></pre>
      <p className="code-explanation">
        {plainEnglish ? example.plainExplanation : example.explanation}
      </p>
    </div>
  );
}

function DependencyTraceView({ trace }: { trace: DependencyTrace }) {
  const arrowColor = 
    trace.type === 'imports' ? '#3b82f6' : 
    trace.type === 'calls' ? '#10b981' : '#f59e0b';

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

// ─── Neural Network Visualization (animated!) ──────────────────

function NeuralNetworkViz() {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [isVisible, setIsVisible] = useState(false);
  const [pulsePhase, setPulsePhase] = useState(0);

  // Intersection observer for trigger
  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.5 }
    );
    if (canvasRef.current) observer.observe(canvasRef.current);
    return () => observer.disconnect();
  }, []);

  // Animation loop
  useEffect(() => {
    if (!isVisible) return;
    const interval = setInterval(() => {
      setPulsePhase(prev => (prev + 0.02) % (2 * Math.PI));
    }, 16); // ~60fps
    return () => clearInterval(interval);
  }, [isVisible]);

  // Draw network
  useEffect(() => {
    if (!isVisible || !canvasRef.current) return;
    const canvas = canvasRef.current;
    const ctx = canvas.getContext('2d');
    if (!ctx) return;

    canvas.width = canvas.offsetWidth;
    canvas.height = canvas.offsetHeight;

    // Network architecture
    const layers = [
      { neurons: 10, label: 'Input (10 features)' },
      { neurons: 8, label: 'Hidden (ReLU)' },
      { neurons: 2, label: 'Output (softmax)' },
    ];

    const neurons: { x: number; y: number; layer: number }[] = [];
    const connections: { from: typeof neurons[0]; to: typeof neurons[0]; weight: number }[] = [];

    // Create neurons
    layers.forEach((layer, layerIdx) => {
      const x = (layerIdx + 1) * canvas.width / (layers.length + 1);
      const spacing = canvas.height / (layer.neurons + 1);

      for (let i = 0; i < layer.neurons; i++) {
        const y = (i + 1) * spacing;
        neurons.push({ x, y, layer: layerIdx });
      }
    });

    // Create connections
    for (let i = 0; i < neurons.length; i++) {
      for (let j = i + 1; j < neurons.length; j++) {
        if (neurons[i].layer === neurons[j].layer - 1) {
          connections.push({
            from: neurons[i],
            to: neurons[j],
            weight: Math.sin(i * 1.618 + j) * 0.5 + 0.5,
          });
        }
      }
    }

    // Animation
    const animate = () => {
      ctx.clearRect(0, 0, canvas.width, canvas.height);

      // Draw connections
      connections.forEach((conn, idx) => {
        const alpha = 0.1 + 0.3 * Math.sin(pulsePhase + conn.weight * 10);
        ctx.strokeStyle = `rgba(168, 85, 247, ${alpha})`;
        ctx.lineWidth = 1 + conn.weight * 2;
        ctx.beginPath();
        ctx.moveTo(conn.from.x, conn.from.y);
        ctx.lineTo(conn.to.x, conn.to.y);
        ctx.stroke();

        // Animate signal
        const progress = ((pulsePhase * 0.5 + conn.weight) % 1);
        const sx = conn.from.x + (conn.to.x - conn.from.x) * progress;
        const sy = conn.from.y + (conn.to.y - conn.from.y) * progress;
        ctx.fillStyle = '#a855f7';
        ctx.beginPath();
        ctx.arc(sx, sy, 3, 0, Math.PI * 2);
        ctx.fill();
      });

      // Draw neurons
      neurons.forEach((neuron, idx) => {
        const pulse = Math.sin(pulsePhase * 2 + idx * 0.5) * 0.3 + 0.7;

        // Glow
        const gradient = ctx.createRadialGradient(
          neuron.x, neuron.y, 0,
          neuron.x, neuron.y, 20
        );
        gradient.addColorStop(0, `rgba(168, 85, 247, ${0.5 * pulse})`);
        gradient.addColorStop(1, 'rgba(168, 85, 247, 0)');
        ctx.fillStyle = gradient;
        ctx.beginPath();
        ctx.arc(neuron.x, neuron.y, 20, 0, Math.PI * 2);
        ctx.fill();

        // Neuron body
        ctx.fillStyle = neuron.layer === 0 ? '#6366f1' : neuron.layer === 1 ? '#a855f7' : '#ec4899';
        ctx.beginPath();
        ctx.arc(neuron.x, neuron.y, 8, 0, Math.PI * 2);
        ctx.fill();

        // Label
        if (neuron.layer === 0 && idx < 3) {
          ctx.fillStyle = '#8892b0';
          ctx.font = '10px Arial';
          ctx.fillText('●', neuron.x - 3, neuron.y - 15);
        }
      });

      // Layer labels
      ctx.fillStyle = '#8892b0';
      ctx.font = '12px Arial';
      layers.forEach((layer, idx) => {
        const x = (idx + 1) * canvas.width / (layers.length + 1);
        ctx.fillText(layer.label, x - 40, canvas.height - 20);
      });
    };

    animate();
  }, [isVisible, pulsePhase]);

  return (
    <div className="network-viz-container">
      <h4 className="section-label">🧠 Live Neural Network</h4>
      <canvas 
        ref={canvasRef} 
        className="network-canvas"
        style={{ 
          width: '100%', 
          height: '400px', 
          background: 'rgba(0, 0, 0, 0.3)', 
          borderRadius: '10px',
          opacity: isVisible ? 1 : 0,
          transform: isVisible ? 'translateY(0)' : 'translateY(20px)',
          transition: 'all 800ms cubic-bezier(0.16, 1, 0.3, 1)',
        }}
      />
      <p className="viz-caption">
        {neuralAnimations.networkVisualization.feel}
      </p>
    </div>
  );
}

// ─── Cost Calculator ──────────────────────────────────────

function CostCalculator() {
  const [queriesPerMonth, setQueriesPerMonth] = useState(10000);
  const [isVisible, setIsVisible] = useState(false);
  const [displaySavings, setDisplaySavings] = useState(0);

  const llmCost = queriesPerMonth * savingsData.llmCostPerQuery;
  const neuralCost = queriesPerMonth * savingsData.neuralCostPerQuery;
  const annualSavings = (llmCost - neuralCost) * 12;

  // Animate on scroll
  useEffect(() => {
    const observer = new IntersectionObserver(
      ([entry]) => {
        if (entry.isIntersecting) {
          setIsVisible(true);
          observer.disconnect();
        }
      },
      { threshold: 0.5 }
    );
    
    const el = document.querySelector('.cost-calculator');
    if (el) observer.observe(el);
    return () => observer.disconnect();
  }, []);

  // Animate savings counter
  useEffect(() => {
    if (!isVisible) return;
    const target = annualSavings;
    const duration = 2000; // 2 seconds
    const steps = 60;
    const increment = target / steps;
    let current = 0;
    let step = 0;

    const interval = setInterval(() => {
      step++;
      current += increment;
      if (step >= steps) {
        current = target;
        clearInterval(interval);
      }
      setDisplaySavings(Math.round(current * 100) / 100);
    }, duration / steps);

    return () => clearInterval(interval);
  }, [isVisible, annualSavings]);

  return (
    <div 
      className="cost-calculator"
      style={{
        opacity: isVisible ? 1 : 0,
        transform: isVisible ? 'translateY(0)' : 'translateY(-10px)',
        transition: 'all 500ms cubic-bezier(0.16, 1, 0.3, 1)',
      }}
    >
      <h4 className="section-label">💰 Cost Calculator</h4>
      
      <div className="cost-input-section">
        <label>Queries per month:</label>
        <input 
          type="range" 
          min="100" 
          max="100000" 
          step="100"
          value={queriesPerMonth}
          onChange={(e) => setQueriesPerMonth(Number(e.target.value))}
          className="cost-slider"
        />
        <span className="cost-value">{queriesPerMonth.toLocaleString()}</span>
      </div>

      <div className="cost-comparison">
        <div className="cost-box old">
          <h5>BEFORE (LLM)</h5>
          <div className="cost-amount">${llmCost.toFixed(2)}/month</div>
          <small>gpt-3.5-turbo</small>
        </div>
        <div className="cost-box new">
          <h5>AFTER (Neural)</h5>
          <div className="cost-amount">${neuralCost.toFixed(4)}/month</div>
          <small>local inference</small>
        </div>
      </div>

      <div className="savings-badge">
        <strong>{savingsData.savingsPercentage}%</strong> COST REDUCTION!
      </div>

      <div className="annual-savings">
        <span>Estimated Annual Savings: </span>
        <span className="savings-amount">${displaySavings.toLocaleString()}</span>
      </div>
    </div>
  );
}

// ─── Interactive Demo ──────────────────────────────────────

function InteractiveDemo() {
  const [query, setQuery] = useState('How does auth connect to database?');
  const [result, setResult] = useState<{ label: string; confidence: number } | null>(null);
  const [isHovered, setIsHovered] = useState(false);

  const classifyQuery = () => {
    // Simulate neural classification
    const structuralKeywords = ['connect', 'path', 'how does', 'link', 'depend'];
    const semanticKeywords = ['how does it work', 'what is', 'explain'];
    
    const queryLower = query.toLowerCase();
    let structScore = structuralKeywords.filter(k => queryLower.includes(k)).length;
    let semScore = semanticKeywords.filter(k => queryLower.includes(k)).length;
    
    // Simple simulation
    if (queryLower.includes('connect') || queryLower.includes('path')) {
      setResult({ label: 'structural', confidence: 0.95 });
    } else if (queryLower.includes('work') || queryLower.includes('purpose')) {
      setResult({ label: 'semantic', confidence: 0.92 });
    } else if (structScore > semScore) {
      setResult({ label: 'structural', confidence: 0.7 + structScore * 0.1 });
    } else {
      setResult({ label: 'semantic', confidence: 0.7 + semScore * 0.1 });
    }
  };

  return (
    <div 
      className="interactive-demo"
      onMouseEnter={() => setIsHovered(true)}
      onMouseLeave={() => setIsHovered(false)}
      style={{
        transform: isHovered ? 'scale(1.02)' : 'scale(1)',
        boxShadow: isHovered 
          ? '0 10px 30px rgba(168, 85, 247, 0.4)' 
          : '0 0 0 rgba(168, 85, 247, 0)',
        transition: 'all 300ms cubic-bezier(0.16, 1, 0.3, 1)',
      }}
    >
      <h4 className="section-label">🎮 Interactive Demo</h4>
      <div className="demo-input-section">
        <input 
          type="text" 
          className="demo-input"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          placeholder="Type a query..."
        />
        <button className="demo-btn" onClick={classifyQuery}>
          Classify 🚀
        </button>
      </div>

      {result && (
        <div className="demo-result">
          <p><strong>Classification:</strong> <span style={{ color: '#a855f7' }}>{result.label}</span></p>
          <p><strong>Confidence:</strong></p>
          <div className="confidence-bar">
            <div 
              className="confidence-fill" 
              style={{ 
                width: `${result.confidence * 100}%`,
                transition: 'width 1s cubic-bezier(0.16, 1, 0.3, 1)',
              }}
            >
              {(result.confidence * 100).toFixed(0)}%
            </div>
          </div>
        </div>
      )}

      <div className="demo-suggestions">
        <p><strong>Try:</strong></p>
        <button onClick={() => setQuery('How does auth connect to db?')}>
          "How does auth connect to db?"
        </button>
        <button onClick={() => setQuery('What is the purpose of config?')}>
          "What is the purpose of config?"
        </button>
      </div>
    </div>
  );
}

// ─── Main Component ──────────────────────────────────────

interface NeuralEvolutionProps {
  plainEnglish?: boolean;
}

export function NeuralEvolution({ plainEnglish = false }: NeuralEvolutionProps) {
  const [expandedModule, setExpandedModule] = useState<number>(0);

  return (
    <div className="neural-evolution">
      <div className="hero-section">
        <h2 style={{ color: neuralLayer.color }}>🧠 {neuralLayer.label}</h2>
        <p className="hero-subtitle">
          {plainEnglish ? neuralLayer.plainOverview : neuralLayer.overview}
        </p>
        <div className="hero-stats">
          <div className="stat-card">
            <div className="stat-value">1.1KB</div>
            <div className="stat-label">Model Size</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">&lt;1ms</div>
            <div className="stat-label">Inference Time</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">99.9%</div>
            <div className="stat-label">Cost Reduction</div>
          </div>
          <div className="stat-card">
            <div className="stat-value">100%</div>
            <div className="stat-label">Training Accuracy</div>
          </div>
        </div>
      </div>

      {/* Neural Network Visualization */}
      <div style={{ margin: '2rem 0' }}>
        <NeuralNetworkViz />
      </div>

      {/* Cost Calculator */}
      <div style={{ margin: '2rem 0' }}>
        <CostCalculator />
      </div>

      {/* Interactive Demo */}
      <div style={{ margin: '2rem 0' }}>
        <InteractiveDemo />
      </div>

      {/* Architecture Layers */}
      {neuralLayer.modules.map((mod, mi) => (
        <div key={mi} className="module-card">
          <div 
            className="module-header"
            onClick={() => setExpandedModule(expandedModule === mi ? -1 : mi)}
            style={{ borderLeftColor: neuralLayer.color, cursor: 'pointer' }}
          >
            <span className="module-name">{mod.title}</span>
            <span className="module-file">📄 {mod.file}</span>
            <span className="module-chevron">{expandedModule === mi ? '▼' : '▶'}</span>
          </div>
          <p className="module-desc">
            {plainEnglish ? mod.plainDescription : mod.description}
          </p>

          {expandedModule === mi && (
            <div className="module-details">
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
          )}
        </div>
      ))}

      {/* Sequence Flow */}
      <div className="sequence-section">
        <h4 className="section-label">🗺️ How It Flows</h4>
        <div className="sequence-steps">
          {neuralLayer.sequence.map((step, i) => (
            <div key={i} className="sequence-step">
              <div className="step-number" style={{ backgroundColor: neuralLayer.color }}>
                {i + 1}
              </div>
              <div className="step-details">
                <span className="step-module">{step.module}</span>
                <span className="step-action">
                  {plainEnglish ? step.plainAction : step.action}
                </span>
                <div className="step-io">
                  {step.inputs.length > 0 && (
                    <span className="io-tag in">📥 {step.inputs.join(', ')}</span>
                  )}
                  {step.outputs.length > 0 && (
                    <span className="io-tag out">📤 {step.outputs.join(', ')}</span>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
