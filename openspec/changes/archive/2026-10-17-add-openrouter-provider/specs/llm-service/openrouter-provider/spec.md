# Spec Delta

## Purpose

An `llm_service` provider that sends requests to OpenRouter through LangChain's dedicated OpenRouter integration, so any OpenRouter-hosted model can serve the existing `LLMService` contract by changing only `config.yaml`.

## ADDED Requirements

### Requirement: Selected by config only
The provider SHALL be registered under the name `openrouter` as a built-in, so importing `llm_service` makes it available. It SHALL be used only when `config.yaml`'s `llm_service.provider` is `openrouter`; no caller code SHALL change to select it.

#### Scenario: Switching provider
- **WHEN** `config.yaml` sets `provider: openrouter`, `model: <an OpenRouter model id>`, `base_url: https://openrouter.ai/api/v1` and `api_key_env_var: OPENROUTER_API_KEY`, and `.env` holds that key
- **THEN** `get_llm_service()` returns a service whose calls go to OpenRouter with that model

#### Scenario: Other providers unaffected
- **WHEN** `config.yaml` keeps `provider: gemini`
- **THEN** calls behave exactly as before this change

### Requirement: Same request contract as the existing provider
The provider SHALL accept `TextRequest` and `MultimodalRequest`. A text request SHALL be sent as a single user message. A multimodal request SHALL be sent as one user message holding the prompt text followed by each image in order, with base64 images as data URLs and URL images passed as given.

#### Scenario: Images in order
- **WHEN** a `MultimodalRequest` has a prompt and three base64 PNG images
- **THEN** the message sent has one text part followed by three image parts, in the same order

### Requirement: Per-request settings
A request's `model`, `temperature`, `max_tokens` and `timeout_s` SHALL override the configured defaults for that call only. When a request leaves them unset, the configured `model` and `request_timeout_s` SHALL apply, and temperature and max tokens SHALL be left to the provider's default.

#### Scenario: Model override
- **WHEN** the configured model is `google/gemma-4-31b-it` and a request sets `model="anthropic/claude-sonnet-4.6"`
- **THEN** that call uses `anthropic/claude-sonnet-4.6`, and the next call without a model uses `google/gemma-4-31b-it`

#### Scenario: Timeout in seconds
- **WHEN** a request sets `timeout_s=180`
- **THEN** the call is allowed 180 seconds before timing out

### Requirement: Structured output
The provider SHALL return an instance of the caller's `output_schema`, enforced through function calling, as the existing provider does. If the model's reply cannot be parsed or validated against the schema, the provider SHALL raise `LLMValidationError`.

#### Scenario: Valid structured reply
- **WHEN** the model replies with arguments matching the schema
- **THEN** `generate()` returns a validated instance of that schema

#### Scenario: Reply does not match schema
- **WHEN** the model's reply is missing a required field
- **THEN** `generate()` raises `LLMValidationError`, not `LLMProviderError`

### Requirement: Errors and retries
Any network, HTTP or API failure from OpenRouter SHALL be raised as `LLMProviderError` and retried by the shared `BaseLLMService` retry policy. The underlying SDK's own retries SHALL be disabled, so a failing call is attempted no more times than with the existing provider.

#### Scenario: Overloaded upstream
- **WHEN** OpenRouter answers a call with HTTP 503
- **THEN** the call is retried per the shared policy and, if every attempt fails, raises `LLMProviderError` carrying the provider's message

### Requirement: App attribution
Every request SHALL identify the application to OpenRouter as `ai-dj` (attribution title), not the LangChain default.

#### Scenario: Attribution header
- **WHEN** any call is made through this provider
- **THEN** the request's app title is `ai-dj`

### Requirement: Credentials stay out of code
The API key SHALL be read only from the `.env` variable that `config.yaml` names in `api_key_env_var`. It SHALL NOT be read implicitly from any other environment variable, logged, or written to the cache.

#### Scenario: Missing key
- **WHEN** `provider: openrouter` is configured but the named `.env` variable is empty
- **THEN** loading the config fails with the existing "<VAR> is not set" error before any request is made
