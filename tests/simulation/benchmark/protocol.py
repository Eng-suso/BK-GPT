"""PROTO-01: il protocollo sperimentale di G3b in codice.

Il documento e' ``docs/vpt/PROTOCOL.md``; qui ci sono le parti che il codice deve
rispettare:

- i log holdout, congelati per hash in ``protocol/holdout.lock.json``. Nessun
  codice di selezione li legge: una guardia (``sys.addaudithook``) rifiuta
  l'apertura di ogni file che porta il nome di un log holdout, in qualsiasi
  cartella e con qualsiasi estensione da log, finche' non si entra in
  ``final_evaluation`` con l'impronta del lucchetto. ``test_protocol.py``
  fallisce se il codice di selezione li apre o li nomina;
- i log di sviluppo, con la loro categoria (osservabilita' completa, parziale,
  sintetici con verita' nota) e la divisione train / validazione / test;
- le regole di identificabilita': quali metriche un log permette di validare,
  calcolate dai dati e mai dai modelli. Una metrica che non passa e'
  ``NOT VALIDATED`` con il motivo, e il log resta nel benchmark.

La guardia vede le aperture di Python (``open``, ``io``, ``gzip``, ``zipfile``,
``pandas`` con il motore di default, ``os.open``); una libreria che apre i file
da codice nativo la scavalca: per questo il test controlla anche che il codice di
selezione non nomini i log holdout.
"""

from __future__ import annotations

import hashlib
import json
import math
import os
import sys
import threading
from collections import Counter
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Literal

from scripts import fetch_datasets
from tests.simulation.benchmark.log_distance import Event, cases

BENCHMARK = Path(__file__).resolve().parent
ROOT = BENCHMARK.parents[2]
LOCK_PATH = BENCHMARK / "protocol" / "holdout.lock.json"
PROTOCOL_DOC = ROOT / "docs" / "vpt" / "PROTOCOL.md"

# Estensioni con cui un log (o una sua copia convertita) puo' comparire su disco. Non
# ci sono .json e .xml: con nomi generici come "production" bloccherebbero configurazioni.
LOG_SUFFIXES = (".xes", ".xes.gz", ".csv", ".csv.gz", ".zip", ".parquet", ".bpmn", ".pkl")


class HoldoutAccessError(PermissionError):
    """Un log holdout aperto fuori dalla valutazione finale."""


# --------------------------------------------------------------------------- lucchetto


def lock_digest(path: Path = LOCK_PATH) -> str:
    """SHA-256 del lucchetto: cambia se cambia anche un solo log holdout o una regola.

    Il file e' LF anche su Windows (``.gitattributes``): l'impronta non dipende dal checkout.
    """
    return hashlib.sha256(path.read_bytes()).hexdigest()


