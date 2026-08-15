# LLM Service — Spec

**Layer:** `common/` — cross-cutting infrastructure, not owned by any pipeline stage.
**v1 concrete provider:** LangChain (`langchain-openai`) → OpenCode Zen.

---

## 0. Invariant

> **All LLM calls in this codebase go through `llm_service`. No other module
> instantiates a LangChain chat model, imports a provider SDK, or otherwise talks to
> an LLM API directly.**

This is the module's reason for existing, not an incidental property. It is what
keeps the boundary in `ai-dj-design-v3.md` D14 ("no model in the planner") mechanically
true rather than merely conventional: as long as this is the only place a provider
SDK is imported, nothing downstream can accidentally reach for a model call the way
nothing downstream can accidentally reach for a waveform (D2).

It also gives caching, logging, error taxonomy, and concurrency control exactly one
home each (§7) — the payoff for treating "LLM call" as infrastructure rather than
something each consumer reinvents.

---

## 1. Scope & consumers

| Consumer | Status | Feeds |
|---|---|---|
| Familiarity / nostalgia scorer | **v1 — specced here** | Path-search `ν` term (design doc D3); `Track.familiarity_score`, `.era`, `.is_club_edit` (design doc §5.1) |
| Natural-language mix config parser | Deferred — "interface sugar" per design doc §6.1 | `MixPlan.config` |
| Anything else that comes up | Not yet known | — |

The interface (§2) and schema (§3) are designed generic enough that the deferred
consumer is a new prompt template + a new consumer-owned output schema, not a change
to this module.

**Boundary:** this module produces plain `pydantic.BaseModel` instances. Nothing
downstream — cue derivation, edge builder, path search, either renderer — ever calls
an LLM or knows one exists. It is a data source, exactly like the feature extractor is
a data source, just cached on different keys (§6).

---

## 2. Interface (`interface.py`)

```
LLMService (Protocol):
  generate(request: TextRequest | MultimodalRequest, output_schema: type[T]) -> T
  generate_batch(requests: list[TextRequest | MultimodalRequest],
                 output_schema: type[T]) -> list[T]
```

Structured output is the *only* mode — even a plain-text call is modeled as an
`output_schema` with a single string field, so the interface never grows a second
"unstructured" method as new consumers show up.

`generate()` returns the bare parsed `T`, no wrapper. Per-call metadata (latency,
cache hit/miss, token usage) is captured by the service's own logging (§7), not
returned to the caller — every consumer's call site stays trivial:

```
score = llm_service.generate(request, FamiliarityScore)
```

If a consumer ever needs usage stats back, that is a deliberate future
`generate_with_meta` addition — not a change to this signature.

`generate_batch()` exists because the natural shape of familiarity scoring is "N
independent, cacheable calls, no ordering dependency" — see §5 for how it's
implemented once, for every consumer, without an orchestrator.

---

## 3. Request schema (`schema.py`)

Two concrete request shapes, not one flat model with optional fields — a multimodal
call and a text call have different validity rules, and a discriminated pair makes
invalid states (e.g. an empty `images` list masquerading as multimodal) unrepresentable.

```
LLMRequest (abstract base — never instantiated directly):
  model        : str | None      # override; None = factory default model
  temperature  : float | None    # None = provider default; range [0, 2] if set
  max_tokens   : int | None      # None = provider default; must be > 0 if set
  timeout_s    : float | None    # None = service default
  metadata     : dict[str, str]  # consumer name / purpose tag, for logging only —
                                  # never sent to the provider

TextRequest(LLMRequest):
  prompt       : str               # fully rendered by PromptManager (§4) — no
                                    # unresolved {placeholders}; min_length=1

MultimodalRequest(LLMRequest):
  prompt       : str               # same constraint as TextRequest
  images       : list[ImageInput]  # min_length=1 — an empty list means this
                                    # should have been a TextRequest

ImageInput:
  source       : "url" | "base64"  # discriminant
  data         : str               # the URL, or the base64 payload
  mime_type    : str               # e.g. "image/png", "image/jpeg"
```

**Response side is deliberately not specced here.** `output_schema` is any
`pydantic.BaseModel` subclass the *consumer* defines — the service places exactly one
house rule on it: every field should carry a `Field(description=...)`, since that
description is what LangChain's structured-output layer surfaces to the model as the
schema contract. The service has no opinion beyond that; see §4 for why the response
shape lives with the consumer, not here.

**v1 usage note:** the only v1 consumer (familiarity scoring) is text-only.
`MultimodalRequest` is provisioned infrastructure, not an active v1 feature — no
consumer constructs one yet.

---

## 4. Response schema — consumer-owned

`FamiliarityRequest` / `FamiliarityScore` belong to the familiarity-scorer module
(a future `common/` or `ingestion/`-adjacent consumer, out of scope for this spec's
file list), which imports `LLMService` and `TextRequest` from here. This spec defines
`FamiliarityScore` as the first real example, since it's what pins the pattern every
future consumer schema follows:

```
FamiliarityScore:
  familiarity_score : float | None   # nullable soft score (design doc D10) — the
                                      # single scalar persisted to Track and consumed
                                      # by path search's ν term (D3)
  era                : str | None
  is_club_edit       : bool | None
```

