"""Sync and async clients for the imho.run agent API.

``games_like`` and ``game_facts`` use the REST endpoints under
``/api/agent/``. ``find_game_by_description`` exists only as an MCP tool, so
it (and :meth:`call_tool` for any other tool) goes through the MCP endpoint
with a single stateless JSON-RPC request.
"""

from __future__ import annotations

import itertools
import json
import re
from typing import Any, Dict, List, Mapping, Optional, Union, cast

import httpx

from ._version import __version__
from .errors import (
    BadRequestError,
    DisabledError,
    ImhoError,
    NotFoundError,
    RateLimitError,
    ToolError,
)
from .types import (
    CoopMode,
    FindGameResult,
    GameFactsResult,
    GamesLikeResult,
    Lang,
    Perspective,
    Platform,
    SteamDeck,
)

DEFAULT_BASE_URL = "https://imho.run"
DEFAULT_TIMEOUT = 30.0
# find_game_by_description runs a language model; give it more room.
FIND_TIMEOUT = 90.0
MCP_PROTOCOL_VERSION = "2025-06-18"
USER_AGENT = f"imho-python/{__version__} (+https://github.com/0x216/imho-mcp)"

_RATE_TEXT = re.compile(r"Too many requests\. Retry after (\d+(?:\.\d+)?)s", re.I)
_ids = itertools.count(1)

Coop = Union[bool, CoopMode]


# ── request building (shared by both clients) ──────────────────────────────


def _games_like_params(
    game: str,
    n: int,
    lang: Lang,
    free: bool,
    coop: Coop,
    steam_deck: Optional[SteamDeck],
) -> Dict[str, str]:
    if not 1 <= n <= 20:
        raise ValueError("n must be between 1 and 20")
    params = {"q": game, "n": str(n), "lang": lang}
    if free:
        params["free"] = "true"
    if coop is True:
        params["coop"] = "true"
    elif coop in ("online", "local"):
        params["coop"] = cast(str, coop)
    elif coop is not False:
        raise ValueError("coop must be True, False, 'online' or 'local'")
    if steam_deck is not None:
        params["deck"] = steam_deck
    return params


def _find_args(
    description: str,
    lang: Lang,
    platform: Optional[Platform],
    year_min: Optional[int],
    year_max: Optional[int],
    perspective: Optional[Perspective],
) -> Dict[str, Any]:
    args: Dict[str, Any] = {"description": description, "lang": lang}
    for key, value in (
        ("platform", platform),
        ("year_min", year_min),
        ("year_max", year_max),
        ("perspective", perspective),
    ):
        if value is not None:
            args[key] = value
    return args


def _rpc(method: str, params: Optional[Mapping[str, Any]] = None) -> Dict[str, Any]:
    body: Dict[str, Any] = {"jsonrpc": "2.0", "id": next(_ids), "method": method}
    if params is not None:
        body["params"] = dict(params)
    return body


_MCP_HEADERS = {
    "Accept": "application/json, text/event-stream",
    "MCP-Protocol-Version": MCP_PROTOCOL_VERSION,
}


# ── response handling ──────────────────────────────────────────────────────


def _retry_after(resp: httpx.Response) -> Optional[float]:
    value = resp.headers.get("Retry-After")
    try:
        return float(value) if value is not None else None
    except ValueError:
        return None


def _raise_for_rest(resp: httpx.Response) -> Dict[str, Any]:
    try:
        data = resp.json()
    except ValueError:
        data = None
    if resp.status_code < 400 and isinstance(data, dict):
        return data
    detail = resp.text[:500] or resp.reason_phrase
    code: Optional[str] = None
    if isinstance(data, dict):
        code = data.get("error") if isinstance(data.get("error"), str) else None
        if isinstance(data.get("detail"), str):
            detail = data["detail"]
        elif data.get("detail") is not None:  # FastAPI validation errors
            detail = str(data["detail"])
    status = resp.status_code
    if status == 429 or code == "rate_limited":
        raise RateLimitError(detail, status=status, retry_after=_retry_after(resp))
    if status == 404 or code == "not_found":
        raise NotFoundError(detail, code=code or "not_found", status=status)
    if status in (400, 422) or code == "bad_request":
        raise BadRequestError(detail, code=code or "bad_request", status=status)
    if status == 503 or code == "disabled":
        raise DisabledError(detail, code=code or "disabled", status=status)
    raise ImhoError(detail, code=code, status=status)


