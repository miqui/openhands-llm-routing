---
title: "OpenHands LLM routing: implementation plan"
status: draft
date: 2026-10-20
owner: miguel quintero
slug: openhands-llm-routing
related:
  - ../design/openhands-llm-routing-design.md
  - ../decisions/0001-use-openrouter-as-provider.md
  - ../decisions/0002-use-openhands-sdk-harness.md
  - ../decisions/0003-model-pair-sonnet-haiku.md
  - ../decisions/0009-use-claude-5-5-model-pair.md
  - ../decisions/0004-pin-upstream-provider.md
  - ../decisions/0005-routing-policy-set.md
  - ../decisions/0006-otel-to-jaeger.md
  - ../decisions/0007-defer-run-count-and-budget-caps.md
  - ../decisions/0008-synthetic-tasks-with-declared-phases.md
---

# OpenHands LLM routing: implementation plan

Inputs (approved, not modified here): [design](../design/openhands-llm-routing-design.md), [ADR 0001](../decisions/0001-use-openrouter-as-provider.md), [0002](../decisions/0002-use-openhands-sdk-harness.md), [0003](../decisions/0003-model-pair-sonnet-haiku.md) (superseded by [0009](../decisions/0009-use-claude-5-5-model-pair.md)), [0004](../decisions/0004-pin-upstream-provider.md), [0005](../decisions/0005-routing-policy-set.md), [0006](../decisions/0006-otel-to-jaeger.md), [0007](../decisions/0007-defer-run-count-and-budget-caps.md), [0008](../decisions/0008-synthetic-tasks-with-declared-phases.md).

## 1. Summary and approved direction

We measure token usage, prompt-cache hit rate and cost when an OpenHands SDK agent switches between Claude Sonnet and Haiku mid-session, all through OpenRouter with pinned upstream providers ([ADR 0001](../decisions/0001-use-openrouter-as-provider.md), [0002](../decisions/0002-use-openhands-sdk-harness.md), [0003](../decisions/0003-model-pair-sonnet-haiku.md), [0004](../decisions/0004-pin-upstream-provider.md)). Four policy families (sticky, alternate, phase-boundary, switch-at-N for N in {5,10,15}) run on three synthetic tasks with declared phases, with JSONL as source of truth, OTEL traces in local Jaeger and a stdlib-only Markdown report ([ADR 0005](../decisions/0005-routing-policy-set.md), [0006](../decisions/0006-otel-to-jaeger.md), [0008](../decisions/0008-synthetic-tasks-with-declared-phases.md)). Repeats and cost caps are config values calibrated after a first live smoke run, and CI comes first and stays keyless ([ADR 0007](../decisions/0007-defer-run-count-and-budget-caps.md)).

## 2. Toolchain and conventions

- uv project, Python 3.12, package `ohrouting` under `src/ohrouting/`, tests under `tests/`.
- `openhands-sdk` and `openhands-tools` pinned exactly. Versions are not guessed here: task T1 resolves the latest released versions (`uv pip index versions` / PyPI) and records them in `docs/notes/spike-findings.md` and `pyproject.toml`.
- Reporting is stdlib-only. Tests use `unittest` (no pytest, no pandas). Lint and format: ruff (`ruff check`, `ruff format --check`).
- Secrets: `OPENROUTER_API_KEY` is read from the environment only. The user wraps runs with `op run --env-file=...`; the harness never calls `op`, never writes the key to disk, logs, JSONL or spans. CI has no key.
- Config values (models, providers, caps, repeats, endpoints) live in config, never hard-coded in logic ([ADR 0003](../decisions/0003-model-pair-sonnet-haiku.md), [0007](../decisions/0007-defer-run-count-and-budget-caps.md)).
- Mandatory local gate before any push or PR: `betterleaks dir .` must report no findings. Documented in the README.
- Commits are made by the user or on request; each task ends at a checkpoint.

## 3. CI design (first, before any implementation)

