---
title: "ADR 0004: Pin the upstream provider per model"
status: accepted
date: 2026-10-20
owner: miguel quintero
slug: openhands-llm-routing
related:
  - ../design/openhands-llm-routing-design.md
  - 0001-use-openrouter-as-provider.md
  - 0002-use-openhands-sdk-harness.md
  - 0003-model-pair-sonnet-haiku.md
  - 0005-routing-policy-set.md
  - 0006-otel-to-jaeger.md
  - 0007-defer-run-count-and-budget-caps.md
  - 0008-synthetic-tasks-with-declared-phases.md
---

# ADR 0004: Pin the upstream provider per model

Governs: [design doc, Risks and failure modes](../design/openhands-llm-routing-design.md#risks-and-failure-modes)

## Context

OpenRouter can serve one model from several upstream providers. A cache miss caused by a provider change would be indistinguishable from a miss caused by our model switch.

## Decision

Per model, set `provider.order` to one provider and `allow_fallbacks: false`. Record the actual serving provider on every call in the JSONL row. A run where the served provider differs from the pin is flagged and excluded. Pinned providers are set in config.

## Status

Accepted, 2026-10-20.

## Consequences

- Cache misses are attributable to our switch.
- A pinned provider outage fails the run; it is recorded as failed and excluded, never silently retried.
- Results reflect one provider's caching behaviour per model.

## Alternatives considered

- Let OpenRouter route freely: unattributable misses.
- Pin only when a mismatch is observed: loses data from earlier runs.
