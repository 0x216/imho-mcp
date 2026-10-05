"""Offline tests: every request goes to an httpx.MockTransport."""

from __future__ import annotations

import json
import os
from typing import Any, Callable, Dict, List

import httpx
import pytest

from imho import (
    AsyncImhoClient,
    BadRequestError,
    ImhoClient,
    NotFoundError,
    RateLimitError,
    ToolError,
)

Handler = Callable[[httpx.Request], httpx.Response]

GAMES_LIKE = {
    "query": "Hollow Knight",
    "source": "imho.run",
    "seed": {"appid": 367520, "name": "Hollow Knight"},
    "results": [
        {
            "rank": 1,
            "appid": 1030300,
            "name": "Hollow Knight: Silksong",
            "why": "Also Metroidvania.",
        }
    ],
}


def make_client(handler: Handler, seen: List[httpx.Request]) -> ImhoClient:
    def record(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return handler(request)

    http = httpx.Client(base_url="https://imho.run", transport=httpx.MockTransport(record))
    return ImhoClient(http_client=http)


def rpc_ok(result: Dict[str, Any]) -> Handler:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "result": result})

    return handler


def test_games_like_builds_query() -> None:
    seen: List[httpx.Request] = []
    client = make_client(lambda r: httpx.Response(200, json=GAMES_LIKE), seen)
    out = client.games_like("Hollow Knight", n=3, coop="online", free=True, steam_deck="verified")
    assert out["results"][0]["name"] == "Hollow Knight: Silksong"
    req = seen[0]
    assert req.url.path == "/api/agent/games-like"
    assert dict(req.url.params) == {
        "q": "Hollow Knight",
        "n": "3",
        "lang": "en",
        "free": "true",
        "coop": "online",
        "deck": "verified",
    }


def test_games_like_defaults_omit_filters() -> None:
    seen: List[httpx.Request] = []
    client = make_client(lambda r: httpx.Response(200, json=GAMES_LIKE), seen)
    client.games_like("367520", coop=True)
    assert dict(seen[0].url.params) == {"q": "367520", "n": "10", "lang": "en", "coop": "true"}


@pytest.mark.parametrize("n", [0, 21])
def test_games_like_rejects_bad_n(n: int) -> None:
    client = make_client(lambda r: httpx.Response(200, json={}), [])
    with pytest.raises(ValueError):
        client.games_like("x", n=n)


def test_recommend_repeats_list_params() -> None:
    seen: List[httpx.Request] = []
    client = make_client(lambda r: httpx.Response(200, json={"results": []}), seen)
    client.recommend(
        ["Stardew Valley", "Terraria"],
        n=5,
        coop="local",
        steam_deck="playable",
        exclude=["pvp", "grind"],
        exclude_tags=["Horror"],
        liked=["Valheim"],
        disliked=["Rust"],
        preferences="cozy farming",
        year_min=2015,
        popularity_bias=-0.5,
    )
    req = seen[0]
    assert req.url.path == "/api/agent/recommend"
    assert req.url.params.get_list("seed") == ["Stardew Valley", "Terraria"]
    assert req.url.params.get_list("exclude") == ["pvp", "grind"]
    assert req.url.params.get_list("exclude_tags") == ["Horror"]
    assert req.url.params.get_list("liked") == ["Valheim"]
    assert req.url.params.get_list("disliked") == ["Rust"]
    assert req.url.params["coop"] == "local"
    assert req.url.params["deck"] == "playable"
    assert req.url.params["preferences"] == "cozy farming"
    assert req.url.params["year_min"] == "2015"
    assert req.url.params["popularity_bias"] == "-0.5"
    assert "year_max" not in req.url.params and "upcoming" not in req.url.params


def test_recommend_single_string_seed_and_defaults() -> None:
    seen: List[httpx.Request] = []
    client = make_client(lambda r: httpx.Response(200, json={"results": []}), seen)
    client.recommend("Hades")
    assert list(seen[0].url.params.multi_items()) == [
        ("seed", "Hades"),
        ("n", "10"),
        ("lang", "en"),
    ]


@pytest.mark.parametrize(
    "kwargs",
    [
        {"seeds": []},
        {"seeds": ["a", "b", "c", "d"]},
        {"seeds": ["a"], "n": 25},
        {"seeds": ["a"], "popularity_bias": 2.0},
    ],
)
def test_recommend_rejects_bad_input(kwargs: Dict[str, Any]) -> None:
    client = make_client(lambda r: httpx.Response(200, json={}), [])
    with pytest.raises(ValueError):
        client.recommend(**kwargs)


def test_trending_new_releases_search_paths() -> None:
    seen: List[httpx.Request] = []
    client = make_client(lambda r: httpx.Response(200, json={"results": []}), seen)
    client.trending(kind="breakouts", n=3)
    client.new_releases(upcoming=True, coop=True, n=4, lang="ru")
    client.new_releases()
    client.search_games("hollow kn", n=2)
    got = [(r.url.path, list(r.url.params.multi_items())) for r in seen]
    assert got == [
        ("/api/agent/trending", [("kind", "breakouts"), ("n", "3"), ("lang", "en")]),
        (
            "/api/agent/new-releases",
            [("n", "4"), ("lang", "ru"), ("upcoming", "true"), ("coop", "true")],
        ),
        ("/api/agent/new-releases", [("n", "10"), ("lang", "en")]),
        ("/api/agent/search", [("q", "hollow kn"), ("n", "2")]),
    ]


@pytest.mark.parametrize(
    "call",
    [
        lambda c: c.trending(kind="hot"),
        lambda c: c.trending(n=21),
        lambda c: c.search_games("x"),
        lambda c: c.search_games("hades", n=11),
    ],
)
def test_list_tools_reject_bad_input(call: Callable[[ImhoClient], Any]) -> None:
    client = make_client(lambda r: httpx.Response(200, json={}), [])
    with pytest.raises(ValueError):
        call(client)


