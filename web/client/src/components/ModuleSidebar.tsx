import React, { useEffect, useState } from 'react';
import { GraphData, GraphNode } from '../types';
import styles from './ModuleSidebar.module.css';

interface Props {
  node: GraphNode | null;
  degree: number;
  outEdges: { targetId: string; targetLabel: string; type: string }[];
  inEdges: { sourceId: string; sourceLabel: string; type: string }[];
  onClose: () => void;
  onFocusNode: (id: string) => void;
}

export default function ModuleSidebar({
  node,
  degree,
  outEdges,
  inEdges,
  onClose,
  onFocusNode,
}: Props) {
  const [children, setChildren] = useState<GraphData | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!node) { setChildren(null); return; }
    setLoading(true);
    setError(null);

    fetch(`/api/graph/module/${encodeURIComponent(node.id)}/children`)
      .then(async r => {
        const text = await r.text();
        if (!text || text.trim() === '') {
          return { nodes: [], edges: [] };
        }
        try {
          return JSON.parse(text);
        } catch (e) {
          throw new Error(`Invalid JSON response: ${text.substring(0, 100)}`);
        }
      })
      .then(data => setChildren(data))
      .catch(err => setError(String(err)))
      .finally(() => setLoading(false));
  }, [node?.id]);

  const visible = node !== null;

  const functions = children?.nodes.filter(n => n.type === 'function') ?? [];
  const classes = children?.nodes.filter(n => n.type === 'class') ?? [];

  const methodsFor = (classId: string) =>
    (children?.edges ?? [])
      .filter(e => e.type === 'has_method' && e.target === classId)
      .map(e => children?.nodes.find(n => n.id === e.source))
      .filter(Boolean) as GraphNode[];

  return (
    <div className={`${styles.panel} ${visible ? styles.visible : ''}`}>
      <button className={styles.closeBtn} onClick={onClose} aria-label="Close">×</button>

      {node && (
        <>
          <h2 className={styles.title}>{node.label}</h2>

          <div className={styles.statRow}>
            <Stat value={node.metadata.function_count ?? 0} label="Functions" />
            <Stat value={node.metadata.class_count ?? 0} label="Classes" />
            <Stat value={degree} label="Edges" />
          </div>

          {loading && <p className={styles.loading}>Loading details...</p>}
          {error && <p className={styles.error}>Error: {error}</p>}

          {!loading && !error && (
            <>
              {functions.length > 0 && (
                <Section title="Functions">
                  {functions.map(f => (
                    <Item key={f.id} typeTag="fn" label={f.label} />
                  ))}
                </Section>
              )}

              {classes.length > 0 && (
                <Section title="Classes">
                  {classes.map(c => (
                    <React.Fragment key={c.id}>
                      <Item typeTag="class" label={c.label} isClass />
                      {methodsFor(c.id).map(m => (
                        <Item key={m.id} typeTag="m" label={m.label} indent />
                      ))}
                    </React.Fragment>
                  ))}
                </Section>
              )}

              {(outEdges.length > 0 || inEdges.length > 0) && (
                <Section title="Relationships">
                  {outEdges.length > 0 && (
                    <>
                      <span className={styles.dirLabel}>Outbound</span>
                      {outEdges.map((e, i) => (
                        <button
                          key={i}
                          className={styles.relItem}
                          onClick={() => onFocusNode(e.targetId)}
                        >
                          <span className={styles.arrow}>→</span>
                          {e.targetLabel}
                          <span className={styles.relType}>{e.type}</span>
                        </button>
                      ))}
                    </>
                  )}
                  {inEdges.length > 0 && (
                    <>
                      <span className={styles.dirLabel}>Inbound</span>
                      {inEdges.map((e, i) => (
                        <button
                          key={i}
                          className={styles.relItem}
                          onClick={() => onFocusNode(e.sourceId)}
                        >
                          <span className={styles.arrow}>←</span>
                          {e.sourceLabel}
                          <span className={styles.relType}>{e.type}</span>
                        </button>
                      ))}
                    </>
                  )}
                </Section>
              )}

              {functions.length === 0 &&
                classes.length === 0 &&
                outEdges.length === 0 &&
                inEdges.length === 0 && (
                  <p className={styles.loading}>No detailed information available.</p>
                )}
            </>
          )}
        </>
      )}
    </div>
  );
}

function Stat({ value, label }: { value: number; label: string }) {
  return (
    <div style={{ flex: 1, background: 'var(--bg-raised)', padding: '8px', borderRadius: 'var(--radius-sm)', textAlign: 'center' }}>
      <div style={{ fontSize: 18, fontWeight: 700 }}>{value}</div>
      <div style={{ fontSize: 11, color: 'var(--text-muted)', textTransform: 'uppercase', marginTop: 2 }}>{label}</div>
    </div>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div style={{ marginBottom: 16 }}>
      <h3 style={{ fontSize: 12, color: 'var(--text-muted)', textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: 8 }}>
        {title}
      </h3>
      {children}
    </div>
  );
}

function Item({ typeTag, label, isClass, indent }: { typeTag: string; label: string; isClass?: boolean; indent?: boolean }) {
  return (
    <div
      className={styles.item}
      style={{
        marginLeft: indent ? 16 : 0,
        fontSize: indent ? 12 : 13,
      }}
    >
      <span
        className={styles.itemType}
        style={{ color: isClass ? 'var(--pink)' : 'var(--purple)' }}
      >
        {typeTag}
      </span>
      {label}
    </div>
  );
}
