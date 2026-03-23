"""Memory Formatter - Compact context block formatter for Mem0 memories.

Formats raw Mem0 memories into a compact context block targeting < 250 tokens.
"""

from typing import Any


# Memory type to format prefix mapping
MEMORY_FORMATTERS = {
    "preference": "Preference: {content}",
    "decision": "Decision: {content}",
    "convention": "Convention: {content}",
    "episodic": "Note: {content}",
    "correction": "Correction: {content}",
}

# Priority order for memory types (higher = more important)
MEMORY_PRIORITY = {
    "correction": 5,
    "convention": 4,
    "decision": 3,
    "preference": 2,
    "episodic": 1,
}

# Token limit target
TOKEN_LIMIT = 250


def estimate_tokens(text: str) -> int:
    """Estimate token count using simple word-based approximation.

    Uses ~4 characters per token as a rough estimate.
    For more accurate counting, consider using tiktoken.
    """
    return len(text) // 4


def format_single_memory(memory: dict[str, Any]) -> str:
    """Format a single memory into a context line.

    Args:
        memory: Memory object with 'type' and 'content' keys.
                Optional: 'confidence' score.

    Returns:
        Formatted string for the memory.
    """
    memory_type = memory.get("type", "episodic")
    content = memory.get("content", "")
    confidence = memory.get("confidence")

    # Get formatter template
    formatter = MEMORY_FORMATTERS.get(memory_type, "Note: {content}")

    # Format the memory
    formatted = formatter.format(content=content)

    # Add confidence score when < 0.85
    if confidence is not None and confidence < 0.85:
        formatted += f" [confidence: {confidence:.2f}]"

    return formatted


def format_memories(memories: list[dict[str, Any]], token_limit: int = TOKEN_LIMIT) -> str:
    """Format a list of memories into a compact context block.

    Args:
        memories: List of memory objects with 'type' and 'content' keys.
                  Optional: 'confidence' score.
        token_limit: Maximum token target (default: 250)

    Returns:
        Formatted string containing all memories, targeting token_limit.
        Memories are sorted by priority (correction > convention > decision > preference > episodic).
    """
    if not memories:
        return ""

    # Sort memories by priority (higher priority first)
    sorted_memories = sorted(
        memories, key=lambda m: MEMORY_PRIORITY.get(m.get("type", "episodic"), 0), reverse=True
    )

    # Format each memory
    formatted_lines = []
    current_tokens = 0

    for memory in sorted_memories:
        formatted_line = format_single_memory(memory)
        line_tokens = estimate_tokens(formatted_line)

        # Check if adding this line would exceed limit
        if current_tokens + line_tokens > token_limit:
            # Try to fit what we can
            remaining = token_limit - current_tokens
            if remaining > 50:  # Only add if meaningful space left
                # Truncate content if needed
                max_chars = remaining * 4
                if len(formatted_line) > max_chars:
                    formatted_line = formatted_line[:max_chars] + "..."
                formatted_lines.append(formatted_line)
            break

        formatted_lines.append(formatted_line)
        current_tokens += line_tokens

    # Join with newlines
    return "\n".join(formatted_lines)


def get_token_count(formatted_text: str) -> int:
    """Get estimated token count for formatted text.

    Args:
        formatted_text: The formatted memory context block.

    Returns:
        Estimated token count.
    """
    return estimate_tokens(formatted_text)


# Test function
def test_formatter():
    """Test the formatter with sample memories."""
    test_memories = [
        {
            "type": "preference",
            "content": "Use TypeScript over JavaScript for new projects",
            "confidence": 0.92,
        },
        {
            "type": "decision",
            "content": "Use Mem0 for memory storage, Kuzu for graph, Qdrant for vectors",
            "confidence": 0.88,
        },
        {
            "type": "convention",
            "content": "Follow PEP 8 for Python, ESLint for JS/TS",
            "confidence": 0.95,
        },
        {
            "type": "episodic",
            "content": "User prefers dark mode in IDE",
            "confidence": 0.78,  # Should show confidence
        },
        {
            "type": "correction",
            "content": "Previous assumption about auth was wrong - use OAuth not JWT",
            "confidence": 0.99,
        },
    ]

    formatted = format_memories(test_memories)
    token_count = get_token_count(formatted)

    print("=== Formatted Memory Context ===")
    print(formatted)
    print(f"\n=== Token Count: {token_count} ===")
    print(f"Target: < {TOKEN_LIMIT} tokens")
    print(f"Status: {'PASS' if token_count < TOKEN_LIMIT else 'FAIL'}")

    return token_count < TOKEN_LIMIT


if __name__ == "__main__":
    test_formatter()
