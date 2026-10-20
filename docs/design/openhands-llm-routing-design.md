---
title: "OpenHands LLM routing: design"
status: accepted
date: 2026-10-20
owner: miguel quintero
slug: openhands-llm-routing
related:
  - ../decisions/0001-use-openrouter-as-provider.md
  - ../decisions/0002-use-openhands-sdk-harness.md
  - ../decisions/0003-model-pair-sonnet-haiku.md
  - ../decisions/0004-pin-upstream-provider.md
  - ../decisions/0005-routing-policy-set.md
  - ../decisions/0006-otel-to-jaeger.md
  - ../decisions/0007-defer-run-count-and-budget-caps.md
  - ../decisions/0008-synthetic-tasks-with-declared-phases.md
---

# OpenHands LLM routing: design

Design status: approved. Reference: [The hidden cost of LLM routing](https://towardsdatascience.com/the-hidden-cost-of-llm-routing-why-switching-models-costs-more/).

## Problem framing

The KV cache is model-specific. Switching models mid-session in an agent loop discards the cached prefix, so the new model re-reads the whole history at the uncached (or cache-write) price. The article reports roughly 90% prompt-cache reuse within a turn, 55% across turns with the same model, and 8% after a model switch, over 20-turn sessions with three policies (sticky, per-request alternation, phase-boundary switching). With Anthropic pricing, cache reads cost 0.1x and cache writes 1.25x of base input price, so a switch can cost more than the cheaper model saves.

Routing is a state-management decision, and the harness is where the state lives. This project measures token usage, cache hit rate and cost when switching LLMs mid-session in a real agent loop. It is measurement only.

## Assumptions

- Anthropic prompt caching works through OpenRouter for the chosen models, which requires `cache_control` to be set. Unverified; see Open items.
- The OpenHands SDK `switch_llm()` preserves the session on a live conversation. From docs only, not yet run.
- Prices come from real price sheets; OpenRouter usage accounting gives real billed cost.
- The Anthropic cache TTL is 5 minutes, so the runner must not idle between steps.
- The model pair is same-family (see [ADR 0003](../decisions/0003-model-pair-sonnet-haiku.md)).

## Architecture

```
 tasks/ (fixture repo + declared phases)
    |
    v
 runner --asks--> policies (sticky | alternate | phase | switch-at-N)
    |  builds agent + conversation (OpenHands SDK), steps, enforces caps
    |  switch_llm() on live conversation, LLMProfileStore profiles
    v
 OpenRouter (pinned upstream provider per model)
    |  usage + cost per call
    v
 recorder --> results.jsonl (source of truth)
    |                         |
    +--> otel --> Jaeger      +--> report --> Markdown report
 ci: ruff + keyless smoke test with a fake LLM
```

Related: [ADR 0001](../decisions/0001-use-openrouter-as-provider.md), [ADR 0002](../decisions/0002-use-openhands-sdk-harness.md).

## Components

- **tasks/**: synthetic deterministic tasks on a small fixed fixture repo, each with declared phases (explore, implement, test-fix). See [ADR 0008](../decisions/0008-synthetic-tasks-with-declared-phases.md).
- **policies**: pure functions (turn, phase, previous model) to model name.
- **runner**: builds agent and conversation, steps it, asks the policy for a model before each step, calls `switch_llm()` when it changes, enforces per-run and per-sweep budget caps, and does not idle between steps.
- **recorder**: writes one JSONL row per LLM call.
- **otel**: configures OTLP export and span attributes.
- **report**: stdlib-only; cache-hit rate per policy, cost vs sticky, cost-vs-switch-point curve, Markdown output.
- **ci**: ruff lint and a no-LLM smoke test with a fake LLM; no key.

Stack: Python 3.12, uv project, `openhands-sdk` and `openhands-tools` pinned, unittest, stdlib-leaning. The key comes only from `OPENROUTER_API_KEY` in the environment (supplied by the user via `op run`; the harness never calls `op`).

## Routing policies

Defined in [ADR 0005](../decisions/0005-routing-policy-set.md).

| Policy | Rule |
|---|---|
| sticky | one model for the whole session (baseline) |
| alternate | change model on every request (worst case) |
| phase-boundary | change model when the declared phase changes |
| switch-at-N | one switch at turn N in {5, 10, 15} |

Per task: 6 variants (sticky, alternate, phase-boundary, 3 N values), each repeated N times (N is a config value, see [ADR 0007](../decisions/0007-defer-run-count-and-budget-caps.md)). Error-fallback is not done.

## Data model

One JSONL row per LLM call:

- `run_id`, `task`, `policy`, `policy_params` (for example N), `repeat`
- `turn`, `phase`, `model`, `switched` (bool)
- `upstream_provider` (actual serving provider), `provider_pinned_ok`
- `prompt_tokens`, `cached_prompt_tokens`, `uncached_prompt_tokens`, `cache_write_tokens`, `completion_tokens`
- `cost_usd` (OpenRouter billed), `computed_cost_usd` (from price sheet)
- `status` (ok, failed, over_cap), `error`, `ts`

Run-level failures are recorded as failed and excluded from aggregates, never silently retried. Secrets are never written.

## Observability

See [ADR 0006](../decisions/0006-otel-to-jaeger.md). One trace per session, one span per LLM call, attributes: model, policy, phase, prompt/cached/completion tokens, cost, `switched=true` on the switch turn. Default `http://localhost:4318`, http/protobuf, overridable through `OTEL_EXPORTER_OTLP_*`. JSONL is the source of truth, not Jaeger.

Provider pinning ([ADR 0004](../decisions/0004-pin-upstream-provider.md)): `provider.order` plus `allow_fallbacks: false`, served provider logged per call.

## MVP scope

- 3 synthetic tasks (bug fix, feature add, refactor) on a small Python fixture repo, failing tests driving 20+ turns.
- One model pair (Sonnet and Haiku via OpenRouter), four policy families, repeats, provider pinning.
- JSONL results, Jaeger traces, Markdown report.
- README with a "Run manually" section; CI with `lint` and `test` checks on protected `main` (public repo miqui/openhands-llm-routing, published later as a separate gate).

## Not doing

SWE-bench slice, transcript replay, cross-vendor pairs, error-fallback policy, learned or gateway router, quality scoring, local vLLM, production deployment.

## Risks and failure modes

- **No cache_control**: the SDK may not set it for Anthropic via OpenRouter, making everything look 0% cached. The first smoke run must show a nonzero cache hit on sticky.
- **TTL cliff**: 5-minute cache TTL; the runner must not idle between steps.
- **Nondeterminism**: normalise per turn and repeat.
- **Provider failures mid-run**: recorded as failed and excluded, never silently retried.
- **Provider drift**: mitigated by pinning and logging.
- **Cost overrun**: hard caps in the runner, values calibrated later.
- **Secrets**: env var only, never persisted, CI keyless.
- **SDK switch behaviour**: `switch_llm()` may reset or alter state; fallback D2 would be recorded in a new ADR.

## Resolved decisions/TBDs

1. Model IDs: `anthropic/claude-sonnet-4.5`, `anthropic/claude-haiku-4.5` (confirm on OpenRouter during planning). [ADR 0003](../decisions/0003-model-pair-sonnet-haiku.md)
2. Tasks: bug fix, feature add, refactor. [ADR 0008](../decisions/0008-synthetic-tasks-with-declared-phases.md)
3. Repeats, per-run cap, per-sweep cap: deferred to config; calibrate after first smoke run. Unmeasured guesses: N=3, $2/run, $40/sweep, about 54 runs. [ADR 0007](../decisions/0007-defer-run-count-and-budget-caps.md)
4. Phase boundaries declared in task definitions by turn count or tool/event trigger, not LLM-inferred. ADR 0008.
5. switch-at-N with N in {5, 10, 15}. [ADR 0005](../decisions/0005-routing-policy-set.md)
6. Jaeger default `http://localhost:4318` http/protobuf, env-overridable. [ADR 0006](../decisions/0006-otel-to-jaeger.md)
7. uv, Python 3.12, pinned SDK, stdlib-only reporting, unittest, ruff plus keyless smoke test.
8. Repo miqui/openhands-llm-routing, public, `main` protected (`lint`, `test`).

## Open items

- Calibrate repeats and caps after the first smoke run (later ADR).
- Confirm current model IDs on OpenRouter.
- Verify SDK `cache_control` behaviour for Anthropic via OpenRouter (nonzero cache hit on sticky).
- Verify `switch_llm()` preserves session and cache-relevant state on a live conversation.

## ADR index

- [ADR 0001: Use OpenRouter as the only LLM provider](../decisions/0001-use-openrouter-as-provider.md)
- [ADR 0002: Use the OpenHands SDK as the agent harness](../decisions/0002-use-openhands-sdk-harness.md)
- [ADR 0003: Use a same-family Sonnet/Haiku pair for the MVP](../decisions/0003-model-pair-sonnet-haiku.md)
- [ADR 0004: Pin the upstream provider per model](../decisions/0004-pin-upstream-provider.md)
- [ADR 0005: Routing policy set mirrors the article, plus a switch-point sweep](../decisions/0005-routing-policy-set.md)
- [ADR 0006: Export OTEL traces to the user's local Jaeger](../decisions/0006-otel-to-jaeger.md)
- [ADR 0007: Defer run count and budget caps until after a smoke run](../decisions/0007-defer-run-count-and-budget-caps.md)
- [ADR 0008: Synthetic deterministic tasks with declared phases](../decisions/0008-synthetic-tasks-with-declared-phases.md)
