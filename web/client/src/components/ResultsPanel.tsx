import React from 'react';
import { ResultsState } from '../types';
import styles from './ResultsPanel.module.css';

interface Props {
  state: ResultsState;
  onClose: () => void;
  onHighlight: (source: string) => void;
}

// Minimal markdown renderer (avoid a heavy dep)
function renderMarkdown(text: string): string {
  return text
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/\*([^*]+)\*/g, '<em>$1</em>')
    .replace(/^#{1,3} (.+)$/gm, '<h3>$1</h3>')
    .replace(/\n/g, '<br />');
}

export default function ResultsPanel({ state, onClose, onHighlight }: Props) {
  if (!state.visible) return null;

  return (
    <div className={styles.panel}>
      <div className={styles.header}>
        <h3 className={styles.title}>{state.title}</h3>
        <div className={styles.headerActions}>
          <button className={styles.iconBtn} onClick={onClose} aria-label="Close">
            ×
          </button>
        </div>
      </div>

      <div className={styles.body}>
          {state.query && (
            <div className={styles.queryChip}>Q: {state.query}</div>
          )}

          {state.type === 'query' ? (
            <div
              className={`${styles.markdownBody} markdown`}
              dangerouslySetInnerHTML={{
                __html: renderMarkdown(state.items[0]?.snippet ?? ''),
              }}
            />
          ) : (
            state.items.map((r, i) => (
              <button
                key={i}
                className={styles.resultItem}
                onClick={() => onHighlight(r.source)}
              >
                <div className={styles.resultTitle}>{r.title || `Result ${i + 1}`}</div>
                <div
                  className={`${styles.resultSnippet} markdown`}
                  dangerouslySetInnerHTML={{ __html: renderMarkdown(r.snippet) }}
                />
              </button>
            ))
          )}
      </div>
    </div>
  );
}
