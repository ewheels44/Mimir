import { ChevronRight, ChevronLeft, Play, Pause, RotateCcw } from 'lucide-react';
import { DemoFlow } from '../data/flows';
import { useState, useEffect } from 'react';

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
  const [animatedLine, setAnimatedLine] = useState<number | null>(null);
  const [visibleSteps, setVisibleSteps] = useState<number[]>([]);

  const isFirst = currentStep === 0;
  const isLast = currentStep === flow.steps.length - 1;

  // Animate steps appearing one by one when flow changes
  useEffect(() => {
    setVisibleSteps([]);
    const timer = setTimeout(() => {
      const steps: number[] = [];
      flow.steps.forEach((_, i) => {
        steps.push(i);
      });
      setVisibleSteps(steps);
    }, 100);
    return () => clearTimeout(timer);
  }, [flow.id]);

  // Auto-animate line drawing between steps
  useEffect(() => {
    if (currentStep > 0) {
      setAnimatedLine(currentStep - 1);
      const timer = setTimeout(() => setAnimatedLine(null), 1500);
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

  return (
    <div className="flow-diagram-wrapper" tabIndex={0}>
      {/* Auto-play toggle */}
      <div className="auto-play-controls">
        <button
          className={`auto-play-btn ${isPlaying ? 'playing' : ''}`}
          onClick={onTogglePlay}
          title={isPlaying ? 'Pause auto-play' : 'Start auto-play'}
        >
          {isPlaying ? <Pause size={14} /> : <Play size={14} />}
          <span>{isPlaying ? 'Playing' : 'Auto-play'}</span>
        </button>
        <span className="auto-play-speed">3s per step</span>
      </div>

      {/* Steps Timeline - horizontal row of nodes */}
      <div className="steps-timeline">
        {flow.steps.map((step, index) => {
          const isActive = index === currentStep;
          const isCompleted = index < currentStep;
          const isWaiting = index > currentStep;
          const visible = visibleSteps.includes(index);

          return (
            <div
              key={step.id}
              className={`timeline-node ${isActive ? 'active' : ''} ${isCompleted ? 'completed' : ''} ${isWaiting ? 'waiting' : ''} ${visible ? 'visible' : ''}`}
              onClick={() => onStepChange(index)}
              onMouseEnter={() => setHoveredNode(index)}
              onMouseLeave={() => setHoveredNode(null)}
              style={{
                '--node-color': isActive ? flow.color : isCompleted ? '#10b981' : undefined,
                '--glow-color': isActive ? `${flow.color}40` : undefined,
                animationDelay: visible ? `${index * 0.15}s` : '0s',
              } as React.CSSProperties}
              role="button"
              tabIndex={0}
              aria-label={`Step ${index + 1}: ${step.label}`}
            >
              <div className="timeline-connector">
                {index > 0 && (
                  <div className={`connector-line ${isCompleted ? 'completed' : 'pending'} ${animatedLine === index - 1 ? 'animating' : ''}`}>
                    {isCompleted && step.timing && (
                      <span className="timing-badge">{step.timing}</span>
                    )}
                  </div>
                )}
              </div>

              <div className="timeline-node-content">
                <div className="timeline-icon">{step.icon}</div>
                <div className="timeline-number">{index + 1}</div>
                <div className="timeline-label">{step.label}</div>
                {step.sublabel && <div className="timeline-sublabel">{step.sublabel}</div>}

                {/* Hover preview */}
                {hoveredNode === index && (
                  <div className="timeline-hover-preview" style={{ borderColor: flow.color }}>
                    <p>{step.explanation.substring(0, 80)}...</p>
                  </div>
                )}
              </div>
            </div>
          );
        })}
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