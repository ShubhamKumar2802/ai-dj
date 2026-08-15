from __future__ import annotations

from typing import TYPE_CHECKING, TypeVar

from langchain_core.exceptions import OutputParserException
from langchain_core.messages import BaseMessage, HumanMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, ValidationError

from common.llm_service.base import BaseLLMService
from common.llm_service.errors import LLMProviderError, LLMValidationError
from common.llm_service.providers.registry import register_provider
from common.llm_service.schema import ImageInput, MultimodalRequest, TextRequest

if TYPE_CHECKING:
    from common.llm_service.factory import LLMServiceConfig

T = TypeVar("T", bound=BaseModel)

_VALIDATION_ERRORS = (ValidationError, OutputParserException)


class OpenAICompatibleLLMService(BaseLLMService):
    """Concrete `LLMService` for any OpenAI-compatible `/chat/completions`
    endpoint, via LangChain's `ChatOpenAI`. Nothing here is OpenCode-Zen-specific
    — `base_url`/`api_key`/`model` are all config-driven (see factory.py) — so
    a second OpenAI-compatible provider needs a new config.yaml entry, not new
    code.
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
        # A fresh client per call — construction does no network I/O, and it sidesteps
        # fighting langchain-openai's per-call-override API for fields (model,
        # temperature, max_tokens, timeout) that vary per request.
        kwargs: dict[str, object] = {
            "base_url": self._base_url,
            "api_key": self._api_key,
            "model": request.model or self._default_model,
            "timeout": request.timeout_s or self._default_timeout_s,
            # BaseLLMService._call_with_retry() already owns retry policy (§8) — the
            # openai SDK's own default retries would stack on top of it silently,
            # turning "4 attempts" into up to ~12 and multiplying total wait time.
            "max_retries": 0,
        }
        if request.temperature is not None:
            kwargs["temperature"] = request.temperature
        if request.max_tokens is not None:
            kwargs["max_tokens"] = request.max_tokens

        llm = ChatOpenAI(**kwargs)
        # method="function_calling" — the default ("json_schema") is OpenAI's newer
        # strict response_format mode, which most models proxied through an
        # OpenAI-compatible gateway like OpenCode Zen don't support. Tool/function
        # calling is the older, far more broadly compatible mechanism.
        structured_llm = llm.with_structured_output(output_schema, method="function_calling")

        try:
            result = structured_llm.invoke(_to_messages(request))
        except _VALIDATION_ERRORS as exc:
            raise LLMValidationError(str(exc)) from exc
        except Exception as exc:  # network/API failures, every shape the SDK raises
            raise LLMProviderError(str(exc)) from exc

        if not isinstance(result, output_schema):
            raise LLMValidationError(
                f"expected {output_schema.__name__}, got {type(result).__name__}"
            )
        return result


def _to_messages(request: TextRequest | MultimodalRequest) -> list[BaseMessage]:
    if isinstance(request, TextRequest):
        return [HumanMessage(content=request.prompt)]

    content: list[dict] = [{"type": "text", "text": request.prompt}]
    content.extend(_image_block(image) for image in request.images)
    return [HumanMessage(content=content)]


def _image_block(image: ImageInput) -> dict:
    if image.source == "url":
        url = image.data
    else:
        url = f"data:{image.mime_type};base64,{image.data}"
    return {"type": "image_url", "image_url": {"url": url}}


def _build(config: LLMServiceConfig) -> OpenAICompatibleLLMService:
    return OpenAICompatibleLLMService(
        base_url=config.base_url,
        api_key=config.api_key,
        model=config.model,
        max_concurrency=config.max_concurrency,
        request_timeout_s=config.request_timeout_s,
    )


register_provider("opencode_zen", _build)
