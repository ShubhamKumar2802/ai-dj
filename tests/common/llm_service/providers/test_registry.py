import pytest

from common.llm_service.providers.registry import get_provider_factory, register_provider


def _dummy_factory(config):
    return "dummy-service"


def test_register_and_get_round_trip():
    register_provider("test-registry-round-trip", _dummy_factory)

    factory = get_provider_factory("test-registry-round-trip")

    assert factory is _dummy_factory


def test_get_unknown_provider_raises_with_registered_names_listed():
    register_provider("test-registry-listed", _dummy_factory)

    with pytest.raises(ValueError, match="test-registry-listed"):
        get_provider_factory("definitely-not-a-registered-provider")


def test_duplicate_registration_raises_by_default():
    register_provider("test-registry-duplicate", _dummy_factory)

    with pytest.raises(ValueError, match="already registered"):
        register_provider("test-registry-duplicate", _dummy_factory)


def test_duplicate_registration_allowed_with_overwrite():
    register_provider("test-registry-overwrite", _dummy_factory)

    def _other_factory(config):
        return "other-service"

    register_provider("test-registry-overwrite", _other_factory, overwrite=True)

    assert get_provider_factory("test-registry-overwrite") is _other_factory


def test_opencode_zen_is_registered_by_default():
    # Merely importing common.llm_service.providers.registry (above) already forces
    # providers/__init__.py to run first, which registers the built-in provider.
    factory = get_provider_factory("opencode_zen")
    assert callable(factory)
