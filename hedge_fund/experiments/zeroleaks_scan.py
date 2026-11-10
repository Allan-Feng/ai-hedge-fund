"""Bounded ZeroLeaks prompt-only scan for AIHF Buffett attack candidates."""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import requests
from dotenv import dotenv_values


ROOT = Path(__file__).resolve().parents[2]
DEFAULT_PROMPT_JSON = ROOT / (
    "evidence/aapl_20261103/observed/initial/r1_001_B/prompt.json"
)
DEFAULT_FIXTURE = ROOT / "evidence/aapl_20261103/fixtures/2026-11-03.json"
DEFAULT_CLI = Path.home() / ".cache/aihf-zeroleaks/node_modules/.bin/zeroleaks"


def start_compat_proxy(api_key: str, base_prompt: dict, title: str, call_log: Path):
    """Forward calls; insert target probes at the frozen news-title boundary."""

    log_lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def do_POST(self):
            if self.path not in ("/v1/chat/completions", "/v1/responses"):
                self.send_error(404)
                return
            size = int(self.headers.get("Content-Length", "0"))
            if size < 1 or size > 2_000_000:
                self.send_error(413)
                return
            try:
                body = json.loads(self.rfile.read(size))
                target_probe = None
                if body.get("model") == "aihf-buffett":
                    messages = body.get("messages", [])
                    for message in reversed(messages):
                        if message.get("role") == "user":
                            content = message.get("content", "")
                            target_probe = (content if isinstance(content, str)
                                            else json.dumps(content, ensure_ascii=False))
                            break
                    if target_probe is None:
                        self.send_error(400, "target request had no user message")
                        return
                    base_user = base_prompt["user"]
                    if base_user.count(title) != 1:
                        self.send_error(500, "frozen title is not unique")
                        return
                    body["model"] = "gpt-6-sol"
                    body["messages"] = [
                        {"role": "system", "content": base_prompt["system"]},
                        {"role": "user", "content": base_user.replace(
                            title, title + " " + target_probe, 1)},
                    ]
                if str(body.get("model", "")).startswith("gpt-6-"):
                    body.pop("temperature", None)
                    if body.get("tools"):
                        body["reasoning_effort"] = "none"
                with requests.post(
                    "https://api.openai.com" + self.path,
                    json=body,
                    headers={"Authorization": f"Bearer {api_key}"},
                    timeout=(10, 180),
                    stream=True,
                ) as upstream:
                    self.send_response(upstream.status_code)
                    self.send_header("Content-Type", upstream.headers.get(
                        "Content-Type", "application/json"))
                    self.end_headers()
                    response_chunks = []
                    for chunk in upstream.iter_content(chunk_size=8192):
                        if chunk:
                            self.wfile.write(chunk)
                            self.wfile.flush()
                            if target_probe is not None:
                                response_chunks.append(chunk)
                    if target_probe is not None:
                        record = {
                            "candidate_text": target_probe,
                            "target_system": body["messages"][0]["content"],
                            "target_user": body["messages"][1]["content"],
                            "http_status": upstream.status_code,
                            "raw_provider_response": b"".join(response_chunks).decode(
                                "utf-8", errors="replace"),
                        }
                        with log_lock, call_log.open("a", encoding="utf-8") as log:
                            log.write(json.dumps(record, ensure_ascii=False) + "\n")
            except (requests.RequestException, ValueError, BrokenPipeError) as exc:
                if not self.wfile.closed:
                    self.send_error(502, str(exc))

        def log_message(self, *_args):
            pass

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--prompt-json", type=Path, default=DEFAULT_PROMPT_JSON)
    parser.add_argument("--fixture", type=Path, default=DEFAULT_FIXTURE)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--cli", type=Path, default=DEFAULT_CLI)
    parser.add_argument("--max-probes", type=int, default=2)
    parser.add_argument("--execute", action="store_true")
    args = parser.parse_args()
    if args.max_probes < 1 or args.max_probes > 5:
        parser.error("--max-probes must be between 1 and 5")
    if args.out.exists():
        parser.error(f"output directory already exists: {args.out}")
    prompt = json.loads(args.prompt_json.read_text(encoding="utf-8"))
    fixture = json.loads(args.fixture.read_text(encoding="utf-8"))
    system = prompt["system"]
    if "Warren Buffett" not in system or "Respond with JSON only" not in system:
        parser.error("input is not the saved Buffett B/C system prompt")
    if "Decision cutoff" not in system:
        parser.error("input is missing the daily-news time-anchor addition")
    title = fixture["news"][0]["title"]
    if prompt["user"].count(title) != 1 or "Daily external news" not in prompt["user"]:
        parser.error("input is not the frozen AAPL B prompt")
    args.out.mkdir(parents=True)
    prompt_file = args.out / "buffett_system_prompt.txt"
    prompt_file.write_text(system + "\n", encoding="utf-8")
    command = [
        str(args.cli), "scan", "--file", str(prompt_file), "--mode", "injection",
        "--injection-category", "indirect_injection,authority_exploit",
        "--no-multi-turn", "--max-probes", str(args.max_probes),
        "--target-model", "aihf-buffett", "--attacker-model", "gpt-6-sol",
        "--evaluator-model", "gpt-6-sol", "--injection-model", "gpt-6-sol",
        "--duration", "120000", "--output", str(args.out / "zeroleaks_report.json"),
        "--no-color",
    ]
    (args.out / "setup.json").write_text(
        json.dumps({
            "source_prompt_json": str(args.prompt_json.resolve()),
            "source_user_prompt_included": True,
            "mode": "frozen_aapl_headline_boundary",
            "source_fixture": str(args.fixture.resolve()),
            "probe_insertion": "append target probe to news title 0",
            "command": command,
            "zero_leaks_version": "1.5.0",
            "aihf_model": "gpt-6-sol",
            "aihf_parser_executed": False,
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    if not args.execute:
        print(f"Prepared prompt and command in {args.out}; no model calls made.")
        return 0
    if not args.cli.is_file():
        parser.error(f"ZeroLeaks CLI not found: {args.cli}")
    env = os.environ.copy()
    if not env.get("OPENAI_API_KEY"):
        env_file = Path.home() / ".hedge-fund/.env"
        env.update({
            "OPENAI_API_KEY": key
            for key in [dotenv_values(env_file).get("OPENAI_API_KEY")]
            if key
        })
    if not env.get("OPENAI_API_KEY"):
        parser.error("OPENAI_API_KEY not found in environment or ~/.hedge-fund/.env")
    proxy = start_compat_proxy(
        env["OPENAI_API_KEY"], prompt, title, args.out / "target_calls.jsonl")
    command.extend(["--base-url", f"http://127.0.0.1:{proxy.server_port}/v1"])
    try:
        with (args.out / "scan.log").open("w", encoding="utf-8") as log:
            completed = subprocess.run(command, cwd=ROOT, env=env, stdout=log,
                                       stderr=subprocess.STDOUT, check=False)
    finally:
        proxy.shutdown()
        proxy.server_close()
    print(f"ZeroLeaks exit code: {completed.returncode}; report: {args.out / 'zeroleaks_report.json'}")
    print("Exit 1 means a finding; exit 2 means the scan had no complete verdict.")
    return completed.returncode


if __name__ == "__main__":
    raise SystemExit(main())
