import pytest
from pydantic import BaseModel

from common.llm_service.errors import LLMProviderError
from common.llm_service.observability import LoggingLLMService
from common.llm_service.schema import TextRequest

_LOGGER_NAME = "ai_dj.llm_service"


class _Result(BaseModel):
    value: str


class _FakeService:
    def __init__(self, fn=None):
        self._fn = fn or (lambda request, output_schema: output_schema(value="ok"))

    def generate(self, request, output_schema):
        return self._fn(request, output_schema)

    def generate_batch(self, requests, output_schema):
        return [self.generate(request, output_schema) for request in requests]


def test_logs_successful_call(caplog):
    caplog.set_level("INFO", logger=_LOGGER_NAME)
    service = LoggingLLMService(_FakeService())
    request = TextRequest(prompt="hi", metadata={"consumer": "test_consumer"})

    service.generate(request, _Result)

    messages = [record.getMessage() for record in caplog.records]
    assert any("llm call ok" in m and "test_consumer" in m for m in messages)


def test_logs_failed_call(caplog):
    caplog.set_level("WARNING", logger=_LOGGER_NAME)

    def fn(request, output_schema):
        raise LLMProviderError("boom")

    service = LoggingLLMService(_FakeService(fn=fn))

    with pytest.raises(LLMProviderError):
        service.generate(TextRequest(prompt="hi"), _Result)

    messages = [record.getMessage() for record in caplog.records]
    assert any("llm call failed" in m for m in messages)


def test_generate_batch_logs_once(caplog):
    caplog.set_level("INFO", logger=_LOGGER_NAME)
    service = LoggingLLMService(_FakeService())
    requests = [TextRequest(prompt="a"), TextRequest(prompt="b")]

    service.generate_batch(requests, _Result)

    batch_logs = [r for r in caplog.records if "llm batch ok" in r.getMessage()]
    assert len(batch_logs) == 1
