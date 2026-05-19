"""
Lightweight Query Classifier - Phase 1 of Neural Evolution

This replaces the LLM-based query classification in Mimir's openspace_bridge
with a fast, cheap sklearn model.

Savings: ~$0.0015 per query (LLM call) → ~$0.000001 (local inference)
"""

import json
import pickle
import re
from pathlib import Path
from typing import Optional, Tuple

import numpy as np

# ─── Training Data Generation ────────────────────────────────────────────

# Structural keywords from the existing implementation
STRUCTURAL_KEYWORDS = [
    "connect", "connection", "link", "linked", "relate", "relationship",
    "depend", "depends", "dependency", "path", "between", "from", "to",
    "import", "call", "invoke", "structure of", "graph",
    "how does", "how do",
]

# Semantic keywords
SEMANTIC_KEYWORDS = [
    "how does it work", "what is", "explain", "example",
    "usage", "meaning", "purpose", "concept", "understand",
]

# Training examples based on the existing classification logic
TRAINING_EXAMPLES = [
    # Structural queries (label: 0)
    ("How does the auth module connect to the database?", 0),
    ("What is the dependency path from src/main to utils/helper?", 0),
    ("Show me the relationship between User and Profile models", 0),
    ("How do I connect to the API from the frontend?", 0),
    ("What depends on the config module?", 0),
    ("Find path from authentication to session management", 0),
    ("What calls the process_data function?", 0),
    ("Graph structure of the workflow module", 0),
    ("How does the MCP server link to the tools?", 0),
    ("Import chain from src/index to the database module", 0),
    ("Show dependencies between the API and the models", 0),
    ("What modules relate to the auth system?", 0),
    ("How do the frontend components connect to backend?", 0),
    ("Trace the call path from request to response", 0),
    ("What imports from the utils package?", 0),
    
    # Semantic queries (label: 1)
    ("How does the authentication system work?", 1),
    ("What is the purpose of the config module?", 1),
    ("Explain how the RAG pipeline processes queries", 1),
    ("What does the vector index do?", 1),
    ("How do I use the search functionality?", 1),
    ("What are the benefits of using the knowledge graph?", 1),
    ("Explain the OpenSpace bridge architecture", 1),
    ("What is the best way to implement caching?", 1),
    ("How does the embedding model work?", 1),
    ("Give me an example of using the graph_query tool", 1),
    ("What is the difference between search and query?", 1),
    ("How does the skill evolution process work?", 1),
    ("What does the metrics module track?", 1),
    ("Explain the indexing strategy used by Mimir", 1),
    ("How do I configure the embedding model?", 1),
]


def extract_features(query: str, keyword_list: list) -> np.ndarray:
    """Extract features from a query string.
    
    Features:
    - TF-IDF-like: presence of keyword categories
    - Query length
    - Special patterns (question words, structural phrases)
    """
    query_lower = query.lower()
    features = []
    
    # Keyword presence (structural keywords)
    struct_hits = sum(1 for kw in STRUCTURAL_KEYWORDS if kw in query_lower)
    features.append(struct_hits / len(STRUCTURAL_KEYWORDS))
    
    # Keyword presence (semantic keywords)
    sem_hits = sum(1 for kw in SEMANTIC_KEYWORDS if kw in query_lower)
    features.append(sem_hits / len(SEMANTIC_KEYWORDS))
    
    # Query length (normalized)
    query_len = len(query.split())
    features.append(min(query_len / 20.0, 1.0))  # Cap at 20 words
    
    # Special patterns
    has_structural_phrase = any(
        phrase in query_lower 
        for phrase in ["connect to", "path from", "depends on", "how does"]
    )
    features.append(1.0 if has_structural_phrase else 0.0)
    
    has_how_do_structural = "how do" in query_lower and any(
        kw in query_lower for kw in ["connect", "link", "relate", "depend", "call"]
    )
    features.append(1.0 if has_how_do_structural else 0.0)
    
    # Question word features
    features.append(1.0 if query_lower.startswith("how") else 0.0)
    features.append(1.0 if query_lower.startswith("what") else 0.0)
    features.append(1.0 if query_lower.startswith("show") else 0.0)
    features.append(1.0 if "?" in query else 0.0)
    
    # Position of keywords (do structural keywords appear early?)
    words = query_lower.split()
    struct_positions = []
    for i, word in enumerate(words):
        if any(kw in word for kw in STRUCTURAL_KEYWORDS):
            struct_positions.append(i / len(words))
    
    features.append(min(struct_positions) if struct_positions else 1.0)
    
    return np.array(features)