def _rpc_result(resp: httpx.Response) -> Dict[str, Any]:
    if resp.status_code == 429:
        raise RateLimitError(resp.text[:500], retry_after=_retry_after(resp))
    if resp.status_code >= 400:
        raise ImhoError(resp.text[:500] or resp.reason_phrase, status=resp.status_code)
    data = resp.json()
    if "error" in data:
        err = data["error"] or {}
        raise BadRequestError(
            str(err.get("message", "JSON-RPC error")),
            code=str(err.get("code")),
            status=resp.status_code,
        )
    return cast(Dict[str, Any], data.get("result") or {})


def _tool_payload(result: Mapping[str, Any]) -> Dict[str, Any]:
    if result.get("isError"):
        text = " ".join(
            str(c.get("text", "")) for c in result.get("content") or [] if isinstance(c, Mapping)
        ).strip()
        match = _RATE_TEXT.search(text)
        if match:
            raise RateLimitError(text, retry_after=float(match.group(1)))
        if text.startswith("No ") and "matched" in text:
            raise NotFoundError(text, code="not_found")
        if "switched off" in text:
            raise DisabledError(text, code="disabled")
        raise ToolError(text or "Tool call failed")
    structured = result.get("structuredContent")
    if isinstance(structured, dict):
        return structured
    # Fall back to the JSON text block.
    for block in result.get("content") or []:
        if isinstance(block, Mapping) and block.get("type") == "text":
            try:
                parsed = json.loads(block.get("text", ""))
            except ValueError:
                continue
            if isinstance(parsed, dict):
                return parsed
    return {"content": list(result.get("content") or [])}


def _client_kwargs(
    base_url: str, timeout: float, headers: Optional[Mapping[str, str]]
) -> Dict[str, Any]:
    merged = {"User-Agent": USER_AGENT}
    if headers:
        merged.update(headers)
    return {"base_url": base_url.rstrip("/"), "timeout": timeout, "headers": merged}


# ── sync client ────────────────────────────────────────────────────────────


class ImhoClient:
    """Blocking client.

    >>> from imho import ImhoClient
    >>> with ImhoClient() as imho:
    ...     picks = imho.games_like("Hollow Knight", n=5, coop=True)
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        headers: Optional[Mapping[str, str]] = None,
        http_client: Optional[httpx.Client] = None,
    ) -> None:
        self._owns_client = http_client is None
        self._http = http_client or httpx.Client(**_client_kwargs(base_url, timeout, headers))

    def __enter__(self) -> "ImhoClient":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def games_like(
        self,
        game: str,
        *,
        n: int = 10,
        lang: Lang = "en",
        free: bool = False,
        coop: Coop = False,
        steam_deck: Optional[SteamDeck] = None,
    ) -> GamesLikeResult:
        """Steam games similar to ``game`` (name, appid or Steam URL), ranked."""
        params = _games_like_params(game, n, lang, free, coop, steam_deck)
        resp = self._http.get("/api/agent/games-like", params=params)
        return cast(GamesLikeResult, _raise_for_rest(resp))

    def game_facts(self, game: str, *, lang: Lang = "en") -> GameFactsResult:
        """Public facts about one Steam game."""
        resp = self._http.get("/api/agent/game-facts", params={"q": game, "lang": lang})
        return cast(GameFactsResult, _raise_for_rest(resp))

    def find_game_by_description(
        self,
        description: str,
        *,
        lang: Lang = "en",
        platform: Optional[Platform] = None,
        year_min: Optional[int] = None,
        year_max: Optional[int] = None,
        perspective: Optional[Perspective] = None,
    ) -> FindGameResult:
        """Identify a game from what someone remembers about it.

        Slow (runs a language model) and limited to 3 calls a minute and 20 a
        day per IP. Use it only when the title is unknown.
        """
        args = _find_args(description, lang, platform, year_min, year_max, perspective)
        payload = self.call_tool("find_game_by_description", args, timeout=FIND_TIMEOUT)
        return cast(FindGameResult, payload)

    def call_tool(
        self,
        name: str,
        arguments: Optional[Mapping[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        """Call any MCP tool by name and return its structured result."""
        body = _rpc("tools/call", {"name": name, "arguments": dict(arguments or {})})
        resp = self._http.post(
            "/mcp",
            json=body,
            headers=_MCP_HEADERS,
            timeout=timeout if timeout is not None else httpx.USE_CLIENT_DEFAULT,
        )
        return _tool_payload(_rpc_result(resp))

    def list_tools(self) -> List[Dict[str, Any]]:
        """The MCP server's tool definitions (name, description, input schema)."""
        resp = self._http.post("/mcp", json=_rpc("tools/list"), headers=_MCP_HEADERS)
        return cast(List[Dict[str, Any]], _rpc_result(resp).get("tools", []))


