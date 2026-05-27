import React, { useRef, useState } from 'react';
import { GraphSettings, EdgeFilters } from '../types';
import styles from './Sidebar.module.css';

interface Props {
  settings: GraphSettings;
  onSettingsChange: (patch: Partial<GraphSettings>) => void;
  onSearch: (query: string) => void;
  onQuery: (question: string) => Promise<void>;
  onLayoutChange: (name: string) => void;
  onFit: () => void;
  onReset: () => void;
  onToggleLabels: () => void;
  onApplyDegree: () => void;
  floating: boolean;
}

const LAYOUTS = [
  { id: 'cose', label: 'Force-directed' },
  { id: 'circle', label: 'Circle' },
  { id: 'grid', label: 'Grid' },
  { id: 'dagre', label: 'Hierarchy' },
];

const EDGE_TYPES: { key: keyof EdgeFilters; label: string; color: string; dash?: boolean }[] = [
  { key: 'calls', label: 'Calls', color: '#f59e0b' },
  { key: 'imports_module', label: 'Imports module', color: '#10b981' },
  { key: 'imports_from', label: 'Imports from', color: '#10b981', dash: true },
  { key: 'inherits_from', label: 'Inherits from', color: '#ec4899' },
];

export default function Sidebar({
  settings,
  onSettingsChange,
  onSearch,
  onQuery,
  onLayoutChange,
  onFit,
  onReset,
  onToggleLabels,
  onApplyDegree,
  floating,
}: Props) {
  const searchRef = useRef<HTMLInputElement>(null);
  const queryRef = useRef<HTMLTextAreaElement>(null);
  const [querying, setQuerying] = useState(false);

  const handleSearch = () => {
    const q = searchRef.current?.value.trim();
    if (q) onSearch(q);
  };

  const handleQuery = async () => {
    const q = queryRef.current?.value.trim();
    if (!q || querying) return;
    setQuerying(true);
    try {
      await onQuery(q);
      if (queryRef.current) {
        queryRef.current.value = '';
      }
    } finally {
      setQuerying(false);
    }
  };

  const toggleEdge = (key: keyof EdgeFilters) => {
    onSettingsChange({
      edgeFilters: { ...settings.edgeFilters, [key]: !settings.edgeFilters[key] },
    });
  };

  return (
    <aside className={`${styles.sidebar} ${floating ? styles.floating : ''}`}>
      <div className={styles.logo}>Mimir</div>

      {/* Search */}
      <div className={styles.section}>
        <input
          ref={searchRef}
          className={styles.input}
          placeholder="Search knowledge base..."
          onKeyDown={e => e.key === 'Enter' && handleSearch()}
        />
        <button className={`${styles.btn} ${styles.btnAccent}`} onClick={handleSearch}>
          Search
        </button>
      </div>

      {/* Query */}
      <div className={styles.section}>
        <textarea
          ref={queryRef}
          className={styles.textarea}
          placeholder="Ask a question..."
          rows={3}
          onKeyDown={e => {
            if (e.key === 'Enter' && !e.shiftKey) {
              e.preventDefault();
              handleQuery();
            }
          }}
        />
        <button
          className={`${styles.btn} ${styles.btnPurple}`}
          onClick={handleQuery}
          disabled={querying}
        >
          {querying ? 'Generating...' : 'Ask'}
        </button>
      </div>

      {/* Controls push to bottom */}
      <div className={styles.controls}>
        {/* Layout */}
        <h3 className={styles.groupLabel}>Layout</h3>
        <div className={styles.layoutGrid}>
          {LAYOUTS.map(l => (
            <button
              key={l.id}
              className={`${styles.controlBtn} ${settings.layout === l.id ? styles.active : ''}`}
              onClick={() => onLayoutChange(l.id)}
            >
              {l.label}
            </button>
          ))}
        </div>

        {/* View */}
        <h3 className={styles.groupLabel}>View</h3>
        <button className={styles.controlBtn} onClick={onFit}>Fit to screen</button>
        <button className={styles.controlBtn} onClick={onReset}>Reset zoom</button>
        <button className={styles.controlBtn} onClick={onToggleLabels}>
          {settings.labelsVisible ? 'Hide labels' : 'Show labels'}
        </button>

        {/* Min degree */}
        <h3 className={styles.groupLabel}>Min connections</h3>
        <div className={styles.filterRow}>
          <input
            type="range"
            min={0}
            max={20}
            step={1}
            value={settings.minDegree}
            onChange={e =>
              onSettingsChange({ minDegree: parseInt(e.target.value, 10) })
            }
          />
          <span className={styles.filterVal}>{settings.minDegree}</span>
          <button
            className={styles.applyBtn}
            onClick={onApplyDegree}
          >
            Apply
          </button>
        </div>

        {/* Physics */}
        <h3 className={styles.groupLabel}>Physics</h3>
        <label className={styles.toggleLabel}>
          <input
            type="checkbox"
            checked={settings.floatingMode}
            onChange={e => onSettingsChange({ floatingMode: e.target.checked })}
          />
          <span>Float mode</span>
        </label>
        <div className={styles.subGroup}>
          <span className={styles.subLabel}>Repulsion</span>
          <div className={styles.filterRow}>
            <input
              type="range"
              min={1000}
              max={200000}
              step={5000}
              value={settings.repulsionStrength}
              onChange={e =>
                onSettingsChange({ repulsionStrength: parseInt(e.target.value, 10) })
              }
            />
            <span className={styles.filterVal}>
              {settings.repulsionStrength >= 1000
                ? `${Math.round(settings.repulsionStrength / 1000)}k`
                : settings.repulsionStrength}
            </span>
          </div>
        </div>

        {/* Relationships */}
        <h3 className={styles.groupLabel}>Relationships</h3>
        {EDGE_TYPES.map(et => (
          <label key={et.key} className={styles.toggleLabel}>
            <input
              type="checkbox"
              checked={settings.edgeFilters[et.key]}
              onChange={() => toggleEdge(et.key)}
            />
            <span>{et.label}</span>
            <span
              className={styles.edgeDot}
              style={{
                background: et.dash ? 'transparent' : et.color,
                border: et.dash ? `2px dashed ${et.color}` : 'none',
              }}
            />
          </label>
        ))}
      </div>
    </aside>
  );
}
