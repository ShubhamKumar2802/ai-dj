from pathlib import Path

from pydantic import BaseModel

from common.llm_service.caching import CachingLLMService
from common.llm_service.schema import TextRequest


class _Result(BaseModel):
    value: str


class _CountingService:
    def __init__(self):
        self.calls = 0

    def generate(self, request, output_schema):
        self.calls += 1
        return output_schema(value=f"result-{self.calls}")

    def generate_batch(self, requests, output_schema):
        return [self.generate(request, output_schema) for request in requests]


def test_cache_miss_then_hit(tmp_path):
    inner = _CountingService()
    service = CachingLLMService(inner, cache_dir=tmp_path, default_model="m")
    request = TextRequest(prompt="hello")

    first = service.generate(request, _Result)
    second = service.generate(request, _Result)

    assert inner.calls == 1
    assert first.value == second.value == "result-1"


def test_different_prompts_are_different_cache_entries(tmp_path):
    inner = _CountingService()
    service = CachingLLMService(inner, cache_dir=tmp_path, default_model="m")

    service.generate(TextRequest(prompt="a"), _Result)
    service.generate(TextRequest(prompt="b"), _Result)

    assert inner.calls == 2


def test_disabled_cache_always_calls_inner(tmp_path):
    inner = _CountingService()
    service = CachingLLMService(inner, cache_dir=tmp_path, default_model="m", enabled=False)
    request = TextRequest(prompt="hello")

    service.generate(request, _Result)
    service.generate(request, _Result)

    assert inner.calls == 2


def test_cache_persists_one_file_per_key_on_disk(tmp_path):
    inner = _CountingService()
    service = CachingLLMService(inner, cache_dir=tmp_path, default_model="m")

    service.generate(TextRequest(prompt="hello"), _Result)

    cached_files = list(Path(tmp_path).glob("*.json"))
    assert len(cached_files) == 1


def test_generate_batch_only_calls_inner_for_misses(tmp_path):
    inner = _CountingService()
    service = CachingLLMService(inner, cache_dir=tmp_path, default_model="m")

    service.generate_batch([TextRequest(prompt="a"), TextRequest(prompt="b")], _Result)
    assert inner.calls == 2

    results = service.generate_batch([TextRequest(prompt="a"), TextRequest(prompt="c")], _Result)

    assert inner.calls == 3
    assert results[0].value == "result-1"
