# MarKom Gateway Feature Parity Plan

## Goal

Build an organization-owned gateway in `markom_gateway/` that implements the selected open-source LiteLLM gateway and SDK behaviors, while using the LiteLLM repository and documentation as a behavior reference during development. This is a staged project, not a single release.

Each item has two checkboxes:

- **Done** means the MarKom implementation and meaningful tests are complete.
- **Reviewed** means a separate review of behavior, security, tests, and documentation is complete.

Mark an item reviewed only after it is implemented and its validation passes. Keep an item unchecked when support is partial, experimental, or unverified.

## Baseline and scope

- Research checked: **October 24, 2026**
- Local LiteLLM package version: **1.98.0**, from the checkout's `pyproject.toml`
- Latest official LiteLLM release checked: **v1.106.3**, published October 24, 2026
- Initial reference baseline: **v1.106.3**. Refresh this baseline and record the new version/date when the parity scope is reviewed.
- Deployment priority: Docker and Docker Compose. CI/CD is out of scope for this plan.
- Product target: open-source gateway and SDK behavior that MarKom selects. Enterprise-only and hosted services are excluded unless separately scoped and approved.
- The target is behavioral compatibility with independently maintained MarKom code. Use LiteLLM source to understand behavior, not to duplicate whole files or large source sections. Review applicable licenses before adapting any specific implementation.
- Removing LiteLLM code or dependencies is a final gated milestone. Do not remove them until all required replacements have passed their acceptance checks.

The upstream project describes support for 100+ providers, an OpenAI-compatible SDK and proxy, and APIs including Chat Completions, Responses, Embeddings, Images, Audio, Batches, Rerank, A2A, and Messages. Its gateway documentation also covers virtual keys, spend tracking, model routing/load balancing, caching, and guardrails. These are upstream scope references, not a promise that every provider or API is already implemented in MarKom.

## Current MarKom status

### Standalone runtime

- [x] Done: OpenAI-compatible `POST /v1/chat/completions`
- [x] Reviewed: OpenAI-compatible `POST /v1/chat/completions`
- [x] Done: `GET /v1/models` for configured model routes
- [x] Reviewed: `GET /v1/models` for configured model routes
- [x] Done: streaming chat completion passthrough
- [x] Reviewed: streaming chat completion passthrough
- [x] Done: bearer-key authentication using `MARKOM_MASTER_KEY`
- [x] Reviewed: bearer-key authentication using `MARKOM_MASTER_KEY`
- [x] Done: OpenRouter provider adapter
- [x] Reviewed: OpenRouter provider adapter
- [x] Done: OpenAI-compatible provider adapter and OpenAI configuration
- [x] Reviewed: OpenAI-compatible provider adapter and OpenAI configuration
- [x] Done: model aliases and ordered provider fallback on network errors, HTTP 429, and HTTP 5xx
- [ ] Reviewed: model aliases and ordered provider fallback on network errors, HTTP 429, and HTTP 5xx
- [x] Done: Dockerfile and standalone Docker Compose service
- [ ] Reviewed: Docker image build and live container smoke test; Docker daemon access was unavailable during initial validation
- [ ] Done: authenticated tenant keys, teams, and persisted identity
- [ ] Reviewed: authenticated tenant keys, teams, and persisted identity

### Existing LiteLLM-dependent features

These capabilities exist in the repository as integrations or admin features, but are not yet verified as independent MarKom runtime features. Do not count them as standalone parity until replaced and tested without importing LiteLLM.

- [ ] Done: audit logging and retention
- [ ] Reviewed: audit logging and retention
- [ ] Done: semantic response cache
- [ ] Reviewed: semantic response cache
- [ ] Done: provider health measurements and health-based routing
- [ ] Reviewed: provider health measurements and health-based routing
- [ ] Done: PII detection and redaction
- [ ] Reviewed: PII detection and redaction
- [ ] Done: admin API, dashboard, RBAC, and compliance endpoints
- [ ] Reviewed: admin API, dashboard, RBAC, and compliance endpoints

## Phased implementation checklist

### Phase 0: Scope, compatibility, and independent foundation

- [ ] Done: define the required API compatibility level and behavior for each endpoint
- [ ] Reviewed: define the required API compatibility level and behavior for each endpoint
- [ ] Done: inventory all imports, runtime dependencies, configuration, and deployment paths that couple `markom_gateway/` to LiteLLM
- [ ] Reviewed: inventory all imports, runtime dependencies, configuration, and deployment paths that couple `markom_gateway/` to LiteLLM
- [ ] Done: establish versioned provider, endpoint, and feature coverage records
- [ ] Reviewed: establish versioned provider, endpoint, and feature coverage records
- [ ] Done: establish common request/response, error, authentication, provider, and storage interfaces
- [ ] Reviewed: establish common request/response, error, authentication, provider, and storage interfaces
- [ ] Done: establish safe configuration and secrets handling for Docker deployments
- [ ] Reviewed: establish safe configuration and secrets handling for Docker deployments