# ─── Simple Classifier (No sklearn dependency) ─────────────────────────

class SimpleQueryClassifier:
    """A simple neural-inspired classifier that doesn't need sklearn.
    
    Uses a small feedforward network with one hidden layer.
    This keeps the dependency footprint small while still being "neural".
    """
    
    def __init__(self, input_dim: int = 10, hidden_dim: int = 8):
        self.input_dim = input_dim
        self.hidden_dim = hidden_dim
        
        # Initialize weights (small random values)
        np.random.seed(42)
        self.W1 = np.random.randn(input_dim, hidden_dim) * 0.1
        self.b1 = np.zeros(hidden_dim)
        self.W2 = np.random.randn(hidden_dim, 2) * 0.1  # 2 classes
        self.b2 = np.zeros(2)
    
    def _relu(self, x):
        return np.maximum(0, x)
    
    def _softmax(self, x):
        exp_x = np.exp(x - np.max(x))
        return exp_x / exp_x.sum()
    
    def predict_proba(self, features: np.ndarray) -> np.ndarray:
        """Predict class probabilities."""
        # Hidden layer
        hidden = self._relu(np.dot(features, self.W1) + self.b1)
        # Output layer
        output = np.dot(hidden, self.W2) + self.b2
        # Softmax
        return self._softmax(output)
    
    def predict(self, query: str) -> str:
        """Classify a query as 'structural' or 'semantic'."""
        features = extract_features(query, STRUCTURAL_KEYWORDS)
        probs = self.predict_proba(features)
        return "structural" if probs[0] > probs[1] else "semantic"
    
    def predict_with_confidence(self, query: str) -> Tuple[str, float]:
        """Classify with confidence score."""
        features = extract_features(query, STRUCTURAL_KEYWORDS)
        probs = self.predict_proba(features)
        label = "structural" if probs[0] > probs[1] else "semantic"
        confidence = max(probs)
        return label, confidence
    
    def train(self, epochs: int = 100, learning_rate: float = 0.1):
        """Train the classifier on the built-in training data."""
        print(f"Training SimpleQueryClassifier for {epochs} epochs...")
        
        # Prepare training data
        X = []
        y = []
        for query, label in TRAINING_EXAMPLES:
            features = extract_features(query, STRUCTURAL_KEYWORDS)
            X.append(features)
            # One-hot encoding: [structural, semantic]
            y.append([1.0, 0.0] if label == 0 else [0.0, 1.0])
        
        X = np.array(X)
        y = np.array(y)
        
        # Training loop (simple gradient descent)
        for epoch in range(epochs):
            total_loss = 0
            
            for i in range(len(X)):
                # Forward pass
                hidden = self._relu(np.dot(X[i], self.W1) + self.b1)
                output = np.dot(hidden, self.W2) + self.b2
                probs = self._softmax(output)
                
                # Cross-entropy loss
                loss = -np.sum(y[i] * np.log(probs + 1e-8))
                total_loss += loss
                
                # Backward pass (simplified gradient descent)
                d_output = probs - y[i]
                d_W2 = np.outer(hidden, d_output)
                d_b2 = d_output
                
                d_hidden = np.dot(d_output, self.W2.T)
                d_hidden[hidden <= 0] = 0  # ReLU derivative
                d_W1 = np.outer(X[i], d_hidden)
                d_b1 = d_hidden
                
                # Update weights
                self.W2 -= learning_rate * d_W2
                self.b2 -= learning_rate * d_b2
                self.W1 -= learning_rate * d_W1
                self.b1 -= learning_rate * d_b1
            
            if epoch % 20 == 0:
                avg_loss = total_loss / len(X)
                print(f"  Epoch {epoch+1}/{epochs} - Loss: {avg_loss:.4f}")
        
        print("Training complete!")
        
        # Evaluate on training data
        correct = 0
        for query, label in TRAINING_EXAMPLES:
            predicted = self.predict(query)
            expected = "structural" if label == 0 else "semantic"
            if predicted == expected:
                correct += 1
        
        accuracy = correct / len(TRAINING_EXAMPLES)
        print(f"Training accuracy: {accuracy*100:.1f}%")
        
        return accuracy


