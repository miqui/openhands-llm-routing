"""T1 spike (d): do SDK OTEL spans reach a local OTLP/HTTP endpoint?

Starts a throwaway stdlib listener on 127.0.0.1:4318, runs a tiny Haiku conversation with one
terminal tool call, flushes, then prints the span names (and attribute keys) the listener decoded.
Key comes from OPENROUTER_API_KEY only. Hard cost cap enforced; total cost printed.
"""

import gzip
import os
import sys
import tempfile
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, HTTPServer

# The SDK enables observability only if these are set before the conversation starts.
os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT", "http://127.0.0.1:4318/v1/traces")
os.environ.setdefault("OTEL_EXPORTER_OTLP_TRACES_PROTOCOL", "http/protobuf")
os.environ.setdefault("OPENHANDS_SUPPRESS_BANNER", "1")

from openhands.sdk import LLM, Agent, Conversation, Tool  # noqa: E402
from openhands.tools.terminal import TerminalTool  # noqa: E402
from opentelemetry.proto.collector.trace.v1.trace_service_pb2 import (  # noqa: E402
    ExportTraceServiceRequest,
)
from pydantic import SecretStr  # noqa: E402

COST_CAP_USD = 0.03
MODEL = os.environ.get("SPIKE_MODEL", "anthropic/claude-haiku-4.5")
SPANS: list[dict] = []
REQUESTS: list[tuple[str, str]] = []


class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("Content-Length", 0)))
        if self.headers.get("Content-Encoding") == "gzip":
            body = gzip.decompress(body)
        REQUESTS.append((self.path, self.headers.get("Content-Type", "")))
        req = ExportTraceServiceRequest()
        try:
            req.ParseFromString(body)
        except Exception as exc:  # noqa: BLE001
            print("decode error:", type(exc).__name__)
        for rs in req.resource_spans:
            for ss in rs.scope_spans:
                for sp in ss.spans:
                    SPANS.append(
                        {
                            "name": sp.name,
                            "trace": sp.trace_id.hex(),
                            "parent": sp.parent_span_id.hex(),
                            "attrs": sorted(a.key for a in sp.attributes),
                        }
                    )
        self.send_response(200)
        self.send_header("Content-Type", "application/x-protobuf")
        self.end_headers()
        self.wfile.write(b"")

    def log_message(self, *args):
        pass


def main() -> None:
    # SPIKE_NO_LISTENER=1 checks that a missing collector does not break the run.
    server = None
    if not os.environ.get("SPIKE_NO_LISTENER"):
        server = HTTPServer(("127.0.0.1", 4318), Handler)
        threading.Thread(target=server.serve_forever, daemon=True).start()
    work = tempfile.mkdtemp(prefix="spike_otel_")
    llm = LLM(
        model=f"openrouter/{MODEL}",
        base_url="https://openrouter.ai/api/v1",
        api_key=SecretStr(os.environ["OPENROUTER_API_KEY"]),
        usage_id="otel",
        litellm_extra_body={"usage": {"include": True}},
        max_output_tokens=200,
    )
    agent = Agent(llm=llm, tools=[Tool(name=TerminalTool.name)])
    conv = Conversation(agent=agent, workspace=work, max_iteration_per_run=5, visualizer=None)
    conv.send_message("Use the terminal tool to run: echo hi . Then reply DONE.")
    conv.run()
    total = conv.conversation_stats.get_combined_metrics().accumulated_cost
    if total > COST_CAP_USD:
        print("COST CAP EXCEEDED")
        sys.exit(2)
    conv.close()
    try:
        from lmnr import Laminar

        Laminar.flush()
        Laminar.shutdown()
    except Exception as exc:  # noqa: BLE001
        print("flush error:", type(exc).__name__)
    if server:
        server.shutdown()
    print("listener requests:", REQUESTS)
    print("spans received:", len(SPANS))
    for name, n in Counter(s["name"] for s in SPANS).items():
        print(f"  span name={name!r} count={n}")
    print("distinct traces:", len({s["trace"] for s in SPANS}))
    seen: dict[str, list[str]] = {}
    for s in SPANS:
        seen.setdefault(s["name"], s["attrs"])
    for name, attrs in seen.items():
        print(f"  attrs[{name}] = {attrs}")
    print("run finished with status:", conv.state.execution_status)
    print("TOTAL COST USD:", f"{total:.5f}")


if __name__ == "__main__":
    main()
