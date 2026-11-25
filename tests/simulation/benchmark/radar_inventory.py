"""RAD-01: inventario e deduplica dei log del Research Radar.

    uv run python scripts/fetch_datasets.py fetch --collection radar
    uv run python scripts/fetch_datasets.py fetch bpic2012 bpic2013-incidents
    uv run python tests/simulation/benchmark/radar_inventory.py            # tutto il radar
    uv run python tests/simulation/benchmark/radar_inventory.py helpdesk   # solo alcune voci

Gira dentro ``protocol.selection_phase()``: la guardia degli holdout resta attiva. Per
ogni file di ogni voce del radar (anche dentro gli archivi non estratti) calcola lo
SHA-256 e lo confronta, per impronta e per nome, con i file dei log di sviluppo e con il
lucchetto degli holdout. Un file che porta il nome di un holdout, o la cui impronta
coincide con il lucchetto, si marca e **non si apre**: se ne calcola solo l'impronta
(``protocol.fingerprint``), mai gli eventi.

Per ogni log (XES, CSV, OCEL 2.0) riporta casi, eventi, attivita', periodo, risorse,
presenza di inizio e fine, osservabilita'; poi confronta il contenuto (attivita' e id
dei casi) con i log di sviluppo e con gli altri log del radar, per trovare le copie
con un'altra forma (un CSV ricavato da un XES, una partizione, un log simulato dallo
stesso processo).

Scrive ``radar/inventory.json`` (senza orari: stessi dati, stesso file) e
``radar/inventory.md``. Nel repo pubblico vanno solo impronte e conteggi, nessun evento.
"""

from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import io
import json
import re
import shutil
import sqlite3
import sys
import tarfile
import tempfile
import zipfile
from collections import Counter
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import BinaryIO
from xml.etree.ElementTree import iterparse

if __package__ in (None, ""):  # lanciato come script
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from scripts import fetch_datasets
from tests.simulation.benchmark import protocol

OUT = protocol.BENCHMARK / "radar"
DATASETS_DIR = protocol.ROOT / "datasets"
# I log di sviluppo letti dalla cache (gli altri sono in datasets/, nel repo).
DEVELOPMENT_CACHE = ("bpic2012", "bpic2013-incidents")

LOG_SUFFIXES = (".xes", ".xes.gz", ".csv", ".csv.gz", ".json", ".jsonocel", ".xmlocel", ".sqlite", ".xml", ".parquet")
ARCHIVE_SUFFIXES = (".zip", ".tar", ".tar.gz", ".tgz")
# Un archivio dentro un altro si legge in un file temporaneo fino a questa dimensione.
MAX_NESTED_ARCHIVE = 2 << 30
# Oltre questa dimensione un OCEL JSON non si carica (json.load tiene tutto in memoria).
MAX_OCEL_JSON = 3 << 30

# --------------------------------------------------------------------------- soglie del confronto

# Dichiarate prima di guardare i risultati; le stesse per ogni coppia di log.
SAME_ACTIVITIES = 0.9  # quota delle attivita' del log piu' piccolo presenti nell'altro
CONTAINED_CASES = 0.9  # quota dei casi di un log presenti nell'altro
OVERLAP_CASES = 0.1  # sovrapposizione parziale dei casi
OVERLAP_ACTIVITIES = 0.5
SAME_PROCESS_ACTIVITIES = 0.8  # Jaccard delle attivita': stesso processo con altri casi (es. simulato)
MIN_ACTIVITIES = 3
DISTINCTIVE_LENGTH = 5  # id dei casi lunghi almeno cosi' (90% del campione) si confrontano da soli

# Nomi normalizzati (minuscolo, solo lettere e cifre) con cui un log di sviluppo puo'
# comparire in un altro pacchetto. Il contenuto decide; il nome si dichiara comunque.
DEVELOPMENT_ALIASES = {
    "AcademicCredentials": ("academiccredentials",),
    "BPIC 2012": ("bpic2012", "bpic12", "bpi12", "bpi2012", "bpichallenge2012"),
    "BPIC 2017 W": ("bpic2017", "bpic17", "bpi17", "bpi2017", "bpichallenge2017"),
    "BPIC 2013 incidents": ("bpic2013", "bpic13", "bpi13", "bpi2013", "bpichallenge2013"),
    "Insurance_Claims": ("insuranceclaims",),
    "Loan_Application": ("loanapplication", "loanapp"),
    "Pharmacy": ("pharmacy",),
    "Procure_to_Pay": ("procuretopay",),
}
# Altri nomi degli holdout (dello stesso log o della stessa organizzazione e serie),
# oltre a quelli del lucchetto: un file che li porta non si apre.
HOLDOUT_EXTRA_ALIASES = {
    "bpic2015_municipality1": ("bpic2015", "bpic15", "bpichallenge2015"),
    "bpic2011_hospital": ("bpic2011", "bpic11", "bpichallenge2011", "hospitallog"),
    "consulta_data_mining": ("consultadatamining",),
    "confidential_2000": ("confidential",),
    "purchasing_example": ("purchasingexample",),
}


def normalized(text: str) -> str:
    return re.sub(r"[^a-z0-9]", "", text.lower())


# --------------------------------------------------------------------------- origine dei dati

# Origine dichiarata per voce del radar (dalla fonte, non dai dati): reale o sintetica,
# organizzazione e settore. ``simulated`` sono i segmenti di percorso dei log simulati
# dentro un pacchetto che contiene anche log reali.
@dataclass(frozen=True, slots=True)
class Origin:
    origin: str  # "reale" | "sintetico" | "misto" | "codice"
    organization: str
    sector: str
    simulated: tuple[str, ...] = ()