### Phase 1: Core gateway API and provider runtime

- [ ] Done: OpenAI-compatible Chat Completions, request validation, errors, and response compatibility
- [ ] Reviewed: OpenAI-compatible Chat Completions, request validation, errors, and response compatibility
- [ ] Done: streaming completions, cancellation, timeouts, and connection cleanup
- [ ] Reviewed: streaming completions, cancellation, timeouts, and connection cleanup
- [ ] Done: model listing and model aliases
- [ ] Reviewed: model listing and model aliases
- [ ] Done: OpenAI-compatible Completions API
- [ ] Reviewed: OpenAI-compatible Completions API
- [ ] Done: provider adapter contracts, credentials, timeouts, and structured errors
- [ ] Reviewed: provider adapter contracts, credentials, timeouts, and structured errors
- [ ] Done: provider compatibility tests and Docker-based smoke tests
- [ ] Reviewed: provider compatibility tests and Docker-based smoke tests

### Phase 2: Provider coverage

Implement providers through MarKom-owned adapters and shared protocol implementations. Provider support is complete only when authentication, request/response conversion, streaming where available, error mapping, model listing behavior, and tests are documented.

- [ ] Done: OpenAI and OpenAI-compatible APIs, including self-hosted endpoints
- [ ] Reviewed: OpenAI and OpenAI-compatible APIs, including self-hosted endpoints
- [ ] Done: OpenRouter
- [ ] Reviewed: OpenRouter
- [ ] Done: Anthropic
- [ ] Reviewed: Anthropic
- [ ] Done: Google AI Studio and Gemini
- [ ] Reviewed: Google AI Studio and Gemini
- [ ] Done: Vertex AI
- [ ] Reviewed: Vertex AI
- [ ] Done: Azure OpenAI
- [ ] Reviewed: Azure OpenAI
- [ ] Done: AWS Bedrock
- [ ] Reviewed: AWS Bedrock
- [ ] Done: AWS SageMaker
- [ ] Reviewed: AWS SageMaker
- [ ] Done: Cohere
- [ ] Reviewed: Cohere
- [ ] Done: Mistral
- [ ] Reviewed: Mistral
- [ ] Done: Hugging Face hosted and self-hosted inference
- [ ] Reviewed: Hugging Face hosted and self-hosted inference
- [ ] Done: Ollama and vLLM
- [ ] Reviewed: Ollama and vLLM
- [ ] Done: Together AI, Fireworks AI, Groq, DeepInfra, Replicate, and other selected hosted providers
- [ ] Reviewed: Together AI, Fireworks AI, Groq, DeepInfra, Replicate, and other selected hosted providers
- [ ] Done: remaining upstream open-source provider integrations inventoried and prioritized
- [ ] Reviewed: remaining upstream open-source provider integrations inventoried and prioritized

### Phase 3: Routing, resilience, and capacity

- [ ] Done: multiple deployments behind a single public model name
- [ ] Reviewed: multiple deployments behind a single public model name
- [ ] Done: routing strategies such as round-robin, weighted, least-busy, latency-aware, and cost-aware
- [ ] Reviewed: routing strategies such as round-robin, weighted, least-busy, latency-aware, and cost-aware
- [ ] Done: retries, backoff, retryable error policy, and request timeouts
- [ ] Reviewed: retries, backoff, retryable error policy, and request timeouts
- [ ] Done: configured fallbacks and fallback limits
- [ ] Reviewed: configured fallbacks and fallback limits
- [ ] Done: concurrency limits and per-deployment RPM/TPM capacity controls
- [ ] Reviewed: concurrency limits and per-deployment RPM/TPM capacity controls
- [ ] Done: circuit breaking, health state, and recovery behavior
- [ ] Reviewed: circuit breaking, health state, and recovery behavior
- [ ] Done: distributed routing and rate-limit state for multi-replica Docker deployments
- [ ] Reviewed: distributed routing and rate-limit state for multi-replica Docker deployments
- [ ] Done: routing decision telemetry and deterministic routing tests
- [ ] Reviewed: routing decision telemetry and deterministic routing tests

### Phase 4: Authentication, keys, teams, and access control

