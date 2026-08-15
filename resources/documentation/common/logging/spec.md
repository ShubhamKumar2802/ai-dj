# Logging — Spec

**Layer:** `common/` — cross-cutting infrastructure, not owned by any pipeline stage.

---

## 0. Purpose

One shared logger setup, reused by every module in this codebase, instead of each
module (`llm_service`, and later `ingestion`, `planning`, `render`, ...) configuring
its own handler and formatter. This is the thing that makes log output consistent and
means there is exactly one place to change the format, or add a second handler, later.

First consumer: `llm_service.observability.LoggingLLMService`
(`resources/documentation/common/llm_service/spec.md` §9).

---

## 1. Interface (`config.py`)

```
get_logger(name: str) -> logging.Logger
```

Wraps stdlib `logging`. On first call in a process, configures exactly one
`StreamHandler` on the root logger with the formatter:

```
"%(asctime)s %(levelname)s %(name)s: %(message)s"
```

and sets its level from config (§2). Every subsequent call — regardless of `name` —
reuses that same configuration; it must not attach a second handler. Returns
`logging.getLogger(name)`, so callers get normal stdlib `Logger` objects and normal
stdlib behavior (propagation, per-logger level overrides, etc.) — this module only
owns the *one-time setup*, not a parallel logging API.

Callers pass their own dotted name (e.g. `"ai_dj.llm_service"`) the same way they
would to `logging.getLogger()` directly — this module doesn't invent a naming scheme.

---

## 2. Configuration

Level comes from `config.yaml`'s top-level `logging:` key:

```yaml
logging:
  level: INFO
```

Read directly by this module with a small local `pyyaml` read of that one key.
Default `INFO` if the file, or the `logging:` key, is absent — this module must work
with zero configuration.

**Deliberately not shared with `llm_service.factory`'s config loading.** Both modules
happen to read the same `config.yaml`, but neither depends on the other's loading
code. A shared "read `config.yaml`" helper is a reasonable extraction — once a
*third* module needs it (rule of three). Two independent, near-identical five-line
reads is cheaper than a shared abstraction sized for a need that doesn't exist yet.

---

## 3. File layout

```
src/common/logging/
  __init__.py     # re-exports get_logger
  config.py        # get_logger() implementation

tests/common/logging/
  test_config.py    # idempotent setup (repeated calls, no duplicate handlers);
                     # level read from a tmp config.yaml; default when file/key absent
```

---

## 4. Testing strategy

No network, no filesystem beyond a `tmp_path`-provided `config.yaml` in tests that
need to check level-reading. The idempotency property (calling `get_logger()` many
times across many modules must never multiply handlers) is the one behavior worth a
dedicated assertion — everything else is a thin wrapper over stdlib `logging`, which
doesn't need its own re-testing.

---

## 5. Rejected alternatives

| Rejected | Instead | Why |
|---|---|---|
| A shared `common/config.py` loader for `config.yaml`, used by both this module and `llm_service.factory` | Two small, independent reads of the same file (§2) | Rule of three — one shared abstraction serving exactly two call sites, for a five-line read, is premature; revisit when a third module needs `config.yaml` |
| A custom logging API (structured logging, a `Logger`-like wrapper class) | Plain stdlib `logging.Logger`, returned as-is | This module's job is the one-time handler/formatter setup, not replacing a well-understood stdlib API every consumer already knows |
