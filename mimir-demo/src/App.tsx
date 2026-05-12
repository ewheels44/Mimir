import { useState, useCallback } from 'react';
import { StateInspector } from './components/StateInspector';
import { ExplanationPanel } from './components/ExplanationPanel';
import { ArchitectureDiagram } from './components/ArchitectureDiagram';
import { ConceptsPanel } from './components/ConceptsPanel';
import { ArchitectureExplainer } from './components/ArchitectureExplainer';
import { allFlows } from './data/flows';
import './styles/index.css';

type Theme = 'dark' | 'light';

function App() {
  const [activeFlowId, setActiveFlowId] = useState<string>('indexing');
  const [currentStep, setCurrentStep] = useState<number>(0);
  const [showArchitecture, setShowArchitecture] = useState<boolean>(false);
  const [showExplainer, setShowExplainer] = useState<boolean>(false);
  const [activeArchNode, setActiveArchNode] = useState<number | null>(null);
  const [theme, setTheme] = useState<Theme>('dark');
  const [plainEnglish, setPlainEnglish] = useState<boolean>(true);

  const activeFlow = allFlows.find(f => f.id === activeFlowId) || allFlows[0];

  const handleFlowChange = useCallback((flowId: string) => {
    setActiveFlowId(flowId);
    setCurrentStep(0);
    setShowArchitecture(false);
    setShowExplainer(false);
    setActiveArchNode(null);
  }, []);

  const toggleTheme = useCallback(() => {
    setTheme(prev => {
      const next = prev === 'dark' ? 'light' : 'dark';
      document.documentElement.setAttribute('data-theme', next);
      return next;
    });
  }, []);

  const handleArchNodeSelect = useCallback((index: number) => {
    if (index < 0) {
      setActiveArchNode(null);
      return;
    }
    setActiveArchNode(index);
    // Map architecture node to a flow — tier 1 = user query flow start, etc.
    const tierMap: Record<number, { flowId: string; stepIdx: number }[]> = {
      0: [{ flowId: 'rag', stepIdx: 0 }],   // User Query → RAG
      1: [{ flowId: 'rag', stepIdx: 1 }],   // MCP Client → Embed Query
      2: [{ flowId: 'rag', stepIdx: 0 }],   // LangGraph Router → RAG Query
      3: [{ flowId: 'rag', stepIdx: 2 }],   // Embedding Engine → Embed Query
      4: [{ flowId: 'rag', stepIdx: 3 }],   // Vector Store → Vector Search
      5: [{ flowId: 'rag', stepIdx: 3 }],   // Content Filter → Search (same step)
      6: [{ flowId: 'indexing', stepIdx: 0 }], // File Watcher → Detect Changes
      7: [{ flowId: 'bridge', stepIdx: 0 }],   // MCP Server → Kill Switch Check
      8: [{ flowId: 'indexing', stepIdx: 3 }], // Manifest DB → Update Manifest
    };
    const targets = tierMap[index];
    if (targets && targets.length > 0) {
      const target = targets[0];
      setActiveFlowId(target.flowId);
      setCurrentStep(target.stepIdx);
      setShowArchitecture(false);
    }
  }, []);

  const renderArchitectureDiagram = () => (
    <section className="architecture-section" aria-label="Architecture Overview">
      <h2 className="architecture-title">
        <span style={{ color: '#6366f1' }}>🏗️</span> System Architecture
      </h2>
      <p className="architecture-subtitle">
        A four-layer system: your tools query through orchestrated workflows,
        backed by semantic retrieval, with change-aware infrastructure keeping everything fresh.
        Click any node to jump to its flow step, or hover for quick previews.
      </p>
      <div className="architecture-diagram-container">
        <ArchitectureDiagram
          activeNode={activeArchNode}
          onNodeSelect={handleArchNodeSelect}
        />
      </div>

      {/* Architecture Legend */}
      <div className="architecture-legend">
        <span>💬 User input flows top-down</span>
        <span>📂 Infrastructure pushes changes up</span>
        <span>🔀 LangGraph orchestrates the middle layers</span>
      </div>
    </section>
  );

  return (
    <div className="app" data-theme={theme}>
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
            className={`nav-btn ${showArchitecture ? 'active' : ''}`}
            onClick={() => {
              setShowArchitecture(true);
              setShowExplainer(false);
              setCurrentStep(0);
            }}
            style={{ borderColor: showArchitecture ? '#6366f1' : undefined }}
          >
            🏗️ Architecture
          </button>
          <button
            className={`nav-btn ${showExplainer ? 'active' : ''}`}
            onClick={() => {
              setShowExplainer(true);
              setShowArchitecture(false);
              setCurrentStep(0);
            }}
            style={{ borderColor: showExplainer ? '#8b5cf6' : undefined }}
          >
            📖 Explain
          </button>
          <button
            className={`nav-btn ${plainEnglish ? 'active' : ''}`}
            onClick={() => setPlainEnglish(prev => !prev)}
            title={`Switch to ${plainEnglish ? 'technical' : 'plain English'} mode`}
          >
            {plainEnglish ? '🔤 Tech' : '🧒 ELI5'}
          </button>
          <button
            className="nav-btn theme-toggle"
            onClick={toggleTheme}
            title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} theme`}
          >
            {theme === 'dark' ? '☀️ Light' : '🌙 Dark'}
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
        <div className="hero-toggle-hint">
          <span className={`toggle-indicator ${plainEnglish ? 'active' : ''}`}>🧒 ELI5</span>
          <span className="toggle-separator">|</span>
          <span className={`toggle-indicator ${!plainEnglish ? 'active' : ''}`}>🔤 Tech</span>
          <span className="toggle-hint-text"> — Toggle between plain English and technical views</span>
        </div>
      </div>

      <div className="main-content">
        {/* === Architecture Overview === */}
        {showArchitecture ? (
          renderArchitectureDiagram()
        ) : showExplainer ? (
          <ArchitectureExplainer plainEnglish={plainEnglish} />
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

            {/* Detail Panels */}
            <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '1.5rem' }}>
              <StateInspector
                step={activeFlow.steps[currentStep]}
                stepIndex={currentStep}
                totalSteps={activeFlow.steps.length}
                flowColor={activeFlow.color}
                plainEnglish={plainEnglish}
              />
              <ExplanationPanel
                step={activeFlow.steps[currentStep]}
                flowColor={activeFlow.color}
                stepIndex={currentStep}
                totalSteps={activeFlow.steps.length}
                plainEnglish={plainEnglish}
              />
            </div>

            {/* Concepts Panel */}
            <div style={{ marginTop: '1.5rem' }}>
              <ConceptsPanel
                activeFlowId={activeFlowId}
              />
            </div>
          </>
        )}
      </div>
    </div>
  );
}

export default App;