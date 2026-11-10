"""Provider-agnostic LLM building blocks: response records, chat model and OpenRouter client.

Needs the optional ``llm`` extra (``openai`` and ``httpx``). The core ``ai_lab`` package does
not import this module.
"""

from ai_lab.llm.chat import ChatModel, InfraErrorKind, LLMInfraError, OpenAIChatModel
from ai_lab.llm.openrouter import (
    FreeModelDailyRequests,
    KeyInfo,
    ModelInfo,
    ModelPricing,
    OpenRouterClient,
    OpenRouterError,
)
from ai_lab.llm.records import LLMResponse, LLMToolCall, Usage

__all__ = [
    "ChatModel",
    "FreeModelDailyRequests",
    "InfraErrorKind",
    "KeyInfo",
    "LLMInfraError",
    "LLMResponse",
    "LLMToolCall",
    "ModelInfo",
    "ModelPricing",
    "OpenAIChatModel",
    "OpenRouterClient",
    "OpenRouterError",
    "Usage",
]
