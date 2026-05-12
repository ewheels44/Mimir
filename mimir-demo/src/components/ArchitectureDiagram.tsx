import { useState, useEffect, useRef } from 'react';
import { ArchStep, architectureFlow } from '../data/architecture';

interface ArchNodeProps {
  step: ArchStep;
  x: number;
  y: number;
  width: number;
  height: number;
  isHovered: boolean;
  isActive: boolean;
  onClick: () => void;
  onEnter: () => void;
  onLeave: () => void;
}

const NODE_W = 180;
const NODE_H = 76;
const PADDING_X = 80;
const LAYER_GAP = 110;
const LAYER_LABEL_OFFSET = 30;

function ArchNode({
  step, x, y, width, height,
  isHovered, isActive, onClick, onEnter, onLeave,
}: ArchNodeProps) {
  const rx = x - width / 2;
  const ry = y - height / 2;

  return (
    <g
      onClick={onClick}
      onMouseEnter={onEnter}
      onMouseLeave={onLeave}
      style={{ cursor: 'pointer' }}
      role="button"
      tabIndex={0}
      aria-label={step.title}
    >
      {/* Glow ring when active/hovered */}
      {(isActive || isHovered) && (
        <rect
          x={rx - 5}
          y={ry - 5}
          width={width + 10}
          height={height + 10}
          rx={12}
          fill="none"
          stroke={step.color}
          strokeWidth="2"
          opacity="0.5"
          filter="url(#arch-glow)"
        >
          <animate
            attributeName="opacity"
            values={isActive ? '0.5;0.15;0.5' : '0.3;0.1;0.3'}
            dur="2s"
            repeatCount="indefinite"
          />
        </rect>
      )}

      {/* Node card */}
      <rect
        x={rx}
        y={ry}
        width={width}
        height={height}
        rx={10}
        fill={isActive || isHovered ? `${step.color}1a` : '#16162a'}
        stroke={isActive ? step.color : isHovered ? `${step.color}80` : '#2d2d3d'}
        strokeWidth={isActive ? 2.5 : 1}
        style={{ transition: 'all 0.3s ease' }}
      />

      {/* Top accent bar */}
      <rect
        x={rx}
        y={ry}
        width={width}
        height="3"
        rx={2}
        fill={step.color}
        opacity={isActive || isHovered ? 1 : 0.4}
      />

      {/* Icon */}
      <text
        x={x}
        y={y - 10}
        textAnchor="middle"
        dominantBaseline="central"
        fontSize="20"
      >
        {step.icon}
      </text>

      {/* Title */}
      <text
        x={x}
        y={y + 12}
        textAnchor="middle"
        fill={isActive ? step.color : '#e8e8f0'}
        fontSize="11"
        fontWeight="600"
        fontFamily="'JetBrains Mono', monospace"
      >
        {step.title.length > 20 ? step.title.substring(0, 18) + '…' : step.title}
      </text>

      {/* Subtitle */}
      <text
        x={x}
        y={y + 28}
        textAnchor="middle"
        fill="#606070"
        fontSize="9"
        fontFamily="'JetBrains Mono', monospace"
      >
        {step.subtitle}
      </text>
    </g>
  );
}

interface ArchDiagramProps {
  activeNode: number | null;
  onNodeSelect: (index: number) => void;
}

