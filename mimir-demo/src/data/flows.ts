export interface FlowStep {
  id: string;
  label: string;
  sublabel?: string;
  icon: string;
  explanation: string;
  rationale: string;
  state: Record<string, { value: string | number | boolean; type: 'string' | 'number' | 'boolean' | 'array' | 'object' }>;
  timing?: string;
  // New: sub-steps for in-depth breakdown
  subSteps?: {
    title: string;
    detail: string;
    visual?: string; // emoji or short visual hint
  }[];
  // New: data flow arrows showing what moves between steps
  inputs?: string[];
  outputs?: string[];
}

export interface DemoFlow {
  id: string;
  title: string;
  description: string;
  color: string;
  icon: string;
  overview: string; // high-level narrative
  steps: FlowStep[];
}

// ─── Indexing Flow ─────────────────────────────────────────────────────────
export const indexingFlow: DemoFlow = {
  id: 'indexing',
  title: 'Incremental Indexing Flow',
  icon: '📊',
  description: 'Watch how Mimir efficiently indexes new documents by detecting changes through SHA-256 hashing, then incrementally updating the vector store without rebuilding the entire index.',
  overview: 'Mimir watches your project files and only re-indexes what changed. It computes SHA-256 hashes for every file, compares them against the manifest, parses changed documents into chunks, generates embeddings, and updates the vector store — all while preserving the existing index.',
  color: '#3b82f6',
  steps: [
    {
      id: 'detect',
      label: 'Detect Changes',
      sublabel: 'SHA-256 Hashing',
      icon: '🔍',
      explanation: 'Mimir scans watched directories and computes a SHA-256 hash for every file. Files whose hashes match the manifest are skipped entirely — no wasted work.',
      rationale: 'SHA-256 is deterministic and collision-resistant. By comparing content hashes instead of file timestamps, we avoid re-indexing files that only had their mtime changed (e.g., git checkout). This reduces indexing from O(n) to O(changed).',
      inputs: ['file_paths', 'manifest.json'],
      outputs: ['changed_files[]', 'unchanged_files[]'],
      timing: '~45ms for 24 files',
      state: {
        'files_scanned': { value: 24, type: 'number' },
        'hashes_computed': { value: 3, type: 'number' },
        'changed_files': { value: '["config.py", "utils.py", "indexing.py"]', type: 'array' },
        'skipped (unchanged)': { value: 21, type: 'number' },
      },
      subSteps: [
        { title: 'Walk Directory Tree', detail: 'Recursively traverse all configured code_dirs and doc_dirs, collecting file paths and metadata.', visual: '📁➡️📄' },
        { title: 'Read File Contents', detail: 'Each file is read in binary mode and fed into the SHA-256 hashing function.', visual: '📄➡️🔐' },
        { title: 'Compare with Manifest', detail: 'The computed hash is compared against manifest.json. If it matches, the file is marked as unchanged and skipped.', visual: '🔐📋✅' },
      ],
    },
    {
      id: 'parse',
      label: 'Parse Documents',
      sublabel: 'LlamaIndex Reader',
      icon: '📄',
      explanation: 'For the 3 changed files, LlamaIndex reads and parses the content. Markdown, Python, JavaScript, and other formats are supported. Recursive chunking splits large files into optimal segments.',
      rationale: 'LlamaIndex handles various file formats and applies smart chunking strategies to create optimal document segments for embedding. Smaller chunks improve retrieval precision; larger chunks preserve context.',
      inputs: ['changed_files[]'],
      outputs: ['documents[]', 'chunks[]'],
      timing: '~120ms',
      state: {
        'documents_loaded': { value: 3, type: 'number' },
        'total_characters': { value: 15420, type: 'number' },
        'chunk_strategy': { value: 'recursive', type: 'string' },
        'chunks_created': { value: 12, type: 'number' },
      },
      subSteps: [
        { title: 'Format Detection', detail: 'Mimir detects file type (Markdown, Python, JS, etc.) and selects the appropriate LlamaIndex reader.', visual: '📄 🏷️' },
        { title: 'Content Extraction', detail: 'Code blocks, comments, and documentation are extracted. Metadata like filename and path are attached.', visual: '📄➡️📝' },
        { title: 'Recursive Chunking', detail: 'Large documents are split into ~512 token chunks with 50-token overlap to preserve context across boundaries.', visual: '📝✂️📦' },
      ],
    },
    {
      id: 'embed',
      label: 'Generate Embeddings',
      sublabel: 'OpenAI Embedding API',
      icon: '🧮',
      explanation: 'Each of the 12 document chunks is sent to OpenAI text-embedding-3-small to generate a 1536-dimensional vector. These vectors capture semantic meaning — similar concepts end up close together in vector space.',
      rationale: 'The embedding model must match the one used for queries. text-embedding-3-small offers excellent quality at ~$0.00002 per 1K tokens. All vectors are normalized to unit length for consistent cosine similarity.',
      inputs: ['chunks[]'],
      outputs: ['embeddings[] (1536-dim each)'],
      timing: '~800ms (batch API call)',
      state: {
        'model': { value: 'text-embedding-3-small', type: 'string' },
        'dimensions': { value: 1536, type: 'number' },
        'embeddings_generated': { value: 12, type: 'number' },
        'api_cost': { value: '$0.00002', type: 'string' },
      },
      subSteps: [
        { title: 'Batch API Request', detail: 'All 12 chunks are sent in a single batch API request to minimize latency and maximize throughput.', visual: '📦📤' },
        { title: 'Vector Generation', detail: 'The embedding model converts each chunk into a 1536-dimensional floating-point vector in a shared semantic space.', visual: '📝➡️🧮' },
        { title: 'Normalization', detail: 'Vectors are L2-normalized to unit length so that cosine similarity reduces to a simple dot product.', visual: '📐' },
      ],
    },
    {
      id: 'store',
      label: 'Update Vector Store',
      sublabel: 'Persistent Storage',
      icon: '💾',
      explanation: 'New embeddings are inserted into the vector store alongside existing ones. Only the 12 new vectors are written — the remaining 835 existing vectors are untouched.',
      rationale: 'Unlike full rebuilds, incremental indexing preserves the existing index. This makes updates O(changed_files) instead of O(all_files). The store persists to disk (2.4 MB total) for fast loading.',
      inputs: ['embeddings[]', 'metadata[]'],
      outputs: ['vector_store/updated'],
      timing: '~30ms',
      state: {
        'new_vectors_inserted': { value: 12, type: 'number' },
        'total_vectors_in_store': { value: 847, type: 'number' },
        'storage_size': { value: '2.4 MB', type: 'string' },
        'persisted_to_disk': { value: true, type: 'boolean' },
      },
      subSteps: [
        { title: 'Open Store Connection', detail: 'Mimir opens the persistent vector store (stored on disk) in append mode.', visual: '💾🔓' },
        { title: 'Insert New Vectors', detail: 'The 12 new embedding vectors + their metadata are appended. Existing vectors remain untouched.', visual: '➕📦➡️💾' },
        { title: 'Flush to Disk', detail: 'The updated store is flushed to ensure data durability before returning.', visual: '💾💿' },
      ],
    },
    {
      id: 'manifest',
      label: 'Update Manifest',
      sublabel: 'Index State Tracking',
      icon: '📋',
      explanation: 'The manifest.json is updated with the new file hashes and timestamp. This serves as the source of truth for the next incremental run, enabling future change detection.',
      rationale: 'The manifest is the single source of truth. On the next run, comparing file hashes against the manifest determines exactly which files changed. Without it, every run would rebuild the entire index from scratch.',
      inputs: ['changed_files[]', 'hashes[]'],
      outputs: ['manifest.json (updated)'],
      timing: '~5ms',
      state: {
        'last_updated': { value: '2026-05-08T16:39:00Z', type: 'string' },
        'indexed_files': { value: 42, type: 'number' },
        'total_documents': { value: 847, type: 'number' },
        'manifest_version': { value: '1.0', type: 'string' },
      },
      subSteps: [
        { title: 'Merge Hashes', detail: 'Old manifest entries are merged with the new hashes from this indexing run.', visual: '📋✏️' },
        { title: 'Write Manifest', detail: 'The updated manifest with all 42 indexed files is written back to disk as JSON.', visual: '📋💾' },
        { title: 'Timestamp Update', detail: 'The last_updated timestamp is set to now, marking the index as current.', visual: '🕐✅' },
      ],
    },
  ],
};

