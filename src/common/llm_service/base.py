import time
from abc import ABC, abstractmethod
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from typing import TypeVar

from pydantic import BaseModel

from common.llm_service.errors import LLMProviderError
from common.llm_service.schema import MultimodalRequest, TextRequest

T = TypeVar("T", bound=BaseModel)

# Initial attempt + retries at these backoffs (seconds) — 4 tries total.
_RETRY_BACKOFFS_S: tuple[float, ...] = (0.5, 1.0, 2.0)


class BaseLLMService(ABC):
    """Concrete implementations extend this and implement only `generate()`.
    `generate_batch()` and retry/backoff come free on top of it.
    """

    def __init__(self, max_concurrency: int) -> None:
        self._executor = ThreadPoolExecutor(max_workers=max_concurrency)

    @abstractmethod
    def generate(
        self,
        request: TextRequest | MultimodalRequest,
        output_schema: type[T],
    ) -> T: ...

    def generate_batch(
        self,
        requests: list[TextRequest | MultimodalRequest],
        output_schema: type[T],
    ) -> list[T]:
        futures = [
            self._executor.submit(self.generate, request, output_schema) for request in requests
        ]
        return [future.result() for future in futures]

    def _call_with_retry(self, fn: Callable[[], T]) -> T:
        """Retries only `LLMProviderError` (network/API failures). A
        `LLMValidationError` propagates immediately — the same bad input tends
        to reproduce the same bad output, so retrying it buys nothing.
        """
        last_error: LLMProviderError | None = None
        for backoff in (None, *_RETRY_BACKOFFS_S):
            if backoff is not None:
                time.sleep(backoff)
            try:
                return fn()
            except LLMProviderError as exc:
                last_error = exc
        assert last_error is not None
        raise last_error