Matches `Track`'s actual fields per design doc §5.1 exactly. Note that §6.1's prose
mentions "recognisability" and "party-appropriateness" as separate signals the LLM
reasons about — those collapse into the single `familiarity_score` scalar here; only
the composite is persisted, keeping D3's path-level objective a single `ν` term
rather than three.

Why this schema doesn't live in `llm_service`: the service must stay ignorant of what
its consumers ask for, or every new consumer becomes a change to this module —
exactly the coupling the invariant in §0 exists to prevent.

---

## 5. Prompt management (`prompt_manager.py`)

`PromptManager` owns loading, rendering, and versioning prompt templates. Consumers
never hand-format strings.

- **Load** — templates live as files under `prompts/` (one per prompt, e.g.
  `prompts/familiarity_score.txt`), read by name.
- **Render** — placeholder substitution for dynamic inputs (e.g. `{title}`, `{film}`,
  `{year}`, `{artist}`) → a finished prompt string, handed to
  `TextRequest`/`MultimodalRequest`.
- **Version** — each template's version is the canonical source for the
  `prompt_version` used in the cache key (§7) — not a separately hand-tracked
  constant. Reload/hot-swap during development is a `PromptManager` concern, not
  something callers or the cache need to know about.

---

## 6. Factory & composition (`factory.py`)

```
LLMServiceConfig:
  provider          : "opencode_zen"   # v1: only value; extensible enum later
  model             : str              # default model id (a free OpenCode Zen model)
  base_url          : str              # default "https://opencode.ai/zen/v1"
  api_key           : str              # from env — never hardcoded, never logged
  max_concurrency   : int              # default cap for generate_batch (§8)
  request_timeout_s : float            # default per-call timeout
  cache_enabled     : bool             # default True

get_llm_service(config: LLMServiceConfig) -> LLMService
```

**Composition happens here, as decorators, in a fixed order:**

```
LoggingLLMService(CachingLLMService(LangChainLLMService(config)))
```

Logging outermost so it sees every request including cache hits; caching sits between
logging and the real provider call so only actual cache misses reach the network.
`LangChainLLMService` (§7) never needs to know caching or logging exist — each
concern is a plain `LLMService` wrapping another `LLMService`.