# ── async client ───────────────────────────────────────────────────────────


class AsyncImhoClient:
    """Async client with the same methods as :class:`ImhoClient`.

    >>> async with AsyncImhoClient() as imho:
    ...     facts = await imho.game_facts("Hades")
    """

    def __init__(
        self,
        base_url: str = DEFAULT_BASE_URL,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        headers: Optional[Mapping[str, str]] = None,
        http_client: Optional[httpx.AsyncClient] = None,
    ) -> None:
        self._owns_client = http_client is None
        self._http = http_client or httpx.AsyncClient(**_client_kwargs(base_url, timeout, headers))

    async def __aenter__(self) -> "AsyncImhoClient":
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    async def games_like(
        self,
        game: str,
        *,
        n: int = 10,
        lang: Lang = "en",
        free: bool = False,
        coop: Coop = False,
        steam_deck: Optional[SteamDeck] = None,
    ) -> GamesLikeResult:
        params = _games_like_params(game, n, lang, free, coop, steam_deck)
        resp = await self._http.get("/api/agent/games-like", params=params)
        return cast(GamesLikeResult, _raise_for_rest(resp))

    async def game_facts(self, game: str, *, lang: Lang = "en") -> GameFactsResult:
        resp = await self._http.get("/api/agent/game-facts", params={"q": game, "lang": lang})
        return cast(GameFactsResult, _raise_for_rest(resp))

    async def find_game_by_description(
        self,
        description: str,
        *,
        lang: Lang = "en",
        platform: Optional[Platform] = None,
        year_min: Optional[int] = None,
        year_max: Optional[int] = None,
        perspective: Optional[Perspective] = None,
    ) -> FindGameResult:
        args = _find_args(description, lang, platform, year_min, year_max, perspective)
        payload = await self.call_tool("find_game_by_description", args, timeout=FIND_TIMEOUT)
        return cast(FindGameResult, payload)

    async def call_tool(
        self,
        name: str,
        arguments: Optional[Mapping[str, Any]] = None,
        *,
        timeout: Optional[float] = None,
    ) -> Dict[str, Any]:
        body = _rpc("tools/call", {"name": name, "arguments": dict(arguments or {})})
        resp = await self._http.post(
            "/mcp",
            json=body,
            headers=_MCP_HEADERS,
            timeout=timeout if timeout is not None else httpx.USE_CLIENT_DEFAULT,
        )
        return _tool_payload(_rpc_result(resp))

    async def list_tools(self) -> List[Dict[str, Any]]:
        resp = await self._http.post("/mcp", json=_rpc("tools/list"), headers=_MCP_HEADERS)
        return cast(List[Dict[str, Any]], _rpc_result(resp).get("tools", []))


__all__ = ["AsyncImhoClient", "ImhoClient", "DEFAULT_BASE_URL", "USER_AGENT"]
