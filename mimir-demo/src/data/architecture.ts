// ─── Architecture Flow Data ─────────────────────────────────────────────────
export interface ArchStep {
  title: string;
  subtitle: string;
  description: string;
  icon: string;
  color: string;
  tier: number; // 1 = top, 4 = bottom
  position: number; // horizontal position within tier
  inputs?: string[];
  outputs?: string[];
}

export interface ArchLayer {
  tier: number;
  label: string;
  steps: ArchStep[];
}

export const architectureFlow: ArchLayer[] = [
  {
    tier: 1,
    label: 'User Layer',
    steps: [
      {
        title: 'User Query',
        subtitle: 'Natural Language',
        description: 'Users ask questions in plain English. No need to know file names or code structure.',
        icon: '💬',
        color: '#6366f1',
        tier: 1,
        position: 0,
        inputs: ['User input'],
        outputs: ['Parsed query'],
      },
      {
        title: 'MCP Client',
        subtitle: 'OpenCode / Claude',
        description: 'The MCP-compatible client sends structured requests to the Mimir server.',
        icon: '📡',
        color: '#8b5cf6',
        tier: 1,
        position: 1,
        inputs: ['User request'],
        outputs: ['Tool calls'],
      },
    ],
  },
  {
    tier: 2,
    label: 'Orchestration Layer',
    steps: [
      {
        title: 'LangGraph Router',
        subtitle: 'Workflow Dispatch',
        description: 'Routes requests to the appropriate workflow: simple search, full RAG, or multi-turn agent.',
        icon: '🔀',
        color: '#f59e0b',
        tier: 2,
        position: 0,
        inputs: ['Parsed query'],
        outputs: ['Workflow selection'],
      },
      {
        title: 'RAG Pipeline',
        subtitle: '4-Step Retrieval',
        description: 'Embed → Search → Assemble → Generate. The core path for answering questions.',
        icon: '🔄',
        color: '#10b981',
        tier: 2,
        position: 1,
        inputs: ['Query vector'],
        outputs: ['LLM response'],
      },
      {
        title: 'Knowledge Agent',
        subtitle: 'Multi-Turn Loop',
        description: 'Iterative agent that calls tools, observes results, and loops until confident.',
        icon: '🧠',
        color: '#ec4899',
        tier: 2,
        position: 2,
        inputs: ['Complex query'],
        outputs: ['Synthesized answer'],
      },
    ],
  },
  {
    tier: 3,
    label: 'Retrieval Layer',
    steps: [
      {
        title: 'Embedding Engine',
        subtitle: 'text-embedding-3-small',
        description: 'Converts text to 1536-dimension vectors using OpenAI or compatible API.',
        icon: '🧮',
        color: '#3b82f6',
        tier: 3,
        position: 0,
        inputs: ['Text'],
        outputs: ['1536-dim vectors'],
      },
      {
        title: 'Vector Store',
        subtitle: 'Cosine Similarity Search',
        description: 'Stores and searches document embeddings. Incremental updates — no full rebuilds.',
        icon: '💾',
        color: '#10b981',
        tier: 3,
        position: 1,
        inputs: ['Embeddings'],
        outputs: ['Similar documents'],
      },
      {
        title: 'Content Filter',
        subtitle: 'Security Gate',
        description: 'Blocks API keys, secrets, and sensitive content before it reaches the LLM.',
        icon: '🛡️',
        color: '#ef4444',
        tier: 3,
        position: 2,
        inputs: ['Search results'],
        outputs: ['Safe results'],
      },
    ],
  },
  {
    tier: 4,
    label: 'Infrastructure Layer',
    steps: [
      {
        title: 'File Watcher',
        subtitle: 'Incremental Indexing',
        description: 'SHA-256 hashing detects changes. Only changed files are re-indexed.',
        icon: '📂',
        color: '#f59e0b',
        tier: 4,
        position: 0,
        inputs: ['File changes'],
        outputs: ['Updated index'],
      },
      {
        title: 'MCP Server',
        subtitle: 'Tool Bridge',
        description: 'Exposes graph traversal, search, and file reading tools via MCP protocol.',
        icon: '🔌',
        color: '#8b5cf6',
        tier: 4,
        position: 1,
        inputs: ['Tool requests'],
        outputs: ['Structured data'],
      },
      {
        title: 'Manifest DB',
        subtitle: 'Index State',
        description: 'Tracks all indexed files, their hashes, and update timestamps.',
        icon: '📋',
        color: '#6366f1',
        tier: 4,
        position: 2,
        inputs: ['Hashes'],
        outputs: ['Change detection'],
      },
    ],
  },
];