#!/usr/bin/env python3
"""Smoke test for the imho.run MCP server and REST API.

Standard library only, so it runs anywhere with Python 3.8+:

    python scripts/smoke_test.py            # 6 checks, about 7 requests
    python scripts/smoke_test.py --find     # also calls find_game_by_description
                                            # (slow, counts against its 20/day limit)

Exit code 0 when every check passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.parse
import urllib.request
from typing import Any, Callable, Dict, List, Tuple

UA = "imho-mcp-smoke-test/1.0 (+https://github.com/0x216/imho-mcp)"
EXPECTED_TOOLS = {"games_like", "game_facts", "find_game_by_description"}


def http(
    method: str, url: str, body: Any = None, timeout: float = 60.0
) -> Tuple[int, Dict[str, Any]]:
    data = None
    headers = {"User-Agent": UA, "Accept": "application/json, text/event-stream"}
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as err:
        text = err.read().decode("utf-8", "replace")
        try:
            return err.code, json.loads(text)
        except ValueError:
            return err.code, {"raw": text[:300]}


class Smoke:
    def __init__(self, base: str) -> None:
        self.base = base.rstrip("/")
        self.mcp = f"{self.base}/mcp"
        self.rpc_id = 0
        self.failures = 0

    def rpc(self, method: str, params: Any = None, timeout: float = 60.0) -> Dict[str, Any]:
        self.rpc_id += 1
        body: Dict[str, Any] = {"jsonrpc": "2.0", "id": self.rpc_id, "method": method}
        if params is not None:
            body["params"] = params
        status, data = http("POST", self.mcp, body, timeout=timeout)
        assert status == 200, f"HTTP {status}: {data}"
        assert "error" not in data, f"JSON-RPC error: {data['error']}"
        return data["result"]

    def check(self, name: str, fn: Callable[[], str]) -> None:
        try:
            note = fn()
        except Exception as exc:  # noqa: BLE001 - report every failure, keep going
            self.failures += 1
            print(f"FAIL  {name}: {exc}")
        else:
            print(f"ok    {name}: {note}")

    # ── checks ──────────────────────────────────────────────────────────────

    def initialize(self) -> str:
        result = self.rpc(
            "initialize",
            {
                "protocolVersion": "2025-06-18",
                "capabilities": {},
                "clientInfo": {"name": "imho-mcp-smoke-test", "version": "1.0"},
            },
        )
        info = result["serverInfo"]
        assert "tools" in result["capabilities"], "no tools capability"
        return f"{info.get('title') or info['name']} {info['version']}, protocol {result['protocolVersion']}"

    def tools_list(self) -> str:
        tools: List[Dict[str, Any]] = self.rpc("tools/list")["tools"]
        names = {t["name"] for t in tools}
        missing = EXPECTED_TOOLS - names
        assert not missing, f"missing tools: {sorted(missing)}"
        for tool in tools:
            ann = tool.get("annotations") or {}
            assert ann.get("readOnlyHint") is True, f"{tool['name']} is not readOnlyHint"
        return ", ".join(sorted(names))

    def mcp_games_like(self) -> str:
        result = self.rpc(
            "tools/call", {"name": "games_like", "arguments": {"game": "Hollow Knight", "n": 3}}
        )
        assert result.get("isError") is False, result.get("content")
        data = result["structuredContent"]
        assert data["seed"]["appid"] == 367520, data["seed"]
        picks = data["results"]
        assert 1 <= len(picks) <= 3, f"{len(picks)} results"
        assert all(p.get("why") and p.get("url", "").startswith("https://imho.run/") for p in picks)
        return "; ".join(p["name"] for p in picks)

    def rest_games_like(self) -> str:
        q = urllib.parse.urlencode({"q": "stardew valley", "n": 3, "coop": "true"})
        status, data = http("GET", f"{self.base}/api/agent/games-like?{q}")
        assert status == 200, f"HTTP {status}: {data}"
        assert data["filters"]["coop"] is True
        assert data["results"], "no results"
        return f"seed {data['seed']['name']}, {len(data['results'])} co-op picks"

    def rest_game_facts(self) -> str:
        status, data = http("GET", f"{self.base}/api/agent/game-facts?q=1145360")
        assert status == 200, f"HTTP {status}: {data}"
        game = data["game"]
        assert game["name"] == "Hades", game["name"]
        return f"{game['name']} ({game.get('year')}), Deck: {game.get('steam_deck')}"

    def rest_not_found(self) -> str:
        status, data = http("GET", f"{self.base}/api/agent/game-facts?q=zzzzqqqxx")
        assert status == 404 and data.get("error") == "not_found", f"HTTP {status}: {data}"
        return "404 not_found"

    def openapi(self) -> str:
        status, data = http("GET", f"{self.base}/openapi.json")
        assert status == 200, f"HTTP {status}"
        assert str(data["openapi"]).startswith("3."), data.get("openapi")
        return f"OpenAPI {data['openapi']}, {len(data['paths'])} paths"

    def find_game(self) -> str:
        args = {"description": "you play a cat in a cyberpunk city with a small drone"}
        result = self.rpc(
            "tools/call", {"name": "find_game_by_description", "arguments": args}, timeout=120.0
        )
        assert result.get("isError") is False, result.get("content")
        data = result["structuredContent"]
        top = data["results"][0]["name"] if data["results"] else None
        return f"top: {top}, confidence {data.get('confidence')}"


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--base-url", default="https://imho.run")
    parser.add_argument(
        "--find", action="store_true", help="also call find_game_by_description (rate-limited)"
    )
    args = parser.parse_args()

    s = Smoke(args.base_url)
    s.check("MCP initialize", s.initialize)
    s.check("MCP tools/list", s.tools_list)
    s.check("MCP games_like", s.mcp_games_like)
    s.check("REST games-like", s.rest_games_like)
    s.check("REST game-facts", s.rest_game_facts)
    s.check("REST not found", s.rest_not_found)
    s.check("OpenAPI", s.openapi)
    if args.find:
        s.check("MCP find_game_by_description", s.find_game)
    print("PASS" if not s.failures else f"{s.failures} check(s) failed")
    return 1 if s.failures else 0


if __name__ == "__main__":
    sys.exit(main())
