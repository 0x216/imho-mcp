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

| Tool | What it does |
| --- | --- |
| `games_like` | Steam games similar to one game, ranked by imho.run's recommender, each with a one-line reason, price, Steam Deck status, year, review numbers, the imho.run page URL and the Steam URL. Filters: free only, co-op (any / online / local), Steam Deck verified or playable. |
| `game_facts` | Public facts about one Steam game: year, developers, genres, top tags, price, Steam Deck status, review numbers, a summary mined from player reviews (difficulty, length, session shape, co-op, hooks, dealbreakers) and links. |
| `find_game_by_description` | Identifies a game from what the user remembers (plot, look, platform, era). Returns ranked candidates with a reason each, a `confidence`, and a `find_game_url` that opens imho.run's Find a game page with the description filled in. Runs a language model, so it is slower and has a lower limit. |

All three tools are annotated `readOnlyHint: true` and `destructiveHint: false`.
The `game` argument accepts a name (typos and Russian titles work), a Steam
appid or a Steam store URL. Answers come in English or Russian (`lang`).

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

## REST API

Plain GET requests, JSON responses. The OpenAPI schema is at
<https://imho.run/openapi.json>.

```bash
curl "https://imho.run/api/agent/games-like?q=hollow%20knight&n=3"
curl "https://imho.run/api/agent/games-like?q=stardew%20valley&n=10&coop=true&deck=verified"
curl "https://imho.run/api/agent/game-facts?q=1145360"
```

| Endpoint | Parameters |
| --- | --- |
| `GET /api/agent/games-like` | `q` (required: name, appid or Steam URL), `n` (1-20, default 10), `lang` (`en`/`ru`), `free` (`true`/`false`), `coop` (`true`, `online` or `local`), `deck` (`verified`/`playable`) |
| `GET /api/agent/game-facts` | `q` (required), `lang` |

`find_game_by_description` is available only through MCP.

Errors come back as `{"source": "imho.run", "error": "<code>", "detail": "..."}`
with code `not_found` (HTTP 404), `bad_request`, `rate_limited` (429, with a
`Retry-After` header) or `disabled` (503). Over MCP, a tool that cannot answer
returns `isError: true` with the reason as text.

## Limits and attribution

- 30 requests a minute and 1,000 a day per IP, across REST and MCP.
- `find_game_by_description`: 3 a minute and 20 a day per IP.
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

[`python/`](python/) holds `imho`, a typed httpx client for the same API:

```python
from imho import ImhoClient

with ImhoClient() as imho:
    for game in imho.games_like("Hollow Knight", n=3, steam_deck="verified")["results"]:
        print(game["name"], "-", game["why"])
```

It is not on PyPI yet. Install from this repository:

```bash
pip install "git+https://github.com/0x216/imho-mcp#subdirectory=python"
```

See [`python/README.md`](python/README.md) for the full API.

## Smoke test

[`scripts/smoke_test.py`](scripts/smoke_test.py) uses only the Python standard
library. It runs MCP `initialize`, `tools/list` and a `games_like` call, the
two REST endpoints, a not-found case and the OpenAPI document:

```console
$ python scripts/smoke_test.py
ok    MCP initialize: imho.run game recommendations 1.0.0, protocol 2025-06-18
ok    MCP tools/list: find_game_by_description, game_facts, games_like
ok    MCP games_like: Hollow Knight: Silksong; Ori and the Blind Forest: Definitive Edition; Nine Sols
ok    REST games-like: seed Stardew Valley, 3 co-op picks
ok    REST game-facts: Hades (2020), Deck: verified
ok    REST not found: 404 not_found
ok    OpenAPI: OpenAPI 3.1.0, 2 paths
PASS
```

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
when a tag `python-v<version>` is pushed. One-time setup by the repository
owner:

1. Sign in to <https://pypi.org> (create an account and enable 2FA if needed).
2. Go to **Your account → Publishing** (<https://pypi.org/manage/account/publishing/>).
3. Under **Add a new pending publisher → GitHub**, enter:
   - PyPI Project Name: `imho`
   - Owner: `0x216`
   - Repository name: `imho-mcp`
   - Workflow name: `publish-python.yml`
   - Environment name: `pypi`
4. Click **Add**. The pending publisher becomes the project on the first upload.

Then release:

```bash
# bump python/src/imho/_version.py first if needed
git tag python-v0.1.0
git push origin python-v0.1.0
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
