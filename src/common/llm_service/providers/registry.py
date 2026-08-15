from typing import TYPE_CHECKING, Callable

from common.llm_service.interface import LLMService

if TYPE_CHECKING:
    from common.llm_service.factory import LLMServiceConfig

# Forward-referenced as a string, not imported at runtime — importing LLMServiceConfig
# here for real would be circular (factory.py imports this module to resolve a
# provider; a provider module imports this module to register itself).
ProviderFactory = Callable[["LLMServiceConfig"], LLMService]

_registry: dict[str, ProviderFactory] = {}


def register_provider(name: str, factory: ProviderFactory, *, overwrite: bool = False) -> None:
    """Register a provider factory under `name`. Raises if `name` is already
    registered, unless `overwrite=True` — guards against a stray re-registration
    (e.g. a test reusing a real provider's name) silently clobbering it.
    """
    if name in _registry and not overwrite:
        raise ValueError(
            f"Provider {name!r} is already registered. Pass overwrite=True to replace it."
        )
    _registry[name] = factory


def get_provider_factory(name: str) -> ProviderFactory:
    try:
        return _registry[name]
    except KeyError:
        registered = ", ".join(sorted(_registry)) or "(none)"
        raise ValueError(
            f"No provider registered for {name!r}. Registered providers: {registered}"
        ) from None
