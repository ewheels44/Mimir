# Mimir Neural Evolution - Future Phases Implementation Plan

> **Current Status**: Phase 1 COMPLETE ✅  
> **Last Updated**: 2026-05-20  
> **Goal**: Structured roadmap for implementing neural evolution features in Mimir

---

## Overview

| Phase | Name | Status | Est. Effort | Value |
|-------|------|--------|-------------|-------|
| 1 | Neural Query Classifier | ✅ COMPLETE | 3 hours | 99.9% cost reduction |
| 2 | Pattern Embedding Layer | 📋 PLANNED | 1-2 weeks | Personalized recommendations |
| 3 | Cross-Codebase Transfer | 📋 PLANNED | 2-4 weeks | Multi-project learning |
| 4 | Evolutionary Design | 📋 PLANNED | 1-2 months | Automated architecture optimization |

---

## Phase 1: Neural Query Classifier ✅ COMPLETE

**Completed**: 2026-05-19

### What Was Built
- **`src/mimir/query_classifier.py`**: 10→8→2 neural network
- **Integration**: `openspace_bridge.py` uses neural first, LLM fallback
- **Cost Tracking**: `classification_tracking.json`
- **Visualization**: `mimir-demo/src/components/NeuralEvolution.tsx`

### Results
- **Training accuracy**: 100%
- **Model size**: 1.1KB
- **Cost reduction**: 99.9% ($0.0015 → $0.000001/query)
- **Speed**: <1ms (vs 500ms LLM)

### Files Modified/Created
```
src/mimir/query_classifier.py              (NEW - 362 lines)
src/mimir/query_classifier_model.pkl       (NEW - 1.1KB)
src/mimir/openspace_bridge.py            (MODIFIED - added neural first)
mimir-demo/src/components/NeuralEvolution.tsx  (NEW - 532 lines)
mimir-demo/src/data/neural_evolution.ts       (NEW - 196 lines)
mimir-demo/src/styles/neural.css             (NEW - 314 lines)
PHASE1_COMPLETE.md                        (NEW - summary)
```

---

## Phase 2: Pattern Embedding Layer 📋 PLANNED

**Goal**: Learn and recommend coding patterns based on successful implementations in the codebase.

### What It Will Do
1. **Extract code patterns** from successful code (e.g., "auth patterns", "error handling patterns")
2. **Train embeddings** on these patterns (separate from structural graph)
3. **Recommend patterns** when similar tasks are attempted
4. **Learn from feedback**: "Yes, this pattern works" / "No, use different approach"

### Technical Approach
```
Codebase → AST Analysis → Pattern Extraction → Embedding Model
                                    ↓
                            Store in .knowledge/pattern_embeddings/
                                    ↓
                    Query: "How do I handle auth?"
                                    ↓
                    Retrieve: "Use pattern X (like you did in modules A, B, C)"
```

### Implementation Steps

#### Step 1: Pattern Extraction (3-4 hours)
- **File**: `src/mimir/pattern_extractor.py`
- Extract reusable patterns:
  - Error handling blocks
  - Authentication flows
  - Database query patterns
  - API endpoint structures
- Output: `patterns.json` with code + metadata

#### Step 2: Embedding Model (2-3 hours)
- **File**: `src/mimir/pattern_embedder.py`
- Use existing `text-embedding-3-small` (reuse from config)
- Generate embeddings for each pattern
- Store in `.knowledge/pattern_embeddings.json`

#### Step 3: Recommendation Engine (4-5 hours)
- **File**: `src/mimir/pattern_recommender.py`
- Input: Query/task description
- Output: Top-k similar patterns from codebase
- Integrate with `enrich_task()` in openspace_bridge

#### Step 4: Feedback Loop (2-3 hours)
- Track which patterns user accepts/rejects
- Fine-tune embeddings based on feedback
- Store feedback in `pattern_feedback.json`

#### Step 5: MCP Tool (1-2 hours)
- **New MCP tool**: `mimir-knowledge_pattern_search`
- Allow agents to query for patterns

