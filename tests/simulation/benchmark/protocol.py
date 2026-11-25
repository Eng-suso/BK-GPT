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
import random
import sys
import threading
from collections import Counter
from collections.abc import Callable, Iterator, Sequence
from contextlib import contextmanager
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import BinaryIO, Literal

from scripts import fetch_datasets
from tests.simulation.benchmark.eval_harness import INPUTS, REAL_LIFE
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


def sha256_of(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


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
    # Gira a ogni apertura di file del processo: stringhe, niente Path ne' syscall.
    *folders, name = os.fsdecode(path).lower().replace("\\", "/").split("/")
    blocked = blocked_names()
    if name in blocked.names or not blocked.folders.isdisjoint(folders):
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


def fingerprint(open_binary: Callable[[], BinaryIO]) -> str:
    """SHA-256 di un file che potrebbe essere un holdout, letto solo per l'impronta (RAD-01).

    Serve a dire se una copia trovata altrove coincide con il lucchetto senza leggerne gli
    eventi: restituisce solo l'impronta, mai il contenuto.
    """
    digest = hashlib.sha256()
    with _phase("integrity"), open_binary() as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


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
                if sha256_of(path) != item["sha256"]:
                    problems.append(f"{holdout['id']}: {item['path']} ha un'impronta diversa dal lucchetto")
    return problems


# --------------------------------------------------------------------------- log di sviluppo

Category = Literal["osservabilita completa", "osservabilita parziale", "sintetico con verita nota"]
COMPLETE: Category = "osservabilita completa"
PARTIAL: Category = "osservabilita parziale"
SYNTHETIC: Category = "sintetico con verita nota"

_INPUTS = INPUTS.relative_to(ROOT).as_posix()
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
        DevelopmentLog(key, COMPLETE, f"{_INPUTS}/real-life/{key}_{{train,test}}.csv.gz", "train / test del paper")
        for key in REAL_LIFE
    )
    public = (
        DevelopmentLog("bpic2012", PARTIAL, "manifest bpic2012 (4TU)", "meta' dei casi per inizio"),
        DevelopmentLog("bpic2013_incidents", PARTIAL, "manifest bpic2013-incidents (4TU)", "meta' dei casi per inizio"),
    )
    synthetic = tuple(
        DevelopmentLog(f"{process}{variant}", SYNTHETIC, f"{_INPUTS}/synthetic/{process}{variant}.csv.gz", "meta' dei casi per inizio")
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


# --------------------------------------------------------------------------- confronti appaiati (PROTO-02)

# Accanto alla regola degli intervalli non sovrapposti (eval_harness.within_intervals), che resta
# quella delle mete gia' scritte: dove le repliche sono appaiate (stesso seed, stesso log) si
# riporta anche un test sulla differenza. Le distanze sono "piu' basso e' meglio".
PAIRED_BOOTSTRAP_SAMPLES = 10_000
PAIRED_SEED = 20261125
PAIRED_ALPHA = 0.05


@dataclass(frozen=True, slots=True)
class PairedComparison:
    mean_difference: float  # media di a - b: negativa se a ha distanze piu' basse
    ci_low: float  # intervallo bootstrap al 95% della differenza media
    ci_high: float
    wilcoxon_p: float  # test dei ranghi con segno, esatto, a due code
    verdict: Literal["a meglio", "b meglio", "pari"]


def _wilcoxon_exact(differences: Sequence[float]) -> float:
    """p a due code del test dei ranghi con segno, esatto (enumera i segni: fino a 20 coppie).

    Le differenze nulle si tolgono (Wilcoxon); i pari hanno il rango medio.
    """
    values = [d for d in differences if d != 0]
    n = len(values)
    if n == 0:
        return 1.0
    if n > 20:
        raise ValueError("il test esatto enumera 2^n segni: al massimo 20 coppie")
    order = sorted(range(n), key=lambda i: abs(values[i]))
    ranks = [0.0] * n
    i = 0
    while i < n:
        j = i
        while j + 1 < n and abs(values[order[j + 1]]) == abs(values[order[i]]):
            j += 1
        for k in range(i, j + 1):
            ranks[order[k]] = (i + j) / 2 + 1
        i = j + 1
    observed = sum(r for r, v in zip(ranks, values, strict=True) if v > 0)
    total = sum(ranks)
    distance = abs(observed - total / 2)
    extreme = 0
    for mask in range(1 << n):
        positive = sum(ranks[k] for k in range(n) if mask >> k & 1)
        extreme += abs(positive - total / 2) >= distance - 1e-12
    return extreme / (1 << n)


def paired_comparison(a: Sequence[float], b: Sequence[float], *, seed: int = PAIRED_SEED) -> PairedComparison:
    """Due configurazioni con le stesse repliche appaiate: chi ha la distanza piu' bassa, e quanto.

    Vince chi ha l'intervallo bootstrap della differenza media tutto dalla sua parte dello zero;
    il p di Wilcoxon si riporta accanto. Deterministico: stesso seed, stesso risultato.
    """
    if len(a) != len(b) or len(a) < 2:
        raise ValueError("servono almeno due repliche appaiate, tante per parte")
    differences = [x - y for x, y in zip(a, b, strict=True)]
    n = len(differences)
    rng = random.Random(seed)
    means = sorted(math.fsum(rng.choices(differences, k=n)) / n for _ in range(PAIRED_BOOTSTRAP_SAMPLES))
    low = means[int(PAIRED_BOOTSTRAP_SAMPLES * PAIRED_ALPHA / 2)]
    high = means[int(PAIRED_BOOTSTRAP_SAMPLES * (1 - PAIRED_ALPHA / 2)) - 1]
    verdict: Literal["a meglio", "b meglio", "pari"] = "a meglio" if high < 0 else "b meglio" if low > 0 else "pari"
    return PairedComparison(round(math.fsum(differences) / n, 6), round(low, 6), round(high, 6),
                            round(_wilcoxon_exact(differences), 6), verdict)


# --------------------------------------------------------------------------- metriche di CF-01 (PROTO-02)

# Una copertura del 90% si ottiene anche con intervalli enormi: con la copertura si riportano
# ampiezza, errore puntuale sul Δ KPI e direzione dell'effetto. Un effetto vero piu' piccolo di
# questa quota del KPI di partenza non ha una direzione da indovinare (proposta).
DIRECTION_MIN_EFFECT = 0.01


@dataclass(frozen=True, slots=True)
class CounterfactualOutcome:
    """Un intervento su un sintetico con verita' nota: Δ KPI vero, previsto e intervallo al 95%."""

    baseline: float  # KPI prima dell'intervento (verita')
    true_delta: float
    predicted_delta: float
    low: float
    high: float


@dataclass(frozen=True, slots=True)
class CounterfactualMetrics:
    cases: int
    coverage: float  # quota di Δ veri dentro l'intervallo (meta di CF-01: almeno 90%)
    mean_width: float  # ampiezza media dell'intervallo, nelle unita' del KPI
    mean_relative_width: float  # ampiezza / |KPI di partenza|
    mean_absolute_error: float  # |Δ previsto - Δ vero|
    mean_relative_error: float  # |Δ previsto - Δ vero| / |KPI di partenza|
    direction_cases: int  # interventi con un effetto vero di almeno DIRECTION_MIN_EFFECT
    direction_accuracy: float | None  # quota con il segno del Δ previsto giusto, su quelli


def counterfactual_metrics(outcomes: Sequence[CounterfactualOutcome]) -> CounterfactualMetrics:
    """Le metriche complete di CF-01 su un insieme di interventi con verita' nota."""
    if not outcomes:
        raise ValueError("nessun intervento")
    for o in outcomes:
        if o.low > o.high:
            raise ValueError("intervallo con il minimo sopra il massimo")
        if o.baseline == 0:
            raise ValueError("KPI di partenza nullo: errore relativo non definito")
    n = len(outcomes)
    directional = [o for o in outcomes if abs(o.true_delta) >= DIRECTION_MIN_EFFECT * abs(o.baseline)]
    right = sum(math.copysign(1, o.predicted_delta) == math.copysign(1, o.true_delta) and o.predicted_delta != 0
                for o in directional)
    return CounterfactualMetrics(
        cases=n,
        coverage=round(sum(o.low <= o.true_delta <= o.high for o in outcomes) / n, 4),
        mean_width=round(math.fsum(o.high - o.low for o in outcomes) / n, 6),
        mean_relative_width=round(math.fsum((o.high - o.low) / abs(o.baseline) for o in outcomes) / n, 6),
        mean_absolute_error=round(math.fsum(abs(o.predicted_delta - o.true_delta) for o in outcomes) / n, 6),
        mean_relative_error=round(math.fsum(abs(o.predicted_delta - o.true_delta) / abs(o.baseline) for o in outcomes) / n, 6),
        direction_cases=len(directional),
        direction_accuracy=round(right / len(directional), 4) if directional else None,
    )
