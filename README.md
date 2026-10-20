# openhands-llm-routing

Experiment harness measuring what switching LLMs mid-session costs in an OpenHands SDK agent loop.

## Goal

Measure token usage, prompt-cache hit rate and cost when an agent switches between models
(Claude Sonnet and Haiku via OpenRouter) during a session, under several routing policies.
Measurement only; no router is built.

Motivation: [The hidden cost of LLM routing](https://towardsdatascience.com/the-hidden-cost-of-llm-routing-why-switching-models-costs-more/).
The article reports roughly 90% prompt-cache reuse within a turn, 55% across turns with the same
model, and 8% after a model switch (figures are the article's, not measured here).

## Status

Phase 3 (build) is in progress. **Only the CI/skeleton and the SDK spike exist.** The CLI, runner,
recorder and report do not exist yet, so there is nothing to run end to end.

- [x] T0: CI workflow, pyproject, ruff, package skeleton, placeholder test
- [x] T1: SDK spike (`spikes/`, `docs/notes/spike-findings.md`)
- [ ] T2: config module
- [ ] T3: policies
- [ ] T4: task definitions and fixture repo
- [ ] T5: recorder (JSONL)
- [ ] T6: runner and CLI
- [ ] T7: OTEL span attributes
- [ ] T8: fake-LLM smoke test in CI
- [ ] T9: report command
- [ ] T10: first live smoke run, calibration, ADR 0009
- [ ] T11: full sweep
- [ ] T12: results report and final README

Everything below under "How it works" describes the design, not shipped code (see
[the plan](docs/plans/openhands-llm-routing-plan.md)).

## How it works (planned)

```
 tasks/ (fixture repo + declared phases)
    |
    v
 runner --asks--> policies (sticky | alternate | phase | switch-at-N)
    |  builds agent + conversation (OpenHands SDK), steps, enforces caps
    |  switch_llm() on live conversation
    v
 OpenRouter (pinned upstream provider per model)
    |  usage + cost per call
    v
 recorder --> results.jsonl (source of truth)
    |                         |
    +--> otel --> Jaeger      +--> report --> Markdown report
```

- **Policies** ([ADR 0005](docs/decisions/0005-routing-policy-set.md)): `sticky` (one model, baseline),
  `alternate` (switch every request), `phase-boundary` (switch when the declared task phase changes),
  `switch-at-N` (one switch at turn 5, 10 or 15).
- **OpenRouter + pinning** ([ADR 0001](docs/decisions/0001-use-openrouter-as-provider.md),
  [0004](docs/decisions/0004-pin-upstream-provider.md)): all calls go through OpenRouter; the upstream
  provider is pinned with `provider.order` and `allow_fallbacks: false`, and the serving provider is logged.
- **Tracing** ([ADR 0006](docs/decisions/0006-otel-to-jaeger.md)): one trace per session, exported over
  OTLP http/protobuf to `http://localhost:4318` (local Jaeger). JSONL, not Jaeger, is the source of truth.

## Key spike findings

From [docs/notes/spike-findings.md](docs/notes/spike-findings.md) (real SDK and OpenRouter calls,
total spend $0.139):

- `switch_llm()` preserves history, conversation id, system prompt and tool/workspace state.
- The first call after a switch is a cold cache: full cache write on the new model, zero reads, even
  though system prompt and tool schemas are byte-identical.
- The SDK sets `cache_control` by default for `anthropic/*` via OpenRouter; no extra option needed.
- `LLMProfileStore.load()` drops `api_key`; it must be re-attached from the environment.
- OTEL spans reach an OTLP/HTTP endpoint with env vars only; Jaeger itself was not run.
- Not yet tested: whether the first model's cache is still warm when switching back within 5 minutes.

## Requirements

- Python 3.12 and [uv](https://docs.astral.sh/uv/)
- For live runs only: `OPENROUTER_API_KEY` in the environment, for example supplied by 1Password
  `op run`. The harness never calls `op` and never stores the key.
- Optional: a local Jaeger accepting OTLP on port 4318.

## Run manually

Checks that work today (keyless). Output below was captured from a real run:

```
$ uv sync
Resolved 353 packages in 3ms
Checked 188 packages in 4ms

$ uv run ruff check .
All checks passed!

$ uv run ruff format --check .
17 files already formatted

$ uv run python -m unittest discover -s tests -v
test_package_imports (test_placeholder.PlaceholderTest.test_package_imports) ... ok

----------------------------------------------------------------------
Ran 1 test in 0.000s

OK
```

(`uv sync` timings and package counts vary; a first sync downloads packages.)

### Live spikes (spend real money)

**Not re-run for this README; see `docs/notes/spike-findings.md` for recorded results.** Each script
caps its own spend; all three together cost about $0.14. Put this in an env file (it holds a
1Password reference, not a key):

```
OPENROUTER_API_KEY=op://hermes1/OpenRouter/credential
```

```
op run --env-file=<your.env> -- uv run python spikes/spike_cache.py
op run --env-file=<your.env> -- uv run python spikes/spike_switch.py
op run --env-file=<your.env> -- uv run python spikes/spike_otel.py
```

The planned `run`, `sweep` and `report` commands do not exist yet; they will be documented when built (T6, T9, T12).

## Documentation layout

- `docs/design/`: [design](docs/design/openhands-llm-routing-design.md)
- `docs/decisions/`: ADRs 0001-0008
- `docs/plans/`: [implementation plan](docs/plans/openhands-llm-routing-plan.md) (T0-T12)
- `docs/notes/`: [spike findings](docs/notes/spike-findings.md)

## CI

`.github/workflows/ci.yml` runs on every PR and on pushes to `main`, with two jobs: `lint`
(`ruff check`, `ruff format --check`) and `test` (`unittest discover`). No secrets are used.
`main` is protected, requiring both checks.

## Production-style checklist

- [x] Secrets via environment only; never written to disk, logs, JSONL or spans
- [x] Keyless CI with `permissions: contents: read`
- [x] Pinned dependencies (`openhands-sdk`/`openhands-tools` `==1.56.0`, `uv.lock`, `uv sync --frozen` in CI)
- [x] GitHub Actions pinned by commit SHA
- [x] Local gate before push: `betterleaks dir .` must be clean
- [ ] Per-run and per-sweep cost caps (planned, T2/T6; values set after the smoke run, ADR 0007)
- [ ] Upstream provider pinning enforced and verified per call (planned, T6; accepted in spikes)

## License

License: TBD (no LICENSE file yet).
