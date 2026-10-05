"""Find a forgotten game by description: a Gradio Space over imho.run's MCP server.

A thin client. Every search goes to the public, stateless MCP endpoint
https://imho.run/mcp (JSON-RPC over HTTP, no key). No model runs here.

Rate limits: imho.run allows `find_game_by_description` 3 calls a minute and
20 a day per IP. Everyone using this Space shares the Space's outbound IP, so
the app keeps a cache, serves the examples from `examples.json` without a
call, mirrors the shared quota locally and caps each visitor's live searches.
"""

from __future__ import annotations

import hashlib
import html
import json
import os
import re
import threading
import time
import unicodedata
from functools import lru_cache
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import gradio as gr
import httpx

MCP_URL = os.environ.get("IMHO_MCP_URL", "https://imho.run/mcp")
# The same server without the imho.run front end in between; tried when the
# main URL fails before reaching it (5xx or no connection).
MCP_FALLBACK_URL = os.environ.get("IMHO_MCP_FALLBACK_URL", "https://api.imho.run/api/agent/mcp")
SITE = "https://imho.run"
USER_AGENT = "imho-hf-space/1.0 (+https://github.com/0x216/imho-mcp/tree/main/examples/hf-space)"
UTM = {"utm_source": "huggingface", "utm_medium": "space"}
FIND_TIMEOUT_S = float(os.environ.get("IMHO_FIND_TIMEOUT_S", "60"))
LIKE_TIMEOUT_S = float(os.environ.get("IMHO_LIKE_TIMEOUT_S", "30"))

# Mirrors of imho.run's per-IP limits for find_game_by_description. Raise them
# only if imho.run gives this Space its own bucket.
FIND_PER_MINUTE = int(os.environ.get("IMHO_FIND_PER_MINUTE", "3"))
FIND_PER_DAY = int(os.environ.get("IMHO_FIND_PER_DAY", "20"))
# Live (uncached) searches one visitor may spend per UTC day, so a single
# visitor can't use up everyone's share.
FIND_PER_VISITOR_DAY = int(os.environ.get("IMHO_FIND_PER_VISITOR_DAY", "3"))

# Optional, for a future dedicated bucket on imho.run (see README). Unused by
# imho.run today; sent only when the Space secret is set. Never logged.
PARTNER_KEY = os.environ.get("IMHO_PARTNER_KEY", "").strip()
VISITOR_SALT = os.environ.get("IMHO_VISITOR_SALT", "") or os.urandom(16).hex()

EXAMPLES_FILE = Path(__file__).with_name("examples.json")

FIND_EXAMPLES = [
    "Flash game where you launch a turtle out of a cannon and shoot it with guns to keep it flying",
    "PS2 game: a boy with horns escapes a huge castle while holding hands with a glowing princess",
    "Old PC strategy game where you are the evil one: you dig a dungeon, slap your imps and heroes invade",
    "Racing game with tiny toy cars on a breakfast table, a pool table and a school desk",
    "Side-scroller where you are an earthworm in a robotic space suit and use your own head as a whip",
    "Игра на PS1: маленький фиолетовый дракончик собирает кристаллы и освобождает других драконов",
]
LIKE_EXAMPLES = ["Hollow Knight", "Stardew Valley", "Disco Elysium", "Into the Breach", "Outer Wilds"]

PLATFORMS = {
    "Any platform": None,
    "PC": "pc",
    "PlayStation": "playstation",
    "Xbox": "xbox",
    "Nintendo": "nintendo",
    "Sega": "sega",
    "Mobile": "mobile",
    "Browser / Flash": "browser",
    "Arcade": "arcade",
}


# ── Errors ──────────────────────────────────────────────────────────────────
class ImhoError(Exception):
    """Base class; `str(exc)` is safe to show."""


class RateLimited(ImhoError):
    def __init__(self, retry_after: int, scope: str) -> None:
        super().__init__(f"rate limited ({scope}), retry after {retry_after}s")
        self.retry_after = max(1, int(retry_after))
        self.scope = scope  # "minute", "day" or "visitor"


