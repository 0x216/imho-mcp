"""Refresh examples.json: the answers the Space shows for its examples.

The examples are served from this file so clicking them costs none of the
Space's shared imho.run quota. Run it from your own machine (not the Space):

    python bake_examples.py            # only examples missing from the file
    python bake_examples.py --all      # re-ask every example

It spaces calls 21 s apart to stay under imho.run's 3-a-minute limit for
`find_game_by_description`, and saves after every answer, so a rerun resumes.
"""

from __future__ import annotations

import json
import sys
import time

from app import EXAMPLES_FILE, FIND_EXAMPLES, ImhoError, call_tool, detect_lang, normalize


def main() -> int:
    redo = "--all" in sys.argv
    try:
        baked = json.loads(EXAMPLES_FILE.read_text(encoding="utf-8"))
    except FileNotFoundError:
        baked = {}
    todo = [e for e in FIND_EXAMPLES if redo or normalize(e) not in baked]
    for i, example in enumerate(todo):
        if i:
            time.sleep(21)
        text = normalize(example)
        try:
            payload = call_tool(
                "find_game_by_description",
                {"description": text, "lang": detect_lang(text)},
                timeout=90,
            )
        except ImhoError as exc:
            print(f"FAILED {text[:60]!r}: {exc}")
            continue
        baked[text] = payload
        EXAMPLES_FILE.write_text(json.dumps(baked, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
        top = (payload.get("results") or [{}])[0].get("name")
        print(f"ok {text[:60]!r} -> {top} ({payload.get('confidence')})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
