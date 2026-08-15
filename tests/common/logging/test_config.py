import logging

import pytest

from common.logging import config as logging_config
from common.logging.config import get_logger


@pytest.fixture(autouse=True)
def _reset_root_logger(monkeypatch):
    monkeypatch.setattr(logging_config, "_configured", False)
    root = logging.getLogger()
    original_handlers = list(root.handlers)
    original_level = root.level
    yield
    root.handlers = original_handlers
    root.setLevel(original_level)


def test_get_logger_returns_named_logger():
    logger = get_logger("ai_dj.test")
    assert logger.name == "ai_dj.test"


def test_get_logger_is_idempotent_across_calls():
    root = logging.getLogger()
    get_logger("ai_dj.test.a")
    handler_count_after_first = len(root.handlers)

    get_logger("ai_dj.test.b")

    assert len(root.handlers) == handler_count_after_first


def test_level_read_from_config_yaml(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("logging:\n  level: DEBUG\n")

    get_logger("ai_dj.test.level", config_path=config_path)

    assert logging.getLogger().level == logging.DEBUG


def test_default_level_when_config_file_missing(tmp_path):
    config_path = tmp_path / "does-not-exist.yaml"

    get_logger("ai_dj.test.default", config_path=config_path)

    assert logging.getLogger().level == logging.INFO


def test_default_level_when_logging_key_missing(tmp_path):
    config_path = tmp_path / "config.yaml"
    config_path.write_text("llm_service:\n  model: foo\n")

    get_logger("ai_dj.test.default2", config_path=config_path)

    assert logging.getLogger().level == logging.INFO
