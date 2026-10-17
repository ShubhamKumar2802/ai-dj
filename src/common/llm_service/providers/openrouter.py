from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from langchain_core.exceptions import OutputParserException
from langchain_openrouter import ChatOpenRouter
from pydantic import BaseModel, ValidationError

from common.llm_service.base import BaseLLMService
from common.llm_service.errors import LLMProviderError, LLMValidationError
from common.llm_service.providers._messages import to_messages
from common.llm_service.providers.registry import register_provider
from common.llm_service.schema import MultimodalRequest, TextRequest

if TYPE_CHECKING:
    from common.llm_service.factory import LLMServiceConfig

T = TypeVar("T", bound=BaseModel)

_VALIDATION_ERRORS = (ValidationError, OutputParserException)

# Sent as OpenRouter's X-Title attribution header (ChatOpenRouter defaults to "LangChain").
APP_TITLE = "ai-dj"


class OpenRouterLLMService(BaseLLMService):
    """Concrete `LLMService` for OpenRouter, via LangChain's dedicated `ChatOpenRouter`
    integration rather than `ChatOpenAI` pointed at OpenRouter's OpenAI-compatible
    endpoint — the deliberate exception to "a new provider needs no new code"
    (openspec capability llm-service/openrouter-provider).
    """

    def __init__(
        self,
        *,
        base_url: str,
        api_key: str,
        model: str,
        max_concurrency: int,
        request_timeout_s: float,
    ) -> None:
        super().__init__(max_concurrency=max_concurrency)
        self._base_url = base_url
        self._api_key = api_key
        self._default_model = model
        self._default_timeout_s = request_timeout_s

    def generate(
        self,
        request: TextRequest | MultimodalRequest,
        output_schema: type[T],
    ) -> T:
        return self._call_with_retry(lambda: self._invoke(request, output_schema))

    def _invoke(
        self,
        request: TextRequest | MultimodalRequest,
        output_schema: type[T],
    ) -> T:
        # A fresh client per call, as in OpenAICompatibleLLMService — construction does no
        # network I/O, and per-request overrides stay plain constructor kwargs.
        kwargs: dict[str, object] = {
            "base_url": self._base_url,
            # Always explicit, so ChatOpenRouter's own OPENROUTER_API_KEY env fallback is
            # never consulted — the key comes only from config's api_key_env_var.
            "api_key": self._api_key,
            "model": request.model or self._default_model,
            # ChatOpenRouter's timeout is in milliseconds; ours are seconds.
            "timeout": round((request.timeout_s or self._default_timeout_s) * 1000),
            # BaseLLMService._call_with_retry() owns retry policy — the SDK's own default
            # (2 retries, ~150 s of backoff each) would stack on top of it.
            "max_retries": 0,
            "app_title": APP_TITLE,
        }
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens

        llm = ChatOpenRouter(**kwargs)
        structured_llm = llm.with_structured_output(output_schema, method="function_calling")

        try:
            result = structured_llm.invoke(to_messages(request))
        except _VALIDATION_ERRORS as exc:
            raise LLMValidationError(str(exc)) from exc
        except Exception as exc:  # network/API failures, every shape the SDK raises
            raise LLMProviderError(str(exc)) from exc

        if not isinstance(result, output_schema):
            raise LLMValidationError(
                f"expected {output_schema.__name__}, got {type(result).__name__}"
            )
        return result


def _build(config: LLMServiceConfig) -> OpenRouterLLMService:
    return OpenRouterLLMService(
        base_url=config.base_url,
        api_key=config.api_key,
        model=config.model,
        max_concurrency=config.max_concurrency,
        request_timeout_s=config.request_timeout_s,
    )


register_provider("openrouter", _build)
