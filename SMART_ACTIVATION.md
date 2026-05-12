# Mimir Smart Activation

## Overview

Mimir now uses **smart activation** to automatically decide when to use project knowledge. This fixes P-21 (auto-activate was too aggressive) with a proper solution instead of just turning it off.

## How It Works

```
User Task
    ↓
Smart Classifier (should_use_mimir())
    ↓
┌───────────────────┬───────────────────┐
│   CODE TASKS     │   NON-CODE TASKS  │
│   (use Mimir)    │   (skip Mimir)    │
├───────────────────┼───────────────────┤
│ • "Fix bug in X" │ • "git status"    │
│ • "How does Y?"  │ • "Edit README"   │
│ • "Implement Z"  │ • "What's weather?"│
│ • "Trace deps"   │ • "ls -la"         │
└───────────────────┴───────────────────┘
```

## Classification Rules

### Always Use Mimir (auto_activate = True effectively)

Tasks with these **code keywords** trigger Mimir automatically:
- `function`, `class`, `method`, `module`
- `bug`, `feature`, `refactor`, `implement`, `fix`
- `test`, `mock`, `api`, `dependency`
- Questions: `how does`, `where is`, `what is`, `trace`, `find`

### Skip Mimir (auto_activate = False effectively)

Tasks matching these **non-code patterns** skip Mimir:
- Shell: `git`, `cd`, `ls`, `mkdir`, `rm`, `cp`, `mv`
- Docs only: `README`, `LICENSE`, `CHANGELOG`
- Non-project: `weather`, `time`, `joke`, `story`

## Usage

### For Jcode Agents

The smart activation is now in the system prompt (`~/.jcode/prompts/mimir-Mimir.md`). Jcode will:
1. Read the task
2. Apply the classification rules in the prompt
3. Use Mimir tools only for code-related tasks

### Programmatic Usage

```python
from mimir.activation import should_use_mimir, enrich_task_with_gating

# Simple check
result = should_use_mimir("Fix the bug in auth.py")
# {'should_use': True, 'reason': 'Task has 2 code-related indicators', ...}

# With gating (recommended)
result = enrich_task_with_gating("git status")
# {'should_use': False, 'status': 'skipped', 'skipped_reason': 'Task appears to be non-code'}
```

## Configuration

The skill JSON (`~/.jcode/skills/mimir-Mimir.json`) now has:
```json
{
  "config": {
    "auto_activate": "smart",
    "activation": {
      "mode": "smart",
      "skip_patterns": ["git", "ls", "cd", ...],
      "require_keywords": ["code", "function", "class", ...]
    }
  }
}
```

## Test Results

All classification tests pass:
- ✅ `Fix the bug in auth.py` → **Use Mimir** (code keywords: bug, fix)
- ✅ `git status` → **Skip Mimir** (shell command)
- ✅ `Edit README.md` → **Skip Mimir** (doc-only)
- ✅ `How does the MCP server work?` → **Use Mimir** (question about code)
- ✅ `What is the weather today?` → **Skip Mimir** (non-project question)
- ✅ `Implement new feature for user login` → **Use Mimir** (code keywords: implement, feature)

## Benefits

| Before (auto_activate: false) | After (auto_activate: "smart") |
|--------------------------------|----------------------------------|
| Manual `/skills enable mimir-Mimir` every session | Automatic for code tasks |
| Mimir never auto-activates | Mimir activates when relevant |
| Had to remember to enable | Just works for code tasks |

## Files Modified

1. **`src/mimir/activation.py** (NEW) - Smart classifier logic
2. **`scripts/jcode/mimir_bridge.py** - Updated skill JSON generation
3. **`~/.jcode/skills/mimir-Mimir.json** - Regenerated with smart config
4. **`~/.jcode/prompts/mimir-Mimir.md** - Updated with activation rules

## Next Steps

- Monitor activation accuracy in real usage
- Adjust keywords/patterns based on false positives/negatives
- Consider adding ML-based classification if keyword matching isn't enough
