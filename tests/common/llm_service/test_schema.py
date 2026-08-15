import pytest
from pydantic import ValidationError

from common.llm_service.schema import ImageInput, MultimodalRequest, TextRequest


def test_text_request_valid():
    request = TextRequest(prompt="hello")
    assert request.prompt == "hello"
    assert request.prompt_version is None


def test_text_request_empty_prompt_rejected():
    with pytest.raises(ValidationError):
        TextRequest(prompt="")


def test_multimodal_request_requires_at_least_one_image():
    with pytest.raises(ValidationError):
        MultimodalRequest(prompt="describe this", images=[])


def test_multimodal_request_valid():
    image = ImageInput(source="url", data="https://example.com/x.png", mime_type="image/png")
    request = MultimodalRequest(prompt="describe this", images=[image])
    assert len(request.images) == 1


def test_temperature_out_of_range_rejected():
    with pytest.raises(ValidationError):
        TextRequest(prompt="hi", temperature=3.0)


def test_max_tokens_must_be_positive():
    with pytest.raises(ValidationError):
        TextRequest(prompt="hi", max_tokens=0)


def test_image_input_requires_known_source():
    with pytest.raises(ValidationError):
        ImageInput(source="ftp", data="x", mime_type="image/png")