### Files to Create/Modify
```
src/mimir/pattern_extractor.py           (NEW - ~300 lines)
src/mimir/pattern_embedder.py            (NEW - ~200 lines)
src/mimir/pattern_recommender.py         (NEW - ~250 lines)
src/mimir/pattern_feedback.json          (NEW - feedback storage)
.knowledge/pattern_embeddings.json      (NEW - generated)
mcp_server_llamaindex.py                 (MODIFY - add tool)
```

### Success Criteria
- [ ] Pattern extraction finds 10+ patterns in Mimir codebase
- [ ] Recommendation accuracy >80% (manual eval)
- [ ] Feedback loop improves recommendations over time
- [ ] Integration with `enrich_task()` works

### Estimated Effort
**Total**: 12-17 hours (1-2 weeks part-time)

---

## Phase 3: Cross-Codebase Transfer Learning 📋 PLANNED

**Goal**: Train on multiple projects, apply patterns from one codebase to another.

### What It Will Do
1. **Train on Project A** (e.g., a Django project)
2. **Apply to Project B** (e.g., a FastAPI project)
3. **Transfer patterns**: "This Django auth pattern → similar FastAPI pattern"

### Technical Approach
```
Project A (Django) → Extract patterns → Train embedding space
                                          ↓
                              Shared embedding space
                                          ↓
Project B (FastAPI) → Map to space → Retrieve similar patterns
```

### Implementation Steps

#### Step 1: Multi-Project Index (3-4 hours)
- Extend `config.py` to support multiple project roots
- Create shared index in `.knowledge/shared/`
- Track which project each pattern comes from

#### Step 2: Transfer Model (5-6 hours)
- **File**: `src/mimir/transfer_model.py`
- Use techniques like:
  - Domain adaptation (simple approach)
  - Siamese networks (if needed)
- Map patterns from different codebases to same embedding space

#### Step 3: Cross-Project Search (3-4 hours)
- Modify `enrich_task()` to search across projects
- Add project filter: "only show patterns from Django projects"
- Output: "Similar pattern in Project A (Django), can apply here"

### Files to Create/Modify
```
src/mimir/transfer_model.py              (NEW - ~400 lines)
src/mimir/shared_index.py                (MODIFY - multi-project)
config.py                                (MODIFY - multi-project config)
.knowledge/shared/                        (NEW - shared index)
```

### Success Criteria
- [ ] Successfully transfers patterns between 2+ projects
- [ ] Transfer accuracy >70% (human eval)
- [ ] Performance impact <10% slowdown

### Estimated Effort
**Total**: 2-4 weeks part-time

---

## Phase 4: Evolutionary Design Optimization 📋 PLANNED

**Goal**: Propose architectural mutations, evaluate fitness, evolve better designs over time.

### What It Will Do
1. **Propose mutations**: "Try dependency injection here", "Extract this to a function"
2. **Evaluate fitness**: Test coverage, performance, maintainability metrics
3. **Evolve**: Keep designs with high fitness, discard low-fitness ones
4. **Suggest**: "Based on your past 50 changes, here's the optimal structure"

### Technical Approach
```
Current Design → Mutate → Evaluate (tests, coverage, performance)
                    ↓
            Fitness Score (0-100)
                    ↓
            Keep if better → Update population
                    ↓
            Suggest best design to user
```

### Implementation Steps

#### Step 1: Design Representation (1 week)
- **File**: `src/mimir/design_genome.py`
- Encode code structure as "genome":
  - Module dependencies
  - Function complexity
  - Test coverage
  - Performance metrics

#### Step 2: Mutation Operators (1 week)
- **File**: `src/mimir/mutation_ops.py`
- Mutations:
  - Extract function
  - Inline function
  - Change data structure
  - Add/remove dependencies
  - Refactor to pattern X

#### Step 3: Fitness Evaluation (1 week)
- **File**: `src/mimir/fitness_evaluator.py`
- Metrics:
  - Test coverage (from pytest-cov)
  - Cyclomatic complexity (from radon)
  - Performance (from benchmarks)
  - Code duplication (from pylint)

#### Step 4: Evolutionary Loop (1-2 weeks)
- **File**: `src/mimir/evolution_engine.py`
- Population size: 10-20 designs
- Generations: Run until improvement plateaus
- Selection: Tournament selection
- Crossover: Combine two designs

#### Step 5: Integration (1 week)
- New MCP tool: `mimir-knowledge_suggest_design`
- Returns: "Consider refactoring X to Y (fitness: 85 vs current 70)"

