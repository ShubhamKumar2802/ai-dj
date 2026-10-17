import time
from unittest.mock import MagicMock, patch

import pytest
from langchain_core.exceptions import OutputParserException
from pydantic import BaseModel, ValidationError

import common.llm_service  # noqa: F401  (registers built-in providers)
from common.llm_service.errors import LLMProviderError, LLMValidationError
from common.llm_service.providers.openrouter import OpenRouterLLMService
from common.llm_service.providers.registry import get_provider_factory
from common.llm_service.schema import ImageInput, MultimodalRequest, TextRequest

_CHAT = "common.llm_service.providers.openrouter.ChatOpenRouter"


class _Result(BaseModel):
    value: str


def _make_service():
    return OpenRouterLLMService(
        base_url="https://openrouter.ai/api/v1",
        api_key="key",
        model="google/gemma-4-31b-it",
        max_concurrency=2,
        request_timeout_s=30,
    )


def _fakes(result=None, side_effect=None):
    fake_structured = MagicMock()
    fake_structured.invoke.return_value = result if result is not None else _Result(value="ok")
    fake_structured.invoke.side_effect = side_effect
    fake_llm = MagicMock()
    fake_llm.with_structured_output.return_value = fake_structured
    return fake_llm, fake_structured


def _real_validation_error() -> ValidationError:
    try:
        _Result.model_validate({})
    except ValidationError as exc:
        return exc
    raise AssertionError("expected a ValidationError")


def test_registered_as_openrouter():
    assert get_provider_factory("openrouter").__module__ == (
        "common.llm_service.providers.openrouter"
    )


def test_text_request_returns_parsed_result_via_function_calling():
    fake_llm, fake_structured = _fakes()
    with patch(_CHAT, return_value=fake_llm):
        result = _make_service().generate(TextRequest(prompt="hi"), _Result)

    assert result.value == "ok"
    fake_llm.with_structured_output.assert_called_once_with(_Result, method="function_calling")
    [message] = fake_structured.invoke.call_args.args[0]
    assert message.content == "hi"


def test_multimodal_request_sends_text_then_images():
    fake_llm, fake_structured = _fakes()
    request = MultimodalRequest(
        prompt="describe",
        images=[
            ImageInput(source="base64", data="AAAA", mime_type="image/png"),
            ImageInput(source="url", data="https://example.com/x.png", mime_type="image/png"),
        ],
    )
    with patch(_CHAT, return_value=fake_llm):
        _make_service().generate(request, _Result)

    content = fake_structured.invoke.call_args.args[0][0].content
    assert [block["type"] for block in content] == ["text", "image_url", "image_url"]
    assert content[1]["image_url"]["url"] == "data:image/png;base64,AAAA"
    assert content[2]["image_url"]["url"] == "https://example.com/x.png"


def test_defaults_and_fixed_kwargs():
    fake_llm, _ = _fakes()
    with patch(_CHAT, return_value=fake_llm) as chat:
        _make_service().generate(TextRequest(prompt="hi"), _Result)

    assert chat.call_args.kwargs == {
        "base_url": "https://openrouter.ai/api/v1",
        "api_key": "key",
        "model": "google/gemma-4-31b-it",
        "timeout": 30_000,
        "max_retries": 0,
        "app_title": "ai-dj",
    }


def test_per_request_overrides():
    fake_llm, _ = _fakes()
    request = TextRequest(
        prompt="hi",
        model="anthropic/claude-sonnet-4.6",
        temperature=0.2,
        max_tokens=500,
        timeout_s=180,
    )
    service = _make_service()
    with patch(_CHAT, return_value=fake_llm) as chat:
        service.generate(request, _Result)
        overridden = chat.call_args.kwargs
        service.generate(TextRequest(prompt="again"), _Result)
        default = chat.call_args.kwargs

    assert overridden["model"] == "anthropic/claude-sonnet-4.6"
    assert overridden["temperature"] == 0.2
    assert overridden["max_tokens"] == 500
    assert overridden["timeout"] == 180_000
    assert default["model"] == "google/gemma-4-31b-it"
    assert "temperature" not in default and "max_tokens" not in default


def test_provider_failure_is_retried_then_wrapped(monkeypatch):
    monkeypatch.setattr(time, "sleep", lambda _: None)
    fake_llm, fake_structured = _fakes(side_effect=RuntimeError("503 high demand"))
    with patch(_CHAT, return_value=fake_llm):
        with pytest.raises(LLMProviderError, match="503 high demand"):
            _make_service().generate(TextRequest(prompt="hi"), _Result)

    # initial attempt + 3 backoff retries = 4 total calls
    assert fake_structured.invoke.call_count == 4


@pytest.mark.parametrize(
    "error", [_real_validation_error(), OutputParserException("not json")]
)
def test_validation_failure_is_not_retried(error):
    fake_llm, fake_structured = _fakes(side_effect=error)
    with patch(_CHAT, return_value=fake_llm):
        with pytest.raises(LLMValidationError):
            _make_service().generate(TextRequest(prompt="hi"), _Result)

    assert fake_structured.invoke.call_count == 1


def test_wrong_result_type_is_a_validation_error():
    fake_llm, _ = _fakes(result={"value": "ok"})
    with patch(_CHAT, return_value=fake_llm):
        with pytest.raises(LLMValidationError, match="expected _Result"):
            _make_service().generate(TextRequest(prompt="hi"), _Result)