Implements: design "Components > ci" and "MVP scope"; [ADR 0001](../decisions/0001-use-openrouter-as-provider.md) (key never in CI).

File: `.github/workflows/ci.yml`.

- Triggers: `pull_request` (every PR) and `push` to `main`.
- Top-level `permissions: contents: read` (least privilege); no secrets referenced; no `pull_request_target`.
- Job `lint` (name exactly `lint`): checkout, setup uv, `uv sync --frozen`, `uv run ruff check .`, `uv run ruff format --check .`.
- Job `test` (name exactly `test`): checkout, setup uv, `uv sync --frozen`, `uv run python -m unittest discover -s tests -v`. Includes the no-LLM smoke test with a fake LLM (added in T8; T0 ships a placeholder test so the check is green from the start).
- Actions pinned by full commit SHA (with a version comment), resolved at T0 time; major tags are the documented fallback only if a SHA cannot be verified.
- `concurrency` group cancels superseded runs. `timeout-minutes` set on each job.
- Branch protection on `main` (applied at repo creation in T-PUB): required status checks `lint` and `test`, PR approval required, no force-push, no deletion.
- Local pre-push step (not CI): `betterleaks dir .` clean, then `uv run ruff check . && uv run ruff format --check . && uv run python -m unittest discover -s tests`.

## 4. Task list

Every task ends with **STOP-FOR-CHECKPOINT** (user confirms before the next). Coding tasks are delegated per section 6. Paths are relative to the repo root.

### T0: CI workflow, pyproject, ruff, package skeleton, placeholder test
- Goal: green CI scaffolding before any logic.
- Files: `.github/workflows/ci.yml`, `pyproject.toml`, `uv.lock`, `.gitignore`, `src/ohrouting/__init__.py`, `tests/__init__.py`, `tests/test_placeholder.py`.
- Steps: write pyproject (Python 3.12, ruff config, no SDK dependency yet); write the workflow per section 3, resolving action SHAs; placeholder test asserts the package imports; `.gitignore` covers `.venv`, `results/`, `__pycache__`, `.env*`.
- Verify: `uv sync && uv run ruff check . && uv run ruff format --check . && uv run python -m unittest discover -s tests -v`; inspect workflow for job names `lint`/`test`, permissions, SHA pins; `betterleaks dir .`.
- Deps: none. ADR refs: design CI/MVP scope; ADR 0001.
- STOP-FOR-CHECKPOINT.

### T-PUB: Publication (separate gate, only at user request)
- Goal: create public repo `miqui/openhands-llm-routing` and protect `main`.
- Files: none created.
- Steps: confirm T0 verified; run `betterleaks dir .` (must be clean); run the sanctioned `git-workflow.sh init` (tolerates a clean tree); create repo with branch protection requiring checks `lint` and `test` plus PR approval at creation; push; confirm first CI run is green.
- Verify: `gh api repos/miqui/openhands-llm-routing/branches/main/protection` shows both required checks and the PR review requirement; CI run succeeded.
- Deps: T0 verified, explicit user request. ADR refs: design MVP scope; ADR 0001.
- STOP-FOR-CHECKPOINT.

