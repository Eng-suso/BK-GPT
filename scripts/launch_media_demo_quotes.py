"""Controlla le citazioni dei copioni della demo: ogni testo tra « » deve stare alla lettera in un'intervista.

    python3 scripts/launch_media_demo_quotes.py [docs/launch/demo-chat-scripts.md]
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

SOURCES = Path("tests/golden/esaote_ciclo_passivo/sources")


def main() -> int:
    script = Path(sys.argv[1] if len(sys.argv) > 1 else "docs/launch/demo-chat-scripts.md")
    texts = [path.read_text(encoding="utf-8") for path in sorted(SOURCES.glob("*.md"))]
    quotes = re.findall(r"«([^»]+)»", script.read_text(encoding="utf-8"))
    wrong = [quote for quote in quotes if not any(quote in text for text in texts)]
    for quote in wrong:
        print("! non trovata:", quote)
    print(f"{len(quotes) - len(wrong)}/{len(quotes)} citazioni alla lettera")
    return 1 if wrong else 0


if __name__ == "__main__":
    sys.exit(main())