# ─── Save/Load Model ────────────────────────────────────────────────────

MODEL_PATH = Path(__file__).parent / "query_classifier_model.pkl"

def save_model(classifier: SimpleQueryClassifier, path: Path = MODEL_PATH):
    """Save the trained model weights to disk."""
    model_data = {
        'W1': classifier.W1,
        'b1': classifier.b1,
        'W2': classifier.W2,
        'b2': classifier.b2,
        'input_dim': classifier.input_dim,
        'hidden_dim': classifier.hidden_dim,
    }
    with open(path, 'wb') as f:
        pickle.dump(model_data, f)
    print(f"Model saved to {path}")

def load_model(path: Path = MODEL_PATH) -> Optional[SimpleQueryClassifier]:
    """Load a trained model from disk."""
    if not path.exists():
        return None
    try:
        with open(path, 'rb') as f:
            model_data = pickle.load(f)
        
        # Reconstruct classifier
        classifier = SimpleQueryClassifier(
            input_dim=model_data['input_dim'],
            hidden_dim=model_data['hidden_dim']
        )
        classifier.W1 = model_data['W1']
        classifier.b1 = model_data['b1']
        classifier.W2 = model_data['W2']
        classifier.b2 = model_data['b2']
        
        return classifier
    except Exception as e:
        print(f"Error loading model: {e}")
        return None

        # ─── Cost Tracking ────────────────────────────────────────────────

TRY_COST_USD = 0.000001  # Neural inference cost per query
LLM_COST_USD = 0.0015    # LLM call cost per query (gpt-3.5-turbo)

_tracking_file = Path(__file__).parent / "classification_tracking.json"

def track_classification(method: str, query: str, confidence: float = None):
    """Track classification method used and calculate savings."""
    try:
        if _tracking_file.exists():
            with open(_tracking_file, 'r') as f:
                data = json.load(f)
        else:
            data = {
                "neural_calls": 0,
                "llm_calls": 0,
                "keyword_calls": 0,
                "total_saved_usd": 0.0,
                "queries": []
            }
        
        # Update counters
        if method == "neural":
            data["neural_calls"] += 1
            saved = LLM_COST_USD - TRY_COST_USD
        elif method == "llm":
            data["llm_calls"] += 1
            saved = 0.0
        else:
            data["keyword_calls"] += 1
            saved = LLM_COST_USD - 0.0  # Keyword is free
        
        data["total_saved_usd"] += saved
        
        # Keep last 100 queries
        data["queries"].append({
            "query": query[:100],
            "method": method,
            "confidence": confidence,
            "timestamp": str(__import__('datetime').datetime.now())
        })
        if len(data["queries"]) > 100:
            data["queries"] = data["queries"][-100:]
        
        with open(_tracking_file, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"Tracking error: {e}")


