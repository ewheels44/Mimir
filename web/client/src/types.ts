// ── Graph ─────────────────────────────────────────────────────────────────────

export interface NodeMetadata {
  file_path?: string;
  file_name?: string;
  file_type?: string;
  file_size?: number;
  creation_date?: string;
  last_modified_date?: string;
  function_count?: number;
  class_count?: number;
  total_children?: number;
  module_path?: string;
  external?: boolean;
  line_number?: number;
}

export interface GraphNode {
  id: string;
  label: string;
  type: 'code' | 'document' | 'module' | 'function' | 'class';
  metadata: NodeMetadata;
}

export interface GraphEdge {
  id: string;
  source: string;
  target: string;
  label: string;
  type: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

// ── Settings (persisted to sessionStorage) ────────────────────────────────────

export interface EdgeFilters {
  calls: boolean;
  imports_module: boolean;
  imports_from: boolean;
  inherits_from: boolean;
}

export interface GraphSettings {
  minDegree: number;
  layout: string;
  labelsVisible: boolean;
  floatingMode: boolean;
  repulsionStrength: number;
  edgeFilters: EdgeFilters;
}

export const DEFAULT_SETTINGS: GraphSettings = {
  minDegree: 0,
  layout: 'cose',
  labelsVisible: true,
  floatingMode: true,
  repulsionStrength: 10000,
  edgeFilters: {
    calls: true,
    imports_module: true,
    imports_from: true,
    inherits_from: true,
  },
};

// ── Results panel ─────────────────────────────────────────────────────────────

export interface SearchResult {
  title: string;
  snippet: string;
  source: string;
}

export interface ResultsState {
  visible: boolean;
  title: string;
  type: 'search' | 'query';
  items: SearchResult[];
  query?: string;
}

// ── Insights ──────────────────────────────────────────────────────────────────

export interface ClusterData {
  id: number;
  size: number;
  nodeIds: string[];
}

export interface BridgeNode {
  id: string;
  label: string;
  score: number;
}

export interface InsightData {
  nodeCount: number;
  edgeCount: number;
  clusterCount: number;
  isolatedCount: number;
  bridges: BridgeNode[];
  insight: string;
}
