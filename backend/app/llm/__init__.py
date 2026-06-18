"""LLM abstraction: provider-agnostic chat interface with Ollama backend."""

from app.llm.base import ChatMessage, LLMResponse, Role
from app.llm.provider import LLMProvider, get_llm_provider

__all__ = ["ChatMessage", "LLMResponse", "Role", "LLMProvider", "get_llm_provider"]
