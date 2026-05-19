// ─── Neural Evolution Data — Phase 1 Query Classifier ─────────────────

import { CodeExample, DependencyTrace, ArchitectureLayer } from './architecture_explainer';

// ─── Code Examples ─────────────────────────────────────────────────────

export const neuralCodeExamples: CodeExample[] = [
  {
    file: 'src/mimir/query_classifier.py',
    line: 77,
    title: 'Neural Network Architecture (10→8→2)',
    code: [
      'class SimpleQueryClassifier:',
      '    def __init__(self, input_dim=10, hidden_dim=8):',
      '        self.W1 = np.random.randn(input_dim, hidden_dim) * 0.1',
      '        self.b1 = np.zeros(hidden_dim)',
      '        self.W2 = np.random.randn(hidden_dim, 2) * 0.1',
      '        self.b2 = np.zeros(2)',
    ].join('\n'),
    explanation: 'A 3-layer neural network: 10 input features → 8 hidden neurons (ReLU) → 2 output classes (softmax). Only 1.1KB when saved!',
    plainExplanation: 'Think of this like a tiny brain with 10 sensors, 8神经 cells in the middle, and 2 output neurons that say "structural" or "semantic".',
  },
  {
    file: 'src/mimir/query_classifier.py',
    line: 130,
    title: 'Feature Extraction (10 Input Features)',
    code: [
      'def extract_features(query: str) -> np.ndarray:',
      '    # Structural keyword presence',
      '    struct_hits = sum(1 for kw in KEYWORDS if kw in query)',
      '    features.append(struct_hits / len(KEYWORDS))',
      '    # Query length, patterns, question words...',
      '    return np.array(features)',
    ].join('\n'),
    explanation: 'Extracts 10 numerical features from queries: keyword counts, query length, special patterns ("how does", "connect to"), and question word indicators.',
    plainExplanation: 'We turn your question into 10 numbers. Like: "how many structural keywords?" (0.3), "how long is the query?" (0.5), "does it start with how?" (1.0).',
  },
  {
    file: 'src/mimir/openspace_bridge.py',
    line: 616,
    title: 'Integration: Neural First, LLM Fallback',
    code: [
      '# Try neural classifier first (~$0.000001 per query)',
      'classifier = load_model()',
      'if classifier is not None:',
      '    label, confidence = classifier.predict_with_confidence(query)',
      '    if confidence >= 0.6:',
      '        return label  # Neural classification!',
      '# Fallback to LLM (~$0.0015 per query)',
      'llm = OpenAI(model="gpt-3.5-turbo")',
      'response = llm.complete(classification_prompt)',
    ].join('\n'),
    explanation: 'The _classify_query method now tries the neural classifier first. Only if the neural network is uncertain (confidence < 0.6) does it fall back to the expensive LLM call.',
    plainExplanation: 'Mimir tries the cheap tiny brain first ($0.000001). Only if it\'s unsure does it ask the expensive big brain ($0.0015). This saves 99.9%!',
  },
];

// ─── Dependency Traces ─────────────────────────────────────────────────

export const neuralDependencyTraces: DependencyTrace[] = [
  { from: 'openspace_bridge.py', to: 'query_classifier.py', type: 'imports', line: 618 },
  { from: 'query_classifier.py', to: 'numpy', type: 'imports', line: 16 },
  { from: 'query_classifier.py', to: 'pickle', type: 'imports', line: 12 },
  { from: 'openspace_bridge.py', to: 'LLM (gpt-3.5-turbo)', type: 'calls', line: 645 },
];

// ─── Architecture Layer ────────────────────────────────────────────────

