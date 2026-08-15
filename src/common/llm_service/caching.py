import hashlib
import json
from pathlib import Path
from typing import TypeVar

from pydantic import BaseModel

from common.llm_service.interface import LLMService
from common.llm_service.schema import MultimodalRequest, TextRequest

T = TypeVar("T", bound=BaseModel)


class CachingLLMService:
    """Wraps any LLMService with a disk-backed cache — one JSON file per
    cache key, keyed on the request payload, output schema, resolved model,
    and prompt version. Not in-memory-only: OpenCode Zen calls are meant to
    be cached forever, so a cache that discards on process exit would re-pay
    free-tier rate limits every run.
    """

    def __init__(
        self,
        inner: LLMService,
        *,
        cache_dir: str | Path,
        default_model: str,
        enabled: bool = True,
    ) -> None:
        self._inner = inner
        self._cache_dir = Path(cache_dir)
        self._default_model = default_model
        self._enabled = enabled
        if self._enabled:
            self._cache_dir.mkdir(parents=True, exist_ok=True)

    def generate(
        self,
        request: TextRequest | MultimodalRequest,
        output_schema: type[T],
    ) -> T:
        if not self._enabled:
            return self._inner.generate(request, output_schema)

        key = self._cache_key(request, output_schema)
        cached = self._read(key, output_schema)
        if cached is not None:
            return cached

        result = self._inner.generate(request, output_schema)
        self._write(key, result)
        return result

    def generate_batch(
        self,
        requests: list[TextRequest | MultimodalRequest],
        output_schema: type[T],
    ) -> list[T]:
        if not self._enabled:
            return self._inner.generate_batch(requests, output_schema)

        keys = [self._cache_key(request, output_schema) for request in requests]
        results: list[T | None] = [self._read(key, output_schema) for key in keys]

        miss_indices = [i for i, result in enumerate(results) if result is None]
        if miss_indices:
            miss_requests = [requests[i] for i in miss_indices]
            miss_results = self._inner.generate_batch(miss_requests, output_schema)
            for i, result in zip(miss_indices, miss_results, strict=True):
                self._write(keys[i], result)
                results[i] = result

        assert all(result is not None for result in results)
        return results  # type: ignore[return-value]

    def _cache_key(
        self,
        request: TextRequest | MultimodalRequest,
        output_schema: type[T],
    ) -> str:
        model_id = request.model or self._default_model
        payload = request.model_dump(
            mode="json",
            exclude={"metadata", "model", "timeout_s", "prompt_version"},
        )
        raw = json.dumps(
            {
                "payload": payload,
                "output_schema": output_schema.__name__,
                "model_id": model_id,
                "prompt_version": request.prompt_version,
            },
            sort_keys=True,
        )
        return hashlib.sha256(raw.encode("utf-8")).hexdigest()

    def _path(self, key: str) -> Path:
        return self._cache_dir / f"{key}.json"

    def _read(self, key: str, output_schema: type[T]) -> T | None:
        path = self._path(key)
        if not path.exists():
            return None
        return output_schema.model_validate_json(path.read_text())

    def _write(self, key: str, result: T) -> None:
        self._path(key).write_text(result.model_dump_json())
