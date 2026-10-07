"""Lettura dei file di event log in tabella: intestazione e righe di testo.

Il mapping (``mapping.py``) decide cosa significa ogni colonna; qui si legge e
basta. CSV con codifica e separatore riconosciuti; XES appiattito in una riga
per evento, con gli attributi del trace prefissati ``case:`` come fa la
convenzione di pm4py, cosi' il mapping li tratta come colonne qualsiasi.
"""

from __future__ import annotations

import csv
import io
from dataclasses import dataclass
from xml.etree.ElementTree import Element, ParseError

from defusedxml import ElementTree as SafeElementTree
from defusedxml.common import DefusedXmlException

from backend.workspace_services.source_ingestion import SourceFileError, decode_plain_text

CANDIDATE_DELIMITERS = ",;\t|"


class EventLogFileError(ValueError):
    """Il file non si legge come event log; il messaggio dice perche'."""


@dataclass(frozen=True, slots=True)
class Table:
    header: tuple[str, ...]
    rows: tuple[tuple[str, ...], ...]
    delimiter: str | None = None
    format: str = "csv"


def read_csv(payload: bytes, delimiter: str | None = None) -> Table:
    """Il CSV come tabella. Senza ``delimiter`` lo si riconosce dalle prime righe."""
    try:
        text = decode_plain_text(payload)
    except SourceFileError as exc:
        raise EventLogFileError(str(exc)) from exc
    if not text.strip():
        raise EventLogFileError("Il file è vuoto.")
    sep = delimiter or detect_delimiter(text)
    try:
        rows = [row for row in csv.reader(io.StringIO(text), delimiter=sep) if any(cell.strip() for cell in row)]
    except csv.Error as exc:
        raise EventLogFileError("Il CSV non è valido: controlla virgolette e separatori.") from exc
    header = tuple(cell.strip() for cell in rows[0])
    if len(header) < 2:
        raise EventLogFileError(
            "Il file ha una sola colonna: il separatore non è stato riconosciuto. Indicalo a mano."
        )
    duplicates = sorted({name for name in header if header.count(name) > 1})
    if duplicates:
        raise EventLogFileError(f"Colonne con lo stesso nome: {', '.join(duplicates)}.")
    width = len(header)
    body = tuple(tuple(cell.strip() for cell in (row + [""] * (width - len(row)))[:width]) for row in rows[1:])
    return Table(header=header, rows=body, delimiter=sep, format="csv")


def detect_delimiter(text: str) -> str:
    sample = "\n".join(text.splitlines()[:20])
    try:
        return csv.Sniffer().sniff(sample, delimiters=CANDIDATE_DELIMITERS).delimiter
    except csv.Error:
        # Il separatore piu' frequente nella prima riga: lo Sniffer rinuncia
        # quando le righe hanno campi vuoti in posizioni diverse.
        first = text.splitlines()[0]
        return max(CANDIDATE_DELIMITERS, key=first.count)


def read_xes(payload: bytes) -> Table:
    """Il log XES appiattito: una riga per evento, attributi del trace come ``case:<nome>``."""
    # Il file arriva da fuori: defusedxml rifiuta entita' esterne e espansioni
    # ricorsive (XXE, billion laughs) invece di eseguirle.
    try:
        root = SafeElementTree.fromstring(payload)
    except DefusedXmlException as exc:
        raise EventLogFileError("Il file XES contiene costrutti XML non ammessi (entità o DTD).") from exc
    except ParseError as exc:
        raise EventLogFileError("Il file XES non è un XML valido.") from exc
    traces = [element for element in root if _local(element.tag) == "trace"]
    if not traces:
        raise EventLogFileError("Il file XES non contiene tracce.")

    records: list[dict[str, str]] = []
    columns: list[str] = []
    for trace in traces:
        case_values = {f"case:{key}": value for key, value in _attributes(trace).items()}
        for event in (element for element in trace if _local(element.tag) == "event"):
            record = {**case_values, **_attributes(event)}
            records.append(record)
            for key in record:
                if key not in columns:
                    columns.append(key)
    if not records:
        raise EventLogFileError("Il file XES non contiene eventi.")
    header = tuple(columns)
    rows = tuple(tuple(record.get(column, "") for column in header) for record in records)
    return Table(header=header, rows=rows, format="xes")


def read_table(filename: str, payload: bytes, delimiter: str | None = None) -> Table:
    if filename.lower().endswith(".xes"):
        return read_xes(payload)
    if filename.lower().endswith((".csv", ".txt", ".tsv")):
        return read_csv(payload, delimiter)
    raise EventLogFileError("Formato non supportato: servono CSV o XES.")


def _attributes(element: Element) -> dict[str, str]:
    values: dict[str, str] = {}
    for child in element:
        key = child.get("key")
        if key is not None and child.get("value") is not None:
            values[key] = child.get("value", "")
    return values


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]
