---
title: "ADR 0001: Use OpenRouter as the only LLM provider"
status: accepted
date: 2026-10-20
owner: miguel quintero
slug: openhands-llm-routing
related:
  - ../design/openhands-llm-routing-design.md
  - 0002-use-openhands-sdk-harness.md
  - 0003-model-pair-sonnet-haiku.md
  - 0004-pin-upstream-provider.md
  - 0005-routing-policy-set.md
  - 0006-otel-to-jaeger.md
  - 0007-defer-run-count-and-budget-caps.md
  - 0008-synthetic-tasks-with-declared-phases.md
---

# ADR 0001: Use OpenRouter as the only LLM provider

Governs: [design doc, Architecture](../design/openhands-llm-routing-design.md#architecture)

## Context

The experiment needs two Anthropic models behind one API, real billed cost per call, and the ability to pin the upstream provider. The reference article reports cache behaviour that depends on provider and model. The key must never enter the repo or CI.

## Decision

Route every LLM call through OpenRouter. The harness reads `OPENROUTER_API_KEY` from the environment only; the user supplies it via 1Password `op run`. The harness never calls `op`, never persists the key, and CI never needs a key. Request `usage: {include: true}` so each response carries real billed cost, and read cached vs uncached prompt tokens from the API usage fields.

## Status

Accepted, 2026-10-20.

## Consequences

- One key, one price sheet, one accounting format for both models.
- Cost is measured (OpenRouter-reported), not only computed; raw tokens are reported next to cost.
- Adds a middleman: OpenRouter routing/fallback could confound cache results (handled by ADR 0004).
- Results are specific to OpenRouter's cache pass-through behaviour.

## Alternatives considered

- Direct Anthropic API: cleanest cache semantics, but no uniform cost field and no provider pinning story; deferred.
- Multiple direct providers: more keys and accounting formats; out of MVP scope.
- Local vLLM: no real price sheet; not doing.
