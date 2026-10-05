"""Response shapes of the imho.run agent API.

These are ``TypedDict``s: the client returns the decoded JSON as plain dicts,
and the types only describe them. Keys can be added on the server side at any
time, so code should ignore keys it does not know. Every key here is optional
(``total=False``) because some are omitted when the value is unknown.
"""

from __future__ import annotations

from typing import List, Literal, Optional, TypedDict

Lang = Literal["en", "ru"]
SteamDeck = Literal["verified", "playable"]
CoopMode = Literal["online", "local"]
Platform = Literal["pc", "playstation", "xbox", "nintendo", "sega", "mobile", "browser", "arcade"]
Perspective = Literal["first", "third", "top_down", "side"]


class Price(TypedDict, total=False):
    is_free: bool
    amount: Optional[float]
    currency: Optional[str]
    text: str


class Reviews(TypedDict, total=False):
    total: int
    positive_pct: Optional[int]


class GameRef(TypedDict, total=False):
    appid: int
    name: str
    url: str
    steam_url: str


class Filters(TypedDict, total=False):
    free: bool
    coop: bool
    coop_mode: Optional[CoopMode]
    deck: Optional[SteamDeck]


class Recommendation(TypedDict, total=False):
    rank: int
    appid: int
    name: str
    url: str
    steam_url: str
    why: str
    year: Optional[int]
    price: Price
    steam_deck: Optional[str]
    reviews: Reviews
    genres: List[str]


class GamesLikeResult(TypedDict, total=False):
    query: str
    source: str
    attribution: str
    seed: GameRef
    other_matches: List[GameRef]
    lang: Lang
    filters: Filters
    list_url: str
    results: List[Recommendation]
    generated_at: str


class FactsSummary(TypedDict, total=False):
    tagline: Optional[str]
    difficulty: Optional[str]
    length: Optional[str]
    session_shape: Optional[str]
    co_op: Optional[str]
    hooks: List[str]
    dealbreakers: List[str]
    language: str


class CoopViaMod(TypedDict, total=False):
    mod_name: str
    mod_url: str
    scope: str
    scope_text: str
    max_players: Optional[int]
    maturity: str
    status: str
    last_checked: str
    official_coop_is_summon_only: bool
    note: str
    note_lang: str
    caveats: List[str]


class GameFacts(TypedDict, total=False):
    appid: int
    name: str
    url: str
    similar_url: str
    steam_url: str
    year: Optional[int]
    release_date: Optional[str]
    coming_soon: bool
    developers: List[str]
    genres: List[str]
    tags: List[str]
    price: Price
    steam_deck: Optional[str]
    reviews: Reviews
    description: Optional[str]
    description_lang: str
    summary: FactsSummary
    coop_via_mod: CoopViaMod


class GameFactsResult(TypedDict, total=False):
    query: str
    source: str
    attribution: str
    lang: Lang
    game: GameFacts
    other_matches: List[GameRef]
    generated_at: str


class FoundGame(TypedDict, total=False):
    rank: int
    name: str
    year: Optional[int]
    platforms: List[str]
    why: str
    summary: Optional[str]
    steam_appid: Optional[int]
    url: Optional[str]
    steam_url: Optional[str]
    igdb_url: Optional[str]


class FindGameResult(TypedDict, total=False):
    source: str
    attribution: str
    lang: Lang
    confidence: str
    results: List[FoundGame]
    tool_url: str
    find_game_url: str


__all__ = [
    "CoopMode",
    "CoopViaMod",
    "FactsSummary",
    "Filters",
    "FindGameResult",
    "FoundGame",
    "GameFacts",
    "GameFactsResult",
    "GameRef",
    "GamesLikeResult",
    "Lang",
    "Perspective",
    "Platform",
    "Price",
    "Recommendation",
    "Reviews",
    "SteamDeck",
]
