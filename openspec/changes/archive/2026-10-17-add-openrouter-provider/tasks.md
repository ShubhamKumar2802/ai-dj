# Tasks

## 1. Dependency

- [x] 1.1 Add `langchain-openrouter>=0.2.9,<0.3` to the main dependencies (`uv add "langchain-openrouter>=0.2.9,<0.3"`), and verify `uv run python -c "from langchain_openrouter import ChatOpenRouter"` succeeds and `langchain-core` stays at a compatible version in `uv.lock`

## 2. Shared message conversion

- [x] 2.1 Move `_to_messages` / `_image_block` from `providers/openai_compatible.py` into a new `providers/_messages.py` (as `to_messages`), and update `openai_compatible.py` to import it. Verify `uv run pytest tests/common/llm_service` passes with `test_openai_compatible.py` unchanged
- [x] 2.2 Add `tests/common/llm_service/providers/test_messages.py` covering a text request (single string content) and a multimodal request (text part then image parts in order; base64 → data URL, URL passed as given). Verify the tests pass

## 3. OpenRouter provider

- [x] 3.1 Implement `providers/openrouter.py`: `OpenRouterLLMService(BaseLLMService)` as in design.md (per-call `ChatOpenRouter`, timeout in ms, `max_retries=0`, `app_title="ai-dj"`, function-calling structured output, same error mapping), plus `_build` and `register_provider("openrouter", _build)`. Import it in `providers/__init__.py`. Verify that `get_provider_factory("openrouter")` resolves after `import common.llm_service`
- [x] 3.2 Add `tests/common/llm_service/providers/test_openrouter.py`, with `ChatOpenRouter` patched and no network, covering:
  - text and multimodal requests produce the expected messages
  - `with_structured_output(schema, method="function_calling")` is used
  - per-request model/temperature/max_tokens/timeout override the defaults, and unset values aren't passed
  - `timeout_s=180` → `timeout=180000`
  - `max_retries=0` and `app_title="ai-dj"` are always passed
  - the API key is passed explicitly
  - `ValidationError`/`OutputParserException` → `LLMValidationError`
  - a generic exception → `LLMProviderError`
  - `generate()` retries via the base class

  Verify `uv run pytest tests/common/llm_service` passes

## 4. Config and docs

- [x] 4.1 Add the `openrouter` block to `config.yaml`'s `llm_service:` section. Verify `uv run pytest tests/common/llm_service/test_factory.py` still passes and `load_config()` loads the active settings. (The user made OpenRouter the active provider on 2026-10-17, and the Gemini block is kept commented out.)
- [x] 4.2 Add the amendment to `resources/documentation/common/llm_service/spec.md` (Amendments entry, §7 exception note, §11 file layout with `_messages.py` and `openrouter.py`, pointer to `openspec/specs/llm-service/openrouter-provider/`). Verify by re-reading that §7 no longer claims every new provider needs no code

## 5. Verification

- [x] 5.1 Run `uv run ruff check .` and `uv run pytest`, and verify both pass — **partially deferred (2026-10-17):** `ruff check .` passes and `tests/common/llm_service` passes (50 tests). The full `uv run pytest` run was deferred by the user before it finished: `test_real_audio_smoke.py` extracts features from all 82 tracks in `music/`, which takes too long. Up to that point, the only failure was the unrelated `tests/experiments/lyrics_sourcing/test_config.py::test_committed_config_loads` (it expects `whisper-small-mlx`, but the config has `whisper-large-v3-turbo`).
- [x] 5.2 Live smoke test, after the user adds `OPENROUTER_API_KEY` to `.env`: run `src/common/llm_service/examples/example_llm_call.py` (or an equivalent one-off) with a temporary config using `provider: openrouter` and a vision-capable model. Send one text request and one image request, and verify that both return parsed schema instances, which also confirms the `base_url` value

## Workflow follow-up

- `config.yaml` is already switched to OpenRouter. For the waveform experiment, set `llm.model` in its config to an OpenRouter vision model if it overrides the default.
- Archive the change with `/opsx:archive` after review.
