import { ChevronRight, ChevronLeft, Play, Pause, RotateCcw } from 'lucide-react';
import { DemoFlow } from '../data/flows';
import { useState, useEffect, useRef } from 'react';

interface FlowDiagramProps {
  flow: DemoFlow;
  currentStep: number;
  onStepChange: (step: number) => void;
  onReset: () => void;
  onNext: () => void;
  onPrev: () => void;
  isPlaying: boolean;
  onTogglePlay: () => void;
}

interface NodePosition {
  x: number;
  y: number;
}

interface FlowEdge {
  from: number;
  to: number;
  label?: string;
}

// Calculate dynamic node positions for a flowchart layout
function calculateLayout(stepCount: number, containerWidth: number = 900): { positions: NodePosition[]; edges: FlowEdge[] } {
  const positions: NodePosition[] = [];
  const edges: FlowEdge[] = [];

  // Responsive column count based on step count
  const cols = Math.min(stepCount, 5);

  const nodeSpacingX = containerWidth / (cols + 1);
  const nodeSpacingY = 100;
  const startY = 30;
  const startX = containerWidth / (cols + 1);

  for (let i = 0; i < stepCount; i++) {
    const col = i % cols;
    const row = Math.floor(i / cols);
    positions.push({
      x: startX + col * nodeSpacingX,
      y: startY + row * nodeSpacingY,
    });
  }

  for (let i = 0; i < stepCount - 1; i++) {
    edges.push({ from: i, to: i + 1 });
  }

  return { positions, edges };
}