### Files to Create
```
src/mimir/design_genome.py              (NEW - ~300 lines)
src/mimir/mutation_ops.py               (NEW - ~400 lines)
src/mimir/fitness_evaluator.py           (NEW - ~350 lines)
src/mimir/evolution_engine.py            (NEW - ~500 lines)
tests/test_evolution.py                  (NEW - integration tests)
```

### Success Criteria
- [ ] Successfully proposes 5+ design improvements on Mimir codebase
- [ ] Fitness scores correlate with human judgment (r > 0.7)
- [ ] No "harmful" mutations (that break tests) are suggested
- [ ] User can accept/reject suggestions

### Estimated Effort
**Total**: 1-2 months part-time (significant engineering)

### ⚠️ Prerequisites
- Phase 2 (Pattern Embedding) should be complete
- Need robust test suite in target codebase
- Need clear fitness metrics defined

---

## Implementation Priority

### If You Want Quick Wins (Next 1-2 weeks)
→ **Implement Phase 2** (Pattern Embedding)
- Immediate value: personalized recommendations
- Builds on Phase 1 (neural networks)
- Manageable effort (~15 hours)

### If You Work on Multiple Projects
→ **Implement Phase 3** (Cross-Codebase Transfer)
- Only if you actually have this use case
- Requires Phase 2 as foundation

### If You Want Cutting-Edge Research
→ **Implement Phase 4** (Evolutionary Design)
- Coolest technically, but highest effort
- Make sure you have a real need for automated design optimization
- Consider starting with a simpler subset (just pattern suggestions)

---

## How to Resume Implementation

### For Phase 2 (Pattern Embedding)
```bash
# 1. Create branch
cd /Users/ethanwheeler/Documents/Mimir
git checkout -b feature/phase2-pattern-embeddings

# 2. Start with pattern extraction
# Edit: src/mimir/pattern_extractor.py

# 3. Test on Mimir codebase
python src/mimir/pattern_extractor.py

# 4. Commit progress
git add -A && git commit -m "Phase 2: Add pattern extractor"
```

### For Phase 3/4
```bash
# Similar pattern - create feature branch
git checkout -b feature/phase3-cross-codebase
# or
git checkout -b feature/phase4-evolutionary-design
```

---

## Experiments to Run Before Each Phase

### Before Phase 2
- [ ] Manually identify 10 patterns in Mimir codebase
- [ ] Verify patterns are reusable across modules
- [ ] Check if existing `code_relationships.json` can be leveraged

### Before Phase 3
- [ ] Have 2+ codebases to test with
- [ ] Verify they have somewhat similar tech stacks
- [ ] Check if embeddings transfer between Python projects

### Before Phase 4
- [ ] Define clear fitness metrics for YOUR use case
- [ ] Ensure target codebase has >80% test coverage
- [ ] Have baseline architecture to compare against

---

## Resources

### Papers to Read (for Phase 4)
- "Genetic Programming for Automated Design" (Koza, 1992)
- "Neural Architecture Search" (Zoph & Le, 2016)
- "Evolutionary Code Optimization" (Langdon, 2019)

### Libraries to Consider
- **Phase 2**: `sentence-transformers` (for pattern embeddings)
- **Phase 3**: `adaptdl` (domain adaptation)
- **Phase 4**: `deap` (evolutionary algorithms in Python)

### Existing Mimir Components to Reuse
- `src/mimir/config.py` - Configuration management
- `src/mimir/indexing.py` - Code parsing infrastructure
- `src/mimir/knowledge_graph.py` - Relationship extraction
- `src/mimir/metrics.py` - Cost tracking (extend for fitness)

---

## Timeline (Optimistic)

```
Week 1-2:   Phase 2 (Pattern Embedding)
Week 3-4:   Phase 2 continued + testing
Week 5-8:   Phase 3 (Cross-Codebase) - optional
Week 9-12:  Break / other Mimir features
Week 13-16: Phase 4 (Evolutionary) - if clear need
```

---

**Last Updated**: 2026-05-20  
**Next Action**: Decide if Phase 2 is wanted, then run `git checkout -b feature/phase2-pattern-embeddings` to start!
