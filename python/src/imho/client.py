"""Sync and async clients for the imho.run agent API.

Most methods use the REST endpoints under ``/api/agent/``.
``find_game_by_description`` exists only as an MCP tool, so it (and
:meth:`call_tool` for any other tool) goes through the MCP endpoint with a
single stateless JSON-RPC request.
"""

from __future__ import annotations

import itertools
import json
import re
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple, Union, cast

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
    Exclude,
    FindGameResult,
    GameFactsResult,
    GamesLikeResult,
    Lang,
    NewReleasesResult,
    Perspective,
    Platform,
    RecommendResult,
    SearchResult,
    SteamDeck,
    TrendingKind,
    TrendingResult,
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
Params = List[Tuple[str, str]]
Request = Tuple[str, Params]


# ── request building (shared by both clients) ──────────────────────────────


def _check_n(n: int, maximum: int) -> str:
    if not 1 <= n <= maximum:
        raise ValueError(f"n must be between 1 and {maximum}")
    return str(n)


def _flag(value: bool) -> str:
    return "true" if value else "false"


def _coop_value(coop: Coop) -> Optional[str]:
    if coop is False:
        return None
    if coop is True:
        return "true"
    if coop in ("online", "local"):
        return cast(str, coop)
    raise ValueError("coop must be True, False, 'online' or 'local'")


def _common_filters(
    params: Params, free: bool, coop: Coop, steam_deck: Optional[SteamDeck]
) -> None:
    if free:
        params.append(("free", "true"))
    coop_value = _coop_value(coop)
    if coop_value is not None:
        params.append(("coop", coop_value))
    if steam_deck is not None:
        params.append(("deck", steam_deck))


def _games_like_request(
    game: str, n: int, lang: Lang, free: bool, coop: Coop, steam_deck: Optional[SteamDeck]
) -> Request:
    params: Params = [("q", game), ("n", _check_n(n, 20)), ("lang", lang)]
    _common_filters(params, free, coop, steam_deck)
    return "/api/agent/games-like", params


def _game_facts_request(game: str, lang: Lang) -> Request:
    return "/api/agent/game-facts", [("q", game), ("lang", lang)]


def _recommend_request(
    seeds: Sequence[str],
    *,
    n: int,
    lang: Lang,
    liked: Sequence[str],
    disliked: Sequence[str],
    preferences: Optional[str],
    free: bool,
    coop: Coop,
    steam_deck: Optional[SteamDeck],
    exclude: Sequence[Exclude],
    exclude_tags: Sequence[str],
    year_min: Optional[int],
    year_max: Optional[int],
    upcoming: bool,
    popularity_bias: float,
) -> Request:
    if isinstance(seeds, str):
        seeds = [seeds]
    if not seeds and not liked:
        raise ValueError("give at least one seed game (or liked games)")
    if len(seeds) > 3:
        raise ValueError("at most 3 seeds; pass more games as liked=")
    if not -1.0 <= popularity_bias <= 1.0:
        raise ValueError("popularity_bias must be between -1 and 1")
    params: Params = [("seed", s) for s in seeds]
    params += [("n", _check_n(n, 24)), ("lang", lang)]
    _common_filters(params, free, coop, steam_deck)
    params += [("exclude", e) for e in exclude]
    params += [("exclude_tags", t) for t in exclude_tags]
    params += [("liked", g) for g in liked]
    params += [("disliked", g) for g in disliked]
    if preferences:
        params.append(("preferences", preferences))
    if year_min is not None:
        params.append(("year_min", str(year_min)))
    if year_max is not None:
        params.append(("year_max", str(year_max)))
    if upcoming:
        params.append(("upcoming", "true"))
    if popularity_bias:
        params.append(("popularity_bias", str(popularity_bias)))
    return "/api/agent/recommend", params


def _trending_request(kind: TrendingKind, n: int, lang: Lang) -> Request:
    if kind not in ("rising", "breakouts"):
        raise ValueError("kind must be 'rising' or 'breakouts'")
    return "/api/agent/trending", [("kind", kind), ("n", _check_n(n, 20)), ("lang", lang)]


def _new_releases_request(upcoming: bool, coop: bool, n: int, lang: Lang) -> Request:
    params: Params = [("n", _check_n(n, 20)), ("lang", lang)]
    if upcoming:
        params.append(("upcoming", _flag(upcoming)))
    if coop:
        params.append(("coop", _flag(coop)))
    return "/api/agent/new-releases", params


def _search_request(query: str, n: int) -> Request:
    if len(query.strip()) < 2:
        raise ValueError("query must be at least 2 characters")
    return "/api/agent/search", [("q", query), ("n", _check_n(n, 10))]


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


def _tool_call(name: str, arguments: Optional[Mapping[str, Any]]) -> Dict[str, Any]:
    return _rpc("tools/call", {"name": name, "arguments": dict(arguments or {})})


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


