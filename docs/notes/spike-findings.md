---
title: "T1 spike findings: OpenHands SDK switch, OTEL and cache behaviour"
status: draft
date: 2026-10-20
owner: miguel quintero
slug: openhands-llm-routing
related:
  - ../plans/openhands-llm-routing-plan.md
  - ../decisions/0002-use-openhands-sdk-harness.md
  - ../decisions/0003-model-pair-sonnet-haiku.md
  - ../decisions/0004-pin-upstream-provider.md
  - ../decisions/0006-otel-to-jaeger.md
---

# T1 spike findings

Everything under "Observed" was run against the real SDK and real OpenRouter calls on 2026-10-20 (scripts in `spikes/`). Items under "Inferred" come from reading SDK source or docs and were not exercised.

## 1. Versions (pinned)

| Package | Pin | Note |
|---|---|---|
| `openhands-sdk` | `==1.56.0` | latest resolved by `uv add` on 2026-10-20 |
| `openhands-tools` | `==1.56.0` | same |
| `litellm` | 1.105.2 | transitive |
| `lmnr` (Laminar) | 0.7.67 | transitive; the SDK's OTEL layer is built on it |
| `opentelemetry-sdk` / `-exporter-otlp-proto-http` | 1.45.1 | transitive |

Python 3.12 (project constraint). `uv.lock` updated (353 packages).

## 2. OpenRouter model IDs, endpoints, prices (observed, `/api/v1/models` and `/models/<id>/endpoints`, no key)

Proposed IDs still exist and were used for every live call:

- `anthropic/claude-sonnet-4.5` (context 1,000,000)
- `anthropic/claude-haiku-4.5` (context 200,000)

Newer same-family models are listed now (not used): `anthropic/claude-sonnet-4.6`, `anthropic/claude-sonnet-5`, `anthropic/claude-sonnet-5.5`, `anthropic/claude-haiku-5.5`. Each also has a `:batch` variant (half price; not suitable for interactive runs). See TBD-1.

Price sheet, USD per token (as returned; multiply by 1e6 for per-Mtok):

| Model | prompt | completion | input_cache_read | input_cache_write (5m) | input_cache_write_1h |
|---|---|---|---|---|---|
| claude-sonnet-4.5 | 0.000003 | 0.000015 | 0.0000003 | 0.00000375 | 0.000006 |
| claude-haiku-4.5 | 0.000001 | 0.000005 | 0.0000001 | 0.00000125 | 0.000002 |
| claude-sonnet-5.5 (ref) | 0.000002 | 0.00001 | 0.0000001 | 0.0000025 | 0.000004 |
| claude-haiku-5.5 (ref) | 0.0000001 | 0.0000005 | 0.00000001 | 0.000000125 | 0.0000002 |

Sonnet 4.5 has a tier override above 200k prompt tokens (prompt 0.000006, completion 0.0000225, cache read 0.0000006, cache write 0.0000075). Not reachable in the planned tasks. Cache read is 0.1x and 5-minute cache write is 1.25x prompt, as ADR 0003 states.

Endpoints (provider name / tag):

- sonnet-4.5: Claude Platform on AWS (`claude-on-aws`), Azure (`azure/global`), Amazon Bedrock (`amazon-bedrock`, `amazon-bedrock/eu-west-1`), Anthropic (`anthropic`), Google (`google-vertex/global`, `google-vertex/us-east5`).
- haiku-4.5: Azure (`azure/global`), Bedrock (`amazon-bedrock/global`, `/us`, `/eu-west-1`), Google (`google-vertex/global`, `/us-east5`, `/europe`), Anthropic (`anthropic`).
- Regional endpoints cost 10% more. `anthropic` is the only provider present for both models at base price with the same tag. Observed: `provider: {"order": ["anthropic"], "allow_fallbacks": false}` accepted and every response reported `"provider": "Anthropic"`.

## 3. switch_llm() on a live conversation (observed, `spikes/spike_switch.py`)

Setup: `Agent` with `TerminalTool` + `FileEditorTool`, conversation turn 1 on haiku-4.5, `conv.switch_llm(loaded_profile_llm)` to sonnet-4.5, turn 2. Run twice (identical outcomes; the second run is the reference output below).

