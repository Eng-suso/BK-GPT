"""Acquisizione strutturale dei formati di testo: TXT, MD e CSV.

Anche un testo semplice ha una struttura citabile: i paragrafi di una nota o di
un verbale, le righe di un CSV. Senza porzioni ancorate un'affermazione estratta
da questi file non avrebbe niente da citare (P1.12).

- TXT e MD: un paragrafo per porzione (righe separate da una riga vuota),
  ancora `§3` con riga di inizio. I titoli Markdown restano nel testo.
- CSV: una riga per porzione, ancora `R7` come nel foglio. La prima riga e'
  l'intestazione: ogni porzione la porta, cosi' "1200" si legge come "importo:
  1200" e non come un numero orfano.
"""

from __future__ import annotations

from backend.workspace_services.evidence.canonical import Anchor, CanonicalSource, EvidenceSegment


def paragraphs(text: str, *, format: str) -> CanonicalSource:
    segments: list[EvidenceSegment] = []
    block: list[str] = []
    start = 0

    def close() -> None:
        body = "\n".join(block).strip()
        if body:
            number = len(segments) + 1
            segments.append(
                EvidenceSegment(
                    anchor=Anchor(kind="paragraph", ref=f"§{number}", locator={"paragraph": number, "line": start}),
                    text=body,
                    value_type="text",
                    value=body,
                )
            )

    for index, line in enumerate(text.splitlines(), start=1):
        if line.strip():
            if not block:
                start = index
            block.append(line)
        else:
            close()
            block = []
    close()
    return CanonicalSource(format=format, parser="plaintext", segments=tuple(segments), structure={"paragraphs": len(segments)})


def csv_rows(rows: list[list[str]]) -> CanonicalSource:
    # Le righe vuote restano fuori, ma ogni riga tiene il suo numero nel file:
    # l'ancora deve portare dove la riga e' davvero.
    numbered = [
        (number, [cell.strip() for cell in row])
        for number, row in enumerate(rows, start=1)
        if any(cell.strip() for cell in row)
    ]
    if not numbered:
        return CanonicalSource(format="csv", parser="plaintext", segments=(), structure={"rows": 0})
    (_, header), *data = numbered
    segments: list[EvidenceSegment] = []
    for number, row in data:
        cells = {
            (header[index] if index < len(header) and header[index] else f"colonna {index + 1}"): value
            for index, value in enumerate(row)
            if value
        }
        if not cells:
            continue
        pairs = [f"{name}: {value}" for name, value in cells.items()]
        segments.append(
            EvidenceSegment(
                anchor=Anchor(kind="row", ref=f"R{number}", locator={"row": number}),
                text="; ".join(pairs),
                value_type="row",
                value=cells,
            )
        )
    return CanonicalSource(
        format="csv",
        parser="plaintext",
        segments=tuple(segments),
        structure={"rows": len(rows), "columns": header},
    )
