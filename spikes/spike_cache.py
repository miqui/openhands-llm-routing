"""T1 spike (e): is cache_control applied for Anthropic via OpenRouter with SDK defaults?

Sends identical-prefix calls straight through the SDK LLM (no agent) with a ~5k token filler
prefix (above Haiku 4.5's minimum cacheable length). Reports cache read/write tokens from SDK
metrics and from the logged OpenRouter response. Calls: control (caching_prompt=False) x2, then
SDK defaults x2. Key comes from OPENROUTER_API_KEY only. Hard cost cap; total cost printed.
"""

import json
import os
import sys
import tempfile
import uuid
from pathlib import Path

from openhands.sdk import LLM, Message, TextContent
from pydantic import SecretStr

COST_CAP_USD = float(os.environ.get("SPIKE_COST_CAP", "0.06"))
MODEL = os.environ.get("SPIKE_MODEL", "anthropic/claude-haiku-4.5")
# Unset = SDK default reasoning_effort; otherwise passed through explicitly.
REASONING = os.environ.get("SPIKE_REASONING")
EXTRA_BODY = {
    "provider": {"order": ["anthropic"], "allow_fallbacks": False},
    "usage": {"include": True},
}
# Unique per run so earlier runs cannot pre-warm the cache; deterministic within a run.
NONCE = uuid.uuid4().hex
FILLER = " ".join(f"Line {i}: reference note {NONCE} item {i * 7919 % 1009}." for i in range(480))


def build(caching: bool, log_dir: str, usage_id: str) -> LLM:
    return LLM(
        model=f"openrouter/{MODEL}",
        base_url="https://openrouter.ai/api/v1",
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        usage_id=usage_id,
        caching_prompt=caching,
        litellm_extra_body=EXTRA_BODY,
        log_completions=True,
        log_completions_folder=log_dir,
        max_output_tokens=20,
        temperature=0.0,
        **({"reasoning_effort": REASONING} if REASONING else {}),
    )


def messages(variant: str) -> list[Message]:
    return [
        Message(role="system", content=[TextContent(text=f"[{variant}] Static notes.\n{FILLER}")]),
        Message(role="user", content=[TextContent(text="Reply with the single word OK.")]),
    ]


def main() -> None:
    log_dir = tempfile.mkdtemp(prefix="spike_cache_")
    costs: list[float] = []
    for label, caching in (("control", False), ("sdk_default", True)):
        llm = build(caching, log_dir, label)
        print(f"== {label}; caching_prompt={caching} active={llm.is_caching_prompt_active()}")
        for call in (1, 2):
            llm.completion(messages=messages(label))
            tu = llm.metrics.token_usages[-1]
            print(
                f"call {call}: prompt={tu.prompt_tokens} cache_read={tu.cache_read_tokens} "
                f"cache_write={tu.cache_write_tokens} completion={tu.completion_tokens}"
            )
        costs.append(llm.metrics.accumulated_cost)
        print(f"  accumulated cost: ${costs[-1]:.5f}")
        if sum(costs) > COST_CAP_USD:
            print("COST CAP EXCEEDED")
            sys.exit(2)
    for p in sorted(Path(log_dir).glob("*.json"), key=lambda q: q.stat().st_mtime):
        d = json.loads(p.read_text())
        u = d["response"].get("usage") or {}
        det = u.get("prompt_tokens_details") or {}
        n_cc = json.dumps(d.get("messages")).count("cache_control")
        kw = d.get("kwargs") or {}
        print(
            f"log {p.name[-9:]}: req_reasoning_effort={kw.get('reasoning_effort')} "
            f"reasoning_tokens={(u.get('completion_tokens_details') or {}).get('reasoning_tokens')}"
        )
        print(
            f"log {p.name[-9:]}: cache_control_markers_in_request={n_cc} "
            f"or_prompt={u.get('prompt_tokens')} or_cached={det.get('cached_tokens')} "
            f"or_cache_write={det.get('cache_write_tokens')} or_cost={u.get('cost')} "
            f"served_by={d['response'].get('provider')}"
        )
    print("TOTAL COST USD:", f"{sum(costs):.5f}")


if __name__ == "__main__":
    main()