ORIGINS: dict[str, Origin] = {
    "bps-quality-framework": Origin("misto", "log del paper (Chapela-Campa et al. 2024)", "vari", ("synthetic", "simulated")),
    "simbank": Origin("sintetico", "simulatore di un processo di credito (KU Leuven)", "banca"),
    "procause": Origin("codice", "esperimenti controfattuali (KU Leuven)", "banca"),
    "bpic2019": Origin("reale", "multinazionale olandese di vernici e rivestimenti", "procurement"),
    "bpic2018": Origin("reale", "agenzia pagatrice tedesca (contributi agricoli UE)", "pubblica amministrazione"),
    "bpic2017-full": Origin("reale", "istituto finanziario olandese (stessa banca di BPIC 2012)", "banca"),
    "sepsis-cases": Origin("reale", "ospedale olandese (sistema ERP)", "sanita'"),
    "hospital-billing": Origin("reale", "ospedale olandese (sistema ERP)", "sanita'"),
    "road-traffic-fines": Origin("reale", "polizia locale italiana", "pubblica amministrazione"),
    "helpdesk": Origin("reale", "azienda italiana di software", "assistenza"),
    "ocel-container-logistics": Origin("sintetico", "logistica dei container (simulata)", "logistica"),
    "ocel-order-management": Origin("sintetico", "gestione ordini (simulata)", "vendite"),
    "ocel-procure-to-pay": Origin("sintetico", "procure-to-pay (simulato)", "procurement"),
    "ocel-steel-logistics": Origin("reale", "acciaieria (anonimizzata)", "logistica"),
    "ocel-state-aware": Origin("sintetico", "inventario e manutenzione (simulati)", "manifattura"),
    "ocel-standard-collection": Origin("misto", "collezione ocel-standard.org", "vari"),
    "ocel-lrms-simulated": Origin("sintetico", "O2C, P2P, assunzioni, ospedale (simulati)", "vari"),
    "bpic-ocel2": Origin("reale", "BPIC 2014 (Rabobank), 2016 (UWV), 2017 (banca di BPIC 2012), 2019", "vari"),
    "existential-drifts": Origin("sintetico", "log con drift generati", "nessuno"),
    "cdrift-set": Origin("sintetico", "log con drift generati", "nessuno"),
    "cdlg-drift-val": Origin("sintetico", "log con drift generati da CDLG", "nessuno"),
    "at-kde": Origin("misto", "log degli esperimenti di AT-KDE", "vari", ("simulated", "synthetic", "generated")),
    "agentsimulator": Origin("misto", "log degli esperimenti di AgentSimulator", "vari", ("simulated", "synthetic", "generated")),
    "prosit": Origin("misto", "log degli esperimenti di ProSiT", "vari", ("simulated", "synthetic", "generated")),
    "das-rp": Origin("misto", "log degli esperimenti di DAS", "vari", ("simulated", "synthetic", "generated")),
}
DEFAULT_ORIGIN = Origin("codice", "repository di codice", "nessuno", ("simulated", "synthetic", "generated", "test"))


# --------------------------------------------------------------------------- sorgenti


@dataclass(frozen=True, slots=True)
class Source:
    """Un file del radar, su disco o membro di un archivio (``archivio.zip!membro``)."""

    dataset: str
    path: str  # relativo alla cartella del dataset
    size: int
    opener: Callable[[], BinaryIO]

    @property
    def name(self) -> str:
        return self.path.rsplit("!", 1)[-1].rsplit("/", 1)[-1]

    @property
    def lower(self) -> str:
        return self.name.lower()


def _is_archive(name: str) -> bool:
    return name.lower().endswith(ARCHIVE_SUFFIXES)


def _extracted(directory: Path, archive: Path) -> bool:
    """``fetch_datasets`` ha gia' estratto l'archivio: i suoi file si leggono da disco."""
    return (directory / f".{archive.name}.extracted").exists()


def walk(dataset: str, directory: Path) -> Iterator[Source]:
    """Ogni file della voce, archivi non estratti compresi; mai la cartella ``.git``."""
    for path in sorted(directory.rglob("*")):
        relative = path.relative_to(directory)
        if not path.is_file() or ".git" in relative.parts or path.name.endswith(".extracted") or path.suffix == ".part":
            continue
        yield Source(dataset, relative.as_posix(), path.stat().st_size, lambda p=path: p.open("rb"))


@contextmanager
def _seekable(source: Source) -> Iterator[BinaryIO]:
    """Un archivio dentro un archivio: zipfile vuole un file con seek."""
    with source.opener() as raw:
        if raw.seekable():
            yield raw
            return
        with tempfile.TemporaryFile() as spool:
            shutil.copyfileobj(raw, spool, 1 << 20)
            spool.seek(0)
            yield spool


def members(source: Source) -> Iterator[Source]:
    """I file di un archivio come sorgenti, senza estrarli su disco."""
    prefix = f"{source.path}!"
    with _seekable(source) as handle:
        if zipfile.is_zipfile(handle):
            handle.seek(0)
            with zipfile.ZipFile(handle) as bundle:
                for info in bundle.infolist():
                    if not info.is_dir():
                        yield Source(source.dataset, prefix + info.filename, info.file_size, lambda b=bundle, i=info: b.open(i))
            return
        handle.seek(0)
        with tarfile.open(fileobj=handle, mode="r:*") as bundle:
            for info in bundle:
                if info.isfile():
                    yield Source(
                        source.dataset, prefix + info.name, info.size, lambda b=bundle, i=info: b.extractfile(i)  # type: ignore[return-value,misc]
                    )


