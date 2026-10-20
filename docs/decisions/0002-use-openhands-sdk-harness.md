---
title: "ADR 0002: Use the OpenHands SDK as the agent harness"
status: accepted
date: 2026-10-20
owner: miguel quintero
slug: openhands-llm-routing
related:
  - ../design/openhands-llm-routing-design.md
  - 0001-use-openrouter-as-provider.md
  - 0003-model-pair-sonnet-haiku.md
  - 0004-pin-upstream-provider.md
  - 0005-routing-policy-set.md
  - 0006-otel-to-jaeger.md
  - 0007-defer-run-count-and-budget-caps.md
  - 0008-synthetic-tasks-with-declared-phases.md
---

# ADR 0002: Use the OpenHands SDK as the agent harness

Governs: [design doc, Components](../design/openhands-llm-routing-design.md#components)

## Context

Routing is a state-management decision and the harness is where the state lives. We need a real agent loop with tools, native per-call telemetry, native OTEL tracing, and a way to change model on a live conversation.

## Decision

Drive `openhands-sdk` (with `openhands-tools`, versions pinned) headless in Python. Switch models with the SDK's native `switch_llm()` on a live conversation, using `LLMProfileStore` profiles so the session is preserved (D1). Fallback D2, rebuilding the agent from the transcript, is used only if the SDK blocks D1, and that would be recorded as a new ADR. The runner asks the policy for a model before each step.

## Status

Accepted, 2026-10-20.

## Consequences

- Real agent behaviour (tools, history growth) rather than a synthetic loop.
- Native telemetry gives prompt/completion/cache read/write tokens and cost per call.
- Spike findings come from docs only; `switch_llm()` behaviour and `cache_control` handling are unverified until the first smoke run.
- Coupling to SDK version; pinning mitigates.

## Alternatives considered

- D2 rebuild agent from transcript: changes what "switch" means (history re-sent fresh); fallback only.
- Custom minimal agent loop: full control but not a realistic harness.
- Other harnesses: no comparable native switch + OTEL support identified.
