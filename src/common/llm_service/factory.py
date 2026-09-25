import os
from pathlib import Path

import yaml
from dotenv import load_dotenv
from pydantic import BaseModel

from common.llm_service.caching import CachingLLMService
from common.llm_service.interface import LLMService
from common.llm_service.observability import LoggingLLMService
from common.llm_service.providers.registry import get_provider_factory

_REPO_ROOT = Path(__file__).resolve().parents[3]
_DEFAULT_CONFIG_PATH = _REPO_ROOT / "config.yaml"
_DEFAULT_ENV_PATH = _REPO_ROOT / ".env"


class LLMServiceConfig(BaseModel):
    """Every field required — config.yaml is the only place a default value
    for any of these is declared (see resources/documentation/common/llm_service/spec.md §6).
    """

    provider: str  # looked up in providers/registry.py — not a fixed choice
    model: str
    base_url: str
    api_key: str
    # Which .env variable holds the credential for this provider — config-driven
    # since 2026-09-17 (was hardcoded to OPEN_CODE_ZEN_API_KEY; a second real
    # provider, Gemini, needs its own credential name). No Python default, same
    # as every other field here.
    api_key_env_var: str
    max_concurrency: int
    request_timeout_s: float
    cache_enabled: bool
    cache_dir: str


def load_config(
    config_path: str | Path | None = None,
    env_path: str | Path | None = None,
) -> LLMServiceConfig:
    """Credentials from `.env`, everything else from config.yaml's
    `llm_service:` section — including *which* `.env` variable to read the
    credential from (`api_key_env_var`), so this isn't hardcoded to one
    provider's naming (2026-09-17 amendment, spec §6).
    """
    resolved_config_path = Path(config_path) if config_path is not None else _DEFAULT_CONFIG_PATH
    resolved_env_path = Path(env_path) if env_path is not None else _DEFAULT_ENV_PATH

    load_dotenv(resolved_env_path)

    data: dict = {}
    if resolved_config_path.exists():
        with resolved_config_path.open() as f:
            data = yaml.safe_load(f) or {}
    section = data.get("llm_service", {})

    env_var_name = section.get("api_key_env_var")
    if not env_var_name:
        raise ValueError(
            "llm_service.api_key_env_var is not set in "
            f"{resolved_config_path} — add it (e.g. api_key_env_var: OPEN_CODE_ZEN_API_KEY)"
        )

    api_key = os.environ.get(env_var_name, "")
    if not api_key:
        raise ValueError(
            f"{env_var_name} is not set — add it to .env (checked {resolved_env_path})"
        )

    return LLMServiceConfig(api_key=api_key, **section)


_service_cache: dict[str, LLMService] = {}


def get_llm_service(config: LLMServiceConfig | None = None) -> LLMService:
    """Config-memoized singleton. Composition:
    CachingLLMService(LoggingLLMService(<registered provider>(config))).
    """
    if config is None:
        config = load_config()

    cache_key = config.model_dump_json()
    if cache_key not in _service_cache:
        provider_service = get_provider_factory(config.provider)(config)
        logging_service = LoggingLLMService(provider_service)
        caching_service = CachingLLMService(
            logging_service,
            cache_dir=config.cache_dir,
            default_model=config.model,
            enabled=config.cache_enabled,
        )
        _service_cache[cache_key] = caching_service

    return _service_cache[cache_key]
