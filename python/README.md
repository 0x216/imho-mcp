# imho (Python client for imho.run)

A small typed client for the [imho.run](https://imho.run) API for AI assistants:
Steam games like any game you name, facts about one game, and identifying a
game from a description. It wraps the public REST endpoints under
`https://imho.run/api/agent/` and the MCP endpoint `https://imho.run/mcp`.
The API is free, read-only and needs no key.

> **Not on PyPI yet.** Until the first release, install from GitHub:
>
> ```bash
> pip install "git+https://github.com/0x216/imho-mcp#subdirectory=python"
> ```
>
> After the first release this becomes `pip install imho`.

Requires Python 3.9+ and [httpx](https://www.python-httpx.org/).

## Usage

```python
from imho import ImhoClient

with ImhoClient() as imho:
    picks = imho.games_like("Hollow Knight", n=3)
    for game in picks["results"]:
        print(game["rank"], game["name"], "-", game["why"], game["price"]["text"])
```

```
1 Hollow Knight: Silksong - Also Metroidvania and Souls-like, like Hollow Knight. 19.99 USD
2 Ori and the Blind Forest: Definitive Edition - Also Metroidvania, like Hollow Knight. 4.99 USD
3 Nine Sols - Metroidvania with Sekiro-style parry combat and Taoist myth. 14.99 USD
```

(Output from 2026-10-04. Rankings and prices change.)

### games_like

```python
imho.games_like(
    "Stardew Valley",       # name (typos, Russian titles OK), Steam appid or Steam store URL
    n=10,                   # 1..20
    lang="en",              # "en" or "ru": language of the `why` lines
    free=False,             # only free-to-play games
    coop=False,             # True = any co-op, "online" or "local" (same screen / split screen)
    steam_deck=None,        # "verified" or "playable" (playable or better)
)
```

Returns a dict with `seed` (the game that was matched), `other_matches`,
`results` (each with `rank`, `appid`, `name`, `url`, `steam_url`, `why`,
`year`, `price`, `steam_deck`, `reviews`, `genres`), `list_url` and
`attribution`.

### game_facts

```python
facts = imho.game_facts("Hades")["game"]
facts["summary"]["length"], facts["summary"]["difficulty"], facts["steam_deck"]
# ('massive', 'challenging', 'verified')
```

Year, developers, genres, top tags, price, Steam Deck status, review numbers,
Steam's short description and, when imho.run has one, a summary mined from
player reviews (difficulty, length, session shape, co-op, hooks, dealbreakers).

### find_game_by_description

```python
hit = imho.find_game_by_description(
    "you play a cat in a cyberpunk city with a little drone",
    platform="pc",          # pc, playstation, xbox, nintendo, sega, mobile, browser, arcade
    year_min=None, year_max=None,
    perspective=None,       # first, third, top_down, side
)
hit["confidence"], hit["results"][0]["name"]   # ('medium', 'Stray')
hit["find_game_url"]   # imho.run/find-game with the description filled in
```

This one runs a language model on the server. It takes several seconds and is
limited to 3 calls a minute and 20 a day per IP, so use it only when the title
is unknown.

### Async

```python
import asyncio
from imho import AsyncImhoClient

async def main() -> None:
    async with AsyncImhoClient() as imho:
        facts = await imho.game_facts("1145360")
        print(facts["game"]["name"])

asyncio.run(main())
```

### Any MCP tool

`call_tool(name, arguments)` calls any tool on the MCP server and returns its
structured result, and `list_tools()` returns the tool definitions. Use them
for tools added to the server after this release.

## Errors

| Exception | When |
| --- | --- |
| `NotFoundError` | No game matched the query (HTTP 404). |
| `BadRequestError` | A parameter is out of range or the query is empty (400/422), or an unknown MCP tool. |
| `RateLimitError` | Over the limit (HTTP 429). `retry_after` holds the seconds to wait when known. |
| `DisabledError` | The API is switched off on the server (503). |
| `ToolError` | An MCP tool returned `isError` for another reason. |

All of them subclass `ImhoError`, which has `detail`, `code` and `status`.

## Limits and attribution

30 requests a minute and 1,000 a day per IP; `find_game_by_description` 3 a
minute and 20 a day. Responses are cached on the server.

If you show the results to people, credit imho.run ("Recommendations by
imho.run") and link each game's `url`. Every response has an `attribution`
field with that wording.

## Development

```bash
cd python
uv run --with pytest --with pytest-asyncio --with-editable . pytest -q
IMHO_LIVE=1 uv run --with pytest --with pytest-asyncio --with-editable . pytest -q -m live   # hits the real API
```

## License

MIT. The client is MIT-licensed; the imho.run service and its data are covered
by the [imho.run terms](https://imho.run/terms).
