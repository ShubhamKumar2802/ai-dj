import logging
from pathlib import Path

import yaml

_FORMAT = "%(asctime)s %(levelname)s %(name)s: %(message)s"
_DEFAULT_LEVEL = "INFO"
_REPO_ROOT_CONFIG = Path(__file__).resolve().parents[3] / "config.yaml"

_configured = False


def _read_log_level(config_path: str | Path | None) -> str:
    path = Path(config_path) if config_path is not None else _REPO_ROOT_CONFIG
    if not path.exists():
        return _DEFAULT_LEVEL

    with path.open() as f:
        data = yaml.safe_load(f) or {}

    return data.get("logging", {}).get("level", _DEFAULT_LEVEL)


def get_logger(name: str, *, config_path: str | Path | None = None) -> logging.Logger:
    """Return a stdlib Logger. Configures one shared handler/formatter on the
    root logger the first time this is called in a process; every later call
    (any name) reuses that same configuration.
    """
    global _configured

    if not _configured:
        level_name = _read_log_level(config_path)
        level = getattr(logging, level_name.upper(), logging.INFO)

        handler = logging.StreamHandler()
        handler.setFormatter(logging.Formatter(_FORMAT))

        root = logging.getLogger()
        root.addHandler(handler)
        root.setLevel(level)

        _configured = True

    return logging.getLogger(name)
