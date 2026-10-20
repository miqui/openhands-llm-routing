---
title: "ADR 0007: Defer run count and budget caps until after a smoke run"
status: accepted
date: 2026-10-20
owner: miguel quintero
slug: openhands-llm-routing
related:
  - ../design/openhands-llm-routing-design.md
  - 0001-use-openrouter-as-provider.md
  - 0002-use-openhands-sdk-harness.md
  - 0003-model-pair-sonnet-haiku.md
  - 0004-pin-upstream-provider.md
  - 0005-routing-policy-set.md
  - 0006-otel-to-jaeger.md
  - 0008-synthetic-tasks-with-declared-phases.md
---

# ADR 0007: Defer run count and budget caps until after a smoke run

Governs: [design doc, Resolved decisions/TBDs](../design/openhands-llm-routing-design.md#resolved-decisionstbds)

## Context

Repeats per policy, per-run cost cap and per-sweep cost cap are needed, but real per-run cost is unknown until a run is measured.

## Decision

Repeats N, per-run cap and per-sweep cap are config values with no hard-coded numbers. The runner enforces whatever caps are configured and aborts a run that exceeds its cap. After the first smoke run measures real cost, calibrate the values and record them in a later ADR. Initial rough guesses, explicitly unmeasured: N=3, $2 per run, $40 per sweep, about 54 runs (3 tasks x 6 policy variants x 3 repeats).

## Status

Accepted, 2026-10-20.

## Consequences

- No invented numbers baked into code or docs as facts.
- The first sweep cannot start until calibration is done.
- Spread statistics need N of at least 2; N is chosen after seeing run-to-run variance.

## Alternatives considered

- Fix numbers now: unmeasured, likely wrong.
- No caps: unacceptable cost risk.
