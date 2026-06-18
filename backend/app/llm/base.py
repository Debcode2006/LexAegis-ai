"""
LLM abstraction primitives.

`LLMClient` is the provider-agnostic contract every backend implements. By
programming agents and safety checks against this interface (never against a
concrete client), models can be swapped — Qwen3 ↔ Llama 3.1, or a future
provider — without touching call sites.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Protocol


class Role(str, Enum):
    SYSTEM = "system"
    USER = "user"
    ASSISTANT = "assistant"


@dataclass
class ChatMessage:
    role: Role
    content: str

    def to_dict(self) -> Dict[str, str]:
        return {"role": self.role.value, "content": self.content}


@dataclass
class LLMResponse:
    """Normalized completion result across providers."""

    content: str
    model: str
    prompt_tokens: int = 0
    completion_tokens: int = 0
    latency_ms: float = 0.0
    finish_reason: Optional[str] = None
    raw: Dict = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens


class LLMError(Exception):
    """Raised when an LLM backend fails irrecoverably."""


class LLMClient(Protocol):
    """Minimal chat-completion contract."""

    model: str

    def chat(
        self,
        messages: List[ChatMessage],
        *,
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        stop: Optional[List[str]] = None,
    ) -> LLMResponse:
        ...
