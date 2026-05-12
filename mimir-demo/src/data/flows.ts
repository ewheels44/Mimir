export interface FlowStep {
  id: string;
  label: string;
  sublabel?: string;
  icon: string;
  explanation: string;
  rationale: string;
  // New: plain English alternatives for the ELI5 toggle
  plainLabel?: string;
  plainExplanation?: string;
  state: Record<string, { value: string | number | boolean; type: 'string' | 'number' | 'boolean' | 'array' | 'object' }>;
  timing?: string;
  // New: sub-steps for in-depth breakdown
  subSteps?: {
    title: string;
    detail: string;
    visual?: string; // emoji or short visual hint
    plainTitle?: string;
    plainDetail?: string;
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
      plainLabel: 'Check Which Files Changed',
      sublabel: 'SHA-256 Hashing',
      icon: '🔍',
      explanation: 'Mimir scans watched directories and computes a SHA-256 hash for every file. Files whose hashes match the manifest are skipped entirely — no wasted work.',
      plainExplanation: 'Mimir looks at every file in your project and creates a unique "fingerprint" for each one. If the fingerprint hasn\'t changed since last time, it skips that file. Only files that actually changed get read again.',
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
        { title: 'Walk Directory Tree', plainTitle: 'List All Files', detail: 'Recursively traverse all configured code_dirs and doc_dirs, collecting file paths and metadata.', plainDetail: 'Mimir walks through every folder in your project and makes a list of all the files it finds.', visual: '📁➡️📄' },
        { title: 'Read File Contents', plainTitle: 'Read Each File', detail: 'Each file is read in binary mode and fed into the SHA-256 hashing function.', plainDetail: 'Mimir reads the contents of every file to calculate its unique fingerprint.', visual: '📄➡️🔐' },
        { title: 'Compare with Manifest', plainTitle: 'Compare to Previous Fingerprints', detail: 'The computed hash is compared against manifest.json. If it matches, the file is marked as unchanged and skipped.', plainDetail: 'Mimir checks: "Does this fingerprint match what I recorded last time?" If yes → skip. If no → this file changed!', visual: '🔐📋✅' },
      ],
    },
    {
      id: 'parse',
      label: 'Parse Documents',
      plainLabel: 'Read and Break Up Changed Files',
      sublabel: 'LlamaIndex Reader',
      icon: '📄',
      explanation: 'For the 3 changed files, LlamaIndex reads and parses the content. Markdown, Python, JavaScript, and other formats are supported. Recursive chunking splits large files into optimal segments.',
      plainExplanation: 'Mimir reads each changed file and breaks it into smaller, overlapping pieces — like cutting a long article into paragraphs. This makes it easier to find the right piece later when you ask a question.',
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
        { title: 'Format Detection', plainTitle: 'Figure Out File Type', detail: 'Mimir detects file type (Markdown, Python, JS, etc.) and selects the appropriate LlamaIndex reader.', plainDetail: 'Mimir looks at the file extension (.py, .md, .ts) and picks the right tool to read it.', visual: '📄 🏷️' },
        { title: 'Content Extraction', plainTitle: 'Extract the Text', detail: 'Code blocks, comments, and documentation are extracted. Metadata like filename and path are attached.', plainDetail: 'Mimir pulls out the actual code and comments, and tags each piece with where it came from.', visual: '📄➡️📝' },
        { title: 'Recursive Chunking', plainTitle: 'Cut Into Smaller Pieces', detail: 'Large documents are split into ~512 token chunks with 50-token overlap to preserve context across boundaries.', plainDetail: 'Big files get cut into smaller chunks (like paragraphs) with a little overlap so nothing important gets split apart.', visual: '📝✂️📦' },
      ],
    },
    {
      id: 'embed',
      label: 'Generate Embeddings',
      plainLabel: 'Turn Text Into Numbers',
      sublabel: 'OpenAI Embedding API',
      icon: '🧮',
      explanation: 'Each of the 12 document chunks is sent to OpenAI text-embedding-3-small to generate a 1536-dimensional vector. These vectors capture semantic meaning — similar concepts end up close together in vector space.',
      plainExplanation: 'Mimir sends each piece of text to an AI model that converts it into a long list of numbers (a vector). Think of it like giving every paragraph a unique "address" in a giant map — similar paragraphs end up near each other.',
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
        { title: 'Batch API Request', plainTitle: 'Send All Chunks At Once', detail: 'All 12 chunks are sent in a single batch API request to minimize latency and maximize throughput.', plainDetail: 'Instead of sending chunks one by one, Mimir bundles them all together in one request — it\'s like mailing all your letters in one envelope.', visual: '📦📤' },
        { title: 'Vector Generation', plainTitle: 'Convert to Coordinates', detail: 'The embedding model converts each chunk into a 1536-dimensional floating-point vector in a shared semantic space.', plainDetail: 'The AI model gives each chunk a set of 1,536 numbers that represent its meaning — like GPS coordinates for ideas.', visual: '📝➡️🧮' },
        { title: 'Normalization', plainTitle: 'Standardize the Vectors', detail: 'Vectors are L2-normalized to unit length so that cosine similarity reduces to a simple dot product.', plainDetail: 'Mimir adjusts all vectors to the same "length" so the comparison is fair — like making sure all runners start at the same line.', visual: '📐' },
      ],
    },
    {
      id: 'store',
      label: 'Update Vector Store',
      plainLabel: 'Save New Addresses to the Filing Cabinet',
      sublabel: 'Persistent Storage',
      icon: '💾',
      explanation: 'New embeddings are inserted into the vector store alongside existing ones. Only the 12 new vectors are written — the remaining 835 existing vectors are untouched.',
      plainExplanation: 'Mimir puts the new vector "addresses" into its filing cabinet on disk. The old ones stay exactly where they are — no reorganizing needed. This is why updates are fast.',
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
        { title: 'Open Store Connection', plainTitle: 'Open the Filing Cabinet', detail: 'Mimir opens the persistent vector store (stored on disk) in append mode.', plainDetail: 'Mimir opens the drawer where all the vector "addresses" are kept, ready to add new ones.', visual: '💾🔓' },
        { title: 'Insert New Vectors', plainTitle: 'Add New Entries', detail: 'The 12 new embedding vectors + their metadata are appended. Existing vectors remain untouched.', plainDetail: 'Mimir slides the 12 new addresses into the cabinet without touching any of the 835 existing ones.', visual: '➕📦➡️💾' },
        { title: 'Flush to Disk', plainTitle: 'Close and Lock the Cabinet', detail: 'The updated store is flushed to ensure data durability before returning.', plainDetail: 'Mimir makes sure everything is saved to disk so nothing is lost if the power goes out.', visual: '💾💿' },
      ],
    },
    {
      id: 'manifest',
      label: 'Update Manifest',
      plainLabel: 'Update the Master Ledger',
      sublabel: 'Index State Tracking',
      icon: '📋',
      explanation: 'The manifest.json is updated with the new file hashes and timestamp. This serves as the source of truth for the next incremental run, enabling future change detection.',
      plainExplanation: 'Mimir writes down in its notebook: "These files have these fingerprints, and I checked them at this time." Next time, it just checks the notebook to know what to skip.',
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
        { title: 'Merge Hashes', plainTitle: 'Update the Notebook', detail: 'Old manifest entries are merged with the new hashes from this indexing run.', plainDetail: 'Mimir updates its notebook with the new fingerprints while keeping all the old ones that haven\'t changed.', visual: '📋✏️' },
        { title: 'Write Manifest', plainTitle: 'Save the Notebook', detail: 'The updated manifest with all 42 indexed files is written back to disk as JSON.', plainDetail: 'The notebook is saved so the next time Mimir runs, it knows exactly what it already looked at.', visual: '📋💾' },
        { title: 'Timestamp Update', plainTitle: 'Write the Date', detail: 'The last_updated timestamp is set to now, marking the index as current.', plainDetail: 'Mimir writes today\'s date on the notebook so it knows when it was last checked.', visual: '🕐✅' },
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
      plainLabel: 'Ask a Question in Plain English',
      sublabel: 'Natural Language Input',
      icon: '💬',
      explanation: 'The user asks: "How does the OpenSpace bridge handle circuit breaker failures?" — a natural language question about project-specific code.',
      plainExplanation: 'You simply ask a question in normal English — just like you would ask a colleague. No need to know file names or code structure.',
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
        { title: 'Query Reception', plainTitle: 'Receive the Question', detail: 'The query arrives via MCP or CLI. Mimir parses metadata: top_k=5 results, temperature=0 (deterministic).', plainDetail: 'Mimir receives your question and figures out what you\'re asking for — how many results you want, how precise the answer should be, etc.', visual: '💬📥' },
        { title: 'Intent Classification', plainTitle: 'Figure Out What You Need', detail: 'The system categorizes this as a RAG query (not an agent or simple search).', plainDetail: 'Mimir decides: "This is a knowledge question — I need to look up information in the codebase."', visual: '🏷️' },
        { title: 'Parameter Setup', plainTitle: 'Set Search Parameters', detail: 'Search parameters are configured: how many results to return, similarity threshold, and response style.', plainDetail: 'Mimir sets the knobs: "Find 5 relevant pieces, be precise, don\'t make things up."', visual: '⚙️' },
      ],
    },
    {
      id: 'embed_query',
      label: 'Embed Query',
      plainLabel: 'Convert Your Question to Numbers',
      sublabel: 'Same Model, Same Space',
      icon: '🔢',
      explanation: 'The query text is sent to OpenAI text-embedding-3-small, generating a 1536-dimensional vector that lands in the same vector space as the document embeddings.',
      plainExplanation: 'Mimir converts your question into the same "address format" (numbers) as all the documents, so it can compare them on the same map.',
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
        { title: 'Tokenization', plainTitle: 'Break Into Words', detail: 'The query text is tokenized into subword tokens that the model understands.', plainDetail: 'Mimir breaks your sentence into small word-pieces the AI model can process.', visual: '💬➡️🔤🔤🔤' },
        { title: 'Embedding Generation', plainTitle: 'Generate the Address', detail: 'The model produces a 1536-dimensional dense vector capturing the semantic meaning.', plainDetail: 'The AI gives your question a set of coordinates on the meaning map, just like it did for every document.', visual: '🔤➡️🧮' },
        { title: 'Normalization', plainTitle: 'Standardize', detail: 'The query vector is L2-normalized to ensure cosine similarity works correctly.', plainDetail: 'Mimir adjusts the numbers so the comparison is fair and consistent.', visual: '🧮➡️📐' },
      ],
    },
    {
      id: 'search',
      label: 'Vector Search',
      plainLabel: 'Find the Most Relevant Pieces',
      sublabel: 'Cosine Similarity',
      icon: '🔍',
      explanation: 'The query vector is compared against all 847 document vectors using cosine similarity. The top 5 most similar chunks are retrieved with their scores. Results above the 0.6 threshold are kept.',
      plainExplanation: 'Mimir checks how close your question\'s "address" is to every document\'s address, then picks the 5 most relevant ones — like finding the nearest neighbors on a map.',
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
        { title: 'Index Scan', plainTitle: 'Search All Documents', detail: 'Mimir scans all 847 vectors in the index, computing cosine similarity for each against the query.', plainDetail: 'Mimir measures the "distance" between your question and every document it has indexed.', visual: '📊🔍' },
        { title: 'Score Ranking', plainTitle: 'Rank by Relevance', detail: 'Results are sorted by similarity score. Top 5 are selected for context assembly.', plainDetail: 'Mimir sorts results by relevance and picks the top 5 — like a search engine ranking results.', visual: '📈' },
        { title: 'Threshold Filter', plainTitle: 'Filter Out Irrelevant Results', detail: 'Chunks below the 0.6 similarity threshold would be excluded (none in this case — all 5 passed).', plainDetail: 'If any result is too unrelated (below 0.6 score), Mimir throws it out. All 5 passed the quality check!', visual: '✅✅✅✅✅' },
      ],
    },
    {
      id: 'assemble',
      label: 'Assemble Context',
      plainLabel: 'Package the Evidence',
      sublabel: 'Prompt Engineering',
      icon: '📚',
      explanation: 'Retrieved chunks are formatted with source attribution tags ([SOURCE] filename (score)) and combined into the LLM prompt. The total context is 1,847 tokens, fitting within the 2,500 token budget.',
      plainExplanation: 'Mimir takes the 5 best matches, labels each one with where it came from and how relevant it is, and bundles them into a prompt for the AI to read.',
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
        { title: 'Source Tagging', plainTitle: 'Label Each Piece', detail: 'Each retrieved chunk is prefixed with a source tag containing the filename and similarity score.', plainDetail: 'Mimir stamps each piece with its source and relevance score so the AI knows where it came from.', visual: '🏷️📄' },
        { title: 'Token Budgeting', plainTitle: 'Stay Within the Word Limit', detail: 'The system calculates available tokens (2,500 budget - query tokens) and prioritizes chunks by score.', plainDetail: 'The AI has a limited "memory" for this conversation. Mimir puts the most important pieces first and cuts off the rest.', visual: '📏💰' },
        { title: 'Prompt Assembly', plainTitle: 'Build the Prompt', detail: 'System instructions, source-tagged context, and the user question are concatenated into the final prompt.', plainDetail: 'Mimir combines instructions + the labeled evidence + your question into one complete prompt for the AI.', visual: '📝➕❓➡️📜' },
      ],
    },
    {
      id: 'generate',
      label: 'Generate Response',
      plainLabel: 'Get the Final Answer',
      sublabel: 'gemini-3.1-flash-lite',
      icon: '✨',
      explanation: 'The LLM synthesizes an answer based on the retrieved context and original question. It returns a comprehensive answer referencing the source files, in ~1.2 seconds using 2,100 prompt + 245 completion tokens.',
      plainExplanation: 'The AI reads the instructions and evidence, then writes you a complete answer with citations — like a research paper with footnotes pointing back to the exact code that proves it.',
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
        { title: 'LLM Inference', plainTitle: 'The AI Thinks', detail: 'The formatted prompt is sent to the gemini-3.1-flash-lite model for response generation.', plainDetail: 'The AI reads everything Mimir gave it and starts writing the answer, one word at a time.', visual: '📜🧠' },
        { title: 'Token Streaming', plainTitle: 'Watch It Type', detail: 'The model generates tokens one at a time, streamed back as they arrive for responsiveness.', plainDetail: 'You see the answer appear word by word in real-time, like watching someone type.', visual: '🔤🔤🔤➡️💬' },
        { title: 'Response Delivery', plainTitle: 'Get Your Answer', detail: 'The complete answer is delivered with in-line source citations for verification.', plainDetail: 'The final answer includes footnotes telling you exactly which files and lines prove what it said.', visual: '✅💬📎' },
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
      plainLabel: 'Check If I\'m Ready',
      sublabel: 'Index Health Lookup',
      icon: '🔎',
      explanation: 'Before starting, the agent verifies the knowledge base exists and checks its stats: 42 source files indexed, 847 documents available, project root confirmed.',
      plainExplanation: 'Before doing any work, the agent checks: "Do I have my notes ready?" It counts how many files were indexed and when they were last updated. If there are no notes, it tells you to create them first.',
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
        { title: 'Index Lookup', plainTitle: 'Look Up My Notes', detail: 'Agent queries the manifest to check if a valid index exists for this project.', plainDetail: 'The agent checks the notebook to see if notes have been taken.', visual: '📋🔎' },
        { title: 'Health Check', plainTitle: 'Check If Notes Are Fresh', detail: 'Verifies document count (847) and checks if the index is recent enough to be reliable.', plainDetail: 'The agent checks: "Are these notes recent enough to trust?"', visual: '💚📊' },
        { title: 'Readiness Decision', plainTitle: 'Decide What to Do', detail: 'If the index is healthy, the agent proceeds. Otherwise, it would prompt the user to re-index first.', plainDetail: 'Good notes? Let\'s go! No notes? Let\'s take some first.', visual: '✅➡️🟢' },
      ],
    },
    {
      id: 'think',
      label: 'LLM Decides',
      plainLabel: 'Think About What to Do',
      sublabel: 'Tool Selection & Planning',
      icon: '🤔',
      explanation: 'The LLM analyzes the question and decides which tool to call. In this case: "I should use graph_neighbors to find what modules the OpenSpace bridge connects to, then read those files."',
      plainExplanation: 'The AI thinks like a detective: "To answer this question, I need to find out what files are connected to the bridge. Let me look at the map of the codebase." It picks the right tool for the job.',
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
        { title: 'Question Decomposition', plainTitle: 'Break Question Into Sub-Questions', detail: 'The LLM breaks "How does the bridge handle failures?" into sub-questions: What does the bridge connect to? Where are error handlers?', plainDetail: 'The AI breaks the big question into smaller ones: "What connects to the bridge?" and "Where are the error handlers?"', visual: '❓➡️📋' },
        { title: 'Tool Selection', plainTitle: 'Pick the Right Tool', detail: 'From available tools (graph_neighbors, search, file_reader), graph_neighbors is chosen to explore the dependency graph.', plainDetail: 'The AI decides: "I need to look at the code map to find connected files."', visual: '🔧🧠➡️📌' },
        { title: 'Parameter Planning', plainTitle: 'Set How Deep to Look', detail: 'The LLM sets depth=2 to explore two levels of the dependency graph for comprehensive coverage.', plainDetail: '"Let me look 2 levels deep so I don\'t miss anything important."', visual: '⚙️' },
      ],
    },
    {
      id: 'execute',
      label: 'Execute Tool',
      plainLabel: 'Follow the Map',
      sublabel: 'MCP Tool Call',
      icon: '⚡',
      explanation: 'The graph_neighbors tool is called via MCP protocol. It traverses the codebase\'s dependency graph and returns 8 connected nodes including callers, callees, and related modules.',
      plainExplanation: 'The AI follows the roads on the code map starting from the bridge file. It finds 8 connected locations — files that call or are called by the bridge. This is like asking "What\'s near this landmark?" on a map.',
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
        { title: 'MCP Request', plainTitle: 'Send a Request', detail: 'A structured MCP tool_call request is sent with the tool name and parameters.', plainDetail: 'The AI sends a structured request: "Use graph_neighbors to explore openspace_bridge.py, depth 2."', visual: '📤📦' },
        { title: 'Graph Traversal', plainTitle: 'Walk the Code Map', detail: 'The tool walks the dependency graph starting from openspace_bridge.py, following "calls" and "imports_from" edges.', plainDetail: 'The tool walks along the roads on the map, following arrows that show which files call which.', visual: '🕸️➡️🔍' },
        { title: 'Result Collection', plainTitle: 'Collect the Findings', detail: '8 connected nodes are found and returned as structured JSON with node metadata and edge types.', plainDetail: 'The map reveals 8 connected locations. Each one has a label saying what kind of connection it has.', visual: '📦📥' },
      ],
    },
    {
      id: 'observe',
      label: 'Observe Results',
      plainLabel: 'Look at What I Found',
      sublabel: 'State Update & Memory',
      icon: '👁️',
      explanation: 'Tool results are appended to the conversation state. The agent now "sees" 8 connected modules including config.py and openspace_bridge.py. It decides whether to explore further or synthesize an answer.',
      plainExplanation: 'The AI now has 8 new pieces of information in its working memory. It looks at them and thinks: "I found config.py and the bridge file, but I still don\'t know how errors are handled. Let me look deeper."',
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
        { title: 'State Merge', plainTitle: 'Add to Memory', detail: 'The 8 neighbor nodes are merged into the agent\'s working memory, linked to their source files and edge types.', plainDetail: 'The AI adds these 8 findings to its mental notebook, with tags showing how each connects.', visual: '➕🧠' },
        { title: 'Progress Evaluation', plainTitle: 'Am I Done Yet?', detail: 'The LLM checks: "Do I have enough to answer?" With 8 nodes but no error handling details yet, it decides to loop.', plainDetail: 'The AI checks its notes: "I have the map, but I still need the error handling chapter."', visual: '🤔❓' },
        { title: 'Loop Decision', plainTitle: 'Go Deeper', detail: 'A second iteration is triggered to dive deeper into the error handling modules discovered.', plainDetail: '"I need more info." The AI goes back to explore the files it found.', visual: '🔄➡️🔁' },
      ],
    },
    {
      id: 'respond',
      label: 'Final Response',
      plainLabel: 'Tell Me the Answer',
      sublabel: 'Synthesized Answer',
      icon: '✅',
      explanation: 'After 2 loop iterations and gathering information from 24 nodes, the agent synthesizes a comprehensive answer. It traces failure handling from the bridge through config fallbacks, citing specific files and line references.',
      plainExplanation: 'The AI has now explored the whole code map. It sits down and writes you a complete answer — like a detective presenting a case with all the evidence, citing exactly which files prove each point.',
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
        { title: 'Synthesis', plainTitle: 'Put It All Together', detail: 'The LLM combines all gathered information into a coherent answer, linking together the circuit breaker, fallback config, and error propagation patterns.', plainDetail: 'The AI connects all the pieces: "When the bridge fails, config provides fallbacks, and here\'s exactly how that works..."', visual: '🧩➡️📝' },
        { title: 'Source Attribution', plainTitle: 'Cite the Evidence', detail: 'Each claim in the answer is tagged with its source file for verifiability.', plainDetail: 'Every claim has a footnote pointing to the exact file and line, so you can check.', visual: '📎✍️' },
        { title: 'Final Delivery', plainTitle: 'Present the Answer', detail: 'The complete answer is returned to the user with confidence score (0.92) and total cost metrics.', plainDetail: 'You get a clear, cited answer plus a confidence score and how much it cost to generate.', visual: '💬✅📊' },
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
      plainLabel: 'Check If the Bridge Is Turned On',
      sublabel: 'Feature Flag Gate',
      icon: '🔌',
      explanation: 'The very first check: is the bridge enabled? The environment variable MIMIR_OPENSPACE_ENABLED controls this. If false, the entire bridge is bypassed instantly.',
      plainExplanation: 'Before doing anything, Mimir checks: "Am I allowed to talk to OpenSpace?" It\'s like a light switch — if it\'s off, nothing goes through. This can be flipped in an emergency.',
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
        { title: 'Environment Read', plainTitle: 'Check the Switch', detail: 'The system reads MIMIR_OPENSPACE_ENABLED from environment variables or application config.', plainDetail: 'Mimir looks at its settings to see if the bridge is turned on or off.', visual: '⚙️🔌' },
        { title: 'Gate Decision', plainTitle: 'Go or Stop', detail: 'If true, continue to the bridge. If false, skip everything and return empty results instantly.', plainDetail: 'Switch on? Let\'s go! Switch off? Stop right here and return nothing.', visual: '🔀' },
        { title: 'Logging', plainTitle: 'Write It Down', detail: 'The decision is logged for audit trails and debugging.', plainDetail: 'Mimir writes down what it decided so you can check later.', visual: '📝' },
      ],
    },
    {
      id: 'circuit_check',
      label: 'Circuit Breaker',
      plainLabel: 'Check If the Connection Is Healthy',
      sublabel: 'Failure Tracking',
      icon: '⚡',
      explanation: 'If recent API calls to OpenSpace have failed, the circuit may be OPEN. After 3 consecutive failures, calls are blocked for 60 seconds to prevent cascading failures.',
      plainExplanation: 'Think of this like a fuse in your house. If too many things go wrong (3 failures in a row), the fuse "trips" and stops all calls for 60 seconds. This prevents a small problem from taking down everything.',
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
        { title: 'Failure Counter', plainTitle: 'Count Recent Failures', detail: 'The system tracks consecutive failures. Currently at 0/3 threshold.', plainDetail: 'Mimir counts how many things went wrong in a row: "0 out of 3 — all good!"', visual: '🔴🔴🔴⬜' },
        { title: 'State Machine', plainTitle: 'Three Possible States', detail: 'Three states: CLOSED (normal), OPEN (blocked), HALF_OPEN (testing recovery).', plainDetail: 'CLOSED = everything works. OPEN = too many failures, stop trying. HALF_OPEN = "let me try one more thing to see if it\'s fixed."', visual: '🔄' },
        { title: 'Timeout', plainTitle: 'Wait and Try Again', detail: 'After 60 seconds, the circuit transitions to HALF_OPEN and allows one test request.', plainDetail: 'After waiting 60 seconds, Mimir cautiously tries one request to see if the problem is fixed.', visual: '⏱️➡️🧪' },
      ],
    },
    {
      id: 'cache_check',
      label: 'LRU Cache Lookup',
      plainLabel: 'Check If I Already Know the Answer',
      sublabel: 'TTL-based Cache',
      icon: '💨',
      explanation: 'Before making any API call, Mimir checks a local LRU cache. Recently queried results (within 600 seconds) are returned instantly without external API calls.',
      plainExplanation: 'Mimir remembers recent answers for 10 minutes. If you ask the same question again, it gives you the cached answer instantly — no need to search again. It can remember up to 128 answers at once, and forgets the oldest ones first.',
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
        { title: 'Cache Key Generation', plainTitle: 'Create a Fingerprint', detail: 'The query is hashed into a cache key for O(1) lookup.', plainDetail: 'Mimir creates a unique fingerprint for the question so it can find it quickly in memory.', visual: '🔑' },
        { title: 'LRU Lookup', plainTitle: 'Search Memory', detail: 'The cache is checked. 47/128 slots are in use. This query is a miss.', plainDetail: 'Mimir looks through its memory of 47 saved answers. Not this one — no match.', visual: '🔍💨' },
        { title: 'TTL Validation', plainTitle: 'Check If the Answer Is Still Fresh', detail: 'Even on a hit, the entry must be within the 600-second TTL window.', plainDetail: 'Even if the answer is in memory, Mimir checks: "Is this still recent enough (under 10 minutes old)?"', visual: '⏰✅' },
      ],
    },
    {
      id: 'search',
      label: 'Execute Search',
      plainLabel: 'Search the Knowledge Base',
      sublabel: 'Semantic Vector Search',
      icon: '🔍',
      explanation: 'The query is embedded and searched against the vector store. 847 candidates are scanned, and the top 5 results (scores: 0.89, 0.82, 0.78, 0.71, 0.68) are returned. Freshness score is 0.82 — "recent".',
      plainExplanation: 'Mimir converts the query into numbers and searches its memory of 847 documents. It finds the 5 most relevant pieces, each tagged with how relevant and how recent they are.',
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
        { title: 'Query Embedding', plainTitle: 'Convert Query to Numbers', detail: 'The search query "Build auth middleware" is embedded using the same model used for indexing.', plainDetail: 'Mimir converts the search question into the same number format used for all documents, so they can be compared.', visual: '🔤➡️🧮' },
        { title: 'ANN Search', plainTitle: 'Find the Best Matches', detail: 'Approximate nearest neighbor search finds the 5 most similar vectors out of 847 total.', plainDetail: 'Mimir scans all 847 documents and picks the 5 that are most similar to the query.', visual: '🎯📊' },
        { title: 'Metadata Enrichment', plainTitle: 'Add Labels to Results', detail: 'Each result is enriched with source filename, score, timestamp, and freshness calculation.', plainDetail: 'Each result gets labeled with where it came from, how relevant it is, and how recent it is.', visual: '📎✨' },
      ],
    },
    {
      id: 'filter',
      label: 'Content Filter',
      plainLabel: 'Remove Anything Sensitive',
      sublabel: 'Security & Privacy Layer',
      icon: '🛡️',
      explanation: 'Every result passes through a content filter that checks for sensitive information (API keys, IPs, credentials). Blocked content is redacted and blacklisted filenames are excluded automatically.',
      plainExplanation: 'Before sending anything to the AI, Mimir scans it for secrets like passwords or API keys. If found, they\'re replaced with [REDACTED]. This keeps your private info safe.',
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
        { title: 'Pattern Matching', plainTitle: 'Scan for Secrets', detail: 'Results are scanned against regex patterns for secrets (API keys, tokens, private IPs).', plainDetail: 'Mimir checks every piece of text for things like API keys, passwords, and IP addresses.', visual: '🔍🛡️' },
        { title: 'Filename Filtering', plainTitle: 'Block Sensitive Files', detail: 'Files matching blocked patterns (*.env, *secret*, etc.) are excluded.', plainDetail: 'Files like .env or *secret* are automatically blocked from being sent out.', visual: '🚫' },
        { title: 'Redaction', plainTitle: 'Redact Sensitive Content', detail: 'Any sensitive content found is replaced with [REDACTED] before passing to the LLM.', plainDetail: 'If any secrets are found, they\'re replaced with [REDACTED] so the AI never sees them.', visual: '⬛' },
      ],
    },
    {
      id: 'assemble_bridge',
      label: 'Context Assembly',
      plainLabel: 'Put It All Together',
      sublabel: 'Token-Optimized Packaging',
      icon: '📦',
      explanation: 'Safe results are formatted with source tags and truncated to fit the 2,500 token max_context_tokens budget. Fresh results get priority; stale content may be dropped to stay within limits.',
      plainExplanation: 'Mimir bundles the safe results into a neat package for the AI, making sure the most important and recent info goes in first. If there\'s too much, it trims the oldest stuff to fit.',
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
        { title: 'Priority Sorting', plainTitle: 'Sort by Importance', detail: 'Results are sorted by freshness score first, then by similarity score. Most relevant + recent goes first.', plainDetail: 'Mimir puts the freshest, most relevant results at the top of the list.', visual: '📊⬆️' },
        { title: 'Token Budgeting', plainTitle: 'Fit Within the Word Limit', detail: 'Each result\'s token count is accumulated until the 2,500 token budget is reached. Overflow results are truncated.', plainDetail: 'Mimir counts the words and makes sure everything fits within the AI\'s memory limit. Too much? Cut the least important parts.', visual: '📏💰' },
        { title: 'Context Packaging', plainTitle: 'Wrap It Up', detail: 'The final set of results is formatted with source tags into a single context string ready for the LLM.', plainDetail: 'Everything is neatly packaged with labels so the AI knows exactly what each piece is and where it came from.', visual: '📦🎀' },
      ],
    },
  ],
};

export const allFlows = [indexingFlow, ragFlow, agentFlow, bridgeFlow];