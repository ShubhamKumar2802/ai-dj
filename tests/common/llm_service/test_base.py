import time

import pytest
from pydantic import BaseModel

from common.llm_service.base import BaseLLMService
from common.llm_service.errors import LLMProviderError, LLMValidationError
from common.llm_service.schema import TextRequest


class _Result(BaseModel):
    value: str


class _FakeService(BaseLLMService):
    def __init__(self, max_concurrency, fn):
        super().__init__(max_concurrency=max_concurrency)
        self._fn = fn

    def generate(self, request, output_schema):
        return self._fn(request)


def test_generate_batch_preserves_order():
    service = _FakeService(2, lambda request: _Result(value=request.prompt))
    requests = [TextRequest(prompt=f"p{i}") for i in range(5)]

    results = service.generate_batch(requests, _Result)

    assert [r.value for r in results] == ["p0", "p1", "p2", "p3", "p4"]


def test_generate_batch_bounds_concurrency():
    in_flight = 0
    max_in_flight = 0

    def fn(request):
        nonlocal in_flight, max_in_flight
        in_flight += 1
        max_in_flight = max(max_in_flight, in_flight)
        time.sleep(0.05)
        in_flight -= 1
        return _Result(value=request.prompt)

    service = _FakeService(2, fn)
    requests = [TextRequest(prompt=f"p{i}") for i in range(6)]

    service.generate_batch(requests, _Result)

    assert max_in_flight <= 2


def test_call_with_retry_retries_on_provider_error(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    service = _FakeService(1, lambda request: None)

    attempts = []

    def fn():
        attempts.append(1)
        if len(attempts) < 3:
            raise LLMProviderError("transient")
        return _Result(value="ok")

    result = service._call_with_retry(fn)

    assert result.value == "ok"
    assert len(attempts) == 3


def test_call_with_retry_raises_after_exhausting_attempts(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    service = _FakeService(1, lambda request: None)

    def fn():
        raise LLMProviderError("still failing")

    with pytest.raises(LLMProviderError):
        service._call_with_retry(fn)


def test_call_with_retry_does_not_retry_validation_errors(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    service = _FakeService(1, lambda request: None)

    attempts = []

    def fn():
        attempts.append(1)
        raise LLMValidationError("bad")

    with pytest.raises(LLMValidationError):
        service._call_with_retry(fn)

    assert len(attempts) == 1