export function FlowDiagram({
  flow,
  currentStep,
  onStepChange,
  onReset,
  onNext,
  onPrev,
  isPlaying,
  onTogglePlay,
}: FlowDiagramProps) {
  const [hoveredNode, setHoveredNode] = useState<number | null>(null);
  const [animatedEdge, setAnimatedEdge] = useState<number | null>(null);
  const [visibleSteps, setVisibleSteps] = useState<number[]>([]);
  const [svgWidth, setSvgWidth] = useState(900);
  const containerRef = useRef<HTMLDivElement>(null);

  const isFirst = currentStep === 0;
  const isLast = currentStep === flow.steps.length - 1;

  // Measure container width for responsive layout
  useEffect(() => {
    const updateWidth = () => {
      if (containerRef.current) {
        setSvgWidth(Math.max(containerRef.current.offsetWidth - 4, 300));
      }
    };
    updateWidth();
    window.addEventListener('resize', updateWidth);
    return () => window.removeEventListener('resize', updateWidth);
  }, []);

  // Animate steps appearing
  useEffect(() => {
    setVisibleSteps([]);
    const steps: number[] = [];
    flow.steps.forEach((_, i) => {
      const timer = setTimeout(() => {
        steps.push(i);
        setVisibleSteps([...steps]);
      }, i * 80 + 100);
      return () => clearTimeout(timer);
    });
    return () => {
      flow.steps.forEach((_step, i) => clearTimeout(i as any));
    };
  }, [flow.id]);

  // Animate edge drawing
  useEffect(() => {
    if (currentStep > 0) {
      setAnimatedEdge(currentStep - 1);
      const timer = setTimeout(() => setAnimatedEdge(null), 1800);
      return () => clearTimeout(timer);
    }
  }, [currentStep]);

  // Auto-advance when playing
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout>;
    if (isPlaying && !isLast) {
      timer = setTimeout(() => {
        onNext();
      }, 3000);
    } else if (isPlaying && isLast) {
      timer = setTimeout(() => {
        onReset();
      }, 2000);
    }
    return () => {
      clearTimeout(timer);
    };
  }, [isPlaying, currentStep, isLast, onNext, onReset]);

  const { positions, edges } = calculateLayout(flow.steps.length, svgWidth);

  // Generate smooth SVG path between two points
  const getPathD = (from: NodePosition, to: NodePosition): string => {
    const midX = (from.x + to.x) / 2;
    return `M ${from.x + 60} ${from.y + 50} C ${midX} ${from.y + 50}, ${midX} ${to.y + 50}, ${to.x - 60} ${to.y + 50}`;
  };

  return (
    <div className="flow-diagram-wrapper" ref={containerRef}>
      {/* Auto-play toggle */}
      <div className="auto-play-controls">
        <button
          className={`auto-play-btn ${isPlaying ? 'playing' : ''}`}
          onClick={onTogglePlay}
        >
          {isPlaying ? <Pause size={14} /> : <Play size={14} />}
          <span>{isPlaying ? 'Playing' : 'Auto-play'}</span>
        </button>
        <span className="auto-play-speed">3s per step</span>
      </div>

      {/* SVG Flow Graph */}
      <div className="flow-graph-container">
        <svg
          width={svgWidth}
          height={Math.max(...positions.map(p => p.y)) + 140}
          viewBox={`0 0 ${svgWidth} ${Math.max(...positions.map(p => p.y)) + 140}`}
          className="flow-graph-svg"
          style={{ width: '100%', height: 'auto' }}
        >
          <defs>
            {/* Glow filter */}
            <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            {/* Active pulse animation */}
            <filter id="pulse-glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="6" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>

            {/* Arrowhead marker */}
            <marker
              id="arrow-default"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="8"
              markerHeight="8"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#4a4a5a" />
            </marker>
            <marker
              id="arrow-active"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="8"
              markerHeight="8"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill={flow.color} />
            </marker>
            <marker
              id="arrow-completed"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="8"
              markerHeight="8"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#10b981" />
            </marker>
            <marker
              id="arrow-anim"
              viewBox="0 0 10 10"
              refX="9"
              refY="5"
              markerWidth="8"
              markerHeight="8"
              orient="auto-start-reverse"
            >
              <path d="M 0 0 L 10 5 L 0 10 z" fill={flow.color} />
            </marker>

            {/* Particle for animation */}
            <radialGradient id="particle-gradient">
              <stop offset="0%" stopColor={flow.color} stopOpacity="1" />
              <stop offset="100%" stopColor={flow.color} stopOpacity="0" />
            </radialGradient>
          </defs>

          {/* Edges */}
          {edges.map((edge, index) => {
            const fromPos = positions[edge.from];
            const toPos = positions[edge.to];
            const isBeforeCurrent = edge.to <= currentStep;
            const isAtCurrent = edge.from === currentStep - 1 && edge.to === currentStep;
            const isAfterCurrent = edge.from >= currentStep;

            // Animated particle along the edge
            const showParticle = isAtCurrent || (animatedEdge === edge.from && edge.to === animatedEdge + 1);

            return (
              <g key={`edge-${index}`}>
                {/* Main edge path */}
                <path
                  d={getPathD(fromPos, toPos)}
                  fill="none"
                  stroke={
                    isBeforeCurrent ? '#10b981' :
                    isAtCurrent ? flow.color :
                    isAfterCurrent ? '#2d2d3d' : '#2d2d3d'
                  }
                  strokeWidth={
                    isBeforeCurrent || isAtCurrent ? 2.5 : 1.5
                  }
                  strokeDasharray={isAfterCurrent ? '4,4' : 'none'}
                  markerEnd={
                    isBeforeCurrent ? 'url(#arrow-completed)' :
                    isAtCurrent ? 'url(#arrow-active)' :
                    'url(#arrow-default)'
                  }
                  style={{
                    transition: 'stroke 0.5s ease, stroke-width 0.5s ease',
                    filter: isAtCurrent ? `drop-shadow(0 0 6px ${flow.color}60)` : 'none',
                  }}
                />

                {/* Animated particle */}
                {showParticle && (
                  <circle r="4" fill={flow.color} filter="url(#glow)">
                    <animateMotion
                      dur="1.5s"
                      repeatCount="3"
                      path={getPathD(fromPos, toPos)}
                      begin="0s"
                    />
                  </circle>
                )}

                {/* Timing label */}
                {flow.steps[edge.to]?.timing && (
                  <text
                    x={(fromPos.x + toPos.x) / 2}
                    y={(fromPos.y + toPos.y) / 2 - 8}
                    textAnchor="middle"
                    fill="#606070"
                    fontSize="10"
                    fontFamily="'JetBrains Mono', monospace"
                  >
                    {flow.steps[edge.to].timing}
                  </text>
                )}
              </g>
            );
          })}

          {/* Nodes */}
          {flow.steps.map((step, index) => {
            const pos = positions[index];
            const isActive = index === currentStep;
            const isCompleted = index < currentStep;
            const visible = visibleSteps.includes(index);

            const nodeWidth = 120;
            const nodeHeight = 70;
            const rx = pos.x - nodeWidth / 2;
            const ry = pos.y;

            return (
              <g
                key={step.id}
                className="flow-chart-node"
                onClick={() => onStepChange(index)}
                onMouseEnter={() => setHoveredNode(index)}
                onMouseLeave={() => setHoveredNode(null)}
                style={{ cursor: 'pointer' }}
                opacity={visible ? 1 : 0}
              >
                <animate
                  attributeName="opacity"
                  from="0"
                  to="1"
                  dur="0.4s"
                  fill="freeze"
                  begin={`${index * 0.12 + 0.1}s`}
                />

                {/* Connection line to previous (for L/R layout effect) */}
                {isActive && (
                  <rect
                    x={rx - 4}
                    y={ry - 4}
                    width={nodeWidth + 8}
                    height={nodeHeight + 8}
                    rx={12}
                    fill="none"
                    stroke={flow.color}
                    strokeWidth="2"
                    filter="url(#pulse-glow)"
                    opacity="0.4"
                  >
                    <animate
                      attributeName="opacity"
                      values="0.4;0.1;0.4"
                      dur="2s"
                      repeatCount="indefinite"
                    />
                  </rect>
                )}

                {/* Node background */}
                <rect
                  x={rx}
                  y={ry}
                  width={nodeWidth}
                  height={nodeHeight}
                  rx={10}
                  fill={
                    isActive
                      ? `${flow.color}20`
                      : isCompleted
                      ? '#10b9810d'
                      : '#1a1a2e'
                  }
                  stroke={
                    isActive
                      ? flow.color
                      : isCompleted
                      ? '#10b981'
                      : '#2d2d3d'
                  }
                  strokeWidth={isActive ? 2.5 : isCompleted ? 1.5 : 1}
                  style={{
                    transition: 'all 0.4s ease',
                    filter: isActive ? `drop-shadow(0 0 12px ${flow.color}30)` : 'none',
                  }}
                />

                {/* Top accent bar */}
                <rect
                  x={rx}
                  y={ry}
                  width={nodeWidth}
                  height="3"
                  rx={2}
                  fill={
                    isActive
                      ? flow.color
                      : isCompleted
                      ? '#10b981'
                      : 'transparent'
                  }
                  style={{ transition: 'fill 0.4s ease' }}
                />

                {/* Icon */}
                <text
                  x={pos.x}
                  y={ry + 24}
                  textAnchor="middle"
                  fontSize="16"
                >
                  {step.icon}
                </text>

                {/* Label */}
                <text
                  x={pos.x}
                  y={ry + 42}
                  textAnchor="middle"
                  fill={isActive ? flow.color : isCompleted ? '#10b981' : '#888'}
                  fontSize="11"
                  fontWeight="600"
                  fontFamily="'JetBrains Mono', monospace"
                  style={{ transition: 'fill 0.4s ease' }}
                >
                  {step.label.length > 16 ? step.label.substring(0, 14) + '…' : step.label}
                </text>

                {/* Step number badge */}
                <circle
                  cx={rx + 16}
                  cy={ry + 16}
                  r="10"
                  fill={
                    isActive
                      ? flow.color
                      : isCompleted
                      ? '#10b981'
                      : '#2d2d3d'
                  }
                  style={{ transition: 'fill 0.4s ease' }}
                />
                <text
                  x={pos.x - (nodeWidth / 2) + 16}
                  y={ry + 19.5}
                  textAnchor="middle"
                  fill={isActive || isCompleted ? 'white' : '#555'}
                  fontSize="9"
                  fontWeight="700"
                  fontFamily="'JetBrains Mono', monospace"
                >
                  {index + 1}
                </text>

                {/* Hover tooltip */}
                {hoveredNode === index && (
                  <g>
                    <rect
                      x={rx - 5}
                      y={ry - 50}
                      width={nodeWidth + 10}
                      height="40"
                      rx={6}
                      fill="#1a1a2e"
                      stroke={flow.color}
                      strokeWidth="1"
                      opacity="0.95"
                    />
                    <text
                      x={pos.x}
                      y={ry - 34}
                      textAnchor="middle"
                      fill="#e8e8f0"
                      fontSize="9"
                      fontFamily="'JetBrains Mono', monospace"
                    >
                      {step.explanation.substring(0, 60)}...
                    </text>
                  </g>
                )}
              </g>
            );
          })}

          {/* "START" indicator */}
          <circle cx={positions[0]?.x || 60} cy={positions[0]?.y + 70 || 100} r="6" fill="#10b981" />
          <text
            x={positions[0]?.x || 60}
            y={positions[0]?.y + 88 || 100}
            textAnchor="middle"
            fill="#10b981"
            fontSize="9"
            fontWeight="600"
            fontFamily="'JetBrains Mono', monospace"
          >
            START
          </text>

          {/* "END" indicator */}
          {positions[positions.length - 1] && (
            <>
              <circle cx={positions[positions.length - 1].x} cy={positions[positions.length - 1].y + 70} r="6" fill={flow.color} />
              <text
                x={positions[positions.length - 1].x}
                y={positions[positions.length - 1].y + 88}
                textAnchor="middle"
                fill={flow.color}
                fontSize="9"
                fontWeight="600"
                fontFamily="'JetBrains Mono', monospace"
              >
                END
              </text>
            </>
          )}
        </svg>
      </div>

      {/* Step Controls */}
      <div className="step-controls">
        <button
          className="control-btn secondary"
          onClick={onReset}
          title="Reset to beginning"
        >
          <RotateCcw size={16} />
          Reset
        </button>

        <button
          className="control-btn secondary"
          onClick={onPrev}
          disabled={isFirst}
          title="Previous step"
        >
          <ChevronLeft size={18} />
          Previous
        </button>

        <div className="step-progress">
          <div
            className="progress-bar"
            style={{ width: `${((currentStep + 1) / flow.steps.length) * 100}%`, backgroundColor: flow.color }}
          />
        </div>

        <button
          className="control-btn primary"
          onClick={onNext}
          disabled={isLast}
          style={{ backgroundColor: flow.color }}
          title="Next step"
        >
          Next
          <ChevronRight size={18} />
        </button>

        <span className="step-indicator">
          <span className="step-current" style={{ color: flow.color }}>{currentStep + 1}</span>
          <span className="step-separator">/</span>
          <span className="step-total">{flow.steps.length}</span>
        </span>
      </div>

      {/* Sub-step Detail Panel */}
      {flow.steps[currentStep]?.subSteps && (
        <div className="substeps-panel">
          <h4 className="substeps-title">
            <span style={{ color: flow.color }}>⬇</span> Deep Dive: {flow.steps[currentStep].label}
          </h4>
          <div className="substeps-list">
            {flow.steps[currentStep].subSteps!.map((sub, i) => (
              <div
                key={i}
                className="substep-item"
                style={{ animationDelay: `${i * 0.2}s` }}
              >
                <span className="substep-visual">{sub.visual}</span>
                <div className="substep-content">
                  <span className="substep-title">{sub.title}</span>
                  <span className="substep-detail">{sub.detail}</span>
                </div>
              </div>
            ))}
          </div>

          {/* Input/Output data flow */}
          {(flow.steps[currentStep].inputs || flow.steps[currentStep].outputs) && (
            <div className="data-io-section">
              <div className="data-io-block inputs">
                <span className="data-io-label">📥 Inputs</span>
                <div className="data-tags">
                  {flow.steps[currentStep].inputs?.map((inp, i) => (
                    <span key={i} className="data-tag" style={{ borderColor: flow.color }}>{inp}</span>
                  ))}
                </div>
              </div>
              <div className="data-io-arrow">→</div>
              <div className="data-io-block outputs">
                <span className="data-io-label">📤 Outputs</span>
                <div className="data-tags">
                  {flow.steps[currentStep].outputs?.map((out, i) => (
                    <span key={i} className="data-tag" style={{ borderColor: '#10b981' }}>{out}</span>
                  ))}
                </div>
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  );
}