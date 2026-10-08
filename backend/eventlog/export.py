"""Scrittura di un event log canonico in CSV e XES.

Un log simulato esce in una forma che il wizard di import rilegge senza
mapping inventato: stesse colonne, timestamp ISO 8601 in UTC. L'hash e' sul
contenuto scritto, cosi' due download dello stesso run sono byte per byte uguali.
"""

from __future__ import annotations

import csv
import hashlib
import io
from dataclasses import dataclass
from datetime import datetime, timezone
from xml.sax.saxutils import quoteattr

from backend.eventlog.model import CanonicalEvent, EventLog

CSV_COLUMNS = ("case_id", "activity", "enable_time", "start_time", "end_time", "resource", "role")


@dataclass(frozen=True, slots=True)
class Exported:
    content: bytes
    media_type: str
    extension: str
    sha256: str


def to_csv(log: EventLog) -> Exported:
    buffer = io.StringIO(newline="")
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(CSV_COLUMNS)
    for event in _ordered(log):
        writer.writerow([
            event.case_id,
            event.activity,
            _iso(event.enabled) if event.enabled else "",
            _iso(event.start) if event.start else "",
            _iso(event.end),
            event.resource or "",
            event.role or "",
        ])
    return _exported(buffer.getvalue(), "text/csv; charset=utf-8", "csv")


def to_xes(log: EventLog, *, metadata: dict[str, str | int] | None = None) -> Exported:
    """XES 1.0 con inizio e completamento come eventi separati (ciclo di vita standard)."""
    lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<log xes.version="1.0" xmlns="http://www.xes-standard.org/">',
        '  <extension name="Concept" prefix="concept" uri="http://www.xes-standard.org/concept.xesext"/>',
        '  <extension name="Time" prefix="time" uri="http://www.xes-standard.org/time.xesext"/>',
        '  <extension name="Lifecycle" prefix="lifecycle" uri="http://www.xes-standard.org/lifecycle.xesext"/>',
        '  <extension name="Organizational" prefix="org" uri="http://www.xes-standard.org/org.xesext"/>',
        '  <classifier name="Activity" keys="concept:name"/>',
    ]
    for key, value in (metadata or {}).items():
        tag = "int" if isinstance(value, int) and not isinstance(value, bool) else "string"
        lines.append(f"  <{tag} key={quoteattr(key)} value={quoteattr(str(value))}/>")
    by_case: dict[str, list[CanonicalEvent]] = {}
    for event in _ordered(log):
        by_case.setdefault(event.case_id, []).append(event)
    for case_id, events in by_case.items():
        lines.append("  <trace>")
        lines.append(f'    <string key="concept:name" value={quoteattr(case_id)}/>')
        for event in events:
            if event.start is not None:
                lines.extend(_xes_event(event, "start", event.start))
            lines.extend(_xes_event(event, "complete", event.end))
        lines.append("  </trace>")
    lines.append("</log>")
    return _exported("\n".join(lines) + "\n", "application/xml; charset=utf-8", "xes")


def _xes_event(event: CanonicalEvent, transition: str, moment: datetime) -> list[str]:
    out = [
        "    <event>",
        f'      <string key="concept:name" value={quoteattr(event.activity)}/>',
        f'      <string key="lifecycle:transition" value="{transition}"/>',
        f'      <date key="time:timestamp" value="{_iso(moment)}"/>',
    ]
    if event.enabled:
        out.append(f'      <date key="deliR:enabled" value="{_iso(event.enabled)}"/>')
    if event.resource:
        out.append(f'      <string key="org:resource" value={quoteattr(event.resource)}/>')
    if event.role:
        out.append(f'      <string key="org:role" value={quoteattr(event.role)}/>')
    out.append("    </event>")
    return out


def _ordered(log: EventLog) -> list[CanonicalEvent]:
    return sorted(
        log.events,
        key=lambda e: (e.start or e.end, e.end, _case_key(e.case_id), e.activity),
    )


def _case_key(case_id: str) -> tuple[int, int | str]:
    return (0, int(case_id)) if case_id.isdigit() else (1, case_id)


def _iso(moment: datetime) -> str:
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=timezone.utc)
    return moment.astimezone(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def _exported(text: str, media_type: str, extension: str) -> Exported:
    content = text.encode("utf-8")
    return Exported(content, media_type, extension, hashlib.sha256(content).hexdigest())