// ─── RAG Flow ───────────────────────────────────────────────────────────────
export const ragFlow: DemoFlow = {
  id: 'rag',
  title: 'RAG Pipeline',
  icon: '🤖',
  description: 'Experience the Retrieval-Augmented Generation flow: query embedding, semantic search, context assembly, and LLM response generation. This is how Mimir answers natural language questions about your codebase.',
  overview: 'When you ask a question, Mimir embeds it into the same vector space as your indexed documents, finds the most similar chunks via cosine similarity, assembles them into a rich context prompt, and the LLM generates an answer grounded in your actual code.',
  color: '#8b5cf6',
  steps: [
    {
      id: 'query',
      label: 'User Query',
      sublabel: 'Natural Language Input',
      icon: '💬',
      explanation: 'The user asks: "How does the OpenSpace bridge handle circuit breaker failures?" — a natural language question about project-specific code.',
      rationale: 'Users don\'t need to know which files are relevant. Natural language queries are flexible, but they must be embedded to match against the vector store\'s numerical representations.',
      inputs: ['user question (text)'],
      outputs: ['parsed query', 'query parameters'],
      timing: 'User typed in ~3 seconds',
      state: {
        'query_text': { value: 'How does the OpenSpace bridge handle circuit breaker failures?', type: 'string' },
        'top_k': { value: 5, type: 'number' },
        'temperature': { value: 0, type: 'number' },
        'mode': { value: 'rag', type: 'string' },
      },
      subSteps: [
        { title: 'Query Reception', detail: 'The query arrives via MCP or CLI. Mimir parses metadata: top_k=5 results, temperature=0 (deterministic).', visual: '💬📥' },
        { title: 'Intent Classification', detail: 'The system categorizes this as a RAG query (not an agent or simple search).', visual: '🏷️' },
        { title: 'Parameter Setup', detail: 'Search parameters are configured: how many results to return, similarity threshold, and response style.', visual: '⚙️' },
      ],
    },
    {
      id: 'embed_query',
      label: 'Embed Query',
      sublabel: 'Same Model, Same Space',
      icon: '🔢',
      explanation: 'The query text is sent to OpenAI text-embedding-3-small, generating a 1536-dimensional vector that lands in the same vector space as the document embeddings.',
      rationale: 'Using the exact same embedding model is critical — if the query and documents use different models, their vectors would be in incompatible spaces and similarity would be meaningless.',
      inputs: ['query text'],
      outputs: ['query_vector (1536-dim)'],
      timing: '~200ms (API call)',
      state: {
        'query_vector': { value: '[0.023, -0.089, 0.156, ... 1533 more]', type: 'array' },
        'dimensions': { value: 1536, type: 'number' },
        'model': { value: 'text-embedding-3-small', type: 'string' },
      },
      subSteps: [
        { title: 'Tokenization', detail: 'The query text is tokenized into subword tokens that the model understands.', visual: '💬➡️🔤🔤🔤' },
        { title: 'Embedding Generation', detail: 'The model produces a 1536-dimensional dense vector capturing the semantic meaning.', visual: '🔤➡️🧮' },
        { title: 'Normalization', detail: 'The query vector is L2-normalized to ensure cosine similarity works correctly.', visual: '🧮➡️📐' },
      ],
    },
    {
      id: 'search',
      label: 'Vector Search',
      sublabel: 'Cosine Similarity',
      icon: '🔍',
      explanation: 'The query vector is compared against all 847 document vectors using cosine similarity. The top 5 most similar chunks are retrieved with their scores. Results above the 0.6 threshold are kept.',
      rationale: 'Cosine similarity measures the angle between vectors, making it robust to vector length differences. It finds documents that are semantically similar, not just keyword matches — "circuit breaker" can match files about error handling patterns.',
      inputs: ['query_vector', 'vector_store'],
      outputs: ['top_k document chunks + scores'],
      timing: '~15ms (in-memory search)',
      state: {
        'candidates_scanned': { value: 847, type: 'number' },
        'similarity_scores': { value: '[0.89, 0.82, 0.78, 0.71, 0.68]', type: 'array' },
        'retrieved_docs': { value: 5, type: 'number' },
        'similarity_threshold': { value: 0.6, type: 'number' },
      },
      subSteps: [
        { title: 'Index Scan', detail: 'Mimir scans all 847 vectors in the index, computing cosine similarity for each against the query.', visual: '📊🔍' },
        { title: 'Score Ranking', detail: 'Results are sorted by similarity score. Top 5 are selected for context assembly.', visual: '📈' },
        { title: 'Threshold Filter', detail: 'Chunks below the 0.6 similarity threshold would be excluded (none in this case — all 5 passed).', visual: '✅✅✅✅✅' },
      ],
    },
    {
      id: 'assemble',
      label: 'Assemble Context',
      sublabel: 'Prompt Engineering',
      icon: '📚',
      explanation: 'Retrieved chunks are formatted with source attribution tags ([SOURCE] filename (score)) and combined into the LLM prompt. The total context is 1,847 tokens, fitting within the 2,500 token budget.',
      rationale: 'Source tags like [openspace_bridge.py (0.89)] let the LLM (and you) trace answers back. The token budget prevents prompt overflow — results are prioritized by freshness and relevance; stale content may be truncated.',
      inputs: ['retrieved_docs[]'],
      outputs: ['formatted_prompt with context'],
      timing: '~5ms',
      state: {
        'context_length': { value: '1,847 tokens', type: 'string' },
        'sources': { value: '["openspace_bridge.py", "circuit_breaker.py", "config.py"]', type: 'array' },
        'format': { value: '[SOURCE] filename (score)\\ncontent...', type: 'string' },
        'token_budget': { value: 2500, type: 'number' },
      },
      subSteps: [
        { title: 'Source Tagging', detail: 'Each retrieved chunk is prefixed with a source tag containing the filename and similarity score.', visual: '🏷️📄' },
        { title: 'Token Budgeting', detail: 'The system calculates available tokens (2,500 budget - query tokens) and prioritizes chunks by score.', visual: '📏💰' },
        { title: 'Prompt Assembly', detail: 'System instructions, source-tagged context, and the user question are concatenated into the final prompt.', visual: '📝➕❓➡️📜' },
      ],
    },
    {
      id: 'generate',
      label: 'Generate Response',
      sublabel: 'gemini-3.1-flash-lite',
      icon: '✨',
      explanation: 'The LLM synthesizes an answer based on the retrieved context and original question. It returns a comprehensive answer referencing the source files, in ~1.2 seconds using 2,100 prompt + 245 completion tokens.',
      rationale: 'RAG grounds LLM responses in actual code, dramatically reducing hallucinations. The response includes source citations so you can verify. The lite model balances quality, speed, and cost for most queries.',
      inputs: ['formatted_prompt'],
      outputs: ['final_answer (text)'],
      timing: '~1,200ms (LLM generation)',
      state: {
        'model': { value: 'google/gemini-3.1-flash-lite-preview', type: 'string' },
        'prompt_tokens': { value: 2100, type: 'number' },
        'completion_tokens': { value: 245, type: 'number' },
        'total_latency': { value: '1.2s', type: 'string' },
        'sources_cited': { value: 3, type: 'number' },
      },
      subSteps: [
        { title: 'LLM Inference', detail: 'The formatted prompt is sent to the gemini-3.1-flash-lite model for response generation.', visual: '📜🧠' },
        { title: 'Token Streaming', detail: 'The model generates tokens one at a time, streamed back as they arrive for responsiveness.', visual: '🔤🔤🔤➡️💬' },
        { title: 'Response Delivery', detail: 'The complete answer is delivered with in-line source citations for verification.', visual: '✅💬📎' },
      ],
    },
  ],
};