class Busy(ImhoError):
    pass


class BadInput(ImhoError):
    pass


class NotFound(ImhoError):
    pass


# ── MCP client ──────────────────────────────────────────────────────────────
_RATE_RE = re.compile(r"too many requests\. retry after (\d+)s", re.IGNORECASE)
_http = httpx.Client(
    headers={"User-Agent": USER_AGENT, "Accept": "application/json"},
    follow_redirects=True,
)
_rpc_id = 0
_rpc_lock = threading.Lock()


def call_tool(name: str, arguments: dict[str, Any], *, timeout: float, visitor: str = "") -> dict:
    """One `tools/call` against imho.run's MCP server; returns structuredContent."""
    global _rpc_id
    with _rpc_lock:
        _rpc_id += 1
        msg_id = _rpc_id
    headers = {}
    if PARTNER_KEY:
        headers["X-Imho-Partner-Key"] = PARTNER_KEY
        if visitor:
            headers["X-Imho-End-User"] = visitor
    body = {
        "jsonrpc": "2.0",
        "id": msg_id,
        "method": "tools/call",
        "params": {"name": name, "arguments": arguments},
    }
    resp = None
    for url in dict.fromkeys(u for u in (MCP_URL, MCP_FALLBACK_URL) if u):
        try:
            resp = _http.post(url, json=body, headers=headers, timeout=timeout)
        except httpx.TimeoutException as exc:
            # The server may still be working on it: don't send it twice.
            raise Busy("imho.run took too long to answer") from exc
        except httpx.HTTPError:
            continue
        if resp.status_code < 500:
            break
    if resp is None:
        raise Busy("could not reach imho.run")
    if resp.status_code == 429:
        raise RateLimited(int(resp.headers.get("retry-after") or 60), "minute")
    if resp.status_code >= 500:
        raise Busy(f"imho.run answered HTTP {resp.status_code}")
    try:
        data = resp.json()
    except ValueError as exc:
        raise Busy("imho.run sent an unreadable answer") from exc
    if "error" in data:
        raise BadInput(str(data["error"].get("message") or "bad request"))
    result = data.get("result") or {}
    if result.get("isError"):
        text = " ".join(c.get("text", "") for c in result.get("content") or [])
        m = _RATE_RE.search(text)
        if m:
            wait = int(m.group(1))
            raise RateLimited(wait, "day" if wait > 120 else "minute")
        low = text.lower()
        if "busy" in low or "internal error" in low or "switched off" in low:
            raise Busy(text)
        if "no steam game matched" in low:
            raise NotFound(text)
        raise BadInput(text or "imho.run could not run this search")
    payload = result.get("structuredContent")
    if payload is None:  # older servers: JSON in the text block
        payload = json.loads(result["content"][0]["text"])
    return payload


