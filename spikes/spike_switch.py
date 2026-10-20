"""T1 spike (c)+(f): LLMProfileStore + switch_llm() on a live conversation.

Checks: history preserved, tools still work, what state resets, and whether the request
prefix (system prompt, tool schemas) is byte-identical across the switch.
Key comes from OPENROUTER_API_KEY only. Hard cost cap enforced; total cost printed.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

from openhands.sdk import LLM, Agent, Conversation, LLMProfileStore, Tool
from openhands.tools.file_editor import FileEditorTool
from openhands.tools.terminal import TerminalTool
from pydantic import SecretStr

COST_CAP_USD = 0.12
FIRST = os.environ.get("SPIKE_FIRST", "anthropic/claude-haiku-4.5")
SECOND = os.environ.get("SPIKE_SECOND", "anthropic/claude-sonnet-4.5")
EXTRA_BODY = {
    "provider": {"order": ["anthropic"], "allow_fallbacks": False},
    "usage": {"include": True},
}


def build(model: str, usage_id: str, log_dir: str) -> LLM:
    return LLM(
        model=f"openrouter/{model}",
        base_url="https://openrouter.ai/api/v1",
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        usage_id=usage_id,
        litellm_extra_body=EXTRA_BODY,
        log_completions=True,
        log_completions_folder=log_dir,
        max_output_tokens=300,
        temperature=0.0,
    )


def cost(conv) -> float:
    return conv.conversation_stats.get_combined_metrics().accumulated_cost


def check_cap(conv, where: str) -> None:
    c = cost(conv)
    print(f"[cost] after {where}: ${c:.5f}")
    if c > COST_CAP_USD:
        print("COST CAP EXCEEDED, aborting")
        sys.exit(2)


def strip_cc(obj):
    """Return obj with every cache_control key removed (markers move each turn)."""
    if isinstance(obj, dict):
        return {k: strip_cc(v) for k, v in obj.items() if k != "cache_control"}
    if isinstance(obj, list):
        return [strip_cc(v) for v in obj]
    return obj


def load_logs(log_dir: str) -> list[dict]:
    files = sorted(Path(log_dir).glob("*.json"), key=lambda p: p.stat().st_mtime)
    return [json.loads(p.read_text()) for p in files]


def main() -> None:
    work = tempfile.mkdtemp(prefix="spike_switch_")
    log_dir = os.path.join(work, "logs")
    profiles = LLMProfileStore(base_dir=os.path.join(work, "profiles"))
    first, second = build(FIRST, "first", log_dir), build(SECOND, "second", log_dir)
    profiles.save("first", first)
    profiles.save("second", second)
    loaded = profiles.load("second")
    print("profile load keeps api_key:", loaded.api_key is not None)
    print("profile load keeps litellm_extra_body:", loaded.litellm_extra_body == EXTRA_BODY)
    print("profile load keeps log_completions:", loaded.log_completions)
    # Profiles are saved without secrets, so the key must be re-attached from env.
    loaded = loaded.model_copy(update={"api_key": SecretStr(os.environ["OPENROUTER_API_KEY"])})

    agent = Agent(
        llm=first,
        tools=[Tool(name=TerminalTool.name), Tool(name=FileEditorTool.name)],
    )
    conv = Conversation(agent=agent, workspace=work, max_iteration_per_run=6, visualizer=None)
    conv.send_message(
        "Use the terminal tool to run: echo marker-alpha > note.txt  . "
        "Then reply with the single word DONE."
    )
    conv.run()
    check_cap(conv, "turn 1 (first model)")
    n_events_before = len(conv.state.events)
    sys_before = [e for e in conv.state.events if type(e).__name__ == "SystemPromptEvent"]
    print("events before switch:", n_events_before, "conv id:", conv.id)
    print("agent llm before:", conv.agent.llm.model, "usage_id:", conv.agent.llm.usage_id)
    stats_before = {
        k: v.accumulated_cost for k, v in conv.conversation_stats.usage_to_metrics.items()
    }
    print("stats usage_ids before:", sorted(stats_before))

    conv.switch_llm(loaded)
    print("agent llm after:", conv.agent.llm.model, "usage_id:", conv.agent.llm.usage_id)
    print("events right after switch (history kept):", len(conv.state.events))
    sys_after = [e for e in conv.state.events if type(e).__name__ == "SystemPromptEvent"]
    print("system prompt events before/after:", len(sys_before), len(sys_after))

    conv.send_message(
        "Use the terminal tool to run: cat note.txt . "
        "Then reply with the contents of that file and the exact text of my FIRST instruction."
    )
    conv.run()
    check_cap(conv, "turn 2 (second model)")
    events = list(conv.state.events)
    print("events after turn 2:", len(events))
    tool_obs = [e for e in events if type(e).__name__ == "ObservationEvent"]
    print("observation events total:", len(tool_obs))
    for e in tool_obs:
        print("  obs:", type(e.observation).__name__)
    last_msgs = [e for e in events if type(e).__name__ == "MessageEvent" and e.source == "agent"]
    if last_msgs:
        parts = last_msgs[-1].llm_message.content
        print("final agent text:", " ".join(getattr(p, "text", "") for p in parts)[:400])
    print("stats usage_ids after:", sorted(conv.conversation_stats.usage_to_metrics))
    for k, v in conv.conversation_stats.usage_to_metrics.items():
        print(f"  usage_id={k} cost=${v.accumulated_cost:.5f}")
    print("execution_status:", conv.state.execution_status)

    # (f) prefix comparison from logged requests
    logs = load_logs(log_dir)
    print("logged LLM calls:", len(logs))
    rows = []
    for i, d in enumerate(logs):
        msgs = d.get("messages") or d.get("kwargs", {}).get("messages")
        tools = d.get("tools") or d.get("kwargs", {}).get("tools")
        model = d.get("kwargs", {}).get("model") or d.get("model")
        sysmsg = json.dumps(msgs[0], sort_keys=True) if msgs else None
        tl = json.dumps(tools, sort_keys=True) if tools else None
        usage = d.get("usage_summary")
        rows.append((i, model, sysmsg, tl, usage, d.get("cost")))
        print(
            f"call {i}: model={model} n_msgs={len(msgs or [])} "
            f"sys_len={len(sysmsg or '')} tools_len={len(tl or '')} "
            f"usage={usage} cost={d.get('cost')}"
        )
    for i in range(1, len(rows)):
        print(
            f"call {i} vs call 0: system_identical={rows[i][2] == rows[0][2]} "
            f"tools_identical={rows[i][3] == rows[0][3]}"
        )
    # Where does the first message list diverge between models? (shared-prefix length)
    m0 = logs[0].get("messages") or []
    for i in range(1, len(logs)):
        mi = logs[i].get("messages") or []
        k = 0
        while k < min(len(m0), len(mi)) and json.dumps(
            strip_cc(m0[k]), sort_keys=True
        ) == json.dumps(strip_cc(mi[k]), sort_keys=True):
            k += 1
        print(f"call {i}: identical leading messages (ignoring cache_control) vs call 0 = {k}")
    # cache_control markers in the sent messages
    for i, d in enumerate(logs):
        s = json.dumps(d.get("messages") or [])
        print(f"call {i}: cache_control occurrences in messages = {s.count('cache_control')}")
    for i, d in enumerate(logs):
        r = d.get("response", {})
        u = r.get("usage") or {}
        det = u.get("prompt_tokens_details") or {}
        print(
            f"call {i}: served_by={r.get('provider')} model={r.get('model')} "
            f"prompt={u.get('prompt_tokens')} cached={det.get('cached_tokens')} "
            f"cache_write={det.get('cache_write_tokens')} or_cost={u.get('cost')}"
        )
    print("kwargs keys call 0:", sorted(logs[0].get("kwargs", {}).keys()))
    print("TOTAL COST USD:", f"{cost(conv):.5f}")
    print("log dir:", log_dir)


if __name__ == "__main__":
    main()
