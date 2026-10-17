"""Request -> LangChain message conversion, shared by every built-in provider."""

from langchain_core.messages import BaseMessage, HumanMessage

from common.llm_service.schema import ImageInput, MultimodalRequest, TextRequest


def to_messages(request: TextRequest | MultimodalRequest) -> list[BaseMessage]:
    if isinstance(request, TextRequest):
        return [HumanMessage(content=request.prompt)]

    content: list[dict] = [{"type": "text", "text": request.prompt}]
    content.extend(_image_block(image) for image in request.images)
    return [HumanMessage(content=content)]


def _image_block(image: ImageInput) -> dict:
    if image.source == "url":
        url = image.data
    else:
        url = f"data:{image.mime_type};base64,{image.data}"
    return {"type": "image_url", "image_url": {"url": url}}
