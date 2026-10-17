# Design

## Context

See proposal.md for motivation; requirements are in `specs/llm-service/openrouter-provider/spec.md`.

How `llm_service` works today (legacy spec `resources/documentation/common/llm_service/spec.md` §6–§8):
- **Provider registry:** `providers/registry.py` maps a name to a factory `LLMServiceConfig -> LLMService`. `providers/__init__.py` imports each built-in module, and each module registers itself at import time.
- **Existing provider:** `OpenAICompatibleLLMService` (`providers/openai_compatible.py`) extends `BaseLLMService`, which owns bounded concurrency and `_call_with_retry`. It builds a fresh `ChatOpenAI` per call, uses `with_structured_output(schema, method="function_calling")`, and maps `ValidationError`/`OutputParserException` → `LLMValidationError` and everything else → `LLMProviderError`. It is registered as `opencode_zen` and `gemini`.
- **Composition:** `get_llm_service()` wraps any provider as `CachingLLMService(LoggingLLMService(provider))`, so caching and logging need nothing provider-specific.

What `langchain-openrouter` 0.2.9 (`ChatOpenRouter`, checked in the published wheel) provides:
- **Constructor aliases:** `model`, `api_key`, `base_url` (passed to the SDK as `server_url`), `temperature`, `max_tokens`, `timeout` (**milliseconds, int**) and `max_retries` (default 2, roughly 150 s of backoff each).
- **Attribution:** `app_title` / `app_url` set the `X-Title` / `HTTP-Referer` headers, and default to "LangChain" and the LangChain docs URL.
- **Structured output:** `with_structured_output(schema, method="function_calling" | "json_schema")`.
- **Images:** user message list content (text and `image_url` blocks) is passed through.
- **Requirements:** `langchain-core>=1.5.5`, which the repo already pins, and the `openrouter` SDK.

## Goals / Non-Goals

**Goals:**
- A second, independent provider class behind the unchanged `LLMService` contract, with test coverage matching `test_openai_compatible.py`.
- One shared implementation of request → LangChain message conversion.

**Non-Goals:**
- OpenRouter-specific routing features (`openrouter_provider` order, `route="fallback"`, plugins, reasoning settings). They're easy to add later as new config fields, but each would add a required `LLMServiceConfig` field for every provider, so they wait for a real need.
- Switching the repo's active provider. That is the user's config edit.
- Migrating the `llm_service` legacy spec into OpenSpec.

## Decisions

### A dedicated class wrapping `ChatOpenRouter`, not another registry name on the OpenAI-compatible class
The user chose this explicitly. Registering `openrouter` on `OpenAICompatibleLLMService` with `base_url=https://openrouter.ai/api/v1` would also work and needs no new dependency. The dedicated class wins for two reasons:
- It is the integration OpenRouter documents for LangChain.
- It opens the door to OpenRouter-native options (provider routing, fallbacks) without hacking `ChatOpenAI`.

The cost is a new dependency, and an amendment explaining why §7's "never new code" rule doesn't apply here: `ChatOpenRouter` is a different client class, not an OpenAI-compatible endpoint.

### Share message conversion in `providers/_messages.py`
`_to_messages` and `_image_block` move out of `openai_compatible.py` into a new private module, and both providers import from it. This is a pure move with no behaviour change; the existing provider tests are the guard.
*Alternative:* import the private helpers from `openai_compatible.py`. That's rejected because it couples one provider to another's internals.

### Same shape as the existing provider
`OpenRouterLLMService(BaseLLMService)` has the same constructor keywords as `OpenAICompatibleLLMService` (`base_url`, `api_key`, `model`, `max_concurrency`, `request_timeout_s`) and implements only `generate()`. Each call:
1. Builds a fresh `ChatOpenRouter` with:
   - `model = request.model or default`
   - `api_key`, `base_url`
   - `timeout = round((request.timeout_s or default_s) * 1000)`
   - `max_retries = 0`
   - `app_title = "ai-dj"`
   - `temperature` and `max_tokens` only when set
2. Calls `with_structured_output(schema, method="function_calling")`.
3. Calls `.invoke(to_messages(request))`.

Errors are mapped exactly as in the existing provider. Building per call matches the existing provider's reasoning: construction does no network I/O, and per-request overrides stay simple.

`api_key` is always passed explicitly, so `ChatOpenRouter`'s own `OPENROUTER_API_KEY` env fallback is never consulted (spec: credentials only via `api_key_env_var`). `app_url` keeps the library default; only the title is required by the spec.
*Alternative:* `ChatOpenRouter(...).bind(model=...)` per call. It's rejected because rebuilding is simpler and matches existing code.

### Registration and config
`providers/openrouter.py` defines `_build(config)` and calls `register_provider("openrouter", _build)`, and `providers/__init__.py` imports it. `config.yaml` gets a commented block next to the existing ones:

```yaml
# provider: openrouter
# model: google/gemma-4-31b-it
# base_url: https://openrouter.ai/api/v1
# api_key_env_var: OPENROUTER_API_KEY
```

`LLMServiceConfig` itself is unchanged.

### Dependency
`uv add langchain-openrouter` (main group). `uv.lock` updates accordingly. `llm_service` imports `providers/__init__.py` eagerly, so the package is a hard dependency rather than an optional extra.

### Legacy spec amendment
Add an entry to `resources/documentation/common/llm_service/spec.md` → Amendments:
- the new `openrouter` built-in provider
- the `_messages.py` move (§11 file layout)
- a note in §7 that a provider with its own LangChain integration is the exception to "never new code"
- a pointer to `openspec/specs/llm-service/openrouter-provider/` for its behaviour

Per that folder's README this is an amendment, not a version bump: it's additive, and no public signature changes.

## Risks / Trade-offs

- [`ChatOpenRouter` is young (0.2.x) and may change its constructor or behaviour] → Mitigation: pin `>=0.2.9,<0.3` in `pyproject.toml`. The unit tests assert the exact keyword arguments passed, so an API change fails loudly.
- [`base_url` → SDK `server_url` may expect a different shape than `https://openrouter.ai/api/v1`] → Mitigation: the live smoke-test task confirms it. If it's wrong, the config value changes; no spec change.
- [The SDK raises its own exception types] → Mitigation: covered by the catch-all → `LLMProviderError`, with a test using a generic exception.
- [Not every OpenRouter model supports function calling or images] → This is a model-capability limit, as the legacy spec §7 already notes. It surfaces as `LLMProviderError` or `LLMValidationError`, not a silent failure.
- [Images through a third-party proxy] → OpenRouter receives the waveform PNGs and prompts. They're the same kind of data already sent to Gemini, with no personal data.