// ─── Knowledge Agent Flow ───────────────────────────────────────────────────
export const agentFlow: DemoFlow = {
  id: 'agent',
  title: 'Knowledge Agent Loop',
  icon: '🧠',
  description: 'Watch the multi-turn agent: it checks the index, decides which tool to call, executes it, observes results, and loops until it has enough information to answer. This is how Mimir handles complex multi-hop questions.',
  overview: 'The agent uses LangGraph to orchestrate an iterative loop. It reasons about what information is needed, selects and calls MCP tools (like graph_neighbors for exploring code dependencies), integrates results, and repeats until it can synthesize a complete answer. Each iteration is transparent and traceable.',
  color: '#10b981',
  steps: [
    {
      id: 'check',
      label: 'Check Knowledge Base',
      sublabel: 'Index Health Lookup',
      icon: '🔎',
      explanation: 'Before starting, the agent verifies the knowledge base exists and checks its stats: 42 source files indexed, 847 documents available, project root confirmed.',
      rationale: 'If no index exists or is empty, the agent can immediately inform the user and offer to index — rather than failing later with confusing errors. This early check saves time and provides clear feedback.',
      inputs: ['project_config'],
      outputs: ['index_metadata', 'document_count'],
      timing: '~5ms',
      state: {
        'has_index': { value: true, type: 'boolean' },
        'source_files': { value: 42, type: 'number' },
        'document_count': { value: 847, type: 'number' },
        'project_root': { value: '/Users/.../Documents/Mimir', type: 'string' },
        'index_freshness': { value: '12 hours ago', type: 'string' },
      },
      subSteps: [
        { title: 'Index Lookup', detail: 'Agent queries the manifest to check if a valid index exists for this project.', visual: '📋🔎' },
        { title: 'Health Check', detail: 'Verifies document count (847) and checks if the index is recent enough to be reliable.', visual: '💚📊' },
        { title: 'Readiness Decision', detail: 'If the index is healthy, the agent proceeds. Otherwise, it would prompt the user to re-index first.', visual: '✅➡️🟢' },
      ],
    },
    {
      id: 'think',
      label: 'LLM Decides',
      sublabel: 'Tool Selection & Planning',
      icon: '🤔',
      explanation: 'The LLM analyzes the question and decides which tool to call. In this case: "I should use graph_neighbors to find what modules the OpenSpace bridge connects to, then read those files."',
      rationale: 'The agent uses tool calling to explore the codebase strategically. The LLM chooses actions based on what will best answer the user\'s question — it can call multiple tools in parallel and plan multi-step exploration.',
      inputs: ['question', 'index_metadata'],
      outputs: ['tool_plan', 'selected_tool', 'tool_args'],
      timing: '~400ms (LLM reasoning)',
      state: {
        'thought_process': { value: 'Use graph_neighbors to find connected modules', type: 'string' },
        'tool_selected': { value: 'graph_neighbors', type: 'string' },
        'args': { value: '{ node_id: "openspace_bridge.py", depth: 2 }', type: 'object' },
        'reasoning': { value: 'Need to understand bridge dependencies first', type: 'string' },
      },
      subSteps: [
        { title: 'Question Decomposition', detail: 'The LLM breaks "How does the bridge handle failures?" into sub-questions: What does the bridge connect to? Where are error handlers?', visual: '❓➡️📋' },
        { title: 'Tool Selection', detail: 'From available tools (graph_neighbors, search, file_reader), graph_neighbors is chosen to explore the dependency graph.', visual: '🔧🧠➡️📌' },
        { title: 'Parameter Planning', detail: 'The LLM sets depth=2 to explore two levels of the dependency graph for comprehensive coverage.', visual: '⚙️' },
      ],
    },
    {
      id: 'execute',
      label: 'Execute Tool',
      sublabel: 'MCP Tool Call',
      icon: '⚡',
      explanation: 'The graph_neighbors tool is called via MCP protocol. It traverses the codebase\'s dependency graph and returns 8 connected nodes including callers, callees, and related modules.',
      rationale: 'Tools encapsulate complex operations (graph traversal, file IO, API calls) behind simple interfaces. The MCP protocol enables any MCP-compatible client (OpenCode, Claude Desktop) to use these tools.',
      inputs: ['tool_name', 'tool_args'],
      outputs: ['structured_result_data'],
      timing: '~25ms (tool execution)',
      state: {
        'tool': { value: 'graph_neighbors', type: 'string' },
        'result_nodes': { value: 8, type: 'number' },
        'edge_types': { value: '["calls", "imports_from"]', type: 'array' },
        'max_depth': { value: 2, type: 'number' },
        'execution_time': { value: '25ms', type: 'string' },
      },
      subSteps: [
        { title: 'MCP Request', detail: 'A structured MCP tool_call request is sent with the tool name and parameters.', visual: '📤📦' },
        { title: 'Graph Traversal', detail: 'The tool walks the dependency graph starting from openspace_bridge.py, following "calls" and "imports_from" edges.', visual: '🕸️➡️🔍' },
        { title: 'Result Collection', detail: '8 connected nodes are found and returned as structured JSON with node metadata and edge types.', visual: '📦📥' },
      ],
    },
    {
      id: 'observe',
      label: 'Observe Results',
      sublabel: 'State Update & Memory',
      icon: '👁️',
      explanation: 'Tool results are appended to the conversation state. The agent now "sees" 8 connected modules including config.py and openspace_bridge.py. It decides whether to explore further or synthesize an answer.',
      rationale: 'This observe step is critical — it gives the LLM actual data to reason about rather than abstract speculation. The conversation history grows with each loop, enabling the agent to accumulate knowledge across multiple hops.',
      inputs: ['tool_result'],
      outputs: ['updated_conversation_state', 'loop_decision'],
      timing: 'Instant',
      state: {
        'neighbors_found': { value: 8, type: 'number' },
        'top_connections': { value: '["config.py", "openspace_bridge.py"]', type: 'array' },
        'conversation_messages': { value: 3, type: 'number' },
        'current_loop': { value: 1, type: 'number' },
        'needs_more_info': { value: true, type: 'boolean' },
      },
      subSteps: [
        { title: 'State Merge', detail: 'The 8 neighbor nodes are merged into the agent\'s working memory, linked to their source files and edge types.', visual: '➕🧠' },
        { title: 'Progress Evaluation', detail: 'The LLM checks: "Do I have enough to answer?" With 8 nodes but no error handling details yet, it decides to loop.', visual: '🤔❓' },
        { title: 'Loop Decision', detail: 'A second iteration is triggered to dive deeper into the error handling modules discovered.', visual: '🔄➡️🔁' },
      ],
    },
    {
      id: 'respond',
      label: 'Final Response',
      sublabel: 'Synthesized Answer',
      icon: '✅',
      explanation: 'After 2 loop iterations and gathering information from 24 nodes, the agent synthesizes a comprehensive answer. It traces failure handling from the bridge through config fallbacks, citing specific files and line references.',
      rationale: 'The multi-turn approach handles complex questions that a single search cannot answer. The agent explores multiple code paths, accumulating context until it can provide a thorough, source-cited answer.',
      inputs: ['full_conversation_state'],
      outputs: ['final_comprehensive_answer'],
      timing: '~200ms (final LLM synthesis)',
      state: {
        'has_answer': { value: true, type: 'boolean' },
        'sources_cited': { value: 3, type: 'number' },
        'confidence': { value: 0.92, type: 'number' },
        'total_tokens_used': { value: 2840, type: 'number' },
        'loops_completed': { value: 2, type: 'number' },
        'nodes_explored': { value: 24, type: 'number' },
      },
      subSteps: [
        { title: 'Synthesis', detail: 'The LLM combines all gathered information into a coherent answer, linking together the circuit breaker, fallback config, and error propagation patterns.', visual: '🧩➡️📝' },
        { title: 'Source Attribution', detail: 'Each claim in the answer is tagged with its source file for verifiability.', visual: '📎✍️' },
        { title: 'Final Delivery', detail: 'The complete answer is returned to the user with confidence score (0.92) and total cost metrics.', visual: '💬✅📊' },
      ],
    },
  ],
};

