import time
from unittest.mock import MagicMock, patch

import pytest
from pydantic import BaseModel, ValidationError

from common.llm_service.errors import LLMProviderError, LLMValidationError
from common.llm_service.providers.openai_compatible import OpenAICompatibleLLMService
from common.llm_service.schema import ImageInput, MultimodalRequest, TextRequest


class _Result(BaseModel):
    value: str


def _make_service():
    return OpenAICompatibleLLMService(
        base_url="https://opencode.ai/zen/v1",
        api_key="key",
        model="big-pickle",
        max_concurrency=2,
        request_timeout_s=10,
    )


def _real_validation_error() -> ValidationError:
    try:
        _Result.model_validate({})
    except ValidationError as exc:
        return exc
    raise AssertionError("expected a ValidationError")


def test_generate_text_request_returns_parsed_result():
    service = _make_service()
    fake_structured = MagicMock()
    fake_structured.invoke.return_value = _Result(value="ok")
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value = fake_structured

    with patch("common.llm_service.providers.openai_compatible.ChatOpenAI", return_value=fake_llm):
        result = service.generate(TextRequest(prompt="hi"), _Result)

    assert result.value == "ok"
    fake_llm.with_structured_output.assert_called_once_with(_Result, method="function_calling")


def test_generate_multimodal_request_builds_multipart_content():
    service = _make_service()
    fake_structured = MagicMock()
    fake_structured.invoke.return_value = _Result(value="ok")
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value = fake_structured

    image = ImageInput(source="url", data="https://example.com/x.png", mime_type="image/png")
    request = MultimodalRequest(prompt="describe", images=[image])

    with patch("common.llm_service.providers.openai_compatible.ChatOpenAI", return_value=fake_llm):
        service.generate(request, _Result)

    messages = fake_structured.invoke.call_args.args[0]
    content = messages[0].content
    assert content[0] == {"type": "text", "text": "describe"}
    assert content[1]["image_url"]["url"] == "https://example.com/x.png"


def test_generate_wraps_provider_failure(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)

    service = _make_service()
    fake_structured = MagicMock()
    fake_structured.invoke.side_effect = ConnectionError("boom")
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value = fake_structured

    with patch("common.llm_service.providers.openai_compatible.ChatOpenAI", return_value=fake_llm):
        with pytest.raises(LLMProviderError):
            service.generate(TextRequest(prompt="hi"), _Result)

    # initial attempt + 3 backoff retries = 4 total calls
    assert fake_structured.invoke.call_count == 4


def test_generate_wraps_validation_failure_without_retry():
    service = _make_service()
    fake_structured = MagicMock()
    fake_structured.invoke.side_effect = _real_validation_error()
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value = fake_structured

    with patch("common.llm_service.providers.openai_compatible.ChatOpenAI", return_value=fake_llm):
        with pytest.raises(LLMValidationError):
            service.generate(TextRequest(prompt="hi"), _Result)

    assert fake_structured.invoke.call_count == 1