**Singleton — memoized by config, not a raw global.** `get_llm_service()` caches the
constructed (already-decorated) instance keyed on the resolved config, so the
underlying LangChain client / HTTP connection pool is built once and reused — the
actual reason a singleton matters here, not global-state convenience. A different
config (e.g. a test passing an explicit override, or a mock `LLMService` injected for
a consumer's unit tests) gets its own instance rather than colliding with the cached
default.

---

## 7. Concrete implementation — `LangChainLLMService` (`langchain_impl.py`)

Extends `BaseLLMService` (§8) and implements only `generate()` — `generate_batch()`
comes free from the base class's bounded-concurrency default. Wraps LangChain's
`ChatOpenAI` pointed at OpenCode Zen via `base_url`/`api_key`.

- Dispatches `TextRequest` → plain message content; `MultimodalRequest` → LangChain's
  multi-part message content (text block + image blocks).
- Uses `with_structured_output(output_schema)` per call so the schema is enforced at
  the LangChain layer, not hand-parsed JSON.
- **Pydantic validation at both boundaries**: the request (`TextRequest` /
  `MultimodalRequest`) is validated at construction time, before any call is made;
  the response is validated against `output_schema` on the way back out. A response
  that fails schema validation (`LLMValidationError`) is a distinct error case from a
  network/provider failure (`LLMProviderError`, §9) — "the model replied with
  garbage" and "the API call failed" are different failure modes with different
  causes and different retry semantics.

---

## 8. Concurrency & reliability — bounded concurrency, not an orchestrator (`base.py`)

`BaseLLMService.generate_batch()` dispatches independent, idempotent, cacheable calls
— exactly what familiarity scoring is: N tracks, no ordering dependency between them
— with a **capped concurrency** (async + semaphore, or a small thread pool;
implementation detail, not exposed to consumers) sized to `config.max_concurrency`,
plus per-call retry/backoff on transient provider errors. Because it's implemented
once on the base class, `LangChainLLMService` and any future concrete implementation
get it for free by implementing only `generate()`.

**No Prefect (or similar orchestrator).** That class of tool earns its cost when
there's a multi-step DAG with cross-step dependencies, scheduling, or a need for a
persistent run history/dashboard. This module's actual shape is "N independent API
calls, run some at a time, retry the failures" — a bounded-concurrency batch call
with backoff covers it completely, without introducing a scheduler/server dependency
into a project whose whole planning stage is otherwise millisecond-fast, in-process
metadata munging (design doc D1, D2). Revisit only if a real multi-step LLM workflow
with dependencies shows up — nothing in scope today has that shape.

---

## 9. Cross-cutting concerns

Each is an `LLMService`-wrapping decorator (§6's composition order), independently
testable against a fake inner service.

**Caching — `CachingLLMService` (`caching.py`).** Generic, not familiarity-specific:
key on `hash(request_payload, output_schema_name, model_id, prompt_version)`, where
`prompt_version` comes from `PromptManager` (§5). Distinct from design doc D6's audio
content-hash cache — nothing here is audio-keyed; this cache is keyed on the
identifying text fields and the prompt/model that produced the response.

**Logging/observability — `LoggingLLMService` (`observability.py`).** Every call
logged once, centrally: consumer name (from `LLMRequest.metadata`), model, latency,
cache hit/miss, token count if available. The reason this belongs in `llm_service`
rather than each consumer reimplementing it.

**Error handling — `errors.py`.** The service raises typed errors —
`LLMProviderError` (network/API failures) and `LLMValidationError`
(schema-validation failures) — on failure/timeout. Each *consumer* decides how to
degrade; the service itself never decides this. For familiarity scoring specifically
that means `familiarity_score = null` (soft score, design doc D10), never blocking a
track from planning — but that degradation policy lives in the consumer, not here.

---

## 10. Testing strategy

The interface lets every consumer's tests use a mock/fixture `LLMService` — no live
API calls, no network, in any consumer's unit tests. This mirrors design doc D2's
metadata-only testability goal one layer over: planning is testable from JSON
fixtures because analysis is metadata by the time it reaches planning; consumers of
`llm_service` are testable from fixtures for the same reason one layer earlier.

- `LangChainLLMService` gets its own thin test against recorded/fixture responses,
  isolated from every consumer's tests.
- `CachingLLMService` and `LoggingLLMService` are tested against a fake inner
  `LLMService`, independent of the real provider.
- `PromptManager` is tested independently (template load/render/version) with no LLM
  calls involved at all.
- `interface.py` and `errors.py` have no dedicated test files — a `Protocol` and
  plain exception classes carry no behavior to test.

---

## 11. File layout

`llm_service` is the first module under a new `common/` layer, alongside future
layers like `ingestion/`, `planning/`, `render/` (per `resources/documentation/README.md`).
Tests mirror `src/` 1:1, per `tests/README.md`.

```
src/common/llm_service/
  __init__.py            # public exports: LLMService, get_llm_service, TextRequest,
                          # MultimodalRequest, ImageInput, LLMProviderError,
                          # LLMValidationError
  interface.py            # LLMService Protocol
  base.py                  # BaseLLMService — default generate_batch() (§8)
  schema.py                 # LLMRequest, TextRequest, MultimodalRequest, ImageInput (§3)
  errors.py                  # LLMProviderError, LLMValidationError
  factory.py                  # LLMServiceConfig + get_llm_service() (§6)
  langchain_impl.py            # LangChainLLMService (§7)
  caching.py                    # CachingLLMService decorator (§9)
  observability.py                # LoggingLLMService decorator (§9)
  prompt_manager.py                 # PromptManager (§5)
  prompts/                           # template assets (not importable code)
    familiarity_score.txt

tests/common/llm_service/
  test_base.py             # default generate_batch() against a fake generate()
  test_schema.py            # TextRequest / MultimodalRequest / ImageInput validation
  test_factory.py             # config-memoized singleton behavior
  test_langchain_impl.py        # LangChainLLMService against fixture/recorded responses
  test_caching.py                 # CachingLLMService decorator
  test_observability.py             # LoggingLLMService decorator
  test_prompt_manager.py              # template load/render/version, no LLM calls
```

---

## 12. Rejected alternatives

| Rejected | Instead | Why |
|---|---|---|
| One `LLMRequest` with an optional `images` field | `TextRequest` / `MultimodalRequest` as separate concrete types (§3) | An empty-but-present `images` list is a valid-looking but meaningless state; a discriminated pair makes it unrepresentable |
| Familiarity-scorer-specific service, generalized later if needed | Generic `llm_service` from the start, familiarity scoring as its first consumer (§1) | "Common" was the explicit scope — every future LLM call (NL config parsing, anything else) must not require touching this module's public surface |
| Prefect / workflow orchestrator for batch calls | Bounded-concurrency `generate_batch()` on `BaseLLMService` (§8) | No multi-step DAG, no cross-step dependency, no scheduling need — an orchestrator's cost buys nothing here |
| Caching/logging baked into `LangChainLLMService` | Decorator composition in the factory (§6, §9) | Keeps the provider implementation swappable and each concern independently testable against a fake inner service |
| `generate()` returning a result wrapper (output + usage + cache flag) | Bare `T` return; metadata captured by logging as a side effect (§2) | Keeps every consumer's call site a one-liner; usage stats are a deliberate future addition, not default ceremony |

---

## 13. Open questions

| # | Question | Blocks |
|---|---|---|
| Q1 | OpenCode Zen free-tier rate limits / stability under a ~15-track run | `max_concurrency` default (§6, §8) |
| Q2 | Prompt versioning scheme — semantic version in the template file, or content-hash of the template itself | Cache key stability (§9) |
| Q3 | Does NL-config-parsing (deferred, §1) need anything beyond a new consumer schema + a new `PromptManager` template, or does it expose a gap in `LLMRequest` | Scope of this module when that consumer is built |
