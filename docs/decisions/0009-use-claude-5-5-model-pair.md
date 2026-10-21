---
title: "ADR 0009: Use the Claude 5.5 Sonnet/Haiku pair for the MVP"
status: accepted
date: 2026-10-20
owner: miguel quintero
slug: openhands-llm-routing
supersedes: 0003-model-pair-sonnet-haiku.md
related:
  - ../design/openhands-llm-routing-design.md
  - 0003-model-pair-sonnet-haiku.md
  - 0004-pin-upstream-provider.md
  - 0007-defer-run-count-and-budget-caps.md
  - ../notes/spike-findings.md
---

# ADR 0009: Use the Claude 5.5 Sonnet/Haiku pair for the MVP

Governs: [design doc, Assumptions](../design/openhands-llm-routing-design.md#assumptions). Supersedes [ADR 0003](0003-model-pair-sonnet-haiku.md).

## Context

ADR 0003 chose the 4.5 generation. The T1 spike found OpenRouter now lists a newer same-family generation, and the user chose it. The pair stays same-family so tokenizer and cache mechanism do not confound the switch effect. Evidence is in the [spike findings addendum](../notes/spike-findings.md#addendum-claude-55-pair-2026-10-20).

## Decision

Frontier: `anthropic/claude-sonnet-5.5`. Cheap: `anthropic/claude-haiku-5.5`. Both confirmed on `/api/v1/models` on 2026-10-20, both have an `anthropic` endpoint at base price, so the ADR 0004 pin (`provider.order: ["anthropic"]`, `allow_fallbacks: false`) is unchanged. IDs live in config, not code. Prices (USD per Mtok, anthropic endpoint): Sonnet 5.5 prompt 2, completion 10, cache read 0.10, cache write 2.50; Haiku 5.5 prompt 0.10, completion 0.50, cache read 0.01, cache write 0.125. These are stored with results. Cache read is 0.05x prompt for Sonnet and 0.1x for Haiku; 5-minute write is 1.25x.

`reasoning_effort` is an explicit config value with default `"none"` (lowest). The SDK default is `"high"`, which on a trivial Haiku 5.5 call spent all output tokens on reasoning; a fixed explicit value removes that variance from the measurements. `"none"` was verified on Haiku 5.5 only; the Sonnet 5.5 check happens in the T6 smoke run and a rejection must fail loudly.

## Status

Accepted, 2026-10-20. Supersedes ADR 0003.

## Consequences

- SDK defaults set `cache_control` for Haiku 5.5 via OpenRouter (write on call 1, read on call 2, observed). Sonnet 5.5 caching is inferred until the T6 smoke run.
- Sonnet is 20x Haiku on prompt price (was 3x), so switching economics differ strongly from the 4.5 pair; ADR 0007 caps stay unmeasured until calibrated.
- Haiku 5.5 has a price tier above 100k prompt tokens; not expected in the planned tasks.
- The switch-back cache warmth question (TBD-4) is tested in the T6 smoke run, not before.
- Findings still may not generalise to cross-vendor routing.

## Alternatives considered

- Keep the 4.5 pair: verified and working, but the user chose the newer generation.
- Mixed generation (Sonnet 5.5 with Haiku 4.5): adds a generation confound; not considered further.