- [ ] Done: master/admin credentials with secure storage and rotation
- [ ] Reviewed: master/admin credentials with secure storage and rotation
- [ ] Done: virtual API key creation, listing, updating, revocation, expiration, and hashing
- [ ] Reviewed: virtual API key creation, listing, updating, revocation, expiration, and hashing
- [ ] Done: users, teams, memberships, and service identities
- [ ] Reviewed: users, teams, memberships, and service identities
- [ ] Done: model allowlists, aliases, and access policy per key/team
- [ ] Reviewed: model allowlists, aliases, and access policy per key/team
- [ ] Done: key/team RPM, TPM, concurrency, and budget enforcement
- [ ] Reviewed: key/team RPM, TPM, concurrency, and budget enforcement
- [ ] Done: authentication integrations and scoped authorization rules
- [ ] Reviewed: authentication integrations and scoped authorization rules
- [ ] Done: persistence migrations, transaction safety, and database recovery behavior
- [ ] Reviewed: persistence migrations, transaction safety, and database recovery behavior

### Phase 5: Usage, cost, budgets, and accounting

- [ ] Done: token usage capture across providers and endpoints
- [ ] Reviewed: token usage capture across providers and endpoints
- [ ] Done: provider/model cost calculation with versioned pricing data
- [ ] Reviewed: provider/model cost calculation with versioned pricing data
- [ ] Done: spend records associated with keys, users, teams, and end users
- [ ] Reviewed: spend records associated with keys, users, teams, and end users
- [ ] Done: budgets, budget windows, alerts, and hard enforcement
- [ ] Reviewed: budgets, budget windows, alerts, and hard enforcement
- [ ] Done: usage and spend query APIs with pagination and filtering
- [ ] Reviewed: usage and spend query APIs with pagination and filtering
- [ ] Done: accounting reconciliation and tests for missing or provider-reported usage
- [ ] Reviewed: accounting reconciliation and tests for missing or provider-reported usage

### Phase 6: Data APIs and modality support

- [ ] Done: Embeddings
- [ ] Reviewed: Embeddings
- [ ] Done: Responses API and conversation/state handling
- [ ] Reviewed: Responses API and conversation/state handling
- [ ] Done: Anthropic Messages API compatibility
- [ ] Reviewed: Anthropic Messages API compatibility
- [ ] Done: image generation and image understanding
- [ ] Reviewed: image generation and image understanding
- [ ] Done: audio transcription and translation
- [ ] Reviewed: audio transcription and translation
- [ ] Done: text-to-speech and speech/audio generation
- [ ] Reviewed: text-to-speech and speech/audio generation
- [ ] Done: reranking
- [ ] Reviewed: reranking
- [ ] Done: batch jobs and batch lifecycle APIs
- [ ] Reviewed: batch jobs and batch lifecycle APIs
- [ ] Done: files and fine-tuning APIs where supported by selected providers
- [ ] Reviewed: files and fine-tuning APIs where supported by selected providers
- [ ] Done: remaining documented upstream endpoints inventoried and dispositioned
- [ ] Reviewed: remaining documented upstream endpoints inventoried and dispositioned

### Phase 7: Caching, guardrails, and request policies

- [ ] Done: exact response caching with TTL, invalidation, and cache controls
- [ ] Reviewed: exact response caching with TTL, invalidation, and cache controls
- [ ] Done: supported cache backends for local Docker and multi-replica deployments
- [ ] Reviewed: supported cache backends for local Docker and multi-replica deployments
- [ ] Done: semantic caching with opt-in thresholds and safe response eligibility
- [ ] Reviewed: semantic caching with opt-in thresholds and safe response eligibility
- [ ] Done: guardrail interface, ordering, configuration, and failure behavior
- [ ] Reviewed: guardrail interface, ordering, configuration, and failure behavior
- [ ] Done: PII detection, masking, and blocking policies
- [ ] Reviewed: PII detection, masking, and blocking policies
- [ ] Done: prompt-injection and content policy integrations
- [ ] Reviewed: prompt-injection and content policy integrations
- [ ] Done: request/response transformations, parameter validation, and policy checks
- [ ] Reviewed: request/response transformations, parameter validation, and policy checks

### Phase 8: Logs, metrics, tracing, and operations

- [ ] Done: structured request logs with sensitive-content redaction
- [ ] Reviewed: structured request logs with sensitive-content redaction
- [ ] Done: metrics for traffic, errors, latency, token usage, and spend
- [ ] Reviewed: metrics for traffic, errors, latency, token usage, and spend
- [ ] Done: tracing and supported observability export integrations
- [ ] Reviewed: tracing and supported observability export integrations
- [ ] Done: audit trail, retention, export, and data deletion workflows
- [ ] Reviewed: audit trail, retention, export, and data deletion workflows
- [ ] Done: health, readiness, dependency checks, and operational diagnostics
- [ ] Reviewed: health, readiness, dependency checks, and operational diagnostics
- [ ] Done: Docker deployment, configuration, persistence, backup, and upgrade documentation
- [ ] Reviewed: Docker deployment, configuration, persistence, backup, and upgrade documentation

