"""Controlla la mappa delle citazioni inglesi della demo (e2e/launch-media/data/en/quotes.json).

Ogni chiave italiana deve stare alla lettera in un'intervista italiana, ogni valore
inglese alla lettera nella versione inglese delle interviste. Controlla anche che
nessuna citazione usata dalla demo (evidenze, copioni, golden, demo.ts) manchi dalla mappa.

    python3 scripts/launch_media_quotes_en.py
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SOURCES_IT = Path("tests/golden/esaote_ciclo_passivo/sources")
SOURCES_EN = Path("e2e/launch-media/data/en/sources")
QUOTES = Path("e2e/launch-media/data/en/quotes.json")


def _quote_fields(node: object, out: list[str]) -> None:
    # raccoglie ricorsivamente tutti i campi "quote"
    if isinstance(node, dict):
        for key, value in node.items():
            if key == "quote" and isinstance(value, str):
                out.append(value)
            else:
                _quote_fields(value, out)
    elif isinstance(node, list):
        for item in node:
            _quote_fields(item, out)


def used_quotes() -> set[str]:
    """Le citazioni italiane che la demo usa, dalle quattro fonti."""
    found: list[str] = []
    _quote_fields(json.loads(Path("e2e/launch-media/data/demo-evidence.json").read_text(encoding="utf-8")), found)
    golden = json.loads(Path("tests/golden/esaote_ciclo_passivo/expected.json").read_text(encoding="utf-8"))
    _quote_fields(golden.get("expected_claims"), found)
    _quote_fields(golden.get("expected_evidence_bindings"), found)
    found += re.findall(r"«([^»]+)»", Path("docs/launch/demo-chat-scripts.md").read_text(encoding="utf-8"))
    found += re.findall(r'claim\(\w+, "[^"]*", "([^"]+)"\)', Path("e2e/launch-media/demo.ts").read_text(encoding="utf-8"))
    # « » vuoto nella nota del copione: non e' una citazione
    return {quote for quote in found if quote.strip()}


def main() -> int:
    italian = [path.read_text(encoding="utf-8") for path in sorted(SOURCES_IT.glob("*.md"))]
    english = [path.read_text(encoding="utf-8") for path in sorted(SOURCES_EN.glob("*.md"))]
    quotes: dict[str, str] = json.loads(QUOTES.read_text(encoding="utf-8"))
    wrong = 0
    for it, en in quotes.items():
        if not any(it in text for text in italian):
            print("! italiana non trovata:", it)
            wrong += 1
        elif not any(en in text for text in english):
            print("! inglese non trovata:", en)
            wrong += 1
    missing = sorted(used_quotes() - quotes.keys())
    for quote in missing:
        print("! manca dalla mappa:", quote)
    print(f"{len(quotes) - wrong}/{len(quotes)} citazioni")
    return 1 if wrong or missing else 0


if __name__ == "__main__":
    sys.exit(main())
