from langchain_core.messages import HumanMessage

from common.llm_service.providers._messages import to_messages
from common.llm_service.schema import ImageInput, MultimodalRequest, TextRequest


def test_text_request_is_one_string_message():
    messages = to_messages(TextRequest(prompt="hi"))
    assert messages == [HumanMessage(content="hi")]


def test_multimodal_request_is_text_then_images_in_order():
    request = MultimodalRequest(
        prompt="describe",
        images=[
            ImageInput(source="base64", data="AAAA", mime_type="image/png"),
            ImageInput(source="url", data="https://example.com/x.jpg", mime_type="image/jpeg"),
            ImageInput(source="base64", data="BBBB", mime_type="image/png"),
        ],
    )
    [message] = to_messages(request)
    assert message.content == [
        {"type": "text", "text": "describe"},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,AAAA"}},
        {"type": "image_url", "image_url": {"url": "https://example.com/x.jpg"}},
        {"type": "image_url", "image_url": {"url": "data:image/png;base64,BBBB"}},
    ]
