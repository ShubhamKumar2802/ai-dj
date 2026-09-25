"""Importing this package registers every built-in strategy (see registry.py).

Mirrors ``common/llm_service/providers/__init__.py`` — each strategy module
calls ``register_strategy`` at import time as a side effect.
"""

from render.transition_renderer.strategies import cut_on_the_one  # noqa: F401
