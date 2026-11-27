"""Quanta parte del prompt resta uguale da una chiamata all'altra: il prefisso che va in cache.

Legge le richieste salvate dal finto OpenAI (`FAKE_DUMP_DIR`), le raggruppa per
tipo di chiamata (primo messaggio di sistema e tool) e, per ogni chiamata, dice
quanti token iniziali sono identici alla precedente dello stesso tipo e dove
divergono. OpenAI riusa dalla cache solo quel prefisso: e' il numero da tenere
alto (docs/load-test/README.md).

    FAKE_DUMP_DIR=/var/tmp/delir-load/dump uv run python -m scripts.load_test.fake_openai &
    # ... qualche turno nella stessa chat ...
    uv run python -m scripts.load_test.prefix_report /var/tmp/delir-load/dump

I token sono stimati (caratteri / 4): bastano per confrontare un prima e un dopo.
"""

from __future__ import annotations

import argparse
import collections
import json
from pathlib import Path


def _kind(body: dict) -> tuple[str, str]:
    system = ""
    for message in body.get("messages") or []:
        if message.get("role") in ("system", "developer"):
            content = message.get("content")
            system = content if isinstance(content, str) else json.dumps(content)
            break
    tools = ",".join(sorted(t["function"]["name"] for t in body.get("tools") or []))
    return system[:60].replace("\n", " "), tools[:60]


def _serial(body: dict) -> str:
    """Come la vede la cache: prima i tool, poi i messaggi, in ordine."""
    return json.dumps(body.get("tools") or [], ensure_ascii=False) + json.dumps(
        body.get("messages") or [], ensure_ascii=False
    )


def _layout(body: dict) -> str:
    parts = [f"tools:{len(json.dumps(body.get('tools') or [])) // 4}"]
    for message in body.get("messages") or []:
        content = message.get("content")
        size = len(content if isinstance(content, str) else json.dumps(content)) // 4
        parts.append(f"{message.get('role')}:{size}")
    return " | ".join(parts)


def report(dump_dir: Path, min_tokens: int = 1000) -> list[dict]:
    groups: dict[tuple[str, str], list[dict]] = collections.defaultdict(list)
    for path in sorted(dump_dir.glob("*.json")):
        body = json.loads(path.read_text(encoding="utf-8"))
        groups[_kind(body)].append(body)
    rows = []
    for (system, tools), bodies in groups.items():
        serials = [_serial(b) for b in bodies]
        if len(serials) < 2 or len(serials[0]) < min_tokens * 4:
            continue
        for previous, (current, body) in zip(serials, zip(serials[1:], bodies[1:])):
            same = 0
            for a, b in zip(previous, current):
                if a != b:
                    break
                same += 1
            rows.append({
                "call": system, "tools": tools,
                "prompt_tokens": len(current) // 4, "cached_prefix_tokens": same // 4,
                "cached_share": round(same / len(current), 3),
                "diverges_at": current[max(0, same - 60): same + 80],
                "layout": _layout(body),
            })
    return rows


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    parser.add_argument("dump_dir", type=Path)
    parser.add_argument("--min-tokens", type=int, default=1000)
    args = parser.parse_args()
    for row in report(args.dump_dir, args.min_tokens):
        print(f"{row['cached_share']:>6.0%}  {row['cached_prefix_tokens']:>6}/{row['prompt_tokens']:<6} "
              f"{row['call'][:40]!r}  diverge: {row['diverges_at'][:90]!r}")
        print(f"        {row['layout']}")


if __name__ == "__main__":
    main()
