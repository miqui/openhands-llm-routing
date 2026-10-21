---
title: "ADR 0003: Use a same-family Sonnet/Haiku pair for the MVP"
status: superseded
date: 2026-10-20
owner: miguel quintero
slug: openhands-llm-routing
related:
  - ../design/openhands-llm-routing-design.md
  - 0009-use-claude-5-5-model-pair.md
  - 0001-use-openrouter-as-provider.md
  - 0002-use-openhands-sdk-harness.md
  - 0004-pin-upstream-provider.md
  - 0005-routing-policy-set.md
  - 0006-otel-to-jaeger.md
  - 0007-defer-run-count-and-budget-caps.md
  - 0008-synthetic-tasks-with-declared-phases.md
---

# ADR 0003: Use a same-family Sonnet/Haiku pair for the MVP

Governs: [design doc, Assumptions](../design/openhands-llm-routing-design.md#assumptions)

## Context

Cross-vendor pairs add tokenizer, caching-semantics and prompt-format differences that confound the cache effect. A frontier/cheap pair is the realistic routing case.

## Decision

Use Claude Sonnet (frontier) and Claude Haiku (cheap) via OpenRouter. Proposed IDs: `anthropic/claude-sonnet-4.5` and `anthropic/claude-haiku-4.5`. IDs live in config, not code, and must be confirmed against OpenRouter's current model list during planning (open item). Prices come from real price sheets and are stored with the results.

## Status

Accepted, 2026-10-20. Superseded by [ADR 0009](0009-use-claude-5-5-model-pair.md) (Claude 5.5 pair), 2026-10-20. The decision text above is kept as history.

## Consequences

- Same tokenizer family and cache mechanism (Anthropic cache read 0.1x, write 1.25x) isolates the model-switch effect.
- Findings may not generalise to cross-vendor routing.
- If an ID is retired, only config changes; runs record the exact IDs used.

## Alternatives considered

- Cross-vendor pair: rejected for MVP.
- Both same-family and cross-vendor: rejected for MVP, cost and confounding.
