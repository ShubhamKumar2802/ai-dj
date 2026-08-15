import pytest

from common.llm_service.factory import get_llm_service, load_config


def _write_config(tmp_path, contents: str):
    path = tmp_path / "config.yaml"
    path.write_text(contents)
    return path


def test_load_config_reads_yaml_and_env(tmp_path, monkeypatch):
    monkeypatch.setenv("OPEN_CODE_ZEN_API_KEY", "secret-key")
    config_path = _write_config(
        tmp_path,
        "llm_service:\n"
        "  provider: opencode_zen\n"
        "  model: big-pickle\n"
        "  base_url: https://opencode.ai/zen/v1\n"
        "  max_concurrency: 2\n"
        "  request_timeout_s: 10\n"
        "  cache_enabled: false\n"
        "  cache_dir: /tmp/cache\n",
    )
    env_path = tmp_path / ".env"
    env_path.write_text("")

    config = load_config(config_path=config_path, env_path=env_path)

    assert config.api_key == "secret-key"
    assert config.model == "big-pickle"
    assert config.max_concurrency == 2
    assert config.cache_enabled is False


def test_load_config_raises_when_api_key_missing(tmp_path, monkeypatch):
    monkeypatch.delenv("OPEN_CODE_ZEN_API_KEY", raising=False)
    config_path = _write_config(tmp_path, "llm_service:\n  model: x\n  base_url: y\n")
    env_path = tmp_path / ".env"
    env_path.write_text("")

    with pytest.raises(ValueError):
        load_config(config_path=config_path, env_path=env_path)


def test_get_llm_service_memoizes_by_config(make_llm_service_config):
    config = make_llm_service_config()

    a = get_llm_service(config)
    b = get_llm_service(config)

    assert a is b


def test_get_llm_service_different_config_gives_different_instance(make_llm_service_config):
    config_a = make_llm_service_config(model="m1")
    config_b = make_llm_service_config(model="m2")

    a = get_llm_service(config_a)
    b = get_llm_service(config_b)

    assert a is not b