# --------------------------------------------------------------------------- impronte


def sha256_stream(handle: BinaryIO) -> str:
    digest = hashlib.sha256()
    for block in iter(lambda: handle.read(1 << 20), b""):
        digest.update(block)
    return digest.hexdigest()


def _hashes(opener: Callable[[], BinaryIO], gz: bool) -> tuple[str, str | None]:
    """SHA-256 del file e, se e' compresso con gzip, del contenuto (stesso log, altra compressione)."""
    with opener() as handle:
        raw = sha256_stream(handle)
    if not gz:
        return raw, None
    try:
        with opener() as handle, gzip.GzipFile(fileobj=handle) as inner:
            return raw, sha256_stream(inner)
    except (OSError, EOFError):
        return raw, None


@dataclass(frozen=True, slots=True)
class HoldoutReference:
    by_hash: dict[str, str]  # sha256 -> id dell'holdout
    aliases: dict[str, str]  # nome normalizzato -> id dell'holdout


def holdout_reference() -> HoldoutReference:
    """Dal lucchetto: impronte, nomi dei file e dei log; piu' gli alias dichiarati qui."""
    by_hash: dict[str, str] = {}
    aliases: dict[str, str] = {}
    for holdout in protocol.load_lock()["holdouts"]:
        ident = holdout["id"]
        aliases[normalized(ident)] = ident
        for name in holdout["names"]:
            aliases[normalized(name)] = ident
        for item in holdout["files"]:
            by_hash[item["sha256"]] = ident
            aliases[normalized(protocol._stem(Path(item["path"]).name))] = ident
        for alias in HOLDOUT_EXTRA_ALIASES.get(ident, ()):
            aliases[alias] = ident
    return HoldoutReference(by_hash, aliases)


def holdout_by_name(source: Source, reference: HoldoutReference) -> str | None:
    """L'id dell'holdout se il file, o una cartella del suo percorso, ne porta il nome.

    Basta la guardia del protocollo o il nome normalizzato che contiene un alias: e'
    voluto largo, un falso allarme lascia fuori un file dall'inventario, non apre un holdout.
    """
    parts = [p for p in re.split(r"[/!]", source.path) if p]
    if protocol.is_holdout(source.path.replace("!", "/")):
        for part in reversed(parts):
            key = normalized(protocol._stem(part))
            for alias, ident in reference.aliases.items():
                if alias in key:
                    return ident
        return "holdout"  # la guardia lo blocca: una cartella o un file del lucchetto
    for part in parts:
        key = normalized(protocol._stem(part))
        for alias, ident in reference.aliases.items():
            if alias and alias in key:
                return ident
    return None


def development_by_name(source: Source) -> str | None:
    key = normalized(source.path)
    for log, aliases in DEVELOPMENT_ALIASES.items():
        if any(alias in key for alias in aliases):
            return log
    return None


# --------------------------------------------------------------------------- lettura dei log

_FORMATS = ("%Y/%m/%d %H:%M:%S", "%d-%m-%Y %H:%M:%S", "%d-%m-%Y %H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%Y%m%d%H%M%S")


def parse_instant(raw: str | None) -> datetime | None:
    """Un istante in UTC senza fuso; None se non si riconosce."""
    if not raw:
        return None
    text = raw.strip()
    if not text:
        return None
    if text.isdigit() and len(text) >= 9:  # epoch in secondi o millisecondi
        value = int(text)
        return datetime(1970, 1, 1) + timedelta(seconds=value / 1000 if len(text) >= 13 else value)
    try:
        instant = datetime.fromisoformat(text.replace("/", "-") if text[:4].isdigit() else text)
    except ValueError:
        for pattern in _FORMATS:
            try:
                instant = datetime.strptime(text, pattern)
                break
            except ValueError:
                continue
        else:
            return None
    if instant.tzinfo is not None:
        instant = instant.astimezone(UTC).replace(tzinfo=None)
    return instant


@dataclass(slots=True)
class Accumulator:
    """Conteggi di un log letto in streaming: niente eventi in memoria, solo insiemi di nomi."""

    kind: str = "piatto"
    events: int = 0
    case_ids: set[str] = field(default_factory=set)
    activities: Counter[str] = field(default_factory=Counter)
    resources: set[str] = field(default_factory=set)
    has_resource_column: bool = False
    lifecycle: Counter[str] = field(default_factory=Counter)
    with_start: int = 0
    with_end: int = 0
    unparsed: int = 0
    first: datetime | None = None
    last: datetime | None = None
    objects: int = 0
    object_types: set[str] = field(default_factory=set)
    rows: list[str] = field(default_factory=list)

    def instant(self, raw: str | None) -> datetime | None:
        moment = parse_instant(raw)
        if raw and moment is None:
            self.unparsed += 1
        if moment is not None:
            self.first = moment if self.first is None or moment < self.first else self.first
            self.last = moment if self.last is None or moment > self.last else self.last
        return moment

    def add(self, case: str | None, activity: str | None, start: str | None, end: str | None,
            resource: str | None, lifecycle: str | None = None) -> None:
        self.events += 1
        if case:
            self.case_ids.add(case)
        if activity:
            self.activities[activity] += 1
        if resource:
            self.resources.add(resource)
        if lifecycle:
            self.lifecycle[lifecycle.lower()] += 1
        if start and self.instant(start):
            self.with_start += 1
        moment = self.instant(end)
        if moment:
            self.with_end += 1
        self.rows.append(f"{case}\x1f{activity}\x1f{moment.isoformat() if moment else ''}")


