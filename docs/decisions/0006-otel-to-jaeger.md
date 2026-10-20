---
title: "ADR 0006: Export OTEL traces to the user's local Jaeger"
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
  - 0007-defer-run-count-and-budget-caps.md
  - 0008-synthetic-tasks-with-declared-phases.md
---

# ADR 0006: Export OTEL traces to the user's local Jaeger

Governs: [design doc, Observability](../design/openhands-llm-routing-design.md#observability)

## Context

Per-call behaviour across a session is easier to inspect visually. The SDK already emits OTEL spans (agent.step, llm.completion, tool.execute) and honours standard `OTEL_EXPORTER_OTLP_*` variables.

## Decision

One trace per session, one span per LLM call, with attributes: model, routing policy, phase, prompt/cached/completion tokens, cost, and `switched=true` on the turn the model changed. Default endpoint `http://localhost:4318` over http/protobuf, overridable via standard env vars. The JSONL results file stays the source of truth; Jaeger is a view. CI exports nothing.

## Status

Accepted, 2026-10-20.

## Consequences

- Visual debugging of switches and cache misses.
- Requires a local Jaeger for the manual run only; absence must not fail a run.
- Span attributes duplicate JSONL fields; JSONL wins on disagreement.

## Alternatives considered

- JSONL only: no visual inspection.
- Hosted tracing backend: extra key and data egress.
- Custom span schema replacing SDK spans: reinvents native tracing.

## Correction (2026-10-20)

The T1 spike ([findings, section 5](../notes/spike-findings.md)) observed the SDK's real span names: the tool span is `TerminalAction` (named by action class), not `tool.execute`; other spans are `conversation`, `conversation.send_message`, `conversation.run`, `agent.step`, `litellm.completion` and `llm.<litellm model>`. The SDK emits no policy, phase or `switched` attributes; the harness adds them in T7. The Decision above is unchanged.