### T1: Spike against the real SDK
- Goal: verify assumptions before building on them. Minimal or no spend (a few short Haiku calls, spike script enforces a small cap, e.g. under $0.10).
- Files: `spikes/spike_switch.py`, `spikes/spike_otel.py`, `spikes/spike_cache.py`, `docs/notes/spike-findings.md`; add `openhands-sdk`, `openhands-tools` pins to `pyproject.toml`/`uv.lock`.
- Steps: (a) resolve and pin latest SDK versions, record them; (b) query the OpenRouter models API (`https://openrouter.ai/api/v1/models`, no key needed) and record current Sonnet and Haiku IDs against `anthropic/claude-sonnet-4.5` and `anthropic/claude-haiku-4.5`, plus the endpoints list for the provider pin and the price sheet; (c) verify `LLMProfileStore` + `switch_llm()` on a live conversation: history preserved, tools still work, what state is reset; (d) verify OTEL spans reach a local OTLP endpoint (stdlib listener on 4318, or Jaeger); (e) verify whether `cache_control` is set for Anthropic via OpenRouter, using two identical-prefix calls and reading cached tokens; (f) verify whether the prompt prefix (system prompt, tool schemas) is unchanged by `switch_llm()`.
- Verify: findings file records versions, IDs, observed behaviour with evidence (token counts, span names); no keys in output (`betterleaks dir .`).
- Deps: T0. ADR refs: ADR 0002, 0003, 0006; design Assumptions, Open items.
- Branching: if `switch_llm()` is blocked or loses state, STOP and draft a new ADR for fallback D2 for user approval before T3 to T6 continue. If `cache_control` is not set, record the minimal documented way to enable it (SDK option or request extra-body) and apply it in T6; if impossible, raise a blocker.
- STOP-FOR-CHECKPOINT.

### T2: Config module
- Goal: all tunables as config values.
- Files: `src/ohrouting/config.py`, `config/default.toml`, `tests/test_config.py`.
- Steps: dataclasses for models (IDs per ADR 0009: Sonnet 5.5 frontier, Haiku 5.5 cheap), pinned provider per model, `reasoning_effort` (explicit default `none`), repeats, per-run cap, per-sweep cap (no unmeasured number treated as fact; a live run requires caps to be set), switch points {5,10,15}, OTLP endpoint default `http://localhost:4318` overridable via `OTEL_EXPORTER_OTLP_*`, price sheet stored with results. The key is read from env only, passed to the LLM builder, and never appears in `repr`.
- Verify: `uv run python -m unittest tests.test_config -v` (env override, missing-key error without value, `repr` redaction); ruff.
- Deps: T1. ADR refs: ADR 0009 (supersedes 0003), 0004, 0006, 0007.
- STOP-FOR-CHECKPOINT.

### T3: Policies
- Goal: pure functions (turn, phase, previous model) to model name.
- Files: `src/ohrouting/policies.py`, `tests/test_policies.py`.
- Steps: implement sticky, alternate, phase-boundary, switch-at-N; table-driven tests over 25 turns: none for sticky, a switch every turn for alternate, switches only at phase change for phase-boundary, exactly one switch at N for switch-at-N.
- Verify: `uv run python -m unittest tests.test_policies -v`.
- Deps: T2. ADR refs: ADR 0005.
- STOP-FOR-CHECKPOINT.

### T4: Task definitions and fixture repo
- Goal: three deterministic tasks (bug fix, feature add, refactor) needing 20+ turns.
- Files: `src/ohrouting/tasks.py`, `tasks/bugfix/`, `tasks/feature/`, `tasks/refactor/` (each a small Python fixture package, failing tests, `task.toml` with prompt and phases), `tests/test_tasks.py`.
- Steps: design each fixture so the first attempt fails tests and several edit/test cycles are needed (multiple modules, cross-file dependencies); declare phases explore, implement, test-fix. Proposed triggers: explore ends at the first file-edit tool event; implement ends at the first test command after an edit; test-fix thereafter; each has a turn-count fallback (explore at most 5 turns, implement at most 12) so boundaries always exist; the run records which boundary fired. Fixtures are copied to a temp workdir per run.
- Verify: unit tests confirm fixture tests fail on a pristine copy (subprocess `unittest`) and phase triggers behave on synthetic event sequences; ruff.
- Deps: T3 (phase names). ADR refs: ADR 0008.
- STOP-FOR-CHECKPOINT.

### T5: Recorder
- Goal: append-only JSONL, one row per LLM call.
- Files: `src/ohrouting/recorder.py`, `tests/test_recorder.py`.
- Steps: fields exactly per the design data model (run_id, task, policy, policy_params, repeat, turn, phase, model, switched, upstream_provider, provider_pinned_ok, prompt/cached/uncached/cache_write/completion tokens, cost_usd, computed_cost_usd, status, error, ts); run-level `failed` and `over_cap` statuses; provider mismatch flagged; scrub secrets from error strings (env key value, `Authorization` text); flush per row.
- Verify: unit tests round-trip rows, failed runs flagged for exclusion, no leakage with a planted fake key; ruff.
- Deps: T2. ADR refs: ADR 0001, 0004, 0007; design Data model.
- STOP-FOR-CHECKPOINT.

