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
  model          : str | None      # override; None = factory default model
  temperature    : float | None    # None = provider default; range [0, 2] if set
  max_tokens     : int | None      # None = provider default; must be > 0 if set
  timeout_s      : float | None    # None = service default
  metadata       : dict[str, str]  # consumer name / purpose tag, for logging only —
                                    # never sent to the provider
  prompt_version : str | None      # set by PromptManager when it renders a template
                                    # (§4); the explicit, typed carrier for the
                                    # `prompt_version` component of the cache key
                                    # (§9) — kept separate from `metadata` because it
                                    # has a real consumer (the cache key), not just
                                    # logging

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
  `{year}`, `{artist}`) → a finished prompt string *and* that template's version,
  both handed to the caller, which attaches them as `TextRequest.prompt` /
  `.prompt_version` (or `MultimodalRequest`'s) — not two separate lookups.
- **Version** — each template's version is the canonical source for the
  `prompt_version` used in the cache key (§7) — not a separately hand-tracked
  constant. Reload/hot-swap during development is a `PromptManager` concern, not
  something callers or the cache need to know about.

---

## 6. Factory & composition (`factory.py`)

```
LLMServiceConfig — every field required, none of them defaulted in Python:
  provider          : str              # a provider registry key (see below) —
                                        # "opencode_zen" is the only one registered
                                        # in v1, but this is a lookup, not a fixed
                                        # choice
  model             : str              # a free OpenCode Zen model id
  base_url          : str              # e.g. "https://opencode.ai/zen/v1"
  api_key           : str              # credential — never hardcoded, never logged
  max_concurrency   : int              # cap for generate_batch (§8)
  request_timeout_s : float            # per-call timeout
  cache_enabled     : bool
  cache_dir         : str              # where CachingLLMService persists responses (§9)

get_llm_service(config: LLMServiceConfig | None = None) -> LLMService
```

**`config.yaml` is the only place a default value for these fields is declared** —
`LLMServiceConfig` itself declares none. Two places for the same default (a Python
fallback *and* a YAML value) is exactly the kind of drift this spec's own invariants
elsewhere warn against; there is exactly one place to change, say, the default
`max_concurrency`, not two.

`config` is optional — when omitted, `get_llm_service()` loads it itself: `api_key`
from the `OPEN_CODE_ZEN_API_KEY` environment variable (`.env`, credentials only, never
committed), everything else from a committed `config.yaml` at the repo root, under a
top-level `llm_service:` key (sibling keys for other modules' config, e.g. `logging:`,
are expected as the codebase grows) — every one of those keys must be present, since
nothing defaults. Passing `config` explicitly — as any consumer's test does — bypasses
both files entirely, but must still supply every field.

**Provider selection is a registry lookup, not a hardcoded call.**
`providers/registry.py` maps a provider name to a *factory function*
(`LLMServiceConfig -> LLMService`), not directly to a class — a class-keyed registry
would force every future provider to accept the exact same constructor kwargs as
`OpenAICompatibleLLMService`, a real constraint the moment a non-OpenAI-compatible
provider shows up with a different shape. `get_llm_service()` resolves the concrete
provider with `get_provider_factory(config.provider)(config)` instead of naming a
class directly.

```
ProviderFactory = Callable[[LLMServiceConfig], LLMService]

register_provider(name: str, factory: ProviderFactory, *, overwrite: bool = False) -> None
  # raises if name is already registered and overwrite=False — guards against a
  # stray re-registration silently clobbering a real provider

get_provider_factory(name: str) -> ProviderFactory
  # raises, listing what *is* registered, if name isn't found
```

Two ways to add a provider:
1. **Built-in** — a new file under `providers/`, defining a factory function and
   calling `register_provider(name, factory_fn)` at module level; add the module to
   `providers/__init__.py`'s import list so importing the package registers every
   built-in provider as a side effect (`OpenAICompatibleLLMService` registers itself
   under `"opencode_zen"` this way — §7).
2. **External** — any caller can call `register_provider()` directly before
   `get_llm_service()`, with no edit to this module at all.

**Composition happens here, as decorators, in a fixed order:**

```
CachingLLMService(LoggingLLMService(OpenAICompatibleLLMService(config)))
```

Caching outermost, logging in the middle: a cache hit short-circuits before reaching
`LoggingLLMService` at all, which is correct, not a gap — a hit did no work worth
logging (no latency, no cost, no provider call happened). `LoggingLLMService` only
ever sees real calls that actually reached (or attempted to reach) the provider, which
is exactly the set of events worth a log line. `OpenAICompatibleLLMService` (§7) never needs
to know caching or logging exist — each concern is a plain `LLMService` wrapping
another `LLMService`.

**Singleton — memoized by config, not a raw global.** `get_llm_service()` caches the
constructed (already-decorated) instance keyed on the resolved config, so the
underlying LangChain client / HTTP connection pool is built once and reused — the
actual reason a singleton matters here, not global-state convenience. A different
config (e.g. a test passing an explicit override, or a mock `LLMService` injected for
a consumer's unit tests) gets its own instance rather than colliding with the cached
default.

---

## 7. Concrete implementation — `OpenAICompatibleLLMService` (`providers/openai_compatible.py`)

Extends `BaseLLMService` (§8) and implements only `generate()` — `generate_batch()`
comes free from the base class's bounded-concurrency default. Wraps LangChain's
`ChatOpenAI` pointed at OpenCode Zen via `base_url`/`api_key`. Registers itself in
`providers/registry.py` (§6) under the name `"opencode_zen"` at module level.

- Dispatches `TextRequest` → plain message content; `MultimodalRequest` → LangChain's
  multi-part message content (text block + image blocks).
- Uses `with_structured_output(output_schema, method="function_calling")` per call so
  the schema is enforced at the LangChain layer, not hand-parsed JSON.
  `method="function_calling"` is deliberate, not the default: LangChain's default
  (`"json_schema"`) is OpenAI's newer strict `response_format` mode, which most models
  proxied through an OpenAI-compatible gateway don't support — confirmed against a
  live call (`invalid_request_error: This response_format type is unavailable now`).
  Tool/function calling is the older, far more broadly compatible mechanism. (Not
  every model tolerates *that* either — a reasoning/"thinking" model can reject the
  forced `tool_choice` function-calling requires; that's a model-capability limit, not
  something this layer can paper over.)
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
— with a **capped concurrency** (a persistent `ThreadPoolExecutor`, sized to
`config.max_concurrency`, created once and reused — not spun up per call) not exposed
to consumers. Because it's implemented once on the base class, `OpenAICompatibleLLMService`
and any future concrete implementation get it for free by implementing only
`generate()`.

**Retry/backoff lives at the point of the actual provider call, not only in the batch
path.** `BaseLLMService` exposes a `_call_with_retry()` helper (3 attempts,
exponential backoff: 0.5s / 1s / 2s) that a concrete implementation's `generate()`
wraps its provider call in. This means a bare single `generate()` call retries exactly
like a call made through `generate_batch()` — retry is a property of "making a
provider call," not of the batching mechanism, so it can't be lost depending on which
entry point a consumer happens to use. Only `LLMProviderError`-shaped failures
(network/API) retry; `LLMValidationError` (bad structured-output parse) never retries
automatically — the same bad input tends to reproduce the same bad output, and §7
already treats it as a distinct failure mode with distinct causes.

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

**Storage: disk-backed, one JSON file per cache key**, under
`LLMServiceConfig.cache_dir` (§6) — one file named `<key>.json` holding the response's
`model_dump()`. Not in-memory-only: OpenCode Zen calls are meant to be "cached
forever" per design doc §6.1, so a cache that discards on process exit would re-pay
free-tier rate limits every run. On a hit, the stored dict is validated back into the
caller's `output_schema` via `output_schema.model_validate(...)` — the schema identity
is guaranteed by the key (which already includes `output_schema_name`), so nothing
about the schema needs to be stored alongside the data.

**Logging/observability — `LoggingLLMService` (`observability.py`).** Every call that
actually reaches (or attempts to reach) the provider is logged once, centrally:
consumer name (from `LLMRequest.metadata`), model, latency, token count if available.
Cache hits are not logged here — they're not visible to this layer by construction
(§6's composition order puts caching outside logging), and a hit did no work worth a
log line anyway. The reason this belongs in `llm_service` rather than each consumer
reimplementing it. Uses `common.logging.get_logger(...)` (see
`resources/documentation/common/logging/spec.md`) rather than configuring its own
handler — the same shared logger setup every module in this codebase uses.

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

- `OpenAICompatibleLLMService` gets its own thin test against recorded/fixture responses,
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
  caching.py                    # CachingLLMService decorator (§9)
  observability.py                # LoggingLLMService decorator (§9)
  prompt_manager.py                 # PromptManager (§5)
  prompts/                           # template assets (not importable code)
    familiarity_score.txt
  providers/                          # concrete provider implementations
    __init__.py                        # imports every built-in provider module,
                                        # registering each as a side effect (§6)
    registry.py                         # register_provider(), get_provider_factory() (§6)
    openai_compatible.py                 # OpenAICompatibleLLMService (§7);
                                          # registers itself as "opencode_zen"

tests/common/llm_service/
  test_base.py             # default generate_batch() against a fake generate()
  test_schema.py            # TextRequest / MultimodalRequest / ImageInput validation
  test_factory.py             # config-memoized singleton behavior
  test_caching.py               # CachingLLMService decorator
  test_observability.py           # LoggingLLMService decorator
  test_prompt_manager.py            # template load/render/version, no LLM calls
  conftest.py                         # make_llm_service_config fixture
  providers/
    test_registry.py                   # register/lookup round trip, unknown-name
                                        # and duplicate-registration errors
    test_openai_compatible.py          # OpenAICompatibleLLMService against
                                        # fixture/recorded responses
```

Concrete provider implementations live under `providers/`; everything else at the top
of `llm_service/` is factory/interface/schema/decorator infrastructure shared by every
provider, not tied to any one of them.

---

## 12. Rejected alternatives

| Rejected | Instead | Why |
|---|---|---|
| One `LLMRequest` with an optional `images` field | `TextRequest` / `MultimodalRequest` as separate concrete types (§3) | An empty-but-present `images` list is a valid-looking but meaningless state; a discriminated pair makes it unrepresentable |
| Familiarity-scorer-specific service, generalized later if needed | Generic `llm_service` from the start, familiarity scoring as its first consumer (§1) | "Common" was the explicit scope — every future LLM call (NL config parsing, anything else) must not require touching this module's public surface |
| Prefect / workflow orchestrator for batch calls | Bounded-concurrency `generate_batch()` on `BaseLLMService` (§8) | No multi-step DAG, no cross-step dependency, no scheduling need — an orchestrator's cost buys nothing here |
| Caching/logging baked into `OpenAICompatibleLLMService` | Decorator composition in the factory (§6, §9) | Keeps the provider implementation swappable and each concern independently testable against a fake inner service |
| `generate()` returning a result wrapper (output + usage + cache flag) | Bare `T` return; metadata captured by logging as a side effect (§2) | Keeps every consumer's call site a one-liner; usage stats are a deliberate future addition, not default ceremony |

---

## 13. Open questions

| # | Question | Blocks |
|---|---|---|
| Q1 | OpenCode Zen free-tier rate limits / stability under a ~15-track run | `max_concurrency` default (§6, §8) |
| Q2 | Prompt versioning scheme — semantic version in the template file, or content-hash of the template itself | Cache key stability (§9) |
| Q3 | Does NL-config-parsing (deferred, §1) need anything beyond a new consumer schema + a new `PromptManager` template, or does it expose a gap in `LLMRequest` | Scope of this module when that consumer is built |

---

## Amendments

- **2026-08-15** — Two clarifications surfaced during initial implementation, both
  additive (no public signature changed; nothing already built against this spec
  breaks):
  1. Retry/backoff moved from "only inside `generate_batch()`'s dispatch loop" to a
     shared `BaseLLMService._call_with_retry()` helper used at the point of the actual
     provider call (§8) — so a bare `generate()` call retries too, not just batched
     calls.
  2. Cache storage was unpinned (generic "key on a hash," no stated backend). Now
     specified: disk-backed, one JSON file per key, under a new
     `LLMServiceConfig.cache_dir` field (§6, §9).
  3. §9's cache key already named `prompt_version` as a component, but no field on
     `LLMRequest` actually carried it from `PromptManager` to `CachingLLMService`.
     Added `LLMRequest.prompt_version: str | None` (§3); `PromptManager.render()`
     returns it alongside the rendered text (§5) instead of it being a second,
     separate lookup.
  4. Composition order reversed: `LoggingLLMService(CachingLLMService(...))` made
     "logs every request including cache hits" unimplementable without either a
     fragile latency heuristic or breaking decorator symmetry, since `generate()`
     deliberately returns a bare value with no hit/miss metadata (§2). Now
     `CachingLLMService(LoggingLLMService(OpenAICompatibleLLMService(config)))` (§6) — a
     cache hit short-circuits before logging is ever reached, which is correct
     (nothing worth logging happened), and logging only sees real provider calls.

- **2026-08-15** — Post-implementation reorganization, all internal/organizational —
  `LLMService`'s public methods and `get_llm_service()`'s signature are unchanged, and
  nothing outside this module ever imported the moved path directly:
  1. Concrete provider implementations moved under a new `providers/` subdirectory;
     `langchain_impl.py` renamed to `providers/openai_compatible.py`, and
     `LangChainLLMService` renamed to `OpenAICompatibleLLMService` — the class has zero
     OpenCode-Zen-specific logic (`base_url`/`api_key`/`model` are all config-driven),
     so it's named for the protocol it speaks, not the library it's built with (§7,
     §11).
  2. `LLMServiceConfig`'s Python-level defaults removed (§6) — every field is now
     required; `config.yaml` is the sole place a default is declared.

- **2026-08-15** — Two more changes, both additive:
  1. **Provider registry added** (§6, §11). `LLMServiceConfig.provider` existed since
     the first draft of this spec but was never actually read — `get_llm_service()`
     always constructed `OpenAICompatibleLLMService` directly. Now `provider` is a
     real registry key: `providers/registry.py` maps it to a factory function
     (`LLMServiceConfig -> LLMService`), and `OpenAICompatibleLLMService` registers
     itself under `"opencode_zen"`. `get_llm_service()`'s signature is unchanged, and
     `config.yaml`'s existing `provider: opencode_zen` continues to resolve to exactly
     the same object graph as before — this closes the gap between what the field
     always claimed to do and what the code actually did.
  2. **`method="function_calling"` documented** (§7) — this was already live in
     `providers/openai_compatible.py` (found and fixed during a live test against
     OpenCode Zen: the default `with_structured_output` method sent a
     `response_format` most proxied models reject) but had never been written back
     into the spec. Recorded here so spec and code agree, per this repo's own rule
     that they must never drift silently.
