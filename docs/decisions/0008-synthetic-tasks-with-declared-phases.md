---
title: "ADR 0008: Synthetic deterministic tasks with declared phases"
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
  - 0007-defer-run-count-and-budget-caps.md
---

# ADR 0008: Synthetic deterministic tasks with declared phases

Governs: [design doc, MVP scope](../design/openhands-llm-routing-design.md#mvp-scope)

## Context

Phase-boundary routing needs known phases, and comparisons need tasks that are repeatable and cheap. Agent behaviour is nondeterministic, so turn counts vary.

## Decision

Use three synthetic tasks (bug fix, feature add, refactor) on a small fixed Python fixture repo with failing tests, designed to need 20+ turns. Phases are explore, implement, test-fix. Boundaries are declared in the task definition by turn count or a tool/event trigger (for example the first file edit), never inferred by an LLM. Per-turn metrics are normalised and each policy is repeated.

## Status

Accepted, 2026-10-20.

## Consequences

- Deterministic fixtures and known phases make policies comparable.
- Synthetic tasks may not represent real workloads.
- A trigger may never fire in a run; the run records which boundary fired.

## Alternatives considered

- SWE-bench slice: rejected, cost and variance.
- Transcript replay: rejected, not a live agent loop.
- LLM-inferred phases: adds cost and a confounder.