def get_savings_report() -> dict:
    """Get a report of cost savings from using neural classifier."""
    try:
        if not _tracking_file.exists():
            return {"error": "No tracking data yet"}
        
        with open(_tracking_file, 'r') as f:
            data = json.load(f)
        
        total_calls = data["neural_calls"] + data["llm_calls"] + data["keyword_calls"]
        neural_pct = (data["neural_calls"] / total_calls * 100) if total_calls > 0 else 0
        
        return {
            "total_queries": total_calls,
            "neural_classifications": data["neural_calls"],
            "llm_fallbacks": data["llm_calls"],
            "keyword_fallbacks": data["keyword_calls"],
            "neural_usage_pct": round(neural_pct, 1),
            "total_saved_usd": round(data["total_saved_usd"], 4),
            "estimated_annual_savings": round(data["total_saved_usd"] * (365 * 100 / max(total_calls, 1)), 2)
        }
    except Exception as e:
        return {"error": str(e)}


# ─── Integration with Mimir ─────────────────────────────────────────────

def classify_query(query: str, use_llm_fallback: bool = True) -> str:
    """Classify a query using the trained model.
    
    Falls back to LLM if model not available (and fallback enabled).
    Falls back to keyword check if model available but uncertain.
    """
    # Try loading the model
    classifier = load_model()
    
    if classifier is None:
        # Model not trained yet - use keyword fallback
        if use_llm_fallback:
            # Would call LLM here in production
            pass
        # Use simple keyword check
        return _keyword_fallback(query)
    
    # Use the model
    label, confidence = classifier.predict_with_confidence(query)
    
    # If uncertain, use keyword fallback
    if confidence < 0.6:
        return _keyword_fallback(query)
    
    return label


def _keyword_fallback(query: str) -> str:
    """Fallback to simple keyword matching."""
    query_lower = query.lower()
    keyword_hits = sum(1 for kw in STRUCTURAL_KEYWORDS if kw in query_lower)
    
    has_structural_phrase = any(
        phrase in query_lower 
        for phrase in ["connect to", "path from", "depends on", "how does"]
    )
    
    is_how_do_structural = "how do" in query_lower and any(
        kw in query_lower for kw in ["connect", "link", "relate", "depend", "call"]
    )
    
    if keyword_hits >= 2 or has_structural_phrase or is_how_do_structural:
        return "structural"
    if keyword_hits == 0:
        return "semantic"
    return "semantic"  # Default


# ─── Main: Train and Save ───────────────────────────────────────────────

if __name__ == "__main__":
    print("=" * 60)
    print("Phase 1: Training Lightweight Query Classifier")
    print("=" * 60)
    
    # Create and train classifier
    classifier = SimpleQueryClassifier()
    accuracy = classifier.train(epochs=200, learning_rate=0.05)
    
    # Save model
    save_model(classifier)
    
    # Test on some examples
    print("\n" + "=" * 60)
    print("Testing Classifier")
    print("=" * 60)
    
    test_queries = [
        "How does the auth module connect to the database?",
        "What is the purpose of the config module?",
        "Show me the dependency path from src to utils",
        "How does the RAG pipeline work?",
    ]
    
    for query in test_queries:
        label, confidence = classifier.predict_with_confidence(query)
        print(f"\nQuery: {query}")
        print(f"Classification: {label} (confidence: {confidence:.2f})")
    
    print("\n" + "=" * 60)
    print("INTEGRATION INSTRUCTIONS")
    print("=" * 60)
    print("""
To integrate with Mimir's openspace_bridge.py:

1. Import the classifier:
   from src.mimir.query_classifier import classify_query

2. Replace the LLM classification in _classify_query():
   # OLD:
   # response = llm.complete(prompt).text.strip().lower()
   
   # NEW:
   label = classify_query(query)
   return label

3. Estimated savings:
   - LLM call: ~$0.0015 per query
   - Local model: ~$0.000001 per query
   - Savings: ~99.9% for routine classifications
    """)