def _text(source: Source) -> Callable[[], io.TextIOWrapper]:
    def opener() -> io.TextIOWrapper:
        handle = source.opener()
        if source.lower.endswith(".gz"):
            handle = gzip.GzipFile(fileobj=handle)  # type: ignore[assignment]
        return io.TextIOWrapper(handle, encoding="utf-8", errors="replace", newline="")

    return opener


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def read_xes(source: Source) -> Accumulator:
    """XES in streaming: id del caso dalla traccia, attributi di primo livello dell'evento."""
    acc = Accumulator()
    with source.opener() as raw:
        handle: BinaryIO = gzip.GzipFile(fileobj=raw) if source.lower.endswith(".gz") else raw  # type: ignore[assignment]
        depth = 0
        trace_depth = event_depth = -1
        case: str | None = None
        attrs: dict[str, str] = {}
        root = None
        for kind, element in iterparse(handle, events=("start", "end")):
            tag = _local(element.tag)
            if kind == "start":
                depth += 1
                if root is None:
                    root = element
                if tag == "trace":
                    trace_depth, case = depth, None
                elif tag == "event":
                    event_depth, attrs = depth, {}
                continue
            if event_depth > 0 and depth == event_depth + 1 and element.get("key"):
                attrs[element.get("key", "")] = element.get("value", "")
            elif trace_depth > 0 and event_depth < 0 and depth == trace_depth + 1 and element.get("key") == "concept:name":
                case = element.get("value")
            elif tag == "event":
                lifecycle = attrs.get("lifecycle:transition")
                timestamp = attrs.get("time:timestamp")
                is_start = (lifecycle or "").lower() == "start"
                acc.add(case, attrs.get("concept:name"), timestamp if is_start else None,
                        None if is_start else timestamp, attrs.get("org:resource"), lifecycle)
                acc.has_resource_column |= "org:resource" in attrs
                event_depth = -1
                element.clear()
            elif tag == "trace":
                trace_depth = -1
                element.clear()
                if root is not None:
                    root.clear()
            depth -= 1
    return acc


_CASE = ("caseconceptname", "caseid", "case", "casename", "traceid", "caseidentifier", "cid")
_ACTIVITY = ("conceptname", "activity", "activityname", "activityid", "task", "eventname", "action", "event")
_START = ("starttime", "starttimestamp", "start", "startdate", "timestart")
_END = ("endtime", "endtimestamp", "completetimestamp", "completetime", "timetimestamp", "timestamp", "end", "enddate", "time", "datetime")
_RESOURCE = ("orgresource", "resource", "user", "agent", "performer")
_LIFECYCLE = ("lifecycletransition", "lifecycle")


def _column(header: list[str], candidates: tuple[str, ...]) -> str | None:
    keys = {normalized(column): column for column in header}
    return next((keys[c] for c in candidates if c in keys), None)


def read_csv(source: Source) -> Accumulator | None:
    """Un CSV e' un log se ha caso, attivita' e almeno un istante; altrimenti None (una tabella)."""
    with _text(source)() as handle:
        sample = handle.read(1 << 16)
    delimiter = max(",;\t|", key=lambda d: sample.split("\n", 1)[0].count(d))
    with _text(source)() as handle:
        reader = csv.DictReader(handle, delimiter=delimiter)
        header = reader.fieldnames or []
        case, activity = _column(header, _CASE), _column(header, _ACTIVITY)
        start, end = _column(header, _START), _column(header, _END)
        resource, lifecycle = _column(header, _RESOURCE), _column(header, _LIFECYCLE)
        if not case or not activity or not (start or end) or case == activity:
            return None
        acc = Accumulator(has_resource_column=resource is not None)
        for row in reader:
            stage = (row.get(lifecycle) or "").lower() if lifecycle else ""
            stamp = row.get(end) if end else None
            if start:
                acc.add(row.get(case), row.get(activity), row.get(start), stamp, row.get(resource) if resource else None)
            elif stage == "start":
                acc.add(row.get(case), row.get(activity), stamp, None, row.get(resource) if resource else None, stage)
            else:
                acc.add(row.get(case), row.get(activity), None, stamp, row.get(resource) if resource else None, stage or None)
    return acc


def _ocel_add(acc: Accumulator, event_type: str | None, time: str | None, related: list[str]) -> None:
    acc.events += 1
    if event_type:
        acc.activities[event_type] += 1
    moment = acc.instant(time)
    if moment:
        acc.with_end += 1
    acc.case_ids.update(related)
    acc.rows.append(f"{','.join(sorted(related))}\x1f{event_type}\x1f{moment.isoformat() if moment else ''}")


def read_ocel_json(source: Source) -> Accumulator | None:
    """OCEL 2.0 (``objects``/``events``) o 1.0 (``ocel:events``) in JSON; None se non e' un OCEL."""
    with source.opener() as handle:
        head = handle.read(1 << 16)
    if not any(marker in head for marker in (b'"objectTypes"', b'"eventTypes"', b'"ocel:events"', b'"ocel:global-log"')):
        return None
    acc = Accumulator(kind="object-centric")
    if source.size > MAX_OCEL_JSON:
        acc.unparsed = -1  # troppo grande per json.load: solo l'impronta
        return acc
    with source.opener() as handle:
        data = json.load(handle)
    if "ocel:events" in data:
        events = data["ocel:events"].values() if isinstance(data["ocel:events"], dict) else data["ocel:events"]
        objects = data.get("ocel:objects", {})
        for event in events:
            _ocel_add(acc, event.get("ocel:activity"), event.get("ocel:timestamp"), [str(o) for o in event.get("ocel:omap", [])])
        values = objects.values() if isinstance(objects, dict) else objects
        acc.objects = len(objects)
        acc.object_types = {str(o.get("ocel:type")) for o in values}
        return acc
    for event in data.get("events", []):
        related = [str(r.get("objectId")) for r in event.get("relationships") or []]
        _ocel_add(acc, event.get("type"), event.get("time"), related)
    acc.objects = len(data.get("objects", []))
    acc.object_types = {str(o.get("type")) for o in data.get("objects", [])}
    return acc


