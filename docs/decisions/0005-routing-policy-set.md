---
title: "ADR 0005: Routing policy set mirrors the article, plus a switch-point sweep"
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
  - 0006-otel-to-jaeger.md
  - 0007-defer-run-count-and-budget-caps.md
  - 0008-synthetic-tasks-with-declared-phases.md
---

# ADR 0005: Routing policy set mirrors the article, plus a switch-point sweep

Governs: [design doc, Routing policies](../design/openhands-llm-routing-design.md#routing-policies)

## Context

The reference article compares sticky, per-request alternation and phase-boundary switching over 20-turn sessions. We also want cost as a function of when a single switch happens.

## Decision

Implement four policy families: `sticky`, `alternate` (switch every request), `phase-boundary` (switch when the task's declared phase changes), and `switch-at-N` with N in {5,10,15} (one switch at turn N). The policy is a pure function of turn, phase and prior model, called by the runner before each step. Error-fallback policy is not done.

## Status

Accepted, 2026-10-20.

## Consequences

- Gives the worst case (alternate), the baseline (sticky), a realistic policy, and a cost-vs-switch-point curve.
- Six variants per task (sticky, alternate, phase-boundary, three N values), which drives run count (ADR 0007).
- No learned or gateway router; no quality scoring, so cheaper is not shown to be better.

## Alternatives considered

- Error-fallback policy: rejected, adds failure-injection complexity.
- Learned/gateway router: out of scope, measurement only.
- Fewer policies: loses the switch-point curve.