### T6: Runner
- Goal: execute one run end to end.
- Files: `src/ohrouting/runner.py`, `src/ohrouting/llm_factory.py`, `src/ohrouting/__main__.py` (CLI `run`, `sweep`), `tests/test_runner.py` (injected fake LLM factory).
- Steps: one LLM profile per model in `LLMProfileStore`; OpenRouter pinning via `provider.order` plus `allow_fallbacks: false`; `usage: {include: true}`; apply the cache_control approach chosen in T1; ask the policy before each step and call `switch_llm()` on change; no sleeps between steps (5-minute cache TTL) and a warning if an inter-step gap exceeds 60 s; enforce per-run and per-sweep caps (abort run as `over_cap`, stop sweep at cap); failed runs recorded, never retried; `--dry-run` prints planned run count and worst-case cost from caps without API calls; a live run refuses to start if caps are unset.
- Verify: `uv run python -m unittest tests.test_runner -v` (switch at expected turns, cap abort, failure recorded not retried, no key in output); ruff.
- Deps: T1, T2, T3, T4, T5. ADR refs: ADR 0001, 0002, 0004, 0005, 0007.
- STOP-FOR-CHECKPOINT.

### T7: OTEL attributes
- Goal: spans carry the experiment metadata.
- Files: `src/ohrouting/otel.py`, `tests/test_otel.py`.
- Steps: configure OTLP http/protobuf export, default `http://localhost:4318`, honouring `OTEL_EXPORTER_OTLP_*`; one trace per session; LLM-call span attributes: policy, phase, model, prompt/cached/completion tokens, cost, `switched=true` on the switch turn; an unreachable endpoint logs a warning and never fails a run; export disabled in tests and CI.
- Verify: unit test with an in-memory span exporter checks attributes and `switched`; manual check (executed in T10): `curl -s -o /dev/null -w '%{http_code}' -X POST http://localhost:4318/v1/traces` returns an HTTP status (endpoint reachable), then the Jaeger UI (`http://localhost:16686`) shows a trace with the attributes.
- Deps: T6, T1 findings. ADR refs: ADR 0006.
- STOP-FOR-CHECKPOINT.

### T8: Fake-LLM smoke test in CI
- Goal: keyless end-to-end test of runner + recorder (+ report when T9 lands).
- Files: `tests/fakes.py`, `tests/test_smoke.py`; edit `.github/workflows/ci.yml` only if extra setup is needed.
- Steps: scripted fake LLM with deterministic usage and tool actions through the real runner for all policies on a tiny task; assert JSONL rows, switch count per policy, cost-cap abort; assert `OPENROUTER_API_KEY` is unset and no network is used.
- Verify: `env -u OPENROUTER_API_KEY uv run python -m unittest discover -s tests -v`; CI `test` green after T-PUB.
- Deps: T6 (T7 optional). ADR refs: ADR 0001, 0005; design ci.
- STOP-FOR-CHECKPOINT.

### T9: Report command
- Goal: stdlib-only Markdown report from JSONL.
- Files: `src/ohrouting/report.py`, `tests/test_report.py`, `tests/fixtures/results_sample.jsonl`.
- Steps: cache-hit rate per policy (cached / prompt tokens, normalised per turn and repeat), cost vs sticky (ratio and delta), cost-vs-switch-point table for N in {5,10,15} (Markdown table, no plotting libs), spread (min/mean/max when repeats >= 2); failed, over_cap and provider-mismatch runs listed but excluded; CLI `report --input <jsonl> --output <md>`.
- Verify: `uv run python -m unittest tests.test_report -v` with a golden-file comparison on the sample fixture; ruff.
- Deps: T5. ADR refs: ADR 0005, 0007; design report.
- STOP-FOR-CHECKPOINT.