export const neuralLayer: ArchitectureLayer = {
  id: 'neural-evolution',
  tier: 2,
  label: 'Neural Evolution Layer',
  subtitle: 'Phase 1: Lightweight Query Classification',
  icon: '🧠',
  color: '#a855f7',
  overview: 'A 10→8→2 neural network classifies queries as "structural" or "semantic" in <1ms, replacing expensive LLM calls with 99.9% cost reduction.',
  plainOverview: 'A tiny AI brain (1.1KB!) reads your question and decides if it\'s about connections or meanings. It\'s 1500x cheaper than asking GPT-3.5!',
  modules: [
    {
      title: 'SimpleQueryClassifier',
      file: 'src/mimir/query_classifier.py',
      description: 'The neural network: 10 input features → 8 hidden neurons → 2 output classes. Trained to 100% accuracy on 30 examples.',
      plainDescription: 'The tiny brain. 10 numbers go in (how many keywords, query length, etc.), 8 neurons think about it, 2 neurons output "structural" or "semantic".',
      keyExports: ['predict', 'predict_with_confidence', 'train'],
      codeExamples: [neuralCodeExamples[0], neuralCodeExamples[1]],
      dependencyTraces: [neuralDependencyTraces[0], neuralDependencyTraces[1]],
    },
    {
      title: 'Classification Integration',
      file: 'src/mimir/openspace_bridge.py',
      description: 'Modified _classify_query() to use neural classifier first, LLM fallback only when uncertain. Tracks savings automatically.',
      plainDescription: 'The glue code. When you ask a question, it asks the tiny brain first. Only if the tiny brain says "I\'m not sure" does it ask the big expensive brain.',
      keyExports: ['_classify_query', 'track_classification'],
      codeExamples: [neuralCodeExamples[2]],
      dependencyTraces: [neuralDependencyTraces[2], neuralDependencyTraces[3]],
    },
    {
      title: 'Cost Tracking',
      file: 'src/mimir/query_classifier.py',
      description: 'Tracks classification method used (neural/llm/keyword) and calculates cumulative savings vs always using LLM.',
      plainDescription: 'The accountant. Keeps track of how much money we\'ve saved by using the tiny brain instead of the expensive one.',
      keyExports: ['track_classification', 'get_savings_report'],
      codeExamples: [],
      dependencyTraces: [],
    },
  ],
  sequence: [
    {
      step: 1,
      module: 'User Query',
      action: 'query: "How does auth connect to db?"',
      plainAction: 'You ask: "How does auth connect to the database?"',
      inputs: ['natural language query'],
      outputs: ['query text'],
    },
    {
      step: 2,
      module: 'Feature Extractor',
      action: 'extract_features(query) → [0.3, 0.5, 1.0, ...]',
      plainAction: 'Turn question into 10 numbers',
      inputs: ['query text'],
      outputs: ['10 feature values'],
    },
    {
      step: 3,
      module: 'Neural Network (10→8→2)',
      action: 'classifier.predict_with_confidence(features)',
      plainAction: 'Tiny brain thinks for <1ms',
      inputs: ['10 feature values'],
      outputs: ['label', 'confidence'],
    },
    {
      step: 4,
      module: 'Decision Point',
      action: 'if confidence >= 0.6: return label',
      plainAction: 'Is the tiny brain confident? (usually yes: 99%+)',
      inputs: ['label', 'confidence'],
      outputs: ['classification result'],
    },
    {
      step: 5,
      module: 'LLM Fallback (rare)',
      action: 'llm.complete(classification_prompt)',
      plainAction: 'Ask the expensive brain (only if tiny brain is unsure)',
      inputs: ['query text'],
      outputs: ['llm classification'],
    },
  ],
};

// ─── Animation Config (Animation Brief Format) ───────────────────

export const neuralAnimations = {
  networkVisualization: {
    element: 'neural network nodes and connections',
    trigger: 'on load',
    fromState: { opacity: 0, translateY: 20, scale: 0.95 },
    toState: { opacity: 1, translateY: 0, scale: 1 },
    duration: '800ms',
    easing: 'cubic-bezier(0.16, 1, 0.3, 1)',
    stagger: '60ms between each node',
    repeat: 'loop with pulse',
    feel: 'like neurons firing in sequence, a wave of activation',
  },
  costCounter: {
    element: 'savings counter',
    trigger: 'on load',
    fromState: { opacity: 0, translateY: -10 },
    toState: { opacity: 1, translateY: 0 },
    duration: '500ms',
    easing: 'cubic-bezier(0.16, 1, 0.3, 1)',
    feel: 'like a number flipping over on a calculator display',
  },
  queryDemo: {
    element: 'interactive demo card',
    trigger: 'on hover',
    fromState: { scale: 1, boxShadow: '0 0 0 rgba(168, 85, 247, 0)' },
    toState: { scale: 1.02, boxShadow: '0 10px 30px rgba(168, 85, 247, 0.4)' },
    duration: '300ms',
    easing: 'cubic-bezier(0.16, 1, 0.3, 1)',
    feel: 'like a card being lifted off the table',
  },
};

// ─── Savings Calculator Data ──────────────────────────────────────

export const savingsData = {
  llmCostPerQuery: 0.0015,
  neuralCostPerQuery: 0.000001,
  savingsPercentage: 99.9,
  scenarios: [
    { queriesPerMonth: 1000, annualSavings: 18 },
    { queriesPerMonth: 10000, annualSavings: 180 },
    { queriesPerMonth: 100000, annualSavings: 1800 },
  ],
};