def read_ocel_sqlite(source: Source) -> Accumulator | None:
    """OCEL 2.0 in SQLite: ``event``, ``object``, ``event_object`` e una tabella ``event_<tipo>`` con l'istante."""
    with tempfile.TemporaryDirectory() as scratch:
        path = Path(scratch) / "log.sqlite"
        with source.opener() as raw, path.open("wb") as out:
            shutil.copyfileobj(raw, out, 1 << 20)
        connection = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
        try:
            tables = {row[0] for row in connection.execute("select name from sqlite_master where type='table'")}
            if not {"event", "object"} <= tables:
                return None
            times: dict[str, str] = {}
            for table in sorted(t for t in tables if t.startswith("event_") and t not in ("event_object", "event_map_type")):
                columns = {row[1] for row in connection.execute(f'pragma table_info("{table}")')}
                if {"ocel_id", "ocel_time"} <= columns:
                    times.update((str(i), str(t)) for i, t in connection.execute(f'select ocel_id, ocel_time from "{table}"'))
            related: dict[str, list[str]] = {}
            if "event_object" in tables:
                for event_id, object_id in connection.execute("select ocel_event_id, ocel_object_id from event_object"):
                    related.setdefault(str(event_id), []).append(str(object_id))
            acc = Accumulator(kind="object-centric")
            for event_id, event_type in connection.execute("select ocel_id, ocel_type from event"):
                _ocel_add(acc, event_type, times.get(str(event_id)), related.get(str(event_id), []))
            acc.objects = connection.execute("select count(*) from object").fetchone()[0]
            acc.object_types = {str(row[0]) for row in connection.execute("select distinct ocel_type from object")}
            return acc
        finally:
            connection.close()


def read_ocel_xml(source: Source) -> Accumulator | None:
    """OCEL 2.0 in XML (``<log><object-types>…<events>``), in streaming."""
    acc = Accumulator(kind="object-centric")
    with source.opener() as handle:
        for kind, element in iterparse(handle, events=("end",)):
            tag = _local(element.tag)
            if tag == "event" and element.get("type") is not None:
                related = [o.get("object-id", "") for o in element.iter() if _local(o.tag) == "relationship"]
                _ocel_add(acc, element.get("type"), element.get("time"), related)
                element.clear()
            elif tag == "object" and element.get("type") is not None:
                acc.objects += 1
                acc.object_types.add(element.get("type", ""))
                element.clear()
    return acc if acc.events or acc.objects else None


def read_log(source: Source) -> Accumulator | None:
    """Il lettore giusto per il file; None se non e' un event log."""
    name = source.lower
    if name.endswith((".xes", ".xes.gz")):
        return read_xes(source)
    if name.endswith((".csv", ".csv.gz")):
        return read_csv(source)
    if name.endswith((".json", ".jsonocel")):
        return read_ocel_json(source)
    if name.endswith(".sqlite"):
        return read_ocel_sqlite(source)
    if name.endswith((".xmlocel", ".xml")):
        with source.opener() as handle:
            head = handle.read(4096).lower()
        if b"<log" in head and b"xes" in head:
            return read_xes(source)
        if b"object-types" in head or b"<ocel" in head or name.endswith(".xmlocel"):
            return read_ocel_xml(source)
    return None


# --------------------------------------------------------------------------- statistiche


@dataclass(slots=True)
class LogStats:
    kind: str
    cases: int
    events: int
    activities: int
    resources: int | None
    first: str | None
    last: str | None
    start_share: float
    end_share: float
    observability: str
    objects: int | None = None
    object_types: int | None = None
    unparsed_instants: int = 0


def is_simulated(source: Source, origin: Origin) -> bool:
    lowered = source.path.lower()
    return origin.origin == "sintetico" or any(marker in lowered for marker in origin.simulated)


def stats(acc: Accumulator, source: Source, origin: Origin) -> LogStats:
    instances = max(acc.with_end, acc.with_start) or acc.events
    if acc.lifecycle.get("start"):  # una riga per transizione: le istanze sono le fini
        instances = max(acc.lifecycle.get("complete", 0), acc.with_end) or acc.events
    start_share = round(min(1.0, acc.with_start / instances), 4) if instances else 0.0
    end_share = round(min(1.0, acc.with_end / instances), 4) if instances else 0.0
    resource_share = 1.0 if acc.has_resource_column and acc.resources else 0.0
    if acc.kind == "object-centric":
        observability = "object-centric"
    elif is_simulated(source, origin):
        observability = "sintetico"
    elif start_share >= protocol.MIN_START_COVERAGE and resource_share and end_share >= 0.95:
        observability = "completa"
    else:
        observability = "parziale"
    return LogStats(
        kind=acc.kind,
        cases=len(acc.case_ids) if acc.kind == "piatto" else 0,
        events=acc.events,
        activities=len(acc.activities),
        resources=len(acc.resources) if acc.has_resource_column else None,
        first=acc.first.date().isoformat() if acc.first else None,
        last=acc.last.date().isoformat() if acc.last else None,
        start_share=start_share,
        end_share=end_share,
        observability=observability,
        objects=acc.objects if acc.kind == "object-centric" else None,
        object_types=len(acc.object_types) if acc.kind == "object-centric" else None,
        unparsed_instants=acc.unparsed,
    )


