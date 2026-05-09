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

const NODE_WIDTH = 160;
const NODE_HEIGHT = 90;

// Calculate dynamic node positions for a flowchart layout
function calculateLayout(stepCount: number, containerWidth: number = 900): { positions: NodePosition[]; edges: FlowEdge[] } {
  const positions: NodePosition[] = [];
  const edges: FlowEdge[] = [];

  // Fewer steps = wider spread; more steps = more columns
  const cols = stepCount <= 3 ? stepCount : Math.min(stepCount, 5);

  const paddingX = 100;
  const paddingY = 80;
  const totalWidth = Math.max(containerWidth, cols * (NODE_WIDTH + paddingX));

  const nodeSpacingX = cols > 1 ? (totalWidth - 2 * paddingX) / (cols - 1) : totalWidth / 2;
  const nodeSpacingY = NODE_HEIGHT + paddingY;
  const startX = paddingX + NODE_WIDTH / 2;
  const startY = paddingY + NODE_HEIGHT / 2;

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
    const ids: number[] = [];
    flow.steps.forEach((_, i) => {
      const timer = setTimeout(() => {
        ids.push(i);
        setVisibleSteps([...ids]);
      }, i * 80 + 100);
      return () => clearTimeout(timer);
    });
    return () => {};
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

  // Dynamic SVG height based on rows
  const rows = Math.ceil(flow.steps.length / Math.min(flow.steps.length, 5));
  const svgHeight = rows * (NODE_HEIGHT + 80) + 180;

  // Generate smooth SVG path between two points
  const getPathD = (from: NodePosition, to: NodePosition): string => {
    const cx1 = from.x + (to.x - from.x) * 0.33;
    const cx2 = from.x + (to.x - from.x) * 0.66;
    return `M ${from.x} ${from.y + NODE_HEIGHT / 2 + 5} C ${cx1} ${from.y + NODE_HEIGHT / 2 + 5}, ${cx2} ${to.y + NODE_HEIGHT / 2 + 5}, ${to.x} ${to.y + NODE_HEIGHT / 2 + 5}`;
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
          width="100%"
          height={svgHeight}
          viewBox={`0 0 ${svgWidth} ${svgHeight}`}
          className="flow-graph-svg"
          style={{ overflow: 'visible' }}
        >
          <defs>
            <filter id="glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="4" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <filter id="pulse-glow" x="-50%" y="-50%" width="200%" height="200%">
              <feGaussianBlur stdDeviation="6" result="blur" />
              <feMerge>
                <feMergeNode in="blur" />
                <feMergeNode in="blur" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <marker id="arrow-default" viewBox="0 0 10 10" refX="9" refY="5"
              markerWidth="8" markerHeight="8" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#4a4a5a" />
            </marker>
            <marker id="arrow-active" viewBox="0 0 10 10" refX="9" refY="5"
              markerWidth="8" markerHeight="8" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill={flow.color} />
            </marker>
            <marker id="arrow-completed" viewBox="0 0 10 10" refX="9" refY="5"
              markerWidth="8" markerHeight="8" orient="auto-start-reverse">
              <path d="M 0 0 L 10 5 L 0 10 z" fill="#10b981" />
            </marker>
          </defs>

          {/* Edges */}
          {edges.map((edge, index) => {
            const fromPos = positions[edge.from];
            const toPos = positions[edge.to];
            const isBeforeCurrent = edge.to <= currentStep;
            const isAtCurrent = edge.from === currentStep - 1 && edge.to === currentStep;
            const isAfterCurrent = edge.from >= currentStep;
            const showParticle = isAtCurrent || (animatedEdge === edge.from && edge.to === animatedEdge + 1);

            return (
              <g key={`edge-${index}`}>
                <path
                  d={getPathD(fromPos, toPos)}
                  fill="none"
                  stroke={isBeforeCurrent ? '#10b981' : isAtCurrent ? flow.color : '#2d2d3d'}
                  strokeWidth={isBeforeCurrent || isAtCurrent ? 2.5 : 1.5}
                  strokeDasharray={isAfterCurrent ? '5,5' : 'none'}
                  markerEnd={
                    isBeforeCurrent ? 'url(#arrow-completed)' :
                    isAtCurrent ? 'url(#arrow-active)' :
                    'url(#arrow-default)'
                  }
                  style={{
                    transition: 'stroke 0.5s ease, stroke-width 0.5s ease',
                    filter: isAtCurrent ? `drop-shadow(0 0 8px ${flow.color}60)` : 'none',
                  }}
                />
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
                {flow.steps[edge.to]?.timing && (
                  <text
                    x={(fromPos.x + toPos.x) / 2}
                    y={(fromPos.y + toPos.y) / 2 + NODE_HEIGHT / 2 - 14}
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
            const nodeX = pos.x - NODE_WIDTH / 2;
            const nodeY = pos.y - NODE_HEIGHT / 2;

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
                  from="0" to="1"
                  dur="0.5s"
                  fill="freeze"
                  begin={`${index * 0.12 + 0.15}s`}
                />

                {/* Glow ring for active node */}
                {isActive && (
                  <rect
                    x={nodeX - 6}
                    y={nodeY - 6}
                    width={NODE_WIDTH + 12}
                    height={NODE_HEIGHT + 12}
                    rx={14}
                    fill="none"
                    stroke={flow.color}
                    strokeWidth="2"
                    filter="url(#pulse-glow)"
                    opacity="0.5"
                  >
                    <animate
                      attributeName="opacity"
                      values="0.5;0.1;0.5"
                      dur="2s"
                      repeatCount="indefinite"
                    />
                  </rect>
                )}

                {/* Node card */}
                <rect
                  x={nodeX}
                  y={nodeY}
                  width={NODE_WIDTH}
                  height={NODE_HEIGHT}
                  rx={12}
                  fill={isActive ? `${flow.color}18` : isCompleted ? '#10b9810d' : '#16162a'}
                  stroke={isActive ? flow.color : isCompleted ? '#10b981' : '#2d2d3d'}
                  strokeWidth={isActive ? 2.5 : isCompleted ? 1.5 : 1}
                  style={{
                    transition: 'all 0.4s ease',
                    filter: isActive ? `drop-shadow(0 0 16px ${flow.color}25)` : 'none',
                  }}
                />

                {/* Top accent gradient bar */}
                <defs>
                  <linearGradient id={`grad-${index}`} x1="0" y1="0" x2="1" y2="0">
                    <stop offset="0%" stopColor={isActive ? flow.color : isCompleted ? '#10b981' : 'transparent'} />
                    <stop offset="100%" stopColor={isActive ? flow.color : isCompleted ? '#10b981' : 'transparent'} stopOpacity={isActive || isCompleted ? 0.3 : 0} />
                  </linearGradient>
                </defs>
                <rect
                  x={nodeX}
                  y={nodeY}
                  width={NODE_WIDTH}
                  height="4"
                  rx={2}
                  fill={`url(#grad-${index})`}
                  style={{ transition: 'all 0.4s ease' }}
                />

                {/* Number badge */}
                <circle
                  cx={nodeX + 18}
                  cy={nodeY + 18}
                  r="11"
                  fill={isActive ? flow.color : isCompleted ? '#10b981' : '#1e1e32'}
                  stroke={isActive ? flow.color : isCompleted ? '#10b981' : '#2d2d3d'}
                  strokeWidth="1"
                  style={{ transition: 'all 0.4s ease' }}
                />
                <text
                  x={nodeX + 18}
                  y={nodeY + 22}
                  textAnchor="middle"
                  fill={isActive || isCompleted ? 'white' : '#444'}
                  fontSize="10"
                  fontWeight="700"
                  fontFamily="'JetBrains Mono', monospace"
                >
                  {index + 1}
                </text>

                {/* Icon */}
                <text
                  x={pos.x}
                  y={nodeY + 38}
                  textAnchor="middle"
                  fontSize="18"
                >
                  {step.icon}
                </text>

                {/* Label - multi-line support */}
                <text
                  x={pos.x}
                  y={nodeY + 58}
                  textAnchor="middle"
                  fill={isActive ? flow.color : isCompleted ? '#10b981' : '#777'}
                  fontSize="11"
                  fontWeight="600"
                  fontFamily="'JetBrains Mono', monospace"
                >
                  <tspan x={pos.x} dy="0">{step.label.length > 18 ? step.label.substring(0, 16) + '…' : step.label}</tspan>
                </text>

                {step.sublabel && (
                  <text
                    x={pos.x}
                    y={nodeY + 72}
                    textAnchor="middle"
                    fill="#555"
                    fontSize="8.5"
                    fontFamily="'JetBrains Mono', monospace"
                  >
                    {step.sublabel.length > 20 ? step.sublabel.substring(0, 18) + '…' : step.sublabel}
                  </text>
                )}

                {/* Status indicators along bottom */}
                <rect
                  x={nodeX + 4}
                  y={nodeY + NODE_HEIGHT - 6}
                  width="6"
                  height="6"
                  rx="3"
                  fill={isActive ? flow.color : isCompleted ? '#10b981' : '#333'}
                  style={{ transition: 'fill 0.4s ease' }}
                />
              </g>
            );
          })}

          {/* Hover tooltips rendered in a separate <g> on top, outside clipping */}
          {hoveredNode !== null && (() => {
            const step = flow.steps[hoveredNode];
            const pos = positions[hoveredNode];
            if (!step || !pos) return null;
            const tipW = 280;
            const tipH = 70;
            let tipX = pos.x + NODE_WIDTH / 2 + 15;
            let tipY = pos.y - NODE_HEIGHT / 2;
            // Flip if too far right
            if (tipX + tipW > svgWidth) tipX = pos.x - NODE_WIDTH / 2 - tipW - 15;
            if (tipY < 10) tipY = 10;

            return (
              <g className="svg-tooltip" style={{ pointerEvents: 'none' }}>
                <rect
                  x={tipX}
                  y={tipY}
                  width={tipW}
                  height={tipH}
                  rx={8}
                  fill="#1a1a2e"
                  stroke={flow.color}
                  strokeWidth="1.5"
                  opacity="0.96"
                />
                {/* Triangle pointer */}
                <polygon
                  points={`${pos.x + NODE_WIDTH / 2},${pos.y} ${pos.x + NODE_WIDTH / 2 + 8},${tipY + 8} ${pos.x + NODE_WIDTH / 2},${tipY + 8}`}
                  fill="#1a1a2e"
                  stroke={flow.color}
                  strokeWidth="1"
                />
                <text x={tipX + 10} y={tipY + 18} fill={flow.color} fontSize="10" fontWeight="700" fontFamily="'JetBrains Mono', monospace">
                  {step.label}
                </text>
                <text x={tipX + 10} y={tipY + 34} fill="#a0a0b0" fontSize="9" fontFamily="'JetBrains Mono', monospace">
                  {step.explanation.substring(0, 80) + (step.explanation.length > 80 ? '…' : '')}
                </text>
                <text x={tipX + 10} y={tipY + 50} fill="#606070" fontSize="8.5" fontFamily="'JetBrains Mono', monospace">
                  Timing: {step.timing || 'Instant'}
                </text>
                <text x={tipX + 10} y={tipY + 64} fill="#606070" fontSize="8.5" fontFamily="'JetBrains Mono', monospace">
                  {Object.keys(step.state).length} state variables
                </text>
              </g>
            );
          })()}

          {/* "START" indicator */}
          {positions[0] && (
            <>
              <circle cx={positions[0].x} cy={svgHeight - 30} r="6" fill="#10b981" />
              <text
                x={positions[0].x}
                y={svgHeight - 12}
                textAnchor="middle"
                fill="#10b981"
                fontSize="9"
                fontWeight="600"
                fontFamily="'JetBrains Mono', monospace"
              >
                START
              </text>
            </>
          )}

          {/* "END" indicator */}
          {positions[positions.length - 1] && (
            <>
              <circle cx={positions[positions.length - 1].x} cy={svgHeight - 30} r="6" fill={flow.color} />
              <text
                x={positions[positions.length - 1].x}
                y={svgHeight - 12}
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