export function ArchitectureDiagram({ activeNode, onNodeSelect }: ArchDiagramProps) {
  const [hoveredNode, setHoveredNode] = useState<number | null>(null);
  const [svgWidth, setSvgWidth] = useState(900);
  const containerRef = useRef<HTMLDivElement>(null);
  const svgHeight = 620;

  // Measure container width
  useEffect(() => {
    const updateWidth = () => {
      if (containerRef.current) {
        setSvgWidth(Math.max(containerRef.current.offsetWidth - 4, 400));
      }
    };
    updateWidth();
    window.addEventListener('resize', updateWidth);
    return () => window.removeEventListener('resize', updateWidth);
  }, []);

  // Flatten all steps with positions
  const allNodes: { step: ArchStep; x: number; y: number; layerIdx: number }[] = [];

  architectureFlow.forEach((layer, li) => {
    const y = LAYER_LABEL_OFFSET + li * (NODE_H + LAYER_GAP) + NODE_H / 2;
    const layerTotalWidth = layer.steps.length * (NODE_W + PADDING_X) - PADDING_X;
    const startX = (svgWidth - layerTotalWidth) / 2 + NODE_W / 2;

    layer.steps.forEach((step, si) => {
      const x = startX + si * (NODE_W + PADDING_X);
      allNodes.push({ step, x, y, layerIdx: li });
    });
  });

  // Edges: connect each node in layer N to the nearest node in layer N+1
  const edges: {
    from: { x: number; y: number };
    to: { x: number; y: number };
    fromIdx: number;
    toIdx: number;
  }[] = [];

  for (let li = 0; li < architectureFlow.length - 1; li++) {
    const currentNodes = allNodes.filter(p => p.layerIdx === li);
    const nextNodes = allNodes.filter(p => p.layerIdx === li + 1);

    for (let ci = 0; ci < currentNodes.length; ci++) {
      const fromPos = currentNodes[ci];
      const ti = Math.min(ci, nextNodes.length - 1);
      const toPos = nextNodes[ti];
      const fromIdx = allNodes.indexOf(fromPos);
      const toIdx = allNodes.indexOf(toPos);

      if (fromPos && toPos) {
        edges.push({
          from: { x: fromPos.x, y: fromPos.y + NODE_H / 2 },
          to: { x: toPos.x, y: toPos.y - NODE_H / 2 },
          fromIdx,
          toIdx,
        });
      }
    }
  }

  return (
    <div className="arch-diagram-wrapper" ref={containerRef}>
      <svg
        width="100%"
        height={svgHeight}
        viewBox={`0 0 ${svgWidth} ${svgHeight}`}
        className="arch-diagram-svg"
        style={{ overflow: 'hidden' }}
      >
        <defs>
          <filter id="arch-glow" x="-50%" y="-50%" width="200%" height="200%">
            <feGaussianBlur stdDeviation="5" result="blur" />
            <feMerge>
              <feMergeNode in="blur" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {/* Edges between layers */}
        {edges.map((edge, i) => {
          const dx = edge.to.x - edge.from.x;
          const dy = edge.to.y - edge.from.y;
          const cx1 = edge.from.x + dx * 0.3;
          const cy1 = edge.from.y + dy * 0.5;
          const cx2 = edge.from.x + dx * 0.7;
          const cy2 = edge.to.y - dy * 0.2;
          const pathD = `M ${edge.from.x} ${edge.from.y} C ${cx1} ${cy1}, ${cx2} ${cy2}, ${edge.to.x} ${edge.to.y}`;

          const connected = edge.fromIdx === activeNode || edge.toIdx === activeNode;
          const targetNode = allNodes[edge.toIdx];
          const edgeColor = connected ? targetNode.step.color : '#2d2d3d';

          return (
            <g key={`edge-${i}`}>
              <path
                d={pathD}
                fill="none"
                stroke={edgeColor}
                strokeWidth={connected ? 2 : 1}
                strokeDasharray={connected ? 'none' : '5,5'}
                opacity={connected ? 0.9 : 0.25}
                style={{ transition: 'all 0.4s ease' }}
              />
              {/* Arrowhead as separate shape */}
              {connected && (
                <polygon
                  points={`${edge.to.x - 2},${edge.to.y - 5} ${edge.to.x + 8},${edge.to.y} ${edge.to.x - 2},${edge.to.y + 5}`}
                  fill={edgeColor}
                />
              )}
              {/* Animated data flow particles along active edges */}
              {connected && activeNode !== null && (
                <>
                  <circle r="3.5" fill={targetNode.step.color} filter="url(#arch-glow)">
                    <animateMotion dur="2s" repeatCount="indefinite" path={pathD} />
                  </circle>
                  <circle r="2" fill={targetNode.step.color} opacity="0.5" filter="url(#arch-glow)">
                    <animateMotion dur="2.8s" repeatCount="indefinite" path={pathD} begin="0.7s" />
                  </circle>
                  <circle r="1.5" fill={targetNode.step.color} opacity="0.3" filter="url(#arch-glow)">
                    <animateMotion dur="3.5s" repeatCount="indefinite" path={pathD} begin="1.4s" />
                  </circle>
                </>
              )}
            </g>
          );
        })}

        {/* Layer labels */}
        {architectureFlow.map((layer) => {
          const layerNodes = allNodes.filter(p => p.layerIdx === layer.tier - 1);
          if (layerNodes.length === 0) return null;
          const minX = Math.min(...layerNodes.map(p => p.x)) - NODE_W / 2;
          const maxX = Math.max(...layerNodes.map(p => p.x)) + NODE_W / 2;
          const y = layerNodes[0].y - NODE_H / 2 - LAYER_LABEL_OFFSET + 8;

          return (
            <g key={`layer-label-${layer.tier}`}>
              <rect
                x={minX + 5}
                y={y - 5}
                width={maxX - minX - 10}
                height="22"
                rx="4"
                fill={`${layer.steps[0].color}0d`}
                stroke={`${layer.steps[0].color}33`}
                strokeWidth="1"
              />
              <text
                x={svgWidth / 2}
                y={y + 10}
                textAnchor="middle"
                fill={layer.steps[0].color}
                fontSize="10"
                fontWeight="700"
                letterSpacing="0.12em"
                fontFamily="'JetBrains Mono', monospace"
                opacity="0.8"
              >
                LAYER {layer.tier} · {layer.label}
              </text>
            </g>
          );
        })}

        {/* Nodes */}
        {allNodes.map(({ step, x, y }, index) => (
          <ArchNode
            key={step.title + index}
            step={step}
            x={x}
            y={y}
            width={NODE_W}
            height={NODE_H}
            isHovered={hoveredNode === index}
            isActive={activeNode === index}
            onClick={() => onNodeSelect(index === activeNode ? -1 : index)}
            onEnter={() => setHoveredNode(index)}
            onLeave={() => setHoveredNode(null)}
          />
        ))}

        {/* Tooltip overlay */}
        {hoveredNode !== null && (() => {
          const pos = allNodes[hoveredNode];
          if (!pos) return null;
          const step = pos.step;
          const tipW = 260;
          const tipH = 90;
          let tipX = pos.x + NODE_W / 2 + 15;
          let tipY = pos.y - NODE_H / 2 - 10;
          if (tipX + tipW > svgWidth - 5) tipX = pos.x - NODE_W / 2 - tipW - 15;
          if (tipY + tipH > svgHeight - 5) tipY = svgHeight - tipH - 10;
          if (tipY < 5) tipY = 5;

          const isTop = tipY < pos.y;
          const arrowY = isTop ? tipY + tipH : tipY - 10;
          const arrowCY = isTop ? tipY + tipH - 2 : tipY + 10;

          return (
            <g style={{ pointerEvents: 'none' }}>
              <rect
                x={tipX}
                y={tipY}
                width={tipW}
                height={tipH}
                rx="8"
                fill="#1a1a2e"
                stroke={step.color}
                strokeWidth="1.5"
                opacity="0.97"
              />
              <polygon
                points={`${pos.x + NODE_W / 2 - 1},${arrowY} ${pos.x + NODE_W / 2 + 7},${arrowCY} ${pos.x + NODE_W / 2 - 1},${arrowCY}`}
                fill="#1a1a2e"
                stroke={step.color}
                strokeWidth="0.8"
              />
              <text x={tipX + 10} y={tipY + 18} fill={step.color} fontSize="10.5" fontWeight="700" fontFamily="'JetBrains Mono', monospace">
                {step.title}
              </text>
              <text x={tipX + 10} y={tipY + 34} fill="#a0a0b0" fontSize="9" fontFamily="'JetBrains Mono', monospace">
                {step.description.substring(0, 80)}{step.description.length > 80 ? '…' : ''}
              </text>
              {step.inputs && (
                <text x={tipX + 10} y={tipY + 50} fill="#f59e0b" fontSize="8.5" fontFamily="'JetBrains Mono', monospace">
                  📥 IN: {step.inputs.join(', ')}
                </text>
              )}
              {step.outputs && (
                <text x={tipX + 10} y={tipY + 64} fill="#10b981" fontSize="8.5" fontFamily="'JetBrains Mono', monospace">
                  📤 OUT: {step.outputs.join(', ')}
                </text>
              )}
            </g>
          );
        })()}
      </svg>
    </div>
  );
}