def _timeout(timeout: Optional[float]) -> Any:
    return timeout if timeout is not None else httpx.USE_CLIENT_DEFAULT


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

    def __enter__(self) -> ImhoClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        if self._owns_client:
            self._http.close()

    def _get(self, request: Request) -> Dict[str, Any]:
        path, params = request
        return _raise_for_rest(self._http.get(path, params=tuple(params)))

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
        req = _games_like_request(game, n, lang, free, coop, steam_deck)
        return cast(GamesLikeResult, self._get(req))

    def recommend(
        self,
        seeds: Sequence[str],
        *,
        n: int = 10,
        lang: Lang = "en",
        liked: Sequence[str] = (),
        disliked: Sequence[str] = (),
        preferences: Optional[str] = None,
        free: bool = False,
        coop: Coop = False,
        steam_deck: Optional[SteamDeck] = None,
        exclude: Sequence[Exclude] = (),
        exclude_tags: Sequence[str] = (),
        year_min: Optional[int] = None,
        year_max: Optional[int] = None,
        upcoming: bool = False,
        popularity_bias: float = 0.0,
    ) -> RecommendResult:
        """Games for someone who likes 1-3 ``seeds``, with the full filter set.

        ``preferences`` is free text ("cozy base building, no horror") read as
        Steam tags. ``disliked`` games are never recommended.
        """
        req = _recommend_request(
            seeds,
            n=n,
            lang=lang,
            liked=liked,
            disliked=disliked,
            preferences=preferences,
            free=free,
            coop=coop,
            steam_deck=steam_deck,
            exclude=exclude,
            exclude_tags=exclude_tags,
            year_min=year_min,
            year_max=year_max,
            upcoming=upcoming,
            popularity_bias=popularity_bias,
        )
        return cast(RecommendResult, self._get(req))

    def game_facts(self, game: str, *, lang: Lang = "en") -> GameFactsResult:
        """Public facts about one Steam game."""
        return cast(GameFactsResult, self._get(_game_facts_request(game, lang)))

    def trending(
        self, *, kind: TrendingKind = "rising", n: int = 10, lang: Lang = "en"
    ) -> TrendingResult:
        """Steam games trending now: ``rising`` (established) or ``breakouts`` (new)."""
        return cast(TrendingResult, self._get(_trending_request(kind, n, lang)))

    def new_releases(
        self, *, upcoming: bool = False, coop: bool = False, n: int = 10, lang: Lang = "en"
    ) -> NewReleasesResult:
        """Well-rated Steam releases of the last 30 days, or dated upcoming games."""
        req = _new_releases_request(upcoming, coop, n, lang)
        return cast(NewReleasesResult, self._get(req))

    def search_games(self, query: str, *, n: int = 5) -> SearchResult:
        """Steam games by title (typos, partial and Russian names are fine)."""
        return cast(SearchResult, self._get(_search_request(query, n)))

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
        resp = self._http.post(
            "/mcp",
            json=_tool_call(name, arguments),
            headers=_MCP_HEADERS,
            timeout=_timeout(timeout),
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

    async def __aenter__(self) -> AsyncImhoClient:
        return self

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        if self._owns_client:
            await self._http.aclose()

    async def _get(self, request: Request) -> Dict[str, Any]:
        path, params = request
        return _raise_for_rest(await self._http.get(path, params=tuple(params)))

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
        req = _games_like_request(game, n, lang, free, coop, steam_deck)
        return cast(GamesLikeResult, await self._get(req))

    async def recommend(
        self,
        seeds: Sequence[str],
        *,
        n: int = 10,
        lang: Lang = "en",
        liked: Sequence[str] = (),
        disliked: Sequence[str] = (),
        preferences: Optional[str] = None,
        free: bool = False,
        coop: Coop = False,
        steam_deck: Optional[SteamDeck] = None,
        exclude: Sequence[Exclude] = (),
        exclude_tags: Sequence[str] = (),
        year_min: Optional[int] = None,
        year_max: Optional[int] = None,
        upcoming: bool = False,
        popularity_bias: float = 0.0,
    ) -> RecommendResult:
        req = _recommend_request(
            seeds,
            n=n,
            lang=lang,
            liked=liked,
            disliked=disliked,
            preferences=preferences,
            free=free,
            coop=coop,
            steam_deck=steam_deck,
            exclude=exclude,
            exclude_tags=exclude_tags,
            year_min=year_min,
            year_max=year_max,
            upcoming=upcoming,
            popularity_bias=popularity_bias,
        )
        return cast(RecommendResult, await self._get(req))

    async def game_facts(self, game: str, *, lang: Lang = "en") -> GameFactsResult:
        return cast(GameFactsResult, await self._get(_game_facts_request(game, lang)))

    async def trending(
        self, *, kind: TrendingKind = "rising", n: int = 10, lang: Lang = "en"
    ) -> TrendingResult:
        return cast(TrendingResult, await self._get(_trending_request(kind, n, lang)))

    async def new_releases(
        self, *, upcoming: bool = False, coop: bool = False, n: int = 10, lang: Lang = "en"
    ) -> NewReleasesResult:
        req = _new_releases_request(upcoming, coop, n, lang)
        return cast(NewReleasesResult, await self._get(req))

    async def search_games(self, query: str, *, n: int = 5) -> SearchResult:
        return cast(SearchResult, await self._get(_search_request(query, n)))

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
        resp = await self._http.post(
            "/mcp",
            json=_tool_call(name, arguments),
            headers=_MCP_HEADERS,
            timeout=_timeout(timeout),
        )
        return _tool_payload(_rpc_result(resp))

    async def list_tools(self) -> List[Dict[str, Any]]:
        resp = await self._http.post("/mcp", json=_rpc("tools/list"), headers=_MCP_HEADERS)
        return cast(List[Dict[str, Any]], _rpc_result(resp).get("tools", []))


__all__ = ["DEFAULT_BASE_URL", "USER_AGENT", "AsyncImhoClient", "ImhoClient"]
