from typing import Literal

from pydantic import BaseModel, Field


class LLMRequest(BaseModel):
    """Abstract base — construct a `TextRequest` or `MultimodalRequest` instead."""

    model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, gt=0)
    timeout_s: float | None = None
    metadata: dict[str, str] = Field(default_factory=dict)
    prompt_version: str | None = None


class TextRequest(LLMRequest):
    prompt: str = Field(min_length=1)


class ImageInput(BaseModel):
    source: Literal["url", "base64"]
    data: str = Field(min_length=1)
    mime_type: str = Field(min_length=1)


class MultimodalRequest(LLMRequest):
    prompt: str = Field(min_length=1)
    images: list[ImageInput] = Field(min_length=1)