### T10: First live smoke run, calibration, ADR 0010
- Goal: first real spend, small and user-approved: one sticky run on Sonnet and one on Haiku on one task.
- Files: `docs/decisions/0010-calibrated-repeats-and-caps.md`, `docs/notes/smoke-run.md`; no keys.
- Steps: user confirms a spend ceiling and supplies the key via `op run --env-file=...` (never typed by the agent); temporary conservative caps via config override; run both sticky runs; check Jaeger reachable and trace visible (T7 check); validate a nonzero cache-hit rate on sticky (blocker if zero: revisit cache_control per T1); record real tokens, cost per run, turns reached, variance estimate; calibrate N, per-run cap, per-sweep cap from measured cost with stated headroom; write ADR 0010 superseding the deferral in [ADR 0007](../decisions/0007-defer-run-count-and-budget-caps.md) (new ADR; ADR 0007 is only marked superseded per the repo's ADR process); report the real cost to the user.
- Verify: `results/smoke-*.jsonl` has rows with `status=ok`; the report command runs on it; `betterleaks dir .` clean.
- Deps: T6, T7, T9; user spend approval. ADR refs: ADR 0001, 0004, 0007; design Risks.
- STOP-FOR-CHECKPOINT.

### T11: Full sweep
- Goal: 3 tasks x 6 variants x N repeats with calibrated caps.
- Files: `results/sweep-<date>.jsonl` (gitignored; summary committed in T12), `docs/notes/sweep-log.md`.
- Steps: `--dry-run` first to show run count and worst-case cost; user approves; run in batches under `op run`; failed runs recorded and excluded, reported not retried (a re-run is a separate user decision).
- Verify: row counts per policy and task match the plan; failures listed; total cost versus sweep cap.
- Deps: T10 and ADR 0010 accepted; explicit user approval. ADR refs: ADR 0004, 0005, 0007.
- STOP-FOR-CHECKPOINT.

### T12: Results report and README
- Goal: findings and run instructions.
- Files: `README.md`, `docs/results/openhands-llm-routing-results.md`, `docs/results/report.md`.
- Steps: generate the report from the sweep; write the results narrative with limits (synthetic tasks, no quality scoring, one provider per model); README with "Run manually" (section 5) and the production-style checklist.
- Verify: every README command executed once in this task and its pasted output matches; links resolve; `betterleaks dir .` clean; CI green on the PR.
- Deps: T9, T11. ADR refs: all.
- STOP-FOR-CHECKPOINT.

## 5. README requirement

- A "Run manually" section with copy-paste commands and expected output. Only commands actually executed during T0 to T12 are documented; nothing is written from imagination. Expected output is pasted from a real run with secrets and personal paths removed.
- Skeleton: prerequisites (uv, Jaeger on 4318, 1Password `op`), `uv sync`, `op run --env-file=<file> -- uv run python -m ohrouting run ...`, `report`, where results land.
- Production-style checklist: key via env only; caps set and reviewed; `--dry-run` reviewed; provider pins confirmed; Jaeger reachable; `betterleaks dir .` clean; lint and tests green; results file backed up; no key in logs.

## 6. Execution approach

- Coding tasks are delegated to subagents in batches of related tasks (proposed: T0; T1; T2+T3; T4+T5; T6+T7; T8+T9), each with full context: design, ADRs, this plan, and the batch's tasks.
- Before each checkpoint the parent independently verifies: re-run `ruff check`, `ruff format --check` and unittest; inspect `git diff`; scan for real or masked credentials (`betterleaks dir .` plus a grep for key-like strings); confirm only intended files changed.
- Subagents do not commit, push or publish unless told. Publication is the separate gate T-PUB (sanctioned `git-workflow.sh init`, betterleaks first, protect `main` with `lint` and `test` at creation), executed only at the user's request after T0 is verified.
- Any change that contradicts an ADR stops work and produces a new ADR for approval.

## 7. TBD register

| # | Item | Proposed resolution | Resolve in |
|---|---|---|---|
| 1 | Current OpenRouter model IDs for Sonnet and Haiku | **Resolved 2026-10-20**: `anthropic/claude-sonnet-5.5` and `anthropic/claude-haiku-5.5` confirmed on OpenRouter (user chose the 5.5 pair, [ADR 0009](../decisions/0009-use-claude-5-5-model-pair.md)); set in config | T1, T2 |
| 2 | Pinned upstream provider per model | **Resolved**: `anthropic` (tag `anthropic`) exists for both 5.5 models at base price; recorded in config | T1, T2 |
| 3 | `openhands-sdk` / `openhands-tools` versions | Latest released via `uv pip`/PyPI, exact pins, recorded | T1 |
| 4 | `cache_control` behaviour via OpenRouter | Two identical-prefix calls; enable explicitly if the SDK does not; hard blocker if cache hits stay zero | T1, T10 |
| 5 | `switch_llm()` preserves session and cache-relevant prefix | Live spike comparing system prompt and tool schemas before and after; if blocked, new ADR for D2 | T1 |
| 6 | Repeats, per-run cap, per-sweep cap | Config values; calibrate from smoke cost and record in ADR 0010 (N=3, $2, $40 stay unmeasured guesses until then) | T10 |
| 7 | Exact phase triggers per task | Proposed in T4: first edit ends explore, first post-edit test run ends implement, turn-count fallbacks | T4 |
| 8 | Jaeger availability | Assumed running locally; T7/T10 check `http://localhost:4318` is reachable and the UI shows a trace; absence never fails a run, but verification is blocked until Jaeger is up | T7, T10 |
| 9 | GitHub Action SHAs | Resolve at T0 and verify against upstream tags | T0 |
| 10 | Price sheet values for computed cost | From the OpenRouter models API at T1; stored with results | T1, T2 |
| 11 | Whether tasks reliably reach 20+ turns | Check in T10; adjust fixtures (T4 follow-up) if not | T4, T10 |
| 12 | `betterleaks` installed on user machine | Assumed; T0 verification runs it; hard blocker for any push if absent | T0 |
| 13 | Publication timing | User-triggered gate T-PUB | T-PUB |

No other TBDs are accepted; new ones are added here with a resolution plan.

## 8. Risks carried from the design and mitigations

| Risk | Mitigation by task |
|---|---|
| No cache_control, everything shows 0% cached | T1 spike; T6 explicit enablement; T10 requires nonzero sticky cache hit |
| TTL cliff (5 min) | T6 no idle between steps plus gap warning; T8 test |
| Nondeterminism | T4 fixed fixtures; T9 per-turn normalisation and repeats; T10 variance estimate |
| Provider failures mid-run | T5/T6 record failed, exclude, never retry; T9 lists them |
| Provider drift | T2 pins; T6 `allow_fallbacks: false`; T5 flags mismatch |
| Cost overrun | T2/T6 caps and dry-run worst case; T10 calibration; T11 approval |
| Secrets | env only (T2); scrubbing (T5); keyless CI (T0, T8); `betterleaks dir .` before every push |
| SDK switch behaviour | T1 spike; new ADR for D2 if blocked |
| SDK version drift | T1 exact pins and lockfile |

## 9. Revision log

| Date | Change | By |
|---|---|---|
| 2026-10-20 | Initial draft | miguel quintero (drafted by agent) |
| 2026-10-20 | Model pair changed to Claude 5.5 (ADR 0009 supersedes ADR 0003); TBD 1 and 2 resolved; T10 calibration ADR renumbered 0009 to 0010; T2 adds a `reasoning_effort` config value (default `none`); switch-back cache warmth test assigned to the T6 smoke run; ADR 0006 corrected (span names, T7 adds policy/phase/switched) | miguel quintero (applied by agent) |