@dataclass(slots=True)
class Signature:
    """Cio' che serve per confrontare due log senza tenerne gli eventi."""

    label: str
    dataset: str
    activities: frozenset[str]
    cases: frozenset[str]
    content: str  # SHA-256 delle righe (caso, attivita', fine) ordinate: stesso log in un'altra forma


def signature(acc: Accumulator, label: str, dataset: str) -> Signature:
    digest = hashlib.sha256()
    for row in sorted(acc.rows):
        digest.update(row.encode("utf-8", "replace") + b"\n")
    return Signature(label, dataset, frozenset(a.strip().lower() for a in acc.activities),
                     frozenset(acc.case_ids), digest.hexdigest())


def distinctive(case_ids: frozenset[str]) -> bool:
    """Id dei casi che non si ripetono per caso fra log diversi (non 1, 2, 3…): almeno 5 caratteri."""
    sample = sorted(case_ids)[:: max(1, len(case_ids) // 1000)]
    return bool(sample) and sum(len(c) >= DISTINCTIVE_LENGTH for c in sample) / len(sample) >= CONTAINED_CASES


def compare(a: Signature, b: Signature) -> str | None:
    """La relazione di ``a`` con ``b`` secondo le soglie dichiarate in cima al file; None se nessuna."""
    if a.content == b.content and a.cases:
        return "stesso contenuto"
    if distinctive(a.cases) and distinctive(b.cases):
        # Stessi casi anche con le attivita' ricodificate (es. numeri al posto dei nomi).
        shared = len(a.cases & b.cases)
        if shared / len(b.cases) >= CONTAINED_CASES:
            return f"contiene i casi di {b.label} ({shared / len(b.cases):.0%})"
        if shared / len(a.cases) >= CONTAINED_CASES:
            return f"casi contenuti in {b.label} ({shared / len(a.cases):.0%})"
    if len(a.activities) < MIN_ACTIVITIES or len(b.activities) < MIN_ACTIVITIES:
        return None
    common = len(a.activities & b.activities)
    smaller = min(len(a.activities), len(b.activities))
    jaccard = common / len(a.activities | b.activities)
    shared = len(a.cases & b.cases) if common else 0
    a_in_b = shared / len(a.cases) if a.cases else 0.0
    b_in_a = shared / len(b.cases) if b.cases else 0.0
    if common / smaller >= SAME_ACTIVITIES and b_in_a >= CONTAINED_CASES:
        return f"contiene {b.label} ({b_in_a:.0%} dei casi)"
    if common / smaller >= SAME_ACTIVITIES and a_in_b >= CONTAINED_CASES:
        return f"contenuto in {b.label} ({a_in_b:.0%} dei casi)"
    if common / smaller >= OVERLAP_ACTIVITIES and max(a_in_b, b_in_a) >= OVERLAP_CASES:
        return f"sovrapposto a {b.label} ({max(a_in_b, b_in_a):.0%} dei casi)"
    if jaccard >= SAME_PROCESS_ACTIVITIES:
        return f"stesso processo di {b.label} (attivita' {jaccard:.0%} in comune)"
    return None


# --------------------------------------------------------------------------- riferimenti di sviluppo


@dataclass(slots=True)
class DevelopmentReference:
    by_hash: dict[str, str]  # sha256 (file o contenuto gz) -> file di sviluppo
    signatures: list[Signature]


def _development_label(path: Path) -> str:
    stem = protocol._stem(path.name)
    stem = re.sub(r"_(train|test)$", "", stem)
    return f"sviluppo {stem}"


def development_reference() -> DevelopmentReference:
    """Impronte di ogni file di ``datasets/`` e dei log di sviluppo in cache; firme dei log."""
    by_hash: dict[str, str] = {}
    signatures: dict[str, Signature] = {}
    files = [p for p in sorted(DATASETS_DIR.rglob("*")) if p.is_file()]
    manifest = fetch_datasets.load_manifest()
    for ident in DEVELOPMENT_CACHE:
        cached = fetch_datasets.dataset_path(manifest[ident]) / manifest[ident]["file"]
        if not cached.is_file():
            raise SystemExit(f"manca {cached}: uv run python scripts/fetch_datasets.py fetch {ident}")
        files.append(cached)
    for path in files:
        relative = path.relative_to(protocol.ROOT).as_posix() if path.is_relative_to(protocol.ROOT) else f"cache/{path.parent.name}/{path.name}"
        raw, content = _hashes(lambda p=path: p.open("rb"), path.name.endswith(".gz"))
        by_hash.setdefault(raw, relative)
        if content:
            by_hash.setdefault(content, relative)
        source = Source("sviluppo", relative, path.stat().st_size, lambda p=path: p.open("rb"))
        if not source.lower.endswith((".csv.gz", ".csv", ".xes.gz", ".xes")):
            continue
        acc = read_log(source)
        if acc is None or not acc.events:
            continue
        label = _development_label(path)
        # train e test sono parti dello stesso log: la firma e' una per log (l'unione).
        if label in signatures:
            previous = signatures[label]
            sig = signature(acc, label, "sviluppo")
            signatures[label] = Signature(label, "sviluppo", previous.activities | sig.activities,
                                          previous.cases | sig.cases, previous.content)
        else:
            signatures[label] = signature(acc, label, "sviluppo")
    return DevelopmentReference(by_hash, list(signatures.values()))


# --------------------------------------------------------------------------- inventario


@dataclass(slots=True)
class FileRecord:
    dataset: str
    path: str  # con il nome redatto se e' un holdout
    bytes: int
    sha256: str
    holdout: str | None = None  # "holdout:<id> (impronta|nome)"
    development: list[str] = field(default_factory=list)  # coincidenze con i log di sviluppo
    radar: list[str] = field(default_factory=list)  # coincidenze con altri log del radar
    log: LogStats | None = None
    note: str | None = None


def redacted(path: str, ident: str) -> str:
    """Il percorso senza il nome dell'holdout (il test dei nomi di PROTO-01 lo vieta nel repo)."""
    parts = re.split(r"([/!])", path)
    return "".join(f"[nome di un holdout: {ident}]" if i == len(parts) - 1 else p for i, p in enumerate(parts))


@dataclass(slots=True)
class Inventory:
    records: list[FileRecord] = field(default_factory=list)
    other_files: Counter[str] = field(default_factory=Counter)  # file che non sono log, per voce
    missing: list[str] = field(default_factory=list)
    signatures: list[tuple[FileRecord, Signature]] = field(default_factory=list)


def inspect(source: Source, inventory: Inventory, holdouts: HoldoutReference, development: DevelopmentReference,
            origin: Origin, skip_archive: bool) -> None:
    named = holdout_by_name(source, holdouts)
    if named:
        # Non si apre: solo l'impronta, per dire se e' proprio il file del lucchetto.
        digest = protocol.fingerprint(source.opener)
        match = holdouts.by_hash.get(digest)
        how = "impronta e nome" if match else "nome"
        inventory.records.append(FileRecord(
            source.dataset, redacted(source.path, named), source.size, digest, holdout=f"holdout:{match or named} ({how})",
            note="non aperto: porta il nome di un log holdout di PROTO-01",
        ))
        return
    raw, content = _hashes(source.opener, source.lower.endswith(".gz"))
    if raw in holdouts.by_hash:
        inventory.records.append(FileRecord(
            source.dataset, source.path, source.size, raw, holdout=f"holdout:{holdouts.by_hash[raw]} (impronta)",
            note="non aperto: coincide con un file del lucchetto",
        ))
        return
    record = FileRecord(source.dataset, source.path, source.size, raw)
    for digest in (raw, content):
        if digest and digest in development.by_hash:
            record.development.append(f"stessa impronta di {development.by_hash[digest]}")
    alias = development_by_name(source)
    if alias:
        record.development.append(f"nome simile a {alias}")
    if _is_archive(source.name):
        inventory.records.append(record)
        if skip_archive:
            record.note = "archivio estratto da fetch_datasets: i file si leggono da disco"
            return
        if source.size > MAX_NESTED_ARCHIVE and "!" in source.path:
            record.note = "archivio annidato oltre il limite: solo l'impronta"
            return
        try:
            for member in members(source):
                inspect(member, inventory, holdouts, development, origin, skip_archive=False)
        except (tarfile.TarError, zipfile.BadZipFile, OSError, EOFError) as exc:
            record.note = f"archivio non leggibile: {exc}"
        return
    acc = None
    if source.lower.endswith(LOG_SUFFIXES):
        try:
            acc = read_log(source)
        except (OSError, EOFError, ValueError, UnicodeError, csv.Error, sqlite3.Error, SyntaxError) as exc:
            record.note = f"non leggibile come log: {type(exc).__name__}: {str(exc)[:120]}"
    if acc is None or not acc.events:
        if record.development or record.note:
            inventory.records.append(record)
        else:
            inventory.other_files[source.dataset] += 1
        return
    record.log = stats(acc, source, origin)
    if acc.unparsed == -1:
        record.note = "OCEL oltre il limite di json.load: solo l'impronta"
    inventory.records.append(record)
    sig = signature(acc, f"{source.dataset}:{source.path}", source.dataset)
    record.development += [r for d in development.signatures if (r := compare(sig, d))]
    inventory.signatures.append((record, sig))


def cross_compare(inventory: Inventory) -> None:
    """Ogni log del radar contro i log delle altre voci del radar (copie fra pacchetti)."""
    entries = inventory.signatures
    for i, (record, sig) in enumerate(entries):
        for other_record, other in entries[i + 1:]:
            if other.dataset == sig.dataset:
                continue
            relation = compare(sig, other)
            if relation:
                record.radar.append(relation)
                back = compare(other, sig)
                if back:
                    other_record.radar.append(back)


def build(ids: list[str]) -> Inventory:
    manifest = fetch_datasets.load_manifest()
    holdouts = holdout_reference()
    development = development_reference()
    inventory = Inventory()
    for ident in ids:
        entry = manifest[ident]
        directory = fetch_datasets.dataset_path(entry)
        if not directory.is_dir():
            inventory.missing.append(ident)
            continue
        origin = ORIGINS.get(ident, DEFAULT_ORIGIN)
        for source in walk(ident, directory):
            path = directory / source.path
            inspect(source, inventory, holdouts, development, origin,
                    skip_archive=_is_archive(source.name) and _extracted(directory, path))
        print(f"ok  {ident}", file=sys.stderr)
    cross_compare(inventory)
    return inventory


# --------------------------------------------------------------------------- report


def to_json(inventory: Inventory, ids: list[str]) -> dict:
    manifest = fetch_datasets.load_manifest()
    return {
        "point": "RAD-01, docs/vpt/PLAN.md",
        "lock_digest": protocol.lock_digest(),
        "thresholds": {
            "same_activities": SAME_ACTIVITIES, "contained_cases": CONTAINED_CASES, "overlap_cases": OVERLAP_CASES,
            "overlap_activities": OVERLAP_ACTIVITIES, "same_process_activities": SAME_PROCESS_ACTIVITIES,
        },
        "datasets": {
            ident: {
                "license": manifest[ident]["license"],
                "source": manifest[ident]["source"],
                **asdict(ORIGINS.get(ident, DEFAULT_ORIGIN)),
                "other_files": inventory.other_files.get(ident, 0),
                "downloaded": ident not in inventory.missing,
            }
            for ident in ids
        },
        "files": [asdict(record) for record in sorted(inventory.records, key=lambda r: (r.dataset, r.path))],
    }


def _fmt(value: float | int | None) -> str:
    if value is None:
        return "—"
    if isinstance(value, float):
        return f"{value:.0%}"
    return f"{value:,}".replace(",", ".")


def _relations(record: dict) -> str:
    parts = [p for p in record["development"] if not p.startswith("nome simile")]
    names = [p for p in record["development"] if p.startswith("nome simile")]
    text = "; ".join(parts[:3] + record["radar"][:2] + names[:1])
    more = len(parts) + len(record["radar"]) - len(parts[:3]) - len(record["radar"][:2])
    return (text + (f"; +{more}" if more > 0 else "")).replace("|", "/") or "—"


def to_markdown(report: dict) -> str:
    files = report["files"]
    logs = [f for f in files if f["log"]]
    lines = [
        "# Inventario del Research Radar (RAD-01)",
        "",
        "Generato da `tests/simulation/benchmark/radar_inventory.py` dentro `protocol.selection_phase()`",
        f"(lucchetto degli holdout `{report['lock_digest'][:12]}…`). Non modificare a mano: rilancia lo script.",
        "Dettaglio completo, con le impronte, in `inventory.json`.",
        "",
        "Osservabilita': **completa** = inizio su almeno il 95% delle attivita', fine e risorse;",
        "**parziale** = manca qualcosa; **sintetico** = log generato da un simulatore; **object-centric** = OCEL.",
        "Le relazioni con i log di sviluppo e con le altre voci vengono da impronta (SHA-256 del file o del",
        "contenuto compresso), nome e contenuto (attivita' e id dei casi; soglie in testa allo script).",
        "",
        "## Holdout di PROTO-01",
        "",
    ]
    held = [f for f in files if f["holdout"]]
    if held:
        lines += ["| Voce | File (nome redatto) | Coincidenza | Nota |", "| --- | --- | --- | --- |"]
        lines += [f"| `{f['dataset']}` | `{f['path']}` | {f['holdout']} | {f['note']} |" for f in held]
    else:
        lines.append("Nessun file del radar coincide con un holdout, ne' per impronta ne' per nome.")
    lines += ["", "## Per voce", "", "| Voce | Origine | Settore | Log | Altri file | Holdout | Legati allo sviluppo |",
              "| --- | --- | --- | --- | --- | --- | --- |"]
    for ident, meta in report["datasets"].items():
        mine = [f for f in files if f["dataset"] == ident]
        own_logs = [f for f in mine if f["log"]]
        dev = [f for f in own_logs if any(not d.startswith("nome simile") for d in f["development"])]
        status = "" if meta["downloaded"] else " (non scaricato)"
        lines.append(
            f"| `{ident}`{status} | {meta['origin']} | {meta['sector']} | {len(own_logs)} | {meta['other_files']} | "
            f"{sum(1 for f in mine if f['holdout'])} | {len(dev)} |"
        )
    lines += ["", "## Log", ""]
    for ident in report["datasets"]:
        own = [f for f in logs if f["dataset"] == ident]
        if not own:
            continue
        lines += [f"### `{ident}`", "",
                  "| File | Casi | Eventi | Attivita' | Periodo | Risorse | Inizio | Fine | Osservabilita' | Relazioni |",
                  "| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |"]
        for f in own:
            log = f["log"]
            cases = _fmt(log["cases"]) if log["kind"] == "piatto" else f"{_fmt(log['objects'])} oggetti / {log['object_types']} tipi"
            period = f"{log['first']} → {log['last']}" if log["first"] else "—"
            lines.append(
                f"| `{f['path']}` | {cases} | {_fmt(log['events'])} | {log['activities']} | {period} | "
                f"{_fmt(log['resources'])} | {_fmt(log['start_share'])} | {_fmt(log['end_share'])} | "
                f"{log['observability']} | {_relations(f)} |"
            )
        lines.append("")
    notes = [f for f in files if f["note"] and not f["holdout"] and not f["log"]]
    if notes:
        lines += ["## Note sui file", "", "| Voce | File | Nota |", "| --- | --- | --- |"]
        lines += [f"| `{f['dataset']}` | `{f['path']}` | {f['note'].replace('|', '/')} |" for f in notes]
    return "\n".join(lines) + "\n"


def radar_ids() -> list[str]:
    return [i for i, e in fetch_datasets.load_manifest().items() if e.get("collection") == "radar"]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("ids", nargs="*", help="voci del radar (default: tutte)")
    parser.add_argument("--out", type=Path, default=OUT)
    args = parser.parse_args(argv)
    ids = args.ids or radar_ids()
    unknown = sorted(set(ids) - set(radar_ids()))
    if unknown:
        parser.error(f"non sono voci del radar: {', '.join(unknown)}")
    with protocol.selection_phase():
        inventory = build(ids)
    report = to_json(inventory, ids)
    args.out.mkdir(parents=True, exist_ok=True)
    (args.out / "inventory.json").write_text(json.dumps(report, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    (args.out / "inventory.md").write_text(to_markdown(report), encoding="utf-8")
    held = sum(1 for f in report["files"] if f["holdout"])
    print(f"{sum(1 for f in report['files'] if f['log'])} log, {held} file holdout (non aperti), mancano: {inventory.missing}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
