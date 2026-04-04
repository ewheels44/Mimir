import React from 'react';
import { InsightData, GraphNode } from '../types';
import styles from './ContextPanel.module.css';

interface Props {
  visible: boolean;
  insights: InsightData | null;
  selectedNode: GraphNode | null;
}

export default function ContextPanel({ visible, insights, selectedNode }: Props) {
  if (!visible) return null;

  return (
    <div className={`${styles.panel} glass-panel`}>
      <h3 className={styles.heading}>Ecological Thinking</h3>
      <p className={styles.intro}>
        This knowledge graph maps your codebase as an ecology of ideas — modules are
        organisms, imports are dependencies, calls are interactions.
      </p>

      {insights && (
        <>
          <div className={styles.stats}>
            <StatBox value={insights.nodeCount} label="Concepts" />
            <StatBox value={insights.edgeCount} label="Connections" />
            <StatBox value={insights.clusterCount} label="Clusters" />
          </div>

          <div className={styles.insightBox}>
            <h4 className={styles.subHeading}>Insight</h4>
            <p className={styles.insightText}>{insights.insight}</p>
          </div>

          {insights.bridges.length > 0 && (
            <div className={styles.bridgesBox}>
              <h4 className={styles.subHeading}>Key bridges</h4>
              {insights.bridges.slice(0, 3).map(b => (
                <div key={b.id} className={styles.bridgeItem}>
                  <span className={styles.bridgeLabel}>{b.label}</span>
                  <span className={styles.bridgeScore}>
                    {(b.score * 100).toFixed(0)}%
                  </span>
                  <div
                    className={styles.bridgeBar}
                    style={{ width: `${b.score * 100}%` }}
                  />
                </div>
              ))}
            </div>
          )}

          {insights.isolatedCount > 0 && (
            <div className={styles.gapBox}>
              <h4 className={styles.subHeading}>Gaps</h4>
              <p className={styles.gapText}>
                {insights.isolatedCount} isolated{' '}
                {insights.isolatedCount === 1 ? 'node has' : 'nodes have'} no connections.
                Consider documenting or linking these modules.
              </p>
              <p className={styles.gapNote}>
                Some nodes are phantom references from method calls on local variables
                (e.g. <code>room.GetParticipant</code>) that the extractor can't resolve
                without type analysis.
              </p>
              <p className={styles.gapTip}>
                <strong>Tip:</strong> Use the min connections slider to filter these out.
                Setting it to <strong>2</strong> removes most phantom nodes and shows only
                well-connected modules.
              </p>
            </div>
          )}
        </>
      )}

      {selectedNode && (
        <div className={styles.nodeContext}>
          <h4 className={styles.subHeading}>Selected: {selectedNode.label}</h4>
          <div className={styles.nodeMeta}>
            {selectedNode.metadata.file_path && (
              <MetaRow label="Path" value={selectedNode.metadata.file_path} />
            )}
            {selectedNode.metadata.function_count != null && (
              <MetaRow
                label="Functions"
                value={String(selectedNode.metadata.function_count)}
              />
            )}
            {selectedNode.metadata.class_count != null && (
              <MetaRow
                label="Classes"
                value={String(selectedNode.metadata.class_count)}
              />
            )}
          </div>
        </div>
      )}
    </div>
  );
}

function StatBox({ value, label }: { value: number; label: string }) {
  return (
    <div className={styles.statBox}>
      <span className={styles.statNum}>{value}</span>
      <span className={styles.statLabel}>{label}</span>
    </div>
  );
}

function MetaRow({ label, value }: { label: string; value: string }) {
  return (
    <div className={styles.metaRow}>
      <span className={styles.metaLabel}>{label}</span>
      <span className={styles.metaValue}>{value}</span>
    </div>
  );
}