@cache
def load_lock(path: Path = LOCK_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


@dataclass(frozen=True, slots=True)
class BlockedNames:
    names: frozenset[str]  # nomi di file esatti (minuscolo)
    stems: frozenset[str]  # nomi senza estensione: bloccati con ogni estensione da log
    folders: frozenset[str]  # cartelle chiuse per intero: i dataset holdout e le loro radici


def _stem(name: str) -> str:
    return name.split(".", 1)[0]


@cache
def blocked_names(path: Path = LOCK_PATH) -> BlockedNames:
    lock = load_lock(path)
    names: set[str] = set()
    stems: set[str] = set()
    folders: set[str] = set()
    for holdout in lock["holdouts"]:
        folders.add(holdout["dataset"].lower())
        for item in holdout["files"]:
            relative = Path(item["path"])
            names.add(relative.name.lower())
            stems.add(_stem(relative.name).lower())
            if len(relative.parts) > 1:  # la radice dell'archivio estratto (es. il pacchetto Camargo)
                folders.add(relative.parts[0].lower())
        stems.update(stem.lower() for stem in holdout["names"])
    for container in lock["containers"]:
        names.add(container["file"].lower())
    return BlockedNames(frozenset(names), frozenset(stems), frozenset(folders))


def _derived(stem: str, blocked: frozenset[str]) -> bool:
    """``production_1``, ``confidential_2000_modif``: un file ricavato da un log holdout."""
    return any(stem == s or stem.startswith((f"{s}_", f"{s}-")) for s in blocked)


def is_holdout(path: str | bytes | os.PathLike) -> bool:
    """Il file e' un log holdout, ne deriva, o sta in un dataset holdout (archivio compreso)."""
    text = os.fsdecode(path)
    name = os.path.basename(text).lower()
    blocked = blocked_names()
    if name in blocked.names:
        return True
    parts = {part.lower() for part in Path(text).parts[:-1]}
    if parts & blocked.folders:
        return True
    return name.endswith(LOG_SUFFIXES) and _derived(_stem(name), blocked.stems)


# --------------------------------------------------------------------------- guardia

_install_lock = threading.Lock()
_installed = False
# La fase vale per il thread che la apre: "closed" (default) e "selection" tengono chiusi
# gli holdout; "final" li apre per la valutazione finale; "integrity" solo per l'impronta.
# Un thread nuovo parte chiuso: aprire gli holdout in un thread non li apre negli altri.
_local = threading.local()
_OPEN_PHASES = {"final", "integrity"}
_ACCMODE = getattr(os, "O_ACCMODE", os.O_RDONLY | os.O_WRONLY | os.O_RDWR)  # Windows non lo definisce
_frozen_files: set[tuple[int, int]] = set()  # (device, inode) dei file holdout nella cache


def _reads(mode: str | None, flags: int) -> bool:
    """L'apertura permette di leggere: ``open`` passa il modo, ``os.open`` solo i flag."""
    if mode is not None:
        return "r" in mode or "+" in mode
    return flags & _ACCMODE in (os.O_RDONLY, os.O_RDWR)


def _same_file_as_a_holdout(target: str | bytes | os.PathLike) -> bool:
    """Un collegamento (anche fisico) con un nome innocuo a un file holdout della cache."""
    if os.path.islink(target) and is_holdout(os.path.realpath(target)):
        return True
    if not _frozen_files:
        return False
    try:
        stat = os.stat(target)
    except OSError:
        return False
    return (stat.st_dev, stat.st_ino) in _frozen_files


def _audit(event: str, args: tuple) -> None:
    if event != "open" or getattr(_local, "phase", "closed") in _OPEN_PHASES:
        return
    target, mode, flags = args
    if isinstance(target, int) or target is None or not _reads(mode, flags):  # descrittore, o sola scrittura
        return
    if is_holdout(target) or _same_file_as_a_holdout(target):
        raise HoldoutAccessError(
            f"{os.fsdecode(target)} e' un log holdout di PROTO-01: si apre solo in "
            "protocol.final_evaluation(), dopo che la selezione e' chiusa (docs/vpt/PROTOCOL.md)"
        )


def _cached_holdout_files() -> set[tuple[int, int]]:
    root = fetch_datasets.cache_dir()
    found = set()
    for holdout in load_lock()["holdouts"]:
        for item in holdout["files"]:
            try:
                stat = (root / holdout["dataset"] / item["path"]).stat()
            except OSError:
                continue
            found.add((stat.st_dev, stat.st_ino))
    return found


def install() -> None:
    """Attiva la guardia per tutto il processo (un audit hook non si toglie: e' voluto)."""
    global _installed
    with _install_lock:
        if not _installed:
            blocked_names()  # il lucchetto si legge prima di attivare la guardia
            _frozen_files.update(_cached_holdout_files())
            sys.addaudithook(_audit)
            _installed = True


@contextmanager
def _phase(name: str) -> Iterator[None]:
    install()
    previous = getattr(_local, "phase", "closed")
    _local.phase = name
    try:
        yield
    finally:
        _local.phase = previous


@contextmanager
def selection_phase() -> Iterator[None]:
    """Sviluppo, scelta di modelli, iperparametri e componenti: gli holdout sono chiusi.

    Ogni punto d'ingresso di G3b, B3.x e SEL-01 che sceglie qualcosa gira qui dentro.
    La guardia non passa ai sottoprocessi (SIMOD, runner): a loro si danno solo percorsi
    di log di sviluppo, e il test sui nomi controlla che il codice non ne citi altri.
    """
    with _phase("selection"):
        yield


@contextmanager
def final_evaluation(digest: str) -> Iterator[None]:
    """Apre gli holdout nel thread corrente. ``digest`` e' l'impronta scritta in PROTOCOL.md.

    Si usa una volta, a selezione chiusa e congelata, e l'apertura si scrive in LOG.md.
    """
    if digest != lock_digest():
        raise HoldoutAccessError("impronta del lucchetto diversa: gli holdout restano chiusi")
    with _phase("final"):
        yield


def verify_frozen(cache_root: Path) -> list[str]:
    """Le differenze fra i log holdout nella cache e il lucchetto; vuota se tutto torna.

    Legge i file solo per calcolarne lo SHA-256, mai per il contenuto.
    """
    problems = []
    with _phase("integrity"):
        for holdout in load_lock()["holdouts"]:
            for item in holdout["files"]:
                path = cache_root / holdout["dataset"] / item["path"]
                if not path.is_file():
                    problems.append(f"{holdout['id']}: manca {path}")
                    continue
                digest = hashlib.sha256()
                with path.open("rb") as handle:
                    for block in iter(lambda: handle.read(1 << 20), b""):
                        digest.update(block)
                if digest.hexdigest() != item["sha256"]:
                    problems.append(f"{holdout['id']}: {item['path']} ha un'impronta diversa dal lucchetto")
    return problems


# --------------------------------------------------------------------------- log di sviluppo

Category = Literal["osservabilita completa", "osservabilita parziale", "sintetico con verita nota"]
COMPLETE: Category = "osservabilita completa"
PARTIAL: Category = "osservabilita parziale"
SYNTHETIC: Category = "sintetico con verita nota"

SYNTHETIC_PROCESSES = ("Insurance_Claims", "Loan_Application", "Pharmacy", "Procure_to_Pay")
SYNTHETIC_VARIANTS = ("", "_1_timer", "_3_timers", "_5_timers", "_5_timers_after")


@dataclass(frozen=True, slots=True)
class DevelopmentLog:
    key: str
    category: Category
    source: str  # da dove si legge
    split: str  # come si divide in train e test


def development_logs() -> tuple[DevelopmentLog, ...]:
    """Tutti i log di sviluppo del benchmark: nessuno escluso, nessun holdout."""
    real = tuple(
        DevelopmentLog(key, COMPLETE, f"datasets/extraneous-delays/inputs/real-life/{key}_{{train,test}}.csv.gz", "train / test del paper")
        for key in ("AcademicCredentials", "BPIC_2012_W", "BPIC_2017_W")
    )
    public = (
        DevelopmentLog("bpic2012", PARTIAL, "manifest bpic2012 (4TU)", "meta' dei casi per inizio"),
        DevelopmentLog("bpic2013_incidents", PARTIAL, "manifest bpic2013-incidents (4TU)", "meta' dei casi per inizio"),
    )
    synthetic = tuple(
        DevelopmentLog(f"{process}{variant}", SYNTHETIC, f"datasets/extraneous-delays/inputs/synthetic/{process}{variant}.csv.gz", "meta' dei casi per inizio")
        for process in SYNTHETIC_PROCESSES
        for variant in SYNTHETIC_VARIANTS
    )
    return real + public + synthetic


# --------------------------------------------------------------------------- divisioni


def split_by_start(events: Sequence[Event], fraction_last: float) -> tuple[list[Event], list[Event]]:
    """I casi ordinati per inizio: i primi e l'ultima quota ``fraction_last``, eventi interi per caso.

    Deterministico: a parita' di inizio decide l'id del caso.
    """
    if not 0 < fraction_last < 1:
        raise ValueError("fraction_last deve stare fra 0 e 1")
    by_case = cases(list(events))
    order = sorted(by_case, key=lambda case: (min(e.start for e in by_case[case]), case))
    if len(order) < 2:
        raise ValueError("servono almeno due casi")
    cut = min(len(order) - 1, max(1, round(len(order) * (1 - fraction_last))))
    first = set(order[:cut])
    return [e for e in events if e.case_id in first], [e for e in events if e.case_id not in first]


VALIDATION_FRACTION = 0.2


def train_validation(train: Sequence[Event]) -> tuple[list[Event], list[Event]]:
    """La validazione e' l'ultimo 20% dei casi del train per inizio: la scelta si fa li', mai sul test."""
    return split_by_start(train, VALIDATION_FRACTION)


# --------------------------------------------------------------------------- identificabilita'

# Soglie dichiarate prima di qualsiasi misura (proposta, da confermare: PROTOCOL.md §4).
MIN_CASES = 30
MAX_CENSORED = 0.05
MIN_START_COVERAGE = 0.95
MIN_RESOURCE_COVERAGE = 0.95
END_COVERAGE = 0.95
MAX_ARRIVAL_RATIO = 2.0  # B con arrivi piu' di 2 volte (o meno della meta') di A: non e' lo stesso flusso
Verdict = Literal["identificabile", "NOT VALIDATED"]
NOT_VALIDATED: Verdict = "NOT VALIDATED"
IDENTIFIABLE: Verdict = "identificabile"


@dataclass(frozen=True, slots=True)
class LogProperties:
    """Proprieta' metodologiche di un log diviso in A (train) e B (test)."""

    cases_train: int
    cases_fit: int
    cases_validation: int
    cases_test: int
    events: int
    start_coverage: float
    resource_coverage: float
    censored_right_test: float
    censored_left_test: float
    arrival_rate_ratio: float | None


def _boundary_activities(sequences: list[list[str]], position: int) -> set[str]:
    """Le attivita' di inizio (0) o fine (-1) che coprono il 95% dei casi, dalle piu' frequenti."""
    counts = Counter(seq[position] for seq in sequences if seq)
    total = sum(counts.values())
    chosen: set[str] = set()
    covered = 0
    for activity, count in sorted(counts.items(), key=lambda item: (-item[1], item[0])):
        if total and covered / total >= END_COVERAGE:
            break
        chosen.add(activity)
        covered += count
    return chosen


def _traces(events: Sequence[Event]) -> list[list[str]]:
    return [[e.activity for e in sorted(group, key=lambda e: (e.start, e.end))] for group in cases(list(events)).values()]


def properties(
    train: Sequence[Event], test: Sequence[Event], *, has_start: Sequence[bool], has_resource: Sequence[bool]
) -> LogProperties:
    """Proprieta' metodologiche del log, calcolate dai dati e non da un modello.

    - casi tagliati a destra in B: la quota di casi di B la cui ultima attivita' non e'
      fra quelle con cui finisce il 95% dei casi "maturi" di A (iniziati nella prima
      meta' di A, che hanno avuto tempo di finire), meno la stessa quota fra i casi
      maturi (il 5% che il 95% lascia fuori per costruzione); a sinistra, lo stesso con
      l'attivita' iniziale e i casi della seconda meta' di A (iniziati a log aperto);
    - copertura dell'inizio e della risorsa sugli eventi;
    - rapporto fra il ritmo degli arrivi di B e quello di A (stazionarieta', solo riportato).
    """
    early, late = split_by_start(train, 0.5)
    early_traces, late_traces = _traces(early), _traces(late)
    ends = _boundary_activities(early_traces, -1)
    starts = _boundary_activities(late_traces, 0)
    test_traces = _traces(test)
    n_test = len(test_traces)

    def excess(outside_test: int, reference: list[list[str]], outside: set[str], position: int) -> float:
        # Il 95% copre per costruzione: anche un log completo ha ~5% di casi fuori. Conta solo
        # la quota di test fuori oltre quella dei casi di riferimento di A.
        base = sum(t[position] not in outside for t in reference) / len(reference) if reference else 0.0
        return round(max(0.0, outside_test / n_test - base), 4) if n_test else 1.0

    def rate(events: Sequence[Event]) -> float:
        by_case = cases(list(events))
        first = sorted(min(e.start for e in g) for g in by_case.values())
        span = (first[-1] - first[0]).total_seconds() / 86400 if len(first) > 1 else 0.0
        return len(first) / span if span > 0 else math.nan

    rate_a, rate_b = rate(train), rate(test)
    fit, validation = train_validation(train)
    return LogProperties(
        cases_train=len(cases(list(train))),
        cases_fit=len({e.case_id for e in fit}),
        cases_validation=len({e.case_id for e in validation}),
        cases_test=n_test,
        events=len(train) + len(test),
        start_coverage=round(sum(has_start) / len(has_start), 4) if has_start else 0.0,
        resource_coverage=round(sum(has_resource) / len(has_resource), 4) if has_resource else 0.0,
        censored_right_test=excess(sum(t[-1] not in ends for t in test_traces), early_traces, ends, -1),
        censored_left_test=excess(sum(t[0] not in starts for t in test_traces), late_traces, starts, 0),
        arrival_rate_ratio=round(rate_b / rate_a, 3) if not (math.isnan(rate_a) or math.isnan(rate_b)) else None,
    )


def identifiability(props: LogProperties, *, synthetic: bool) -> dict[str, tuple[Verdict, str]]:
    """Per metrica: (identificabile | NOT VALIDATED, motivo). Regole di PROTOCOL.md §4, uguali per ogni log."""
    verdicts: dict[str, tuple[Verdict, str]] = {}
    small = props.cases_train < MIN_CASES or props.cases_test < MIN_CASES
    right = props.censored_right_test > MAX_CENSORED
    left = props.censored_left_test > MAX_CENSORED

    def rule(metric: str, failed: list[tuple[bool, str]]) -> None:
        reasons = [why for hit, why in failed if hit]
        verdicts[metric] = (NOT_VALIDATED, "; ".join(reasons)) if reasons else (IDENTIFIABLE, "")

    few = (small, f"meno di {MIN_CASES} casi in train o test")
    cut_right = (right, f"{props.censored_right_test:.0%} dei casi di test tagliati dalla fine del log")
    cut_left = (left, f"{props.censored_left_test:.0%} dei casi di test iniziati prima del log")
    no_start = (props.start_coverage < MIN_START_COVERAGE, f"inizio delle attivita' su {props.start_coverage:.0%} degli eventi")
    no_resource = (props.resource_coverage < MIN_RESOURCE_COVERAGE, f"risorsa su {props.resource_coverage:.0%} degli eventi")
    no_truth = (not synthetic, "serve la verita' del processo: c'e' solo nei sintetici")
    ratio = props.arrival_rate_ratio
    unstable = (
        ratio is None or not 1 / MAX_ARRIVAL_RATIO <= ratio <= MAX_ARRIVAL_RATIO,
        f"arrivi di test {ratio}× quelli di train: non sono lo stesso flusso" if ratio else "ritmo degli arrivi non misurabile",
    )

    rule("cycle_time_w1", [few, cut_right, cut_left])
    rule("ngram", [few, cut_right, cut_left])
    rule("relative_event", [few, cut_right, cut_left])
    rule("absolute_event", [few])
    rule("circadian_event", [few])
    rule("case_arrival", [few, cut_left, unstable])
    rule("processing_time", [few, no_start])
    rule("resources", [few, no_resource])
    rule("waiting_causes", [few, no_truth])
    rule("true_parameters", [few, no_truth])
    rule("counterfactual", [few, no_truth])
    return verdicts
