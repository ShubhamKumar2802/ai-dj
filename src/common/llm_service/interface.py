from typing import Protocol, TypeVar

from pydantic import BaseModel

from common.llm_service.schema import MultimodalRequest, TextRequest

T = TypeVar("T", bound=BaseModel)


class LLMService(Protocol):
    """The single seam every LLM call in this codebase goes through. No other
    module should import a provider SDK or a LangChain chat model directly.
    """

    def generate(
        self,
        request: TextRequest | MultimodalRequest,
        output_schema: type[T],
    ) -> T: ...

    def generate_batch(
        self,
        requests: list[TextRequest | MultimodalRequest],
        output_schema: type[T],
    ) -> list[T]: ...