// ─── OpenSpace Bridge Flow ─────────────────────────────────────────────────
export const bridgeFlow: DemoFlow = {
  id: 'bridge',
  title: 'OpenSpace Bridge with Guardrails',
  icon: '🌉',
  description: 'See how Mimir integrates with OpenSpace while protecting against cascading failures through circuit breakers, caching, and content filtering. This is the production safety layer.',
  overview: 'A bridge between Mimir\'s knowledge base and the OpenSpace SDK. Before any search goes out, Mimir checks a kill switch, circuit breaker state, and cache. Results pass through a content filter before being sent to the LLM. Three layers of protection keep your system safe.',
  color: '#f59e0b',
  steps: [
    {
      id: 'kill_switch',
      label: 'Kill Switch Check',
      sublabel: 'Feature Flag Gate',
      icon: '🔌',
      explanation: 'The very first check: is the bridge enabled? The environment variable MIMIR_OPENSPACE_ENABLED controls this. If false, the entire bridge is bypassed instantly.',
      rationale: 'A kill switch allows instant disable without code changes or redeployment. Critical for emergencies — if Mimir starts causing problems, flipping this switch stops all bridge calls within milliseconds.',
      inputs: ['MIMIR_OPENSPACE_ENABLED env var'],
      outputs: ['continue | bypass'],
      timing: 'Instant',
      state: {
        'env_var': { value: 'MIMIR_OPENSPACE_ENABLED', type: 'string' },
        'enabled': { value: true, type: 'boolean' },
        'result': { value: 'continue', type: 'string' },
      },
      subSteps: [
        { title: 'Environment Read', detail: 'The system reads MIMIR_OPENSPACE_ENABLED from environment variables or application config.', visual: '⚙️🔌' },
        { title: 'Gate Decision', detail: 'If true, continue to the bridge. If false, skip everything and return empty results instantly.', visual: '🔀' },
        { title: 'Logging', detail: 'The decision is logged for audit trails and debugging.', visual: '📝' },
      ],
    },
    {
      id: 'circuit_check',
      label: 'Circuit Breaker',
      sublabel: 'Failure Tracking',
      icon: '⚡',
      explanation: 'If recent API calls to OpenSpace have failed, the circuit may be OPEN. After 3 consecutive failures, calls are blocked for 60 seconds to prevent cascading failures.',
      rationale: 'Circuit breakers are essential for resilience. If the search API is down, we stop trying instead of timing out repeatedly. This prevents thread exhaustion and cascading failures across the system.',
      inputs: ['failure_count', 'last_failure_time'],
      outputs: ['circuit_state: CLOSED | OPEN | HALF_OPEN'],
      timing: 'Instant',
      state: {
        'failure_count': { value: 0, type: 'number' },
        'threshold': { value: 3, type: 'number' },
        'circuit_state': { value: 'CLOSED', type: 'string' },
        'reset_after': { value: '60s', type: 'string' },
      },
      subSteps: [
        { title: 'Failure Counter', detail: 'The system tracks consecutive failures. Currently at 0/3 threshold.', visual: '🔴🔴🔴⬜' },
        { title: 'State Machine', detail: 'Three states: CLOSED (normal), OPEN (blocked), HALF_OPEN (testing recovery).', visual: '🔄' },
        { title: 'Timeout', detail: 'After 60 seconds, the circuit transitions to HALF_OPEN and allows one test request.', visual: '⏱️➡️🧪' },
      ],
    },
    {
      id: 'cache_check',
      label: 'LRU Cache Lookup',
      sublabel: 'TTL-based Cache',
      icon: '💨',
      explanation: 'Before making any API call, Mimir checks a local LRU cache. Recently queried results (within 600 seconds) are returned instantly without external API calls.',
      rationale: 'Caching reduces API calls and latency for repeated or similar queries. The 600-second TTL balances freshness with efficiency. The LRU eviction policy keeps memory usage bounded at 128 entries.',
      inputs: ['query_key'],
      outputs: ['cached_result | cache_miss'],
      timing: '~1ms',
      state: {
        'cache_max_size': { value: 128, type: 'number' },
        'ttl_seconds': { value: 600, type: 'number' },
        'cache_hit': { value: false, type: 'boolean' },
        'current_size': { value: 47, type: 'number' },
      },
      subSteps: [
        { title: 'Cache Key Generation', detail: 'The query is hashed into a cache key for O(1) lookup.', visual: '🔑' },
        { title: 'LRU Lookup', detail: 'The cache is checked. 47/128 slots are in use. This query is a miss.', visual: '🔍💨' },
        { title: 'TTL Validation', detail: 'Even on a hit, the entry must be within the 600-second TTL window.', visual: '⏰✅' },
      ],
    },
    {
      id: 'search',
      label: 'Execute Search',
      sublabel: 'Semantic Vector Search',
      icon: '🔍',
      explanation: 'The query is embedded and searched against the vector store. 847 candidates are scanned, and the top 5 results (scores: 0.89, 0.82, 0.78, 0.71, 0.68) are returned. Freshness score is 0.82 — "recent".',
      rationale: 'Freshness is computed from the index timestamp, allowing downstream systems to know how current the information is. This is critical for fast-moving codebases where stale results could mislead.',
      inputs: ['query_vector', 'vector_store'],
      outputs: ['search_results[] with metadata'],
      timing: '~180ms',
      state: {
        'query': { value: 'Build auth middleware', type: 'string' },
        'results_count': { value: 5, type: 'number' },
        'freshness_score': { value: 0.82, type: 'number' },
        'freshness_label': { value: 'recent', type: 'string' },
        'candidates_scanned': { value: 847, type: 'number' },
      },
      subSteps: [
        { title: 'Query Embedding', detail: 'The search query "Build auth middleware" is embedded using the same model used for indexing.', visual: '🔤➡️🧮' },
        { title: 'ANN Search', detail: 'Approximate nearest neighbor search finds the 5 most similar vectors out of 847 total.', visual: '🎯📊' },
        { title: 'Metadata Enrichment', detail: 'Each result is enriched with source filename, score, timestamp, and freshness calculation.', visual: '📎✨' },
      ],
    },
    {
      id: 'filter',
      label: 'Content Filter',
      sublabel: 'Security & Privacy Layer',
      icon: '🛡️',
      explanation: 'Every result passes through a content filter that checks for sensitive information (API keys, IPs, credentials). Blocked content is redacted and blacklisted filenames are excluded automatically.',
      rationale: 'Mimir never sends secrets or internal infrastructure details to external LLMs. This prevents data leakage. In this case, 0 blocked patterns and 0 redactions were found — all 5 results passed the security check.',
      inputs: ['search_results[]'],
      outputs: ['safe_results[]'],
      timing: '~2ms',
      state: {
        'blocked_patterns_found': { value: 0, type: 'number' },
        'redacted_content': { value: 0, type: 'number' },
        'safe_results': { value: 5, type: 'number' },
        'filtered_out_files': { value: '[]', type: 'array' },
      },
      subSteps: [
        { title: 'Pattern Matching', detail: 'Results are scanned against regex patterns for secrets (API keys, tokens, private IPs).', visual: '🔍🛡️' },
        { title: 'Filename Filtering', detail: 'Files matching blocked patterns (*.env, *secret*, etc.) are excluded.', visual: '🚫' },
        { title: 'Redaction', detail: 'Any sensitive content found is replaced with [REDACTED] before passing to the LLM.', visual: '⬛' },
      ],
    },
    {
      id: 'assemble_bridge',
      label: 'Context Assembly',
      sublabel: 'Token-Optimized Packaging',
      icon: '📦',
      explanation: 'Safe results are formatted with source tags and truncated to fit the 2,500 token max_context_tokens budget. Fresh results get priority; stale content may be dropped to stay within limits.',
      rationale: 'The token budget prevents prompt overflow and controls LLM cost. Without it, large codebases could easily exceed context limits. Fresh results are always prioritized — a result from yesterday beats one from 3 months ago.',
      timing: '~3ms',
      inputs: ['safe_results[]', 'token_budget'],
      outputs: ['final_context_string'],
      state: {
        'max_context_tokens': { value: 2500, type: 'number' },
        'results_truncated': { value: 0, type: 'number' },
        'format': { value: '[SOURCE] (fresh, score=0.89)\\ntext...', type: 'string' },
        'context_ready': { value: true, type: 'boolean' },
      },
      subSteps: [
        { title: 'Priority Sorting', detail: 'Results are sorted by freshness score first, then by similarity score. Most relevant + recent goes first.', visual: '📊⬆️' },
        { title: 'Token Budgeting', detail: 'Each result\'s token count is accumulated until the 2,500 token budget is reached. Overflow results are truncated.', visual: '📏💰' },
        { title: 'Context Packaging', detail: 'The final set of results is formatted with source tags into a single context string ready for the LLM.', visual: '📦🎀' },
      ],
    },
  ],
};

export const allFlows = [indexingFlow, ragFlow, agentFlow, bridgeFlow];