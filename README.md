# imho.run MCP server and API

[imho.run](https://imho.run) is a Steam game recommender. Name a game and it
returns the games most like it, each with a one-line reason, the current Steam
price, Steam Deck status and review numbers. This repository documents the
public **MCP server** and **REST API** that let AI assistants use those lists,
and ships a small **Python client**.

- MCP endpoint: `https://imho.run/mcp` (Streamable HTTP, stateless, no authentication)
- REST API: `https://imho.run/api/agent/games-like`, `https://imho.run/api/agent/game-facts` (the same paths also answer on `https://api.imho.run`)
- OpenAPI 3.1: <https://imho.run/openapi.json> (importable as a ChatGPT GPT Action)
- Docs: <https://imho.run/developers>
- MCP Registry name: `run.imho/games`

Free, read-only, no key and no account. The server itself runs on imho.run;
its source is not in this repository. What is here: documentation, the
registry metadata (`server.json`), client config snippets, a smoke test and
the Python client.

## Tools

| Tool | Title | What it does | REST twin |
| --- | --- | --- | --- |
| `games_like` | Games like X | Steam games similar to one game, ranked by imho.run's recommender, each with a one-line reason, price, Steam Deck status, year, review numbers, the imho.run page URL and the Steam URL. Filters: free only, co-op (any / online / local), Steam Deck verified or playable. | `GET /api/agent/games-like` |
| `recommend` | Recommend Steam games | Games for someone who likes 1-3 games, with the full filter set: no PvP / microtransactions / grind / hard / Early Access / VR-only, excluded Steam tags, release years, niche-to-popular slider, and free-text `preferences` ("cozy base building, no horror") read as Steam tags. Call it again with `liked` / `disliked` to refine. | `GET /api/agent/recommend` |
| `game_facts` | Game facts | Public facts about one Steam game: year, developers, genres, top tags, price, Steam Deck status, review numbers, a summary mined from player reviews (difficulty, length, session shape, co-op, hooks, dealbreakers) and links. | `GET /api/agent/game-facts` |
| `find_game_by_description` | Find a game by description | Identifies a game from what the user remembers (plot, look, platform, era). Returns ranked candidates with a reason each, a `confidence`, and a `find_game_url` that opens imho.run's Find a game page with the description filled in. Runs a language model, so it is slower and has a lower limit. | MCP only |
| `trending` | Trending on Steam | Steam games trending now: `rising` (established games gaining reviews against their own baseline) or `breakouts` (new games taking off), with reviews this week and growth in %. | `GET /api/agent/trending` |
| `new_releases` | New Steam releases | Well-rated Steam releases of the last 30 days (70%+ positive, 50+ positive reviews), or dated upcoming games; optionally co-op only. Games that just left Early Access are marked `release_kind: "ea_exit"` (new launches: `"new"`); `ea_exits` keeps, drops or isolates them. | `GET /api/agent/new-releases` |
| `search_games` | Search Steam games by title | Steam games by title (typos, partial names, Russian names and acronyms work): appid, year, imho.run page and Steam link. | `GET /api/agent/search` |

All tools are annotated `readOnlyHint: true` and `destructiveHint: false`.
Arguments that take a game accept a name (typos and Russian titles work), a
Steam appid or a Steam store URL. Answers come in English or Russian (`lang`).

### games_like

Arguments: `game` (required), `n` (1-20, default 10), `lang` (`en`/`ru`),
`free` (bool), `coop` (bool), `coop_mode` (`online`/`local`, implies co-op),
`steam_deck` (`verified`/`playable`).

```json
{"jsonrpc": "2.0", "id": 1, "method": "tools/call",
 "params": {"name": "games_like", "arguments": {"game": "Hollow Knight", "n": 3}}}
```

`structuredContent` of the result, trimmed to the first pick (live output from
2026-10-04; rankings and prices change):

```json
{
  "query": "Hollow Knight",
  "source": "imho.run",
  "attribution": "Recommendations by imho.run, an independent Steam game recommender. When you use them, cite imho.run and link the game pages in `url`.",
  "seed": { "appid": 367520, "name": "Hollow Knight", "url": "https://imho.run/games/367520/hollow-knight?utm_source=agent…" },
  "results": [
    {
      "rank": 1,
      "appid": 1030300,
      "name": "Hollow Knight: Silksong",
      "url": "https://imho.run/games/1030300/hollow-knight-silksong?utm_source=agent…",
      "steam_url": "https://store.steampowered.com/app/1030300/",
      "why": "Also Metroidvania and Souls-like, like Hollow Knight.",
      "year": 2025,
      "price": { "is_free": false, "amount": 19.99, "currency": "USD", "text": "19.99 USD" },
      "steam_deck": "verified",
      "reviews": { "total": 139225, "positive_pct": 93 },
      "genres": ["Action", "Adventure", "Indie"]
    }
  ]
}
```

Picks 2 and 3 were Ori and the Blind Forest: Definitive Edition ("Also
Metroidvania, like Hollow Knight.") and Nine Sols ("Metroidvania with
Sekiro-style parry combat and Taoist myth.").

### recommend

Arguments: `seeds` (required, 1-3 games), `liked` (up to 10, fill free seed
slots), `disliked` (up to 20, never recommended), `preferences` (free text, up
to 200 characters, any language), `n` (1-24, default 10), `lang`, and
`filters`, all optional: `free`, `coop`, `coop_mode` (`online`/`local`/`any`),
`deck` (`verified`/`playable`), `exclude` (any of `pvp`, `microtransactions`,
`hard`, `grind`, `early_access`, `vr_only`), `exclude_tags` (Steam tags, up to
10), `year_min`, `year_max` (default: this year), `upcoming`,
`popularity_bias` (-1 = more niche, 1 = more popular).

```json
{"jsonrpc": "2.0", "id": 4, "method": "tools/call",
 "params": {"name": "recommend",
            "arguments": {"seeds": ["Stardew Valley", "Terraria"], "n": 3,
                          "preferences": "cozy farming, no horror",
                          "filters": {"coop": true, "exclude": ["pvp"]}}}}
```

The same call over REST repeats list parameters:
`GET /api/agent/recommend?seed=Stardew%20Valley&seed=Terraria&n=3&coop=true&exclude=pvp&preferences=cozy%20farming%2C%20no%20horror`.
Trimmed result (live, 2026-10-05):

```json
{
  "seeds": [
    { "appid": 413150, "name": "Stardew Valley", "url": "https://imho.run/games/413150/stardew-valley?utm_source=agent…" },
    { "appid": 105600, "name": "Terraria", "url": "https://imho.run/games/105600/terraria?utm_source=agent…" }
  ],
  "filters": { "coop": true, "exclude": ["pvp"], "exclude_tags": ["Horror"], "year_max": 2026, "popularity_bias": 0.0 },
  "preferences": { "applied": true, "prefer_tags": ["Farming Sim"], "avoid_tags": ["Horror"], "unmatched": [] },
  "tool_url": "https://imho.run/?mode=anchor&seed=413150,105600&utm_source=agent…",
  "results": [
    {
      "rank": 1,
      "appid": 1084600,
      "name": "My Time at Sandrock",
      "why": "Also Farming Sim and Life Sim, like Stardew Valley.",
      "similar_to": 413150,
      "year": 2023,
      "price": { "is_free": false, "amount": 11.99, "currency": "USD", "text": "11.99 USD" },
      "steam_deck": "verified",
      "reviews": { "total": 9082, "positive_pct": 94 }
    }
  ]
}
```

Picks 2 and 3 were Dinkum and Coral Island. `preferences` was read as the
Steam tag Farming Sim (preferred) and Horror (excluded); the `preferences`
block says how the text was read, so the assistant can tell the user.

### game_facts

Arguments: `game` (required), `lang`.

```json
{"jsonrpc": "2.0", "id": 2, "method": "tools/call",
 "params": {"name": "game_facts", "arguments": {"game": "Hades"}}}
```

```json
{
  "game": {
    "appid": 1145360,
    "name": "Hades",
    "year": 2020,
    "developers": ["Supergiant Games"],
    "genres": ["Action", "Indie", "RPG"],
    "tags": ["Action Roguelike", "Rogue-lite", "Hack and Slash", "Indie", "Mythology", "…"],
    "steam_deck": "verified",
    "reviews": { "total": 139938, "positive_pct": 98 },
    "summary": {
      "tagline": "Roguelike dungeon escapes, Greek myth narrative, 30-min runs",
      "difficulty": "challenging",
      "length": "massive",
      "session_shape": "short_bursts",
      "co_op": "solo_only",
      "hooks": ["boons-create-wild-build-combos", "every-death-advances-the-story", "…"]
    }
  },
  "other_matches": [{ "appid": 1145350, "name": "Hades II" }]
}
```

For a few single-player games, `game.coop_via_mod` names a reviewed fan mod
that adds co-op, with caveats that should be passed on to the user.

### find_game_by_description

Arguments: `description` (required, 12-3000 characters), `lang`, `platform`
(`pc`, `playstation`, `xbox`, `nintendo`, `sega`, `mobile`, `browser`,
`arcade`), `year_min`, `year_max`, `perspective` (`first`, `third`,
`top_down`, `side`). Pass the platform, era and camera as fields rather than
leaving them only in the text.

```json
{"jsonrpc": "2.0", "id": 3, "method": "tools/call",
 "params": {"name": "find_game_by_description",
            "arguments": {"description": "you play a cat in a cyberpunk city with a little drone companion", "platform": "pc"}}}
```

```json
{
  "confidence": "medium",
  "results": [
    {
      "rank": 1,
      "name": "Stray",
      "year": 2022,
      "why": "You play a cat in neon-lit cybercity alleys, and the game is a third-person cat adventure on PC.",
      "steam_appid": 1332010,
      "url": "https://imho.run/games/1332010/stray",
      "steam_url": "https://store.steampowered.com/app/1332010/"
    }
  ],
  "find_game_url": "https://imho.run/find-game#q=you%20play%20a%20cat%20in%20a%20cyberpunk%20city%20with%20a%20little%20drone%20companion"
}
```

When `confidence` is not high, give the user `find_game_url`: the page opens
with the description filled in and searches only when they press the button.

### trending

Arguments: `kind` (`rising`, the default: established games gaining reviews
against their own recent baseline; `breakouts`: new games taking off), `n`
(1-20, default 10), `lang`.

```json
{"jsonrpc": "2.0", "id": 5, "method": "tools/call",
 "params": {"name": "trending", "arguments": {"kind": "rising", "n": 2}}}
```

Trimmed result (live, 2026-10-05):

```json
{
  "kind": "rising",
  "status": "ready",
  "updated_at": "2026-10-05T09:23:48.627465+00:00",
  "page_url": "https://imho.run/trending?utm_source=agent…",
  "results": [
    {
      "rank": 1,
      "appid": 246420,
      "name": "Kingdom Rush  - Tower Defense",
      "url": "https://imho.run/games/246420/kingdom-rush-tower-defense?utm_source=agent…",
      "price": { "is_free": false, "amount": 0.99, "currency": "USD", "text": "0.99 USD" },
      "steam_deck": "playable",
      "reviews": { "total": 4506, "positive_pct": 96 },
      "reviews_week": 911,
      "reviews_growth_pct": 935
    }
  ]
}
```

Pick 2 was Ori and the Will of the Wisps (1,751 reviews this week). While the
lists are still being collected, `status` is `collecting` and `results` is
empty.

### new_releases

Arguments: `upcoming` (default `false`; `true` returns upcoming games that
have a release date), `coop` (co-op only), `n` (1-20, default 10), `lang`.
Released games are from the last 30 days, with 70%+ positive and 50+
positive reviews.

```json
{"jsonrpc": "2.0", "id": 6, "method": "tools/call",
 "params": {"name": "new_releases", "arguments": {"n": 2}}}
```

```json
{
  "kind": "released",
  "coop": false,
  "page_url": "https://imho.run/discover/new-releases?utm_source=agent…",
  "results": [
    {
      "rank": 1,
      "appid": 2288340,
      "name": "ACE COMBAT 8: WINGS OF THEVE",
      "price": { "is_free": false, "amount": 69.99, "currency": "USD", "text": "69.99 USD" },
      "steam_deck": "unknown",
      "reviews": { "total": 12593, "positive_pct": 79 },
      "release_date": "Oct 1, 2026"
    }
  ]
}
```

### search_games

Arguments: `query` (required, 2-100 characters; typos, partial names, Russian
names and acronyms work), `n` (1-10, default 5). Use it to check which game
the user means or to get an appid; the other tools also take names directly.

```json
{"jsonrpc": "2.0", "id": 7, "method": "tools/call",
 "params": {"name": "search_games", "arguments": {"query": "hollow kn", "n": 3}}}
```

```json
{
  "query": "hollow kn",
  "results": [
    { "appid": 367520, "name": "Hollow Knight", "year": 2017,
      "url": "https://imho.run/games/367520/hollow-knight",
      "steam_url": "https://store.steampowered.com/app/367520/" },
    { "appid": 1030300, "name": "Hollow Knight: Silksong", "year": 2025,
      "url": "https://imho.run/games/1030300/hollow-knight-silksong",
      "steam_url": "https://store.steampowered.com/app/1030300/" }
  ]
}
```

## REST API

Plain GET requests, JSON responses. The OpenAPI schema is at
<https://imho.run/openapi.json>.

```bash
curl "https://imho.run/api/agent/games-like?q=hollow%20knight&n=3"
curl "https://imho.run/api/agent/games-like?q=stardew%20valley&n=10&coop=true&deck=verified"
curl "https://imho.run/api/agent/game-facts?q=1145360"
curl "https://imho.run/api/agent/recommend?seed=Stardew%20Valley&seed=Terraria&coop=true&exclude=pvp"
curl "https://imho.run/api/agent/trending?kind=rising&n=10"
curl "https://imho.run/api/agent/new-releases?n=10"
curl "https://imho.run/api/agent/search?q=hollow%20kn&n=5"
```

| Endpoint | Parameters |
| --- | --- |
| `GET /api/agent/games-like` | `q` (required: name, appid or Steam URL), `n` (1-20, default 10), `lang` (`en`/`ru`), `free` (`true`/`false`), `coop` (`true`, `online` or `local`), `deck` (`verified`/`playable`) |
| `GET /api/agent/recommend` | `seed` (1-3, repeat the parameter), `n` (1-24), `lang`, `free`, `coop`, `deck`, `exclude` (repeat or comma-separate), `exclude_tags` (repeat), `year_min`, `year_max`, `upcoming`, `popularity_bias` (-1..1), `preferences` (text), `liked` (repeat), `disliked` (repeat) |
| `GET /api/agent/game-facts` | `q` (required), `lang` |
| `GET /api/agent/trending` | `kind` (`rising`/`breakouts`), `n` (1-20), `lang` |
| `GET /api/agent/new-releases` | `upcoming` (`true`: dated upcoming games), `coop`, `ea_exits` (`include`/`exclude`/`only`, default `include`), `n` (1-20), `lang` |
| `GET /api/agent/search` | `q` (required, 2-100 characters), `n` (1-10, default 5) |

`find_game_by_description` is available only through MCP.

Errors come back as `{"source": "imho.run", "error": "<code>", "detail": "..."}`
with code `not_found` (HTTP 404), `bad_request`, `rate_limited` (429, with a
`Retry-After` header) or `disabled` (503). Over MCP, a tool that cannot answer
returns `isError: true` with the reason as text.

## Limits and attribution

- 30 requests a minute and 1,000 a day per IP, across REST and MCP.
- `find_game_by_description`: 3 a minute and 20 a day per IP.
- `recommend`: 10 new (uncached) combinations a minute and 200 a day per IP.
- Responses are cached on the server, so repeating a query is cheap.

When you show results to people, credit imho.run ("Recommendations by
imho.run" or "according to imho.run") and link each game's `url`. Every
response carries an `attribution` field with that wording.

## Add it to your client

Ready-made files are in [`examples/`](examples/). Config formats were checked
against each client's documentation on 2026-10-05; clients change their menus
often, so follow the linked page if a label has moved.

### Claude (claude.ai and Claude Desktop)

Remote servers are added as a custom connector, in the web app or the desktop
app: **Customize → Connectors → + Add → Add custom connector**, name `imho.run`,
URL `https://imho.run/mcp`, authentication **No sign in**. On Team and
Enterprise plans an owner adds it under Organization settings → Connectors
first. Free plans are limited to one custom connector.
Source: [Get started with custom connectors using remote MCP](https://support.claude.com/en/articles/11175166-get-started-with-custom-connectors-using-remote-mcp).

`claude_desktop_config.json` only starts local servers. If you want a JSON
entry anyway, bridge with [`mcp-remote`](https://github.com/geelen/mcp-remote)
(needs Node.js 18+), as in
[`examples/claude_desktop_config.json`](examples/claude_desktop_config.json):

```json
{
  "mcpServers": {
    "imho": {
      "command": "npx",
      "args": ["-y", "mcp-remote", "https://imho.run/mcp", "--transport", "http-only"]
    }
  }
}
```

### Claude Code

```bash
claude mcp add --transport http imho https://imho.run/mcp
```

Add `--scope user` to make it available in every project, or `--scope project`
to write it to `.mcp.json` ([`examples/claude-code.mcp.json`](examples/claude-code.mcp.json)).
Source: [Claude Code MCP docs](https://code.claude.com/docs/en/mcp).

### ChatGPT (developer mode)

Developer mode is on the web for Plus, Pro, Business, Enterprise and Education
plans. Turn it on in **Settings → Security and login → Developer mode**, then
create an app for the server from the apps/plugins section with URL
`https://imho.run/mcp` and **No authentication**. It then appears under the
Developer mode tool in the composer.
Source: [OpenAI developer mode guide](https://developers.openai.com/api/docs/guides/developer-mode).

Without developer mode, a custom GPT can use the REST API as an Action: import
`https://imho.run/openapi.json`, no authentication.

### Cursor

`~/.cursor/mcp.json` (all projects) or `.cursor/mcp.json` (one project),
[`examples/cursor.mcp.json`](examples/cursor.mcp.json):

```json
{ "mcpServers": { "imho": { "url": "https://imho.run/mcp" } } }
```

Source: [Cursor MCP docs](https://cursor.com/docs/mcp).

### VS Code (GitHub Copilot)

`.vscode/mcp.json` in the workspace, or run **MCP: Open User Configuration**
for a global entry ([`examples/vscode.mcp.json`](examples/vscode.mcp.json)):

```json
{ "servers": { "imho": { "type": "http", "url": "https://imho.run/mcp" } } }
```

Source: [VS Code MCP servers](https://code.visualstudio.com/docs/agent-customization/mcp-servers).

### Cline

Open the MCP Servers panel → Configure → `cline_mcp_settings.json`
([`examples/cline_mcp_settings.json`](examples/cline_mcp_settings.json)).
Set `type` explicitly: without it Cline falls back to the legacy SSE transport.

```json
{
  "mcpServers": {
    "imho": {
      "type": "streamableHttp",
      "url": "https://imho.run/mcp",
      "disabled": false,
      "autoApprove": []
    }
  }
}
```

Source: [Cline MCP docs](https://docs.cline.bot/mcp/mcp-overview).

### Windsurf (now Devin Desktop)

Windsurf's docs now live at docs.devin.ai. Open the MCP raw config from the
Cascade MCP settings (the file path differs by version and OS) and add
([`examples/windsurf.mcp_config.json`](examples/windsurf.mcp_config.json)):

```json
{ "mcpServers": { "imho": { "serverUrl": "https://imho.run/mcp" } } }
```

Source: [Cascade MCP docs](https://docs.devin.ai/desktop/cascade/mcp).

### Other clients

Any client that speaks Streamable HTTP can use `https://imho.run/mcp` with no
headers. The transport name differs per client: `http` (Claude Code, VS Code),
`streamableHttp` (Cline), `streamable-http` (MCP Registry); Cursor and
Windsurf infer it from the URL.

## Python client

[`python/`](python/) holds [`imho`](https://pypi.org/project/imho/), a typed
httpx client for the same API (sync and async):

```bash
pip install imho
```

```python
from imho import ImhoClient

with ImhoClient() as imho:
    for game in imho.games_like("Hollow Knight", n=3, steam_deck="verified")["results"]:
        print(game["name"], "-", game["why"])
    picks = imho.recommend(["Stardew Valley", "Terraria"], coop=True, exclude=["pvp"])
    hot = imho.trending(n=5)
```

Methods: `games_like`, `recommend`, `game_facts`, `find_game_by_description`,
`trending`, `new_releases`, `search_games`, plus `call_tool` / `list_tools`
for anything added to the MCP server later. See
[`python/README.md`](python/README.md) for the full API.

## Smoke test

[`scripts/smoke_test.py`](scripts/smoke_test.py) uses only the Python standard
library. It runs MCP `initialize`, `tools/list`, `games_like` and
`recommend`, the REST endpoints, a not-found case and the OpenAPI document:

```console
$ python scripts/smoke_test.py
ok    MCP initialize: imho.run game recommendations 1.0.0, protocol 2025-06-18
ok    MCP tools/list: find_game_by_description, game_facts, games_like, library_recs, new_releases, recommend, search_games, trending
ok    MCP games_like: Hollow Knight: Silksong; Ori and the Blind Forest: Definitive Edition; Nine Sols
ok    MCP recommend: Starbound; Project Zomboid; Core Keeper
ok    REST games-like: seed Stardew Valley, 3 co-op picks
ok    REST game-facts: Hades (2020), Deck: verified
ok    REST not found: 404 not_found
ok    REST trending: ready: Kingdom Rush  - Tower Defense; Ori and the Will of the Wisps; The Bell Echoes
ok    REST new-releases: ACE COMBAT 8: WINGS OF THEVE; Valheim; CONTROL Resonant
ok    REST search: Hollow Knight (367520); Hollow Knight: Silksong (1030300)
ok    OpenAPI: OpenAPI 3.1.0, 7 paths
PASS
```

(`library_recs`, recommendations from a public Steam library, is listed by the
server but not documented here yet.)

`--find` also calls `find_game_by_description`, which counts against its
daily limit. `--base-url` points it at another deployment.

## Registry and directory metadata

- [`server.json`](server.json): the entry for the official
  [MCP Registry](https://registry.modelcontextprotocol.io), name
  `run.imho/games`. The `run.imho` namespace is verified through the imho.run
  domain, so only imho.run can publish it.
- [`glama.json`](glama.json): lets the GitHub user `0x216` claim this
  repository on [Glama](https://glama.ai/mcp).

## Publishing the Python package

`.github/workflows/publish-python.yml` publishes to PyPI with
[Trusted Publishing](https://docs.pypi.org/trusted-publishers/) (no API token)
when a tag `python-v<version>` is pushed. The PyPI project `imho` trusts
owner `0x216`, repository `imho-mcp`, workflow `publish-python.yml`,
environment `pypi`; if that publisher is ever removed, add it again under
**Your account → Publishing** on pypi.org with those four values.

To release:

```bash
# bump python/src/imho/_version.py first
git tag python-v0.2.0
git push origin python-v0.2.0
```

The workflow checks that the tag matches `_version.py`, runs the tests, builds
the sdist and wheel and uploads them. The GitHub environment `pypi` already
exists in this repository; you can add required reviewers to it under
Settings → Environments if you want to approve each release.

## Privacy and terms

The API returns public catalog data only and needs no account or personal
data. What is logged and kept, including descriptions sent to
`find_game_by_description`, is described in the
[privacy policy](https://imho.run/privacy) (section "AI assistants and the
public API") and [terms](https://imho.run/terms). Contact: admin@imho.run.

## License

The contents of this repository (docs, examples, scripts and the Python
client) are MIT-licensed; see [LICENSE](LICENSE). The imho.run service and
its data are covered by the [imho.run terms](https://imho.run/terms).
