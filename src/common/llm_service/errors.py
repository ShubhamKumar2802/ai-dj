class LLMProviderError(Exception):
    """A network/API failure while calling the provider. Retryable."""


class LLMValidationError(Exception):
    """The provider's response failed validation against the requested
    output_schema. Not retried automatically — the same bad input tends to
    reproduce the same bad output.
    """