# ── Shared quota (mirror of imho.run's fixed windows) ───────────────────────
class SharedQuota:
    """Fixed windows aligned like the server's: minute slots and UTC days."""

    def __init__(self, per_minute: int, per_day: int, per_visitor_day: int) -> None:
        self.per_minute = per_minute
        self.per_day = per_day
        self.per_visitor_day = per_visitor_day
        self._lock = threading.Lock()
        self._minute = (-1, 0)
        self._day = (-1, 0)
        self._visitors: dict[str, int] = {}
        self._blocked_until = 0.0

    def take(self, visitor: str, now: float | None = None) -> None:
        t = time.time() if now is None else now
        minute, day = int(t // 60), int(t // 86400)
        with self._lock:
            if t < self._blocked_until:
                wait = int(self._blocked_until - t) + 1
                raise RateLimited(wait, "day" if wait > 120 else "minute")
            if self._day[0] != day:
                self._day, self._visitors = (day, 0), {}
            if self._minute[0] != minute:
                self._minute = (minute, 0)
            if self._visitors.get(visitor, 0) >= self.per_visitor_day:
                raise RateLimited(86400 - int(t % 86400), "visitor")
            if self._day[1] >= self.per_day:
                raise RateLimited(86400 - int(t % 86400), "day")
            if self._minute[1] >= self.per_minute:
                raise RateLimited(60 - int(t % 60), "minute")
            self._minute = (minute, self._minute[1] + 1)
            self._day = (day, self._day[1] + 1)
            self._visitors[visitor] = self._visitors.get(visitor, 0) + 1

    def refund(self, visitor: str) -> None:
        """A call that never reached the limiter (network error) is given back."""
        with self._lock:
            self._minute = (self._minute[0], max(0, self._minute[1] - 1))
            self._day = (self._day[0], max(0, self._day[1] - 1))
            if self._visitors.get(visitor):
                self._visitors[visitor] -= 1

    def block(self, seconds: int) -> None:
        """The server said no: stop sending until its window resets."""
        with self._lock:
            self._blocked_until = max(self._blocked_until, time.time() + seconds)

    def left_today(self, now: float | None = None) -> int:
        t = time.time() if now is None else now
        with self._lock:
            used = self._day[1] if self._day[0] == int(t // 86400) else 0
            if t < self._blocked_until and self._blocked_until - t > 120:
                return 0
            return max(0, self.per_day - used)


quota = SharedQuota(FIND_PER_MINUTE, FIND_PER_DAY, FIND_PER_VISITOR_DAY)
_ctx = threading.local()


def normalize(text: str) -> str:
    return re.sub(r"\s+", " ", unicodedata.normalize("NFKC", text or "")).strip()


def detect_lang(text: str) -> str:
    cyr = sum(1 for ch in text if "Ѐ" <= ch <= "ӿ")
    lat = sum(1 for ch in text if ch.isascii() and ch.isalpha())
    return "ru" if cyr > lat else "en"


def _load_examples() -> dict[str, dict]:
    try:
        raw = json.loads(EXAMPLES_FILE.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {normalize(k): v for k, v in raw.items() if isinstance(v, dict)}


BAKED = _load_examples()


@lru_cache(maxsize=1024)
def _find_cached(
    description: str, lang: str, platform: str | None, year_min: int | None, year_max: int | None
) -> dict:
    # Only runs on a cache miss: this is where a live search spends quota.
    visitor = getattr(_ctx, "visitor", "anon")
    quota.take(visitor)
    args: dict[str, Any] = {"description": description, "lang": lang}
    if platform:
        args["platform"] = platform
    if year_min:
        args["year_min"] = year_min
    if year_max:
        args["year_max"] = year_max
    try:
        return call_tool("find_game_by_description", args, timeout=FIND_TIMEOUT_S, visitor=visitor)
    except RateLimited as exc:
        quota.block(exc.retry_after)
        raise
    except Busy:
        quota.refund(visitor)
        raise


@lru_cache(maxsize=1024)
def _like_cached(game: str, lang: str, free: bool, coop: bool) -> dict:
    args: dict[str, Any] = {"game": game, "n": 10, "lang": lang}
    if free:
        args["free"] = True
    if coop:
        args["coop"] = True
    return call_tool("games_like", args, timeout=LIKE_TIMEOUT_S)


@lru_cache(maxsize=1024)
def _search_cached(query: str) -> dict:
    return call_tool("search_games", {"query": query[:100], "n": 5}, timeout=LIKE_TIMEOUT_S)


def visitor_id(request: gr.Request | None) -> str:
    """A salted hash of the visitor's IP: kept in memory, never logged."""
    ip = ""
    if request is not None:
        fwd = (request.headers or {}).get("x-forwarded-for", "")
        ip = fwd.split(",")[0].strip() or (request.client.host if request.client else "")
    return hashlib.sha256(f"{VISITOR_SALT}|{ip}".encode()).hexdigest()[:16]


# ── Rendering ───────────────────────────────────────────────────────────────
def with_utm(url: str | None, campaign: str) -> str | None:
    """Our UTM tags on imho.run links (other hosts are left alone)."""
    if not url:
        return url
    parts = urlsplit(url)
    if not parts.netloc.endswith("imho.run"):
        return url
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.startswith("utm_")]
    query += [*UTM.items(), ("utm_campaign", campaign)]
    return urlunsplit(parts._replace(query=urlencode(query)))


def _e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def _link(url: str | None, text: str, cls: str = "") -> str:
    if not url:
        return ""
    return f'<a class="{cls}" href="{_e(url)}" target="_blank" rel="noopener">{_e(text)}</a>'


def _clip(text: str | None, n: int) -> str:
    text = (text or "").strip()
    return text if len(text) <= n else text[: n - 1].rstrip() + "…"


CONFIDENCE = {
    "en": {"high": "High confidence", "medium": "Medium confidence", "low": "Low confidence"},
    "ru": {"high": "Высокая уверенность", "medium": "Средняя уверенность", "low": "Низкая уверенность"},
}
T = {
    "en": {
        "open": "Open on imho.run",
        "refine": "Not it? Refine the search on imho.run",
        "none": "No match this time. Add details: platform, rough year, camera, a character or a level you remember.",
        "credit": "Results by",
    },
    "ru": {
        "open": "Открыть на imho.run",
        "refine": "Не то? Уточните поиск на imho.run",
        "none": "Ничего не нашлось. Добавьте детали: платформу, примерный год, вид камеры, персонажа или уровень.",
        "credit": "Результаты:",
    },
}


def render_find(payload: dict, lang: str) -> str:
    t = T.get(lang, T["en"])
    conf = (payload.get("confidence") or "").lower()
    parts = ['<div class="imho-results">']
    if conf in CONFIDENCE["en"]:
        label = CONFIDENCE.get(lang, CONFIDENCE["en"])[conf]
        parts.append(f'<div class="imho-conf imho-conf-{conf}">{_e(label)}</div>')
    results = payload.get("results") or []
    if not results:
        parts.append(f'<p class="imho-note">{_e(t["none"])}</p>')
    for item in results:
        imho_url = with_utm(item.get("url"), "find_game")
        primary = imho_url or item.get("steam_url") or item.get("igdb_url")
        meta = [str(item["year"])] if item.get("year") else []
        meta += [str(p) for p in (item.get("platforms") or [])[:4]]
        why = item.get("why") or _clip(item.get("summary"), 220)
        links = [
            _link(imho_url, t["open"], "imho-btn"),
            _link(item.get("steam_url"), "Steam"),
            _link(item.get("igdb_url"), "IGDB"),
        ]
        title = _link(primary, item.get("name") or "?") if primary else _e(item.get("name") or "?")
        parts.append(
            '<div class="imho-card">'
            f'<div class="imho-rank">{_e(item.get("rank", ""))}</div>'
            '<div class="imho-body">'
            f'<div class="imho-title">{title}</div>'
            f'<div class="imho-meta">{_e(" · ".join(meta))}</div>'
            f'<div class="imho-why">{_e(why or "")}</div>'
            f'<div class="imho-links">{" ".join(x for x in links if x)}</div>'
            "</div></div>"
        )
    refine = with_utm(payload.get("find_game_url") or payload.get("tool_url"), "find_game")
    if refine:
        parts.append(f'<p class="imho-refine">{_link(refine, t["refine"] + " →")}</p>')
    parts.append(_credit(lang))
    parts.append("</div>")
    return "".join(parts)


def render_like(payload: dict, lang: str) -> str:
    seed = payload.get("seed") or {}
    seed_url = with_utm(seed.get("url"), "games_like")
    head = "Игры, похожие на" if lang == "ru" else "Games like"
    parts = [
        '<div class="imho-results">',
        f'<div class="imho-head">{_e(head)} {_link(seed_url, seed.get("name") or "?")}</div>',
    ]
    others = payload.get("other_matches") or []
    if others:
        if lang == "ru":
            label, hint = "Имелась в виду другая игра?", "введите точное название."
        else:
            label, hint = "Meant another game?", "type its exact title."
        names = ", ".join(_e(o.get("name", "")) for o in others[:4])
        parts.append(f'<p class="imho-note">{_e(label)} {names}: {_e(hint)}</p>')
    for item in payload.get("results") or []:
        meta = [str(item["year"])] if item.get("year") else []
        price = (item.get("price") or {}).get("text")
        if (item.get("price") or {}).get("is_free"):
            price = "Free" if lang == "en" else "Бесплатно"
        if price:
            meta.append(price)
        reviews = item.get("reviews") or {}
        if reviews.get("positive_pct") is not None and reviews.get("total"):
            meta.append(f"{reviews['positive_pct']}% of {reviews['total']:,} reviews positive")
        if item.get("steam_deck") in ("verified", "playable"):
            meta.append(f"Steam Deck {item['steam_deck']}")
        url = with_utm(item.get("url"), "games_like")
        parts.append(
            '<div class="imho-card">'
            f'<div class="imho-rank">{_e(item.get("rank", ""))}</div>'
            '<div class="imho-body">'
            f'<div class="imho-title">{_link(url, item.get("name") or "?")}</div>'
            f'<div class="imho-meta">{_e(" · ".join(meta))}</div>'
            f'<div class="imho-why">{_e(item.get("why") or "")}</div>'
            f'<div class="imho-links">{_link(url, T.get(lang, T["en"])["open"], "imho-btn")} '
            f"{_link(item.get('steam_url'), 'Steam')}</div>"
            "</div></div>"
        )
    full = "Весь список на imho.run" if lang == "ru" else "The full list on imho.run"
    parts.append(
        f'<p class="imho-refine">{_link(with_utm(payload.get("list_url"), "games_like"), full + " →")}</p>'
    )
    parts.append(_credit(lang))
    parts.append("</div>")
    return "".join(parts)


def _credit(lang: str) -> str:
    home = with_utm(SITE + ("/ru" if lang == "ru" else "") + "/find-game", "credit")
    return f'<p class="imho-credit">{_e(T.get(lang, T["en"])["credit"])} {_link(home, "imho.run")}</p>'


def render_error(exc: Exception, lang: str, *, search_url: str | None = None) -> str:
    site = with_utm(search_url or f"{SITE}/find-game", "error")
    direct = _link(site, "imho.run/find-game")
    if isinstance(exc, RateLimited):
        if exc.scope == "visitor":
            msg = (
                f"You've used your {FIND_PER_VISITOR_DAY} live searches for today on this Space "
                "(it shares a small daily quota between all visitors). The examples still work, "
                f"and you can keep searching for free on {direct}."
            )
        elif exc.scope == "day" or exc.retry_after > 120:
            hours = max(1, round(exc.retry_after / 3600))
            msg = (
                "This Space has used today's shared search quota: imho.run allows "
                f"{FIND_PER_DAY} description searches a day per IP, and every visitor here "
                f"shares one IP. It resets in about {hours} h. Search directly on {direct} meanwhile "
                "(no account needed)."
            )
        else:
            msg = (
                f"Too many searches in the last minute (the limit is {FIND_PER_MINUTE} a minute "
                f"for the whole Space). Try again in {exc.retry_after} s, or search on {direct}."
            )
        return f'<div class="imho-error">{msg}</div>'
    if isinstance(exc, Busy):
        return (
            '<div class="imho-error">imho.run is busy right now (the language model behind the '
            f"search can take a while under load). Try again in a minute, or use {direct}.</div>"
        )
    if isinstance(exc, NotFound):
        return f'<div class="imho-error">{_e(exc)}</div>'
    return f'<div class="imho-error">{_e(exc)}</div>'


# ── Handlers ────────────────────────────────────────────────────────────────
def find_game(
    description: str,
    platform_label: str = "Any platform",
    year_from: float | None = None,
    year_to: float | None = None,
    request: gr.Request = None,  # type: ignore[assignment]  # injected by Gradio
) -> tuple[str, str]:
    text = normalize(description)
    lang = detect_lang(text)
    if len(text) < 12:
        return (
            '<div class="imho-error">Describe the game in at least a sentence (12+ characters): '
            "what you did, what you saw, roughly when and where you played it.</div>",
            quota_note(),
        )
    text = text[:3000]
    platform = PLATFORMS.get(platform_label or "", None)
    y_min = int(year_from) if year_from else None
    y_max = int(year_to) if year_to else None
    if y_min and y_max and y_min > y_max:
        y_min, y_max = y_max, y_min

    baked = BAKED.get(text) if not (platform or y_min or y_max) else None
    if baked is not None:
        return render_find(baked, lang), quota_note()
    _ctx.visitor = visitor_id(request)
    try:
        payload = _find_cached(text, lang, platform, y_min, y_max)
    except ImhoError as exc:
        return render_error(exc, lang), quota_note()
    finally:
        _ctx.visitor = "anon"
    return render_find(payload, lang), quota_note()


def games_like(game: str, free: bool = False, coop: bool = False) -> str:
    name = normalize(game)[:200]
    lang = detect_lang(name)
    if not name:
        return '<div class="imho-error">Type a game you like: a Steam title, appid or store link.</div>'
    try:
        payload = _like_cached(name, lang, bool(free), bool(coop))
    except NotFound as exc:
        try:
            hits = _search_cached(name).get("results") or []
        except ImhoError:
            hits = []
        if not hits:
            return render_error(exc, lang)
        items = "".join(
            f"<li>{_link(with_utm(h.get('url'), 'search'), h.get('name') or '?')}"
            f"{' (' + _e(h['year']) + ')' if h.get('year') else ''}</li>"
            for h in hits
        )
        return f'<div class="imho-error">No exact match. Did you mean:<ul>{items}</ul></div>'
    except ImhoError as exc:
        return render_error(exc, lang)
    return render_like(payload, lang)


def quota_note() -> str:
    left = quota.left_today()
    return (
        f"Live searches left today for everyone on this Space: about {left} of {FIND_PER_DAY}. "
        "Repeated questions and the examples are free. "
        f"Unlimited on [imho.run/find-game]({with_utm(SITE + '/find-game', 'quota_note')})."
    )


# ── UI ──────────────────────────────────────────────────────────────────────
CSS = """
.imho-results { display: flex; flex-direction: column; gap: 10px; }
.imho-card { display: flex; gap: 12px; padding: 12px 14px; border-radius: 10px;
  border: 1px solid var(--border-color-primary); background: var(--background-fill-secondary); }
.imho-rank { font-weight: 700; font-size: 1.1em; min-width: 1.6em; color: var(--body-text-color-subdued); }
.imho-body { flex: 1; min-width: 0; }
.imho-title { font-weight: 700; font-size: 1.08em; }
.imho-title a { text-decoration: none; }
.imho-meta { font-size: 0.88em; color: var(--body-text-color-subdued); margin-top: 2px; }
.imho-why { margin-top: 6px; }
.imho-links { margin-top: 8px; font-size: 0.9em; display: flex; gap: 12px; flex-wrap: wrap; }
.imho-btn { font-weight: 600; }
.imho-conf { align-self: flex-start; font-size: 0.85em; font-weight: 600; padding: 2px 10px; border-radius: 999px; }
.imho-conf-high { background: #d9f2df; color: #155724; }
.imho-conf-medium { background: #fff1cc; color: #7a5500; }
.imho-conf-low { background: #f6d8d8; color: #7d1f1f; }
.imho-head { font-size: 1.05em; font-weight: 600; }
.imho-refine { font-weight: 600; margin: 4px 0 0; }
.imho-note, .imho-credit { font-size: 0.88em; color: var(--body-text-color-subdued); margin: 0; }
.imho-error { padding: 12px 14px; border-radius: 10px; border: 1px solid #e0b4b4; background: #fff6f6; color: #5a1a1a; }
.imho-error a { color: inherit; font-weight: 600; }
"""

INTRO = f"""
# Find a forgotten game by description

Describe a game you half-remember: what you did, what you saw, roughly when and on what you
played it. The search runs on [imho.run]({with_utm(SITE + "/find-game", "intro")}), which matches
your description against Steam and IGDB with a retriever trained on solved "what was that game?"
threads, then has a language model check the candidates. English and Russian both work.
"""

LIKE_INTRO = f"""
Name a game you like and get ten games most like it, each with a one-line reason, the US Steam
price and Steam Deck status. From [imho.run]({with_utm(SITE, "intro")}), a Steam game recommender.
"""

FOOTER = f"""
---
This Space is a small client of imho.run's free [MCP server and API]({with_utm(SITE + "/developers", "footer")})
(`https://imho.run/mcp`); the code is in [0x216/imho-mcp](https://github.com/0x216/imho-mcp/tree/main/examples/hf-space).
Descriptions you type are sent to imho.run and handled under its [privacy policy]({SITE}/privacy).
The Space shares one small search quota between all visitors; for unlimited searching use
[imho.run/find-game]({with_utm(SITE + "/find-game", "footer")}).
"""


def build() -> gr.Blocks:
    with gr.Blocks(title="Find a forgotten game") as demo:
        gr.Markdown(INTRO)
        with gr.Tabs():
            with gr.Tab("Find a game by description"):
                desc = gr.Textbox(
                    label="Describe the game you remember",
                    placeholder="e.g. a 2000s PC game where you were a ghost scaring people out of a mansion…",
                    lines=4,
                    max_lines=12,
                )
                with gr.Accordion("Optional: platform and era", open=False):
                    with gr.Row():
                        platform = gr.Dropdown(list(PLATFORMS), value="Any platform", label="Platform")
                        year_from = gr.Number(
                            label="Released after (year)", precision=0, minimum=1970, maximum=2035
                        )
                        year_to = gr.Number(
                            label="Released before (year)", precision=0, minimum=1970, maximum=2035
                        )
                go = gr.Button("Find the game", variant="primary")
                note = gr.Markdown(quota_note())
                out = gr.HTML()
                gr.Examples(
                    examples=[[e] for e in FIND_EXAMPLES],
                    inputs=[desc],
                    outputs=[out, note],
                    fn=find_game,
                    run_on_click=True,
                    cache_examples=False,
                    label="Examples (answered instantly, they don't use the quota)",
                )
                inputs = [desc, platform, year_from, year_to]
                go.click(find_game, inputs, [out, note], concurrency_limit=2)
                desc.submit(find_game, inputs, [out, note], concurrency_limit=2)
            with gr.Tab("Games like X"):
                gr.Markdown(LIKE_INTRO)
                game = gr.Textbox(label="A game you like", placeholder="Hollow Knight")
                with gr.Row():
                    free = gr.Checkbox(label="Free only")
                    coop = gr.Checkbox(label="Co-op only")
                like_go = gr.Button("Show similar games", variant="primary")
                like_out = gr.HTML()
                gr.Examples(
                    examples=[[g] for g in LIKE_EXAMPLES],
                    inputs=[game],
                    outputs=[like_out],
                    fn=games_like,
                    run_on_click=True,
                    cache_examples=False,
                )
                like_go.click(games_like, [game, free, coop], like_out, concurrency_limit=4)
                game.submit(games_like, [game, free, coop], like_out, concurrency_limit=4)
        gr.Markdown(FOOTER)
    return demo


demo = build()

if __name__ == "__main__":
    demo.launch(css=CSS, theme=gr.themes.Soft())
