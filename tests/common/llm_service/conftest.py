import pytest

from common.llm_service.factory import LLMServiceConfig


@pytest.fixture
def make_llm_service_config(tmp_path):
    """Factory fixture: LLMServiceConfig has no Python-level defaults (config.yaml
    is the only place a default is declared), so tests that need one supply every
    field via this helper instead of repeating all of them inline.
    """

    def _make(**overrides) -> LLMServiceConfig:
        fields = {
            "provider": "opencode_zen",
            "model": "big-pickle",
            "base_url": "https://opencode.ai/zen/v1",
            "api_key": "test-key",
            "max_concurrency": 2,
            "request_timeout_s": 10,
            "cache_enabled": True,
            "cache_dir": str(tmp_path),
        }
        fields.update(overrides)
        return LLMServiceConfig(**fields)

    return _make
