import time
from typing import TypeVar

from pydantic import BaseModel

from common.llm_service.interface import LLMService
from common.llm_service.schema import MultimodalRequest, TextRequest
from common.logging import get_logger

T = TypeVar("T", bound=BaseModel)

_logger = get_logger("ai_dj.llm_service")


class LoggingLLMService:
    """Wraps any LLMService. Logs every call that actually reaches (or
    attempts to reach) the inner service — consumer, model, latency. Cache
    hits never reach this layer by construction (see factory.py's composition
    order), so there's nothing to log for them.
    """

    def __init__(self, inner: LLMService) -> None:
        self._inner = inner

    def generate(
        self,
        request: TextRequest | MultimodalRequest,
        output_schema: type[T],
    ) -> T:
        consumer = request.metadata.get("consumer", "unknown")
        model = request.model or "default"

        start = time.monotonic()
        try:
            result = self._inner.generate(request, output_schema)
        except Exception:
            elapsed_ms = (time.monotonic() - start) * 1000
            _logger.warning(
                "llm call failed consumer=%s model=%s elapsed_ms=%.1f",
                consumer,
                model,
                elapsed_ms,
            )
            raise

        elapsed_ms = (time.monotonic() - start) * 1000
        _logger.info(
            "llm call ok consumer=%s model=%s elapsed_ms=%.1f",
            consumer,
            model,
            elapsed_ms,
        )
        return result

    def generate_batch(
        self,
        requests: list[TextRequest | MultimodalRequest],
        output_schema: type[T],
    ) -> list[T]:
        start = time.monotonic()
        results = self._inner.generate_batch(requests, output_schema)
        elapsed_ms = (time.monotonic() - start) * 1000
        _logger.info(
            "llm batch ok count=%d elapsed_ms=%.1f",
            len(requests),
            elapsed_ms,
        )
        return results