### Phase 9: Admin API and dashboard

- [ ] Done: model/deployment management without direct LiteLLM imports
- [ ] Reviewed: model/deployment management without direct LiteLLM imports
- [ ] Done: key, user, team, and role management
- [ ] Reviewed: key, user, team, and role management
- [ ] Done: spend, usage, provider health, and routing views
- [ ] Reviewed: spend, usage, provider health, and routing views
- [ ] Done: audit, guardrail, incident, and compliance workflows
- [ ] Reviewed: audit, guardrail, incident, and compliance workflows
- [ ] Done: dashboard authorization matches backend authorization
- [ ] Reviewed: dashboard authorization matches backend authorization

### Phase 10: Python SDK and ecosystem compatibility

- [ ] Done: MarKom Python client for gateway requests
- [ ] Reviewed: MarKom Python client for gateway requests
- [ ] Done: selected provider-agnostic SDK methods with sync and async behavior
- [ ] Reviewed: selected provider-agnostic SDK methods with sync and async behavior
- [ ] Done: supported OpenAI-compatible client behavior and documented migration path
- [ ] Reviewed: supported OpenAI-compatible client behavior and documented migration path
- [ ] Done: supported tool/function calling and structured output behavior
- [ ] Reviewed: supported tool/function calling and structured output behavior
- [ ] Done: supported LangChain, LlamaIndex, and other selected ecosystem integrations
- [ ] Reviewed: supported LangChain, LlamaIndex, and other selected ecosystem integrations

### Phase 11: Agent and tool gateway capabilities

- [ ] Done: MCP client/server gateway behavior in scope
- [ ] Reviewed: MCP client/server gateway behavior in scope
- [ ] Done: A2A agent gateway behavior in scope
- [ ] Reviewed: A2A agent gateway behavior in scope
- [ ] Done: tool discovery, access policy, credentials, and audit behavior
- [ ] Reviewed: tool discovery, access policy, credentials, and audit behavior

### Phase 12: Parity audit and LiteLLM removal gate

- [ ] Done: compare every selected upstream feature against its MarKom acceptance criteria
- [ ] Reviewed: compare every selected upstream feature against its MarKom acceptance criteria
- [ ] Done: run required unit, integration, API-compatibility, and Docker acceptance tests
- [ ] Reviewed: run required unit, integration, API-compatibility, and Docker acceptance tests
- [ ] Done: verify runtime, admin, test, and deployment code have no required LiteLLM imports
- [ ] Reviewed: verify runtime, admin, test, and deployment code have no required LiteLLM imports
- [ ] Done: replace remaining LiteLLM-dependent docs, configuration, dependencies, and startup paths
- [ ] Reviewed: replace remaining LiteLLM-dependent docs, configuration, dependencies, and startup paths
- [ ] Done: confirm all retained upstream references are documentation-only and explicitly scoped
- [ ] Reviewed: confirm all retained upstream references are documentation-only and explicitly scoped
- [ ] Done: remove LiteLLM source/dependency only after explicit parity sign-off
- [ ] Reviewed: review and approve the removal change before merge

## Completion rules

1. Implement one phase at a time, and keep changes limited to that phase plus necessary regression fixes.
2. For each feature, add tests that fail when the required behavior is broken. Include endpoint or provider contract tests where applicable.
3. Record unsupported provider-specific behavior as unsupported instead of returning fabricated success-shaped responses.
4. Run the narrowest relevant tests first, then the phase acceptance tests and Docker smoke test.
5. Complete the **Done** checkbox only when code, tests, and directly related documentation are ready.
6. Complete the **Reviewed** checkbox only after a review has checked correctness, security, compatibility, and evidence from the tests.
7. Do not delete LiteLLM code, dependencies, or reference material before Phase 12 is approved.

## Reference sources

- [Latest LiteLLM GitHub release](https://api.github.com/repos/BerriAI/litellm/releases/latest)
- [LiteLLM release v1.106.3](https://github.com/BerriAI/litellm/releases/tag/v1.106.3)
- [LiteLLM project README and feature overview](https://github.com/BerriAI/litellm/blob/main/README.md)
- [LiteLLM proxy quick start and endpoint overview](https://docs.litellm.ai/docs/proxy/quick_start)
- [LiteLLM supported providers](https://docs.litellm.ai/docs/providers)
- [LiteLLM virtual keys and spend tracking](https://docs.litellm.ai/docs/proxy/virtual_keys)
- [LiteLLM load balancing and routing](https://docs.litellm.ai/docs/proxy/load_balancing)
- [LiteLLM caching](https://docs.litellm.ai/docs/proxy/caching)
- [LiteLLM guardrails quick start](https://docs.litellm.ai/docs/proxy/guardrails/quick_start)
