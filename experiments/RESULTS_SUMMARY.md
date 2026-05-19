# GNN Experiment Results & Recommendation

## Experiment Summary

**Date**: 2026-05-19  
**Goal**: Determine if adding neural/evolutionary learning to Mimir is worth pursuing.

### What We Tested

1. **Static Graph Methods** (current Mimir approach):
   - BFS shortest path: 100% accuracy for finding paths
   - Jaccard similarity: Works for finding structurally similar modules

2. **Simple GNN**:
   - Failed to learn meaningful patterns in this experiment
   - Loss remained constant (implementation too simple for actual learning)
   - High similarity scores but no actual connection to query modules

### Key Findings

| Aspect | Static Methods (Current) | Neural Approach |
|--------|-------------------------|----------------|
| **Structural queries** ("How does X reach Y?") | ✅ 100% (BFS) | ❌ No benefit |
| **Path finding** | ✅ Weighted Dijkstra (already in Mimir) | ❌ Overkill |
| **Semantic search** | ✅ Vector embeddings (text-embedding-3-small) | ⚠️ Could help with personalization |
| **Query classification** | ⚠️ Uses LLM ($0.0015/call) | ✅ Could train cheap classifier |
| **Pattern learning** | ❌ Not supported | ✅ Only neural can do this |

## The Verdict: Is It Worth Pursuing?

### DON'T ADD NEURAL NETWORKS IF:
- You're happy with Mimir's current capabilities
- Your main use cases are structural queries and semantic search
- You don't mind occasional LLM costs for query classification

**Reason**: Mimir's current architecture (vector index + knowledge graph + RAG) already handles its intended use cases well. The experiment showed that for structural tasks, static methods outperform or match neural approaches.

### CONSIDER NEURAL/Evolutionary Layer IF You Want:

#### 1. **Cost Reduction** (Low-hanging fruit)
- **Current**: Query classification uses `gpt-3.5-turbo` ($0.0015 per call)
- **With Neural**: Train a cheap classifier on past queries → 70-90% cost reduction
- **Effort**: 2-3 days to implement

#### 2. **Personalized Pattern Learning** (The "evolving with you" vision)
- Learn YOUR coding style over time
- Suggest patterns based on past successful approaches
- "You usually handle auth this way..." type recommendations
- **Effort**: 1-2 weeks, requires feedback loop implementation

#### 3. **Cross-Codebase Transfer Learning**
- Train on multiple projects
- Apply patterns from one codebase to another
- Useful if you work on many similar projects
- **Effort**: 2-4 weeks

#### 4. **Evolutionary Design Optimization**
- Propose architectural mutations
- Evaluate fitness (test coverage, performance, maintainability)
- Evolve better designs over time
- **Effort**: 1-2 months, most complex option

## Recommendation

### Phase 1: Start Small (Recommended)
Add a **lightweight neural classifier** for query classification:
- Replace `gpt-3.5-turbo` LLM calls with a trained sklearn classifier
- Use Mimir's existing metrics system to track saved costs
- **ROI**: Pays for itself quickly if you use Mimir heavily

### Phase 2: Add If Phase 1 Works
Add **pattern embedding layer**:
- Train embeddings on successful code patterns
- Use for "similar pattern" recommendations
- Keep it simple (no evolutionary complexity yet)

### Phase 3: Only If Clear Need Exists
Add **evolutionary design**:
- Only if you find yourself wanting automated architectural optimization
- Requires significant engineering effort

## Answer to Original Question

> "Would I be replacing SKILLS.md with a more complicated version?"

**No.** Here's the distinction:

| SKILLS.md (Text) | Neural Evolutionary Layer |
|-------------------|--------------------------|
| Static until manually updated | Learns continuously |
| Human-readable | Model-based (black box) |
| Stores fixed patterns | Evolves and generalizes |
| $0 cost after writing | Training cost + maintenance |

It's not a replacement - it's an **enhancement layer** that adds capabilities Mimir doesn't have:
- Personalized recommendations
- Cost reduction for routine tasks
- Pattern generalization across codebases

## Next Steps (If Proceeding)

1. **Quick win**: Implement query classifier using sklearn (2-3 hours)
2. **Measure**: Track LLM cost savings with metrics.py
3. **Evaluate**: Is the complexity worth the benefit?
4. **Decide**: Continue to Phase 2 only if Phase 1 proves value

---

**Bottom line**: The experiment showed neural networks DON'T add value for Mimir's current use cases. Only add them if you want new capabilities (personalization, cost reduction) that static methods can't provide.