def test_game_facts_not_found() -> None:
    body = {"source": "imho.run", "error": "not_found", "detail": "No Steam game matched 'zz'."}
    client = make_client(lambda r: httpx.Response(404, json=body), [])
    with pytest.raises(NotFoundError) as exc:
        client.game_facts("zz")
    assert exc.value.code == "not_found"
    assert exc.value.status == 404
    assert "zz" in exc.value.detail


def test_rate_limit_reads_retry_after() -> None:
    body = {"error": "rate_limited", "detail": "Too many requests. Retry after 17s."}
    client = make_client(
        lambda r: httpx.Response(429, json=body, headers={"Retry-After": "17"}), []
    )
    with pytest.raises(RateLimitError) as exc:
        client.games_like("Hades")
    assert exc.value.retry_after == 17.0


def test_validation_error_is_bad_request() -> None:
    body = {"detail": [{"loc": ["query", "q"], "msg": "too short"}]}
    client = make_client(lambda r: httpx.Response(422, json=body), [])
    with pytest.raises(BadRequestError):
        client.game_facts("")


def test_find_game_uses_mcp_tool_call() -> None:
    payload = {"confidence": "high", "results": [{"rank": 1, "name": "Stray"}]}
    seen: List[httpx.Request] = []
    client = make_client(
        rpc_ok({"content": [], "structuredContent": payload, "isError": False}), seen
    )
    out = client.find_game_by_description(
        "you play a cat in a cyberpunk city", platform="pc", year_min=2020
    )
    assert out["results"][0]["name"] == "Stray"
    req = seen[0]
    assert req.method == "POST" and req.url.path == "/mcp"
    body = json.loads(req.content)
    assert body["method"] == "tools/call"
    assert body["params"] == {
        "name": "find_game_by_description",
        "arguments": {
            "description": "you play a cat in a cyberpunk city",
            "lang": "en",
            "platform": "pc",
            "year_min": 2020,
        },
    }
    assert "application/json" in req.headers["accept"]


def test_tool_text_fallback_when_no_structured_content() -> None:
    text = json.dumps({"results": [{"name": "Stray"}]})
    client = make_client(
        rpc_ok({"content": [{"type": "text", "text": text}], "isError": False}), []
    )
    assert client.call_tool("anything")["results"][0]["name"] == "Stray"


@pytest.mark.parametrize(
    "text,exc_type",
    [
        ("Too many requests. Retry after 42s, or open https://imho.run directly.", RateLimitError),
        ("No Steam game matched 'zz'. Try the exact title or an appid.", NotFoundError),
        ("Internal error; try again later.", ToolError),
    ],
)
def test_tool_errors(text: str, exc_type: type) -> None:
    client = make_client(rpc_ok({"content": [{"type": "text", "text": text}], "isError": True}), [])
    with pytest.raises(exc_type) as exc:
        client.call_tool("game_facts", {"game": "zz"})
    if exc_type is RateLimitError:
        assert exc.value.retry_after == 42.0  # type: ignore[attr-defined]


def test_unknown_tool_is_bad_request() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        err = {"code": -32602, "message": "Unknown tool: nope"}
        return httpx.Response(200, json={"jsonrpc": "2.0", "id": body["id"], "error": err})

    client = make_client(handler, [])
    with pytest.raises(BadRequestError, match="Unknown tool"):
        client.call_tool("nope")


def test_list_tools() -> None:
    client = make_client(rpc_ok({"tools": [{"name": "games_like"}]}), [])
    assert [t["name"] for t in client.list_tools()] == ["games_like"]


def test_default_client_sends_user_agent() -> None:
    client = ImhoClient()
    try:
        assert client._http.headers["user-agent"].startswith("imho-python/")
        assert str(client._http.base_url).rstrip("/") == "https://imho.run"
    finally:
        client.close()


async def test_async_games_like() -> None:
    seen: List[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json=GAMES_LIKE)

    http = httpx.AsyncClient(base_url="https://imho.run", transport=httpx.MockTransport(handler))
    async with AsyncImhoClient(http_client=http) as imho:
        out = await imho.games_like("Hollow Knight", n=1)
    await http.aclose()
    assert out["seed"]["appid"] == 367520
    assert seen[0].url.params["n"] == "1"


live = pytest.mark.skipif(os.environ.get("IMHO_LIVE") != "1", reason="set IMHO_LIVE=1")


@pytest.mark.live
@live
def test_live_games_like_and_facts() -> None:
    with ImhoClient() as imho:
        picks = imho.games_like("Hollow Knight", n=3)
        assert picks["seed"]["appid"] == 367520
        assert 1 <= len(picks["results"]) <= 3
        facts = imho.game_facts("1145360")
        assert facts["game"]["name"] == "Hades"
        with pytest.raises(NotFoundError):
            imho.game_facts("zzzzqqqxx")
        recs = imho.recommend(["Stardew Valley", "Terraria"], n=3, coop=True)
        assert [s["appid"] for s in recs["seeds"]] == [413150, 105600]
        assert recs["results"] and all(p.get("why") for p in recs["results"])


@pytest.mark.live
@live
def test_live_discovery_tools() -> None:
    with ImhoClient() as imho:
        trending = imho.trending(n=3)
        assert trending["status"] in ("ready", "collecting")
        assert len(trending["results"]) <= 3
        releases = imho.new_releases(n=3)
        assert releases["kind"] == "released"
        hits = imho.search_games("hollow knight", n=3)["results"]
        assert any(h["appid"] == 367520 for h in hits)
