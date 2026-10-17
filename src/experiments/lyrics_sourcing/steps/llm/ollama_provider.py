"""Registers an "ollama" provider with common/llm_service from outside it (spec §4.7).

Ollama's /v1 endpoint is OpenAI-compatible, so the existing OpenAICompatibleLLMService works
unchanged; external registration is the extension route llm_service spec §6 allows, and keeps
`common/` untouched.
"""

from common.llm_service.factory import LLMServiceConfig
from common.llm_service.providers.openai_compatible import OpenAICompatibleLLMService
from common.llm_service.providers.registry import get_provider_factory, register_provider

PROVIDER_NAME = "ollama"


def _build_ollama(config: LLMServiceConfig) -> OpenAICompatibleLLMService:
    return OpenAICompatibleLLMService(
        base_url=config.base_url,
        api_key=config.api_key,
        model=config.model,
        max_concurrency=config.max_concurrency,
        request_timeout_s=config.request_timeout_s,
    )


def ensure_registered() -> None:
    """Idempotent: an existing "ollama" registration is left in place."""
    try:
        get_provider_factory(PROVIDER_NAME)
    except ValueError:
        register_provider(PROVIDER_NAME, _build_ollama)