- Profile store: `LLMProfileStore.save()` then `.load()` round-trips model, `litellm_extra_body` (provider pin and `usage.include`) and `log_completions`, but `api_key` is NOT kept (`profile load keeps api_key: False`). The harness must re-attach the key from env after `load()` (done in the spike via `model_copy`).
- History preserved: `events right after switch (history kept): 5` equals `events before switch: 5`; same conversation id; one `SystemPromptEvent` before and after (`system prompt events before/after: 1 1`).
- Tools still work after the switch: turn 2 ran `cat note.txt` via the terminal tool (2 `TerminalObservation` events total) and the agent answered with the file content and the verbatim first instruction: `final agent text: The contents of the file are: marker-alpha ... The exact text of your FIRST instruction was: Use the terminal tool to run: echo marker-alpha > note.txt  . Then reply with the single word DONE.` History is genuinely visible to the new model. Final `execution_status: FINISHED`.
- State that changes: `agent.llm` (model and usage_id swap); per-model metrics are separate entries in `conversation_stats` keyed by `usage_id` (`stats usage_ids after: ['first', 'second']`, cost $0.01016 and $0.03209). The first sonnet call has a cold cache (see section 6).
- State that is kept: events, conversation id, system prompt event, workspace/terminal state (tool use after the switch saw the file written before it).
- Inferred from source (`local_conversation.switch_llm`, not separately exercised): the condenser LLM is re-derived for the new LLM, the "ask-agent" LLM cache is invalidated, and if the passed `usage_id` already exists with a different config the new LLM inherits that entry's metrics. `switch_profile(name)` also exists (loads from the store, caches under `profile:<name>`); it was NOT run. Use distinct `usage_id` per model so per-model accounting stays separate.
- Branching condition (switch blocked or loses state): not triggered. D1 stands.

## 4. Prefix identity across switch (observed, request logs via `log_completions`)

Compared the four logged requests (2 haiku, 2 sonnet):

```
call 1 vs call 0: system_identical=True tools_identical=True
call 2 vs call 0: system_identical=True tools_identical=True   (first call after switch)
call 3 vs call 0: system_identical=True tools_identical=True
call 2: identical leading messages (ignoring cache_control) vs call 0 = 2
```

System message (15,970 chars serialized) and tool schemas (6,598 chars) are byte-identical across the switch, and the whole pre-switch conversation is replayed unchanged as the prefix (messages compared with `cache_control` keys stripped because the last-message marker moves each turn). The prompt content is therefore not what invalidates the cache after a switch. Anthropic prompt caches are per model: see section 6.

Side observation: the SDK sends `reasoning_effort: "high"` by default for these models (request kwargs: `max_completion_tokens, reasoning_effort, extra_body, prompt_cache_key`). `reasoning_tokens` were 0 on the calls seen. Not investigated further (TBD-3).

## 5. OTEL (observed, `spikes/spike_otel.py`)

Setting `OTEL_EXPORTER_OTLP_TRACES_ENDPOINT=http://127.0.0.1:4318/v1/traces` and `OTEL_EXPORTER_OTLP_TRACES_PROTOCOL=http/protobuf` before the conversation starts is enough; no code-side initialisation. A stdlib `http.server` on 127.0.0.1:4318 decoded the protobuf:

```
listener requests: [('/v1/traces', 'application/x-protobuf'), ('/v1/traces', 'application/x-protobuf')]
spans received: 10
  span name='conversation.send_message' count=1
  span name='litellm.completion' count=2
  span name='llm.openrouter/anthropic/claude-haiku-4.5' count=2
  span name='TerminalAction' count=1
  span name='agent.step' count=2
  span name='conversation.run' count=1
  span name='conversation' count=1
distinct traces: 1
```

