"""LangChain callback handler to capture actual token usage from API calls.

This hooks into LangChain's callback system to record real token usage
from LLM and embedding API responses.
"""

from typing import Any, Dict, List, Optional
from uuid import UUID
from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.messages import BaseMessage
from langchain_core.outputs import LLMResult, ChatResult


class TokenUsageCallbackHandler(BaseCallbackHandler):
    """Captures actual token usage from LangChain LLM and embedding calls."""

    def __init__(self):
        super().__init__()
        self.reset()

    def reset(self):
        self.prompt_tokens = 0
        self.completion_tokens = 0
        self.total_tokens = 0
        self.embedding_tokens = 0
        self.has_data = False

    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        """Capture token usage from LLM response."""
        if response.llm_output and "token_usage" in response.llm_output:
            usage = response.llm_output["token_usage"]
            self.prompt_tokens += usage.get("prompt_tokens", 0)
            self.completion_tokens += usage.get("completion_tokens", 0)
            self.total_tokens += usage.get("total_tokens", 0)
            self.has_data = True

    def on_chat_model_end(self, response: ChatResult, **kwargs: Any) -> None:
        """Capture token usage from chat model response."""
        if response.llm_output and "token_usage" in response.llm_output:
            usage = response.llm_output["token_usage"]
            self.prompt_tokens += usage.get("prompt_tokens", 0)
            self.completion_tokens += usage.get("completion_tokens", 0)
            self.total_tokens += usage.get("total_tokens", 0)
            self.has_data = True

    def get_usage(self) -> Dict[str, int]:
        return {
            "prompt_tokens": self.prompt_tokens,
            "completion_tokens": self.completion_tokens,
            "total_tokens": self.total_tokens,
            "embedding_tokens": self.embedding_tokens,
        }


def create_token_callback() -> TokenUsageCallbackHandler:
    """Create a new token usage callback handler."""
    return TokenUsageCallbackHandler()
