# Proposal

## Why

The only working provider today is Gemini's free tier. During the `waveform-llm-transition` experiment it returned `503 high demand` three times in a row, and its default model (`gemma-4-31b-it`) read the waveform images poorly. OpenRouter puts many models behind a single key, including strong vision models, so switching models becomes a config edit. Use LangChain's dedicated `ChatOpenRouter` integration, as OpenRouter's LangChain guide recommends.

## What Changes

- New built-in provider `openrouter` in `common/llm_service/providers/`, wrapping `langchain_openrouter.ChatOpenRouter`. It is registered in the provider registry and selected only through `config.yaml` (`provider: openrouter`).
- It supports the same contract as the existing provider:
  - `TextRequest` and `MultimodalRequest` (base64 or URL images)
  - schema-enforced structured output
  - per-request `model`, `temperature`, `max_tokens` and `timeout_s`
  - the same `LLMProviderError` / `LLMValidationError` split
- Retries stay owned by `BaseLLMService`; the SDK's own retries are disabled. OpenRouter attribution headers identify the app as ai-dj, not LangChain's default.
- The message conversion now used by `OpenAICompatibleLLMService` (text, plus multi-part content with images) is shared between both providers rather than duplicated. This is an internal move with no behaviour change.
- `config.yaml` gains an OpenRouter block. The user then made it the active provider (2026-10-17), and the Gemini block stays commented out alongside it.
- New dependency: `langchain-openrouter` (which pulls in the `openrouter` SDK).
- The legacy spec `resources/documentation/common/llm_service/spec.md` gets an amendment that points to this capability. §7 currently says a new provider "never needs new code", so the amendment notes this deliberate exception.

## Capabilities

### New Capabilities
- `llm-service/openrouter-provider`: The OpenRouter provider's behaviour inside `llm_service`: how it is selected, what requests it accepts, how structured output, images, timeouts, retries and errors behave, and what it sends to OpenRouter. The rest of `llm_service` stays specified by its legacy spec.

### Modified Capabilities
None. `llm_service` has no OpenSpec capability yet; its legacy spec is updated by amendment, as noted above.

## Impact

- **Code:**
  - new `src/common/llm_service/providers/openrouter.py`
  - shared message conversion moved out of `providers/openai_compatible.py`
  - `providers/__init__.py` imports the new module
- **Tests:** new `tests/common/llm_service/providers/test_openrouter.py`, with the LangChain model mocked and no network. The existing `test_openai_compatible.py` must still pass unchanged.
- **Dependencies:** `langchain-openrouter` added to the main dependencies, because `llm_service` is production code.
- **Config / secrets:** an `OPENROUTER_API_KEY` entry in `.env` is needed only when the user switches `provider` to `openrouter`.
- **Docs:** an amendment to `resources/documentation/common/llm_service/spec.md` (§7 and the Amendments list).
- **No change** to `LLMService`, `get_llm_service()`, the request schemas, caching or logging. Existing callers are unaffected.
