---
title: Find a forgotten game
emoji: 🕹️
colorFrom: indigo
colorTo: yellow
sdk: gradio
sdk_version: 6.29.1
python_version: "3.12"
app_file: app.py
pinned: false
license: mit
short_description: Describe a half-remembered game and get its name
tags:
  - games
  - steam
  - recommender
  - search
  - mcp
---

# Find a forgotten game

Remember a game but not its name? Describe it in your own words ("a PS2 game
where a boy with horns escapes a castle holding a princess's hand") and get
the most likely titles, each with the year, platforms and a one-line reason
it fits. English and Russian descriptions both work. A second tab, **Games
like X**, lists ten games most like one you name, with Steam prices and Steam
Deck status.

The search itself runs on **[imho.run](https://imho.run/find-game?utm_source=huggingface&utm_medium=space&utm_campaign=readme)**,
an independent Steam game recommender. It matches your description against
Steam and IGDB with a retriever trained on solved "what was that game?"
threads, then a language model checks the candidates. For unlimited searches,
follow-up questions and the full result pages, use
[imho.run/find-game](https://imho.run/find-game?utm_source=huggingface&utm_medium=space&utm_campaign=readme).

## How this Space works

This Space is a small client: no model runs here. Each search is one call to
imho.run's free, public MCP server at `https://imho.run/mcp` (tools
`find_game_by_description`, `games_like` and `search_games`). The same server
works in Claude, ChatGPT, Cursor, VS Code and other MCP clients; setup and the
REST API are documented at
[imho.run/developers](https://imho.run/developers?utm_source=huggingface&utm_medium=space&utm_campaign=readme)
and in [0x216/imho-mcp](https://github.com/0x216/imho-mcp).

## Limits

imho.run allows `find_game_by_description` 3 calls a minute and 20 a day per
IP address. Everyone using this Space shares the Space's IP, so the Space:

- answers the examples from `examples.json` without calling imho.run;
- caches answers in memory, so a repeated description costs nothing;
- gives each visitor 3 live searches a day, so one person can't use up everyone's share;
- shows how many shared searches are left today and links to imho.run when they run out.

"Games like X" has a much higher limit (30 a minute, 1,000 a day) and is rarely affected.

## Run it locally

```bash
pip install "gradio==6.29.1" -r requirements.txt
python app.py
```

`python bake_examples.py` refreshes `examples.json` (it spaces calls 21 s
apart and resumes if interrupted). Optional environment variables:
`IMHO_FIND_PER_DAY`, `IMHO_FIND_PER_MINUTE`, `IMHO_FIND_PER_VISITOR_DAY`
(local quota mirror), `IMHO_FIND_TIMEOUT_S`, `IMHO_MCP_URL`, `IMHO_MCP_FALLBACK_URL`.
`IMHO_PARTNER_KEY` (a Space secret) is reserved for a dedicated imho.run quota:
when set, it is sent as the `X-Imho-Partner-Key` header together with a
salted per-visitor hash (`X-Imho-End-User`). imho.run ignores both today.

## Privacy

Descriptions you type are sent to imho.run and handled under its
[privacy policy](https://imho.run/privacy) (section "AI assistants and the
public API"). The Space keeps a salted hash of your IP in memory only, to
count your daily searches, and logs nothing.

## License

The code of this Space is MIT-licensed. Results and the imho.run service are
covered by the [imho.run terms](https://imho.run/terms). Results by
[imho.run](https://imho.run/?utm_source=huggingface&utm_medium=space&utm_campaign=readme).
