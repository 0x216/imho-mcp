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
Exclude = Literal["pvp", "microtransactions", "hard", "grind", "early_access", "vr_only"]
TrendingKind = Literal["rising", "breakouts"]


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


# ── recommend ──────────────────────────────────────────────────────────────


class RecommendQuery(TypedDict, total=False):
    seeds: List[str]
    preferences: Optional[str]
    liked: List[str]
    disliked: List[str]


class RecommendFilters(TypedDict, total=False):
    free: bool
    coop: bool
    coop_mode: Optional[str]
    deck: Optional[SteamDeck]
    exclude: List[str]
    exclude_tags: List[str]
    year_min: Optional[int]
    year_max: Optional[int]
    popularity_bias: float


class PreferencesRead(TypedDict, total=False):
    """How the ``preferences`` text was read."""

    applied: bool
    prefer_tags: List[str]
    avoid_tags: List[str]
    filters: List[str]
    unmatched: List[str]
    suggestions: List[str]


class RecommendPick(Recommendation, total=False):
    similar_to: Optional[int]
    """Appid of the seed this pick is closest to."""


class RecommendResult(TypedDict, total=False):
    query: RecommendQuery
    source: str
    attribution: str
    seeds: List[GameRef]
    lang: Lang
    filters: RecommendFilters
    preferred_tags: List[str]
    tool_url: str
    results: List[RecommendPick]
    preferences_applied: bool
    preferences: PreferencesRead
    ignored: List[str]
    generated_at: str


# ── trending / new releases / search ───────────────────────────────────────


class ListPick(TypedDict, total=False):
    rank: int
    appid: int
    name: str
    url: str
    steam_url: str
    year: Optional[int]
    price: Price
    steam_deck: str
    reviews: Optional[Reviews]
    genres: List[str]
    reviews_week: int
    """trending: Steam reviews in the last 7 days."""
    reviews_growth_pct: int
    """trending: weekly reviews vs the game's own 3-week baseline, in %."""
    release_date: str
    """new_releases: Steam release date."""


class TrendingResult(TypedDict, total=False):
    source: str
    attribution: str
    lang: Lang
    kind: TrendingKind
    status: Literal["ready", "collecting"]
    """``collecting``: the lists are not ready yet and ``results`` is empty."""
    updated_at: Optional[str]
    page_url: str
    results: List[ListPick]


class NewReleasesResult(TypedDict, total=False):
    source: str
    attribution: str
    lang: Lang
    kind: Literal["released", "upcoming"]
    coop: bool
    page_url: str
    results: List[ListPick]


class SearchHit(TypedDict, total=False):
    appid: int
    name: str
    year: Optional[int]
    url: str
    steam_url: str


class SearchResult(TypedDict, total=False):
    query: str
    source: str
    results: List[SearchHit]


__all__ = [
    "CoopMode",
    "CoopViaMod",
    "Exclude",
    "FactsSummary",
    "Filters",
    "FindGameResult",
    "FoundGame",
    "GameFacts",
    "GameFactsResult",
    "GameRef",
    "GamesLikeResult",
    "Lang",
    "ListPick",
    "NewReleasesResult",
    "Perspective",
    "Platform",
    "PreferencesRead",
    "Price",
    "RecommendFilters",
    "RecommendPick",
    "RecommendQuery",
    "RecommendResult",
    "Recommendation",
    "Reviews",
    "SearchHit",
    "SearchResult",
    "SteamDeck",
    "TrendingKind",
    "TrendingResult",
]