- One trace per conversation. The tool span is named by action class (`TerminalAction`), not `tool.execute` as ADR 0006's context assumes; the LLM span name embeds the model (`llm.<litellm model>`).
- `litellm.completion` span attributes include `gen_ai.request.model`, `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`, `gen_ai.usage.cache_read_input_tokens`, `gen_ai.usage.cache_creation_input_tokens`, `gen_ai.response.model`. The `llm.<model>` span carries `gen_ai.usage.cost` plus cache read/creation tokens. There are no policy/phase/switched attributes; those must be added by us.
- Missing collector: run with `SPIKE_NO_LISTENER=1` (nothing on 4318) finished normally: `run finished with status: ConversationExecutionStatus.FINISHED`. So a missing Jaeger does not fail a run (the exporter's background errors, if any, were not inspected).
- Inferred, not exercised: `Conversation(...)` accepts `observability_metadata`, `observability_tags`, `observability_span_name` (seen in its signature), which are candidate ways to attach policy/phase. The real Jaeger UI was not available; only span receipt and names were verified.

## 6. Prompt caching via OpenRouter (observed, `spikes/spike_cache.py` and the switch run)

SDK defaults (`caching_prompt=True`) already set `cache_control` for `anthropic/*` through `openrouter/...`: 2 markers per request (first system block and the last user/tool message). No extra option was needed. Control with `caching_prompt=False` had 0 markers and 0 cache tokens.

Direct two-call test, haiku-4.5, ~13.4k-token identical prefix (filler was larger than the 4k minimum I aimed for):

```
== control; caching_prompt=False active=False
call 1: prompt=13465 cache_read=0 cache_write=0
call 2: prompt=13465 cache_read=0 cache_write=0
== sdk_default; caching_prompt=True active=True
call 1: prompt=13467 cache_read=0 cache_write=13464
call 2: prompt=13467 cache_read=13464 cache_write=0
log: cache_control_markers_in_request=2 or_cached=13464 or_cache_write=0 served_by=Anthropic
```

In the agent run (7k-token system+tools prefix), per-call numbers from the logged OpenRouter `usage` (prompt / cached / cache_write):

```
call 0 haiku-4.5   prompt=6928 cached=0    cache_write=6925
call 1 haiku-4.5   prompt=7143 cached=6925 cache_write=212
call 2 sonnet-4.5  prompt=7181 cached=0    cache_write=7178   <- first call after switch
call 3 sonnet-4.5  prompt=7393 cached=7178 cache_write=209
```

Switch cost evidence: the first call after a switch pays a full cache write (7178 tokens at 1.25x prompt price) on the new model and reads nothing, even though the prefix is byte-identical; the old model's cache is not reused (per-model). The SDK exposes both read and write tokens (`metrics.token_usages[-1].cache_read_tokens / cache_write_tokens`) and the response usage has `prompt_tokens_details.cache_write_tokens`. SDK-computed cost equals OpenRouter's reported `usage.cost` ($0.01822 both for the cache spike's default pair).

## 7. Measured spend (cap $0.25; OpenRouter `usage.cost` / SDK metrics)

| Run | Models | Cost USD |
|---|---|---|
| spike_switch (run 1) | haiku-4.5 x2 calls, sonnet-4.5 x2 | 0.04179 |
| spike_switch (run 2, final script) | same | 0.04224 |
| spike_otel (listener) | haiku-4.5 x2 | 0.00842 |
| spike_otel (no listener) | haiku-4.5 x2 | 0.00178 |
| spike_cache | haiku-4.5 x4 | 0.04519 |
| **Total** | | **0.13942** |

Four sonnet-4.5 calls were used (two per switch run), more than the "1-2" suggested, because a Sonnet<->Haiku switch was the only representative test. Spikes enforce per-script caps (0.12, 0.03, 0.06) and print total cost. The model list and endpoints queries cost nothing.

## 8. Recommendations for T2-T7

- T2: IDs `anthropic/claude-sonnet-4.5` and `anthropic/claude-haiku-4.5` are valid; pin provider `anthropic` for both; store the price sheet above (per-token, incl. `input_cache_write`) with results. Config must hold a `reasoning_effort` setting (default left unset = SDK sends `high`).
- T5: the serving provider is available per call at `response.provider` in the logged completion; record it for the pin check. Cache write tokens come from `prompt_tokens_details.cache_write_tokens` / SDK `cache_write_tokens`; the JSONL `cache_write_tokens` field is feasible.
- T6: keep `litellm_extra_body={"provider": {"order": [...], "allow_fallbacks": false}, "usage": {"include": true}}` (worked); no cache-specific option needed because `caching_prompt` defaults to true; re-attach the API key after `LLMProfileStore.load()` (profiles drop it); use a distinct `usage_id` per model; enable `log_completions` only if wanted for debugging (logs contain full prompts; the logged request kwargs showed no api_key, only a redacted prompt_cache_key). Expect the first call after any switch to be a cold cache on the new model; this is the effect being measured, not a bug. Alternate-every-turn policies will therefore pay a cache write per switch on whichever model they land on, but each model's own cache survives while its TTL (5 min) lasts: not tested here (TBD-4).
- T6/ADR 0006: add policy, phase and `switched` ourselves (own span or `observability_*` args) since the SDK emits none; update the ADR's span-name wording (`TerminalAction`, `llm.<model>`, `litellm.completion`) when convenient.
- T8 CI: observability only turns on if OTEL env vars are set, so the keyless fake-LLM path emits nothing as ADR 0006 requires (inferred from `should_enable_observability` source; not tested).

## 9. New TBDs

- TBD-1: OpenRouter now lists claude-sonnet-5/5.5 and claude-haiku-5.5 (haiku-5.5 is ~10x cheaper than haiku-4.5). User decision: keep the 4.5 pair per ADR 0003 (works, verified) or move to a newer pair (would need a re-spike for caching/prefix behaviour; the models were not called).
- TBD-2: `switch_profile()` was not run live; T6 can use `switch_llm()` with an explicitly built LLM (verified) or test `switch_profile` first.
- TBD-3: effect of default `reasoning_effort="high"` on cost/latency for these models is unmeasured.
- TBD-4: whether the first model's cache is still warm when switching back (within the 5-minute TTL) was not tested; this is the key question for the alternate policy and should be seen in the T6 smoke run (a switch-back test would be ~$0.05).
- TBD-5: Jaeger itself was not run; only span receipt at a stdlib OTLP/HTTP listener was verified.
