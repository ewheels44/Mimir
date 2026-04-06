---
name: codebase-analysis-workflow
description: Systematic workflow for analyzing and auditing existing codebases by exploring structure, reading relevant files, and producing structured analysis reports
---

# Codebase Analysis Workflow

A systematic approach to analyzing and auditing existing codebases without requiring project-specific context. This workflow efficiently navigates unfamiliar codebases to understand architecture, identify issues, and provide actionable recommendations.

## When to Use This Skill

- Analyzing unfamiliar codebases for the first time
- Conducting code quality audits
- Understanding how specific features or components work
- Identifying dependencies and architectural patterns
- Producing structured analysis reports with recommendations

## Workflow Steps

### 1. Explore Project Structure

Start with `list_dir` to understand the overall organization:

```bash
# List root directory
list_dir .

# List key subdirectories
list_dir src/
list_dir tests/
```

**Goal**: Identify major components, naming conventions, and project layout (e.g., src/, lib/, workflows/, tests/, docs/).

### 2. Identify Target Files by Keywords

Map task requirements to likely directory/file locations:

- **Keywords → Locations mapping**:
  - "authentication", "auth" → `auth/`, `security/`, files with `auth` in name
  - "API", "endpoint" → `api/`, `routes/`, `handlers/`
  - "workflow", "agent" → `workflows/`, `agents/`, `processors/`
  - "database", "data" → `db/`, `models/`, `repositories/`
  - "config" → `config/`, `settings/`, root `.yaml`/`.json` files

- **File patterns to prioritize**:
  - Main implementation files (not `__init__.py` unless small project)
  - Files matching task keywords in name
  - Recently modified files (if timestamps available)

### 3. Read Primary Target Files

Read the main implementation file(s) identified in step 2:

```python
# Example: Reading a workflow implementation
read_file("src/workflows/knowledge_agent.py")
```

**What to look for**:
- Imports (identify dependencies to read next)
- Main classes/functions
- External dependencies (libraries, frameworks)
- Configuration usage
- Error handling patterns
- Comments indicating complexity or known issues

### 4. Read Dependencies and Related Files

Based on imports and references, read:

1. **Direct dependencies**: Files imported by target file
2. **Utility modules**: Shared helpers, constants, types
3. **Tests**: Unit tests, integration tests for target files
4. **Configuration**: Settings files, environment configs
5. **CLI/Entry points**: How the code is invoked

```python
# Example sequence
read_file("src/utils/helpers.py")          # Dependency
read_file("tests/test_knowledge_agent.py") # Tests
read_file("src/config/settings.py")        # Configuration
read_file("cli/run_workflow.py")           # Usage
```

**Stop condition**: When you have enough context to answer the analysis question or reach diminishing returns (typically 5-10 files).

### 5. Produce Structured Analysis

Create a comprehensive report with these sections:

#### A. Overview
- Purpose and functionality
- Key components
- Technology stack

#### B. Code Quality
- Code organization and structure
- Readability and maintainability
- Documentation quality
- Design patterns used

**Include**: Concrete code examples showing strengths or weaknesses

#### C. Error Handling
- Exception handling patterns
- Validation approaches
- Error recovery mechanisms
- Logging practices

**Include**: Specific examples from the codebase

#### D. Performance Considerations
- Potential bottlenecks
- Resource usage patterns
- Optimization opportunities
- Scalability concerns

#### E. Architecture & Design
- Component relationships
- Separation of concerns
- Coupling and cohesion
- Extensibility

#### F. Testing
- Test coverage assessment
- Test quality and comprehensiveness
- Missing test scenarios
- Testing patterns used

#### G. Security
- Input validation
- Authentication/authorization
- Sensitive data handling
- Potential vulnerabilities

#### H. Recommendations
- **High Priority**: Critical issues requiring immediate attention
- **Medium Priority**: Important improvements for robustness
- **Low Priority**: Nice-to-have enhancements

**Format**: Each recommendation should include:
- Clear description
- Specific location (file:line or function name)
- Suggested solution or approach
- Rationale

## Example Analysis Structure

```markdown
# Codebase Analysis: [Component Name]

## 1. Overview
The knowledge agent workflow processes user queries using RAG...

## 2. Code Quality
**Strengths:**
- Clear separation between retrieval and generation (rag.py:45-67)
- Well-documented public APIs

**Issues:**
```python
# Example from knowledge_agent.py:123
def process(data):  # Missing type hints
    result = data.get('x')  # No validation
```

## 3. Error Handling
Current approach uses basic try-catch:
```python
try:
    result = api_call()
except Exception as e:  # Too broad
    print(e)  # Poor logging
```

[Continue with remaining sections...]

## 8. Recommendations

### High Priority
1. **Add input validation** (knowledge_agent.py:50-60)
   - Validate query parameters before processing
   - Prevents downstream errors and security issues

[Continue with prioritized list...]
```

## Tips for Effective Analysis

1. **Start broad, then narrow**: Overview first, then deep dive into specific concerns
2. **Follow the data flow**: Trace how data moves through the system
3. **Look for patterns**: Repeated code structures indicate design patterns or anti-patterns
4. **Check boundaries**: Pay attention to input/output interfaces and error boundaries
5. **Consider context**: Read tests and CLI usage to understand intended behavior
6. **Be specific**: Always reference file names, line numbers, or function names
7. **Balance criticism**: Note both strengths and weaknesses

## Adapting to Project Size

**Small projects** (< 10 files):
- Read most/all relevant files
- Focus on overall design coherence

**Medium projects** (10-50 files):
- Focus on target module/component
- Read key dependencies only
- Sample test coverage

**Large projects** (> 50 files):
- Narrow scope to specific subsystem
- Read interfaces/contracts first
- Use file/directory names to infer structure without reading everything

## Common Pitfalls to Avoid

- **Don't read files randomly**: Always have a reason (dependency, test, config)
- **Don't skip tests**: They reveal intended behavior and edge cases
- **Don't assume**: Verify imports and dependencies by reading them
- **Don't overload**: Stop when you have sufficient context (typically 5-10 files)
- **Don't be vague**: Back every observation with specific code references