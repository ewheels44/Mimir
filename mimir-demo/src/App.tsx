import { useState, useCallback } from 'react';
import { FlowDiagram } from './components/FlowDiagram';
import { StateInspector } from './components/StateInspector';
import { ExplanationPanel } from './components/ExplanationPanel';
import { allFlows } from './data/flows';
import { architectureFlow } from './data/architecture';
import { ArchStep } from './data/architecture';

function App() {
  const [activeFlowId, setActiveFlowId] = useState<string>('indexing');
  const [currentStep, setCurrentStep] = useState<number>(0);
  const [isPlaying, setIsPlaying] = useState<boolean>(false);
  const [activeArchTab, setActiveArchTab] = useState<number>(0);

  const activeFlow = allFlows.find(f => f.id === activeFlowId) || allFlows[0];

  const handleFlowChange = useCallback((flowId: string) => {
    setActiveFlowId(flowId);
    setCurrentStep(0);
    setIsPlaying(false);
    setActiveArchTab(0);
  }, []);

  const handleStepChange = useCallback((step: number) => {
    setCurrentStep(step);
  }, []);

  const togglePlay = useCallback(() => {
    setIsPlaying(prev => !prev);
  }, []);

  const renderArchitectureDiagram = () => (
    <section className="architecture-section" aria-label="Architecture Overview">
      <h2 className="architecture-title">
        <span style={{ color: '#6366f1' }}>🏗️</span> System Architecture
      </h2>
      <p className="architecture-subtitle">
        A four-layer system: your tools query through orchestrated workflows,
        backed by semantic retrieval, with change-aware infrastructure keeping everything fresh.
      </p>

      <div className="architecture-diagram">
        {architectureFlow.map((layer) => (
          <div key={layer.tier} className="arch-layer">
            <div className="arch-layer-label">Layer {layer.tier} · {layer.label}</div>
            <div className="arch-layer-nodes">
              {layer.steps.map((step: ArchStep) => (
                <div
                  key={step.title}
                  className={`arch-node ${activeArchTab === layer.tier * 10 + step.position ? 'arch-node-highlight' : ''}`}
                  onClick={() => setActiveArchTab(layer.tier * 10 + step.position)}
                  style={{
                    borderColor: activeArchTab === layer.tier * 10 + step.position ? step.color : undefined,
                    boxShadow: activeArchTab === layer.tier * 10 + step.position
                      ? `0 0 20px ${step.color}40`
                      : undefined,
                  }}
                >
                  <div className="arch-node-icon">{step.icon}</div>
                  <div className="arch-node-title">{step.title}</div>
                  <div className="arch-node-subtitle">{step.subtitle}</div>
                  <div className="arch-node-desc">{step.description}</div>

                  {/* Show inputs/outputs when selected */}
                  {activeArchTab === layer.tier * 10 + step.position && (
                    <div style={{ marginTop: '0.75rem', display: 'flex', flexDirection: 'column', gap: '0.3rem', fontSize: '0.7rem' }}>
                      {step.inputs && (
                        <div style={{ color: '#f59e0b' }}>
                          📥 IN: {step.inputs.join(', ')}
                        </div>
                      )}
                      {step.outputs && (
                        <div style={{ color: '#10b981' }}>
                          📤 OUT: {step.outputs.join(', ')}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              ))}
            </div>

            {/* Connector between layers */}
            {layer.tier < 4 && (
              <div className="arch-layer-connector">
                <div className="arch-connector-arrows">
                  {layer.steps.map((_: ArchStep, i: number) => (
                    <span key={i} className="arch-connector-arrow">↓</span>
                  ))}
                </div>
              </div>
            )}
          </div>
        ))}
      </div>

      {/* Architecture Legend */}
      <div style={{ marginTop: '1.5rem', display: 'flex', justifyContent: 'center', gap: '2rem', flexWrap: 'wrap', fontSize: '0.78rem', color: '#606070' }}>
        <span>💬 User input flows top-down</span>
        <span>📂 Infrastructure pushes changes up</span>
        <span>🔀 LangGraph orchestrates the middle layers</span>
      </div>
    </section>
  );

  return (
    <div className="app">
      {/* Sticky Header */}
      <header className="header">
        <h1>🗿 Mimir</h1>
        <nav className="header-nav">
          {allFlows.map(flow => (
            <button
              key={flow.id}
              className={`nav-btn ${activeFlowId === flow.id ? 'active' : ''}`}
              onClick={() => handleFlowChange(flow.id)}
              style={{
                borderColor: activeFlowId === flow.id ? flow.color : undefined,
              }}
            >
              {flow.icon} {flow.title.split(' ')[0]}
            </button>
          ))}
          <button
            className={`nav-btn ${activeArchTab >= 10 ? 'active' : ''}`}
            onClick={() => {
              setActiveArchTab(10);
              setCurrentStep(0);
            }}
            style={{ borderColor: activeArchTab >= 10 ? '#6366f1' : undefined }}
          >
            🏗️ Architecture
          </button>
        </nav>
      </header>

      {/* Hero Section */}
      <div className="hero-section">
        <div className="hero-icon">🗿</div>
        <h1 className="hero-title">Mimir — Persistent Knowledge for AI Agents</h1>
        <p className="hero-subtitle">
          A semantic knowledge base that gives your AI agents instant access to your codebase.
          Index once, query forever. Every step is explained below with live state tracking.
        </p>
      </div>

      <div className="main-content">
        {/* === Architecture Overview === */}
        {activeArchTab >= 10 ? (
          renderArchitectureDiagram()
        ) : (
          <>
            {/* Flow Header */}
            <div className="demo-header">
              <div style={{ display: 'flex', alignItems: 'center', gap: '0.75rem' }}>
                <h2 className="demo-title" style={{ color: activeFlow.color }}>
                  {activeFlow.icon} {activeFlow.title}
                </h2>
              </div>
              <p className="demo-description">{activeFlow.description}</p>
              <div className="overview-box">
                <strong>How it works:</strong> {activeFlow.overview}
              </div>
            </div>

            {/* Flow Diagram */}
            <div className="flow-container">
              <FlowDiagram
                flow={activeFlow}
                currentStep={currentStep}
                onStepChange={handleStepChange}
                onReset={() => setCurrentStep(0)}
                onNext={() => setCurrentStep(prev => Math.min(prev + 1, activeFlow.steps.length - 1))}
                onPrev={() => setCurrentStep(prev => Math.max(prev - 1, 0))}
                isPlaying={isPlaying}
                onTogglePlay={togglePlay}
              />
            </div>

            {/* Detail Panels */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
              <StateInspector
                step={activeFlow.steps[currentStep]}
                stepIndex={currentStep}
                totalSteps={activeFlow.steps.length}
                flowColor={activeFlow.color}
              />
              <ExplanationPanel
                step={activeFlow.steps[currentStep]}
                flowColor={activeFlow.color}
                stepIndex={currentStep}
                totalSteps={activeFlow.steps.length}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default App;