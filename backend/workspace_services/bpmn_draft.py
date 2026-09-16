"""«Genera BPMN» come comando, non come conversazione.

Il disegno di una bozza dal piano del processo era il finale di una catena
agentica: router di scope, router di processo, sintesi del piano, router del
canvas, subagente di costruzione con i suoi tool, subagente di layout, subagente
di validazione, loop di correzione. Da dodici a venti chiamate al modello in
sequenza per produrre un XML che **il compilatore sa gia' produrre da solo**, e
un finale che poteva essere una domanda invece di un disegno.

Qui la stessa operazione e' un comando deterministico:

    snapshot -> compile -> validate -> (max 1 repair) -> layout -> persist
             -> read-after-write

Zero chiamate al modello quando il piano e' gia' materializzato, zero Mem0,
zero Neo4j. Il tempo e' quello di due letture e una scrittura su Postgres.

Tre regole che questo modulo non negozia:

1. **La richiesta di generare e' gia' l'autorizzazione a una bozza.** Non si
   chiede una seconda conferma e una lacuna di discovery non diventa
   `waiting_for_user`: cio' che non e' stato chiuso esce come annotazione
   (`pending_verification`), perche' una bozza con le lacune dichiarate dentro
   e' esattamente cio' che una bozza e'.
2. **Un fallimento tecnico si racconta come tecnico.** Un compilatore che non
   chiude, un XML che non valida, una scrittura che non si rilegge: `failed` con
   la causa, e un `reason_code` su cui chi sta sopra puo' decidere senza dover
   leggere il testo di una frase.
3. **Niente si dichiara salvato senza rilettura.** Vale qui come nel resto del
   confine (`write_verification`).
"""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from time import perf_counter
from typing import Literal, TypedDict

from backend.agents.chat_mode import WriteNotAllowedInMode
from backend.agents.process_snapshot import ProcessKnowledgeSnapshot, build_process_snapshot
from backend.bpmn import (
    BPMNSemanticModel,
    build_bpmn_semantic_model,
    semantic_model_to_bpmn_xml,
)
from backend.process_understanding import ProcessUnderstanding
from backend.workspace_services.bpmn_canvas_edit import (
    clean_bpmn_visual_metadata_artifacts,
    optimize_bpmn_layout,
    validate_bpmn_xml,
)
from backend.workspace_services.bpmn_provenance_marks import mark_provenance
from backend.workspace_services.write_verification import (
    PersistenceVerificationError,
    verify_bpmn_model_persisted,
)

logger = logging.getLogger(__name__)


DraftStatus = Literal["drafted", "failed", "refused_by_mode"]

# Perche' il comando non ha prodotto un disegno, in una forma su cui si puo'
# decidere. Chi sta sopra - l'API, il nodo del canvas - deve poter distinguere
# «il processo non esiste» da «il compilatore non chiude» senza leggere il testo
# di una frase: una condizione dedotta da una sottostringa e' una condizione che
# si rompe alla prima riscrittura del messaggio.
DraftReasonCode = Literal[
    "drafted",
    "process_not_found",
    "missing_bpmn_model",
    "plan_synthesis_failed",
    "no_plan_no_evidence",
    "compilation_failed",
    "invalid_bpmn",
    "layout_failed",
    "write_not_allowed_in_mode",
    "persistence_failed",
    "model_disappeared",
    "read_after_write_failed",
]

# Un solo tentativo di riparazione, e deterministico. Il loop «finche' il
# modello si dichiara soddisfatto» e' cio' che questo comando esiste per
# togliere di mezzo: se una ricompilazione dal piano non produce un BPMN valido,
# il difetto e' nel piano o nel compilatore e va detto, non ritentato.
MAX_REPAIR_ATTEMPTS = 1


class DraftMetrics(TypedDict):
    """Dove se ne va il tempo, fase per fase, e quanto lavoro non deterministico
    e' servito.

    E' un contratto e non un dizionario di comodo: chi legge queste metriche -
    un test di regressione, un grafico, una risposta a «perche' ci ha messo
    cinque secondi» - deve poter contare sulle stesse chiavi a ogni run.
    """

    load_snapshot_ms: int
    plan_synthesis_ms: int
    semantic_generation_ms: int
    validation_ms: int
    repair_ms: int
    serialization_di_ms: int
    provenance_marks_ms: int
    persistence_ms: int
    read_after_write_ms: int
    total_ms: int
    llm_calls: int
    tool_calls: int
    repair_count: int
    # Elementi del piano che nessuna fonte regge: il numero che dice quanto del
    # disegno e' inferenza invece che evidenza.
    unverified_elements: int
    process_snapshot_version: int | None


@dataclass(frozen=True)
class BpmnDraftResult:
    """L'esito del comando, con il tempo speso in ogni fase.

    `status` dice cosa e' successo davvero: `drafted` quando un BPMN e' stato
    scritto e riletto, `failed` quando una condizione necessaria e' mancata,
    `refused_by_mode` quando la modalita' di chat scelta dall'utente non
    permette di scrivere sul canvas - che non e' un guasto e non e' una lacuna
    di conoscenza.
    """

    status: DraftStatus
    process_id: str
    reason_code: DraftReasonCode = "drafted"
    bpmn_model_id: str = ""
    snapshot_id: str = ""
    snapshot_label: str = ""
    xml: str | None = None
    # Cio' che resta da verificare sul disegno appena prodotto: lacune aperte del
    # piano e avvisi del layout. Non blocca, e non e' un errore.
    pending_verification: list[str] = field(default_factory=list)
    # Le cause tecniche, quando `failed`.
    issues: list[str] = field(default_factory=list)
    reason: str = ""
    metrics: DraftMetrics | None = None

    @property
    def ok(self) -> bool:
        return self.status == "drafted"


class _Stopwatch:
    """Il tempo per fase, misurato dove viene speso.

    Serve a rispondere a «dove se ne vanno i cinque secondi» con un numero e non
    con un'impressione. Non registra ragionamento, solo durate e conteggi.
    """

    def __init__(self) -> None:
        self._started = perf_counter()
        self.phases: dict[str, int] = {}
        self.llm_calls = 0
        self.tool_calls = 0
        self.repair_count = 0
        self.unverified_elements = 0

    def mark(self, phase: str, started_at: float) -> None:
        elapsed = int((perf_counter() - started_at) * 1000)
        self.phases[phase] = self.phases.get(phase, 0) + elapsed

    @property
    def total_ms(self) -> int:
        return int((perf_counter() - self._started) * 1000)

    def as_metrics(self, *, snapshot_version: int | None) -> DraftMetrics:
        return {
            "load_snapshot_ms": self.phases.get("load_snapshot", 0),
            "plan_synthesis_ms": self.phases.get("plan_synthesis", 0),
            "semantic_generation_ms": self.phases.get("semantic_generation", 0),
            "validation_ms": self.phases.get("validation", 0),
            "repair_ms": self.phases.get("repair", 0),
            "serialization_di_ms": self.phases.get("serialization_di", 0),
            "provenance_marks_ms": self.phases.get("provenance_marks", 0),
            "persistence_ms": self.phases.get("persistence", 0),
            "read_after_write_ms": self.phases.get("read_after_write", 0),
            "total_ms": self.total_ms,
            "llm_calls": self.llm_calls,
            "tool_calls": self.tool_calls,
            "repair_count": self.repair_count,
            "unverified_elements": self.unverified_elements,
            "process_snapshot_version": snapshot_version,
        }


def _pending_verification(snapshot: ProcessKnowledgeSnapshot) -> list[str]:
    """Cio' che il disegno porta con se' e che resta da chiudere.

    Le domande aperte del piano - comprese quelle che l'agente ha marcato
    bloccanti - non impediscono la bozza: la rendono una bozza con le sue
    incertezze dichiarate. Chi legge il risultato le vede accanto al disegno
    invece di riceverle al posto del disegno.
    """
    pending = [item.question for item in snapshot.open_questions if not item.answer]
    pending += [
        item for item in snapshot.missing_information if item and item not in pending
    ]
    if snapshot.has_semantic_model and not snapshot.plan_is_current:
        # Il piano c'e' ma non e' costruito sulle fonti di adesso: la
        # ricostruzione e' in coda (`workspace_plan_materializations`). Si
        # disegna quello che c'e' - e' meglio di niente e l'utente lo ha chiesto
        # - dichiarando che una fonte non e' ancora entrata nel piano. Fare qui
        # la sintesi rimetterebbe tre chiamate al modello davanti a chi aspetta.
        pending.insert(
            0,
            "Il piano non e' ancora ricostruito sull'ultima evidenza registrata: "
            "questo disegno descrive il processo senza le fonti piu' recenti.",
        )
    return pending


def _semantic_model(snapshot: ProcessKnowledgeSnapshot) -> BPMNSemanticModel | None:
    """Il modello semantico del piano, se e' quello canonico.

    Un payload legacy - senza piano di compilazione o senza il
    `ProcessUnderstanding` sorgente - non e' confrontabile con il processo, e
    trattarlo come valido riporterebbe il canvas a essere una verita' parallela.
    Un payload illeggibile non e' un guasto del comando: si ricade sulla
    ricompilazione dal piano, che e' la riparazione prevista.
    """
    payload = snapshot.bpmn_semantic_model
    if not payload:
        return None
    try:
        model = BPMNSemanticModel.model_validate(payload)
    except Exception:  # noqa: BLE001 - un piano illeggibile si ricompila, non esplode
        logger.warning(
            "modello semantico non validabile per il processo %s: si ricompila dal piano",
            snapshot.process_id,
            exc_info=True,
        )
        return None
    if not model.compilationPlan or not model.sourceProcessUnderstanding:
        return None
    return model


def _bpmn_process_id(process_name: str) -> str:
    """L'id BPMN del processo, con la stessa formula di `prepare_bpmn_review`.

    Ricalcolarla qui con un'altra regola produrrebbe un modello con un id
    diverso a ogni ricompilazione, e le versioni del canvas smetterebbero di
    essere confrontabili fra loro.
    """
    from backend.workspace_database import slugify

    return f"Process_{slugify(process_name, 'process').replace('-', '_')}"


def _recompile_from_plan(snapshot: ProcessKnowledgeSnapshot) -> BPMNSemanticModel:
    """La riparazione: ricompila il modello semantico dal piano persistito.

    E' l'unica riparazione che ha senso fare senza un modello linguistico e
    senza inventare topologia. Il modello semantico salvato puo' essere stato
    prodotto da una versione precedente del compilatore, o portarsi dietro
    riferimenti che oggi non chiudono; il `ProcessUnderstanding` da cui nasce e'
    il dato autoritativo, e ricompilarlo e' deterministico.
    """
    understanding = ProcessUnderstanding.model_validate(snapshot.process_understanding or {})
    return build_bpmn_semantic_model(
        process_id=_bpmn_process_id(snapshot.process_name or snapshot.process_id),
        process_name=snapshot.process_name or snapshot.process_id,
        process=understanding,
    )


def generate_bpmn_draft(
    process_id: str,
    *,
    change_summary: str = "Bozza BPMN generata dal piano del processo",
    source: str = "bpmn_draft_command",
    synthesize_missing_plan: bool = True,
) -> BpmnDraftResult:
    """Disegna la bozza BPMN dal piano del processo e la persiste.

    Il percorso critico e' deterministico: legge lo snapshot autoritativo,
    compila l'XML dal modello semantico, lo valida, lo ripara al massimo una
    volta ricompilandolo dal piano, lo dispone, lo salva e lo rilegge.

    Args:
        process_id: Il processo, non affidabile.
        change_summary: La riga che descrive la versione salvata del canvas.
        source: L'origine della versione, per la cronologia del canvas.
        synthesize_missing_plan: Se il piano non e' ancora materializzato ma il
            processo ha evidenza agli atti, costruirlo adesso. E' il solo ramo
            che usa un modello linguistico, dichiarato nelle metriche
            (`llm_calls`, `plan_synthesis_ms`): il percorso normale lo trova gia'
            pronto perche' la materializzazione avviene quando cambia la
            conoscenza, non quando si preme il bottone.

    Returns:
        L'esito, con l'XML salvato quando `drafted`, le cause tecniche quando
        `failed` e sempre le metriche di fase.

    Side effects:
        Scrive il modello BPMN e una sua versione; rilegge entrambi per
        verificarlo. Puo' scrivere una nuova versione della review quando il
        piano viene sintetizzato.
    """
    watch = _Stopwatch()

    started = perf_counter()
    snapshot = build_process_snapshot(process_id)
    watch.mark("load_snapshot", started)

    def failure(
        reason_code: DraftReasonCode,
        reason: str,
        *,
        issues: list[str] | None = None,
        status: DraftStatus = "failed",
        pending: list[str] | None = None,
    ) -> BpmnDraftResult:
        return BpmnDraftResult(
            status=status,
            reason_code=reason_code,
            process_id=process_id,
            bpmn_model_id=snapshot.bpmn_model_id if snapshot else "",
            snapshot_id=snapshot.snapshot_id if snapshot else "",
            snapshot_label=snapshot.label if snapshot else "",
            pending_verification=pending or [],
            issues=issues or [],
            reason=reason,
            metrics=watch.as_metrics(snapshot_version=snapshot.version if snapshot else None),
        )

    if snapshot is None:
        return failure(
            "process_not_found",
            f"Processo non trovato: {process_id}",
            issues=[f"Processo non trovato: {process_id}"],
        )

    if not snapshot.bpmn_model_id:
        return failure(
            "missing_bpmn_model",
            "Il processo non ha un modello BPMN collegato su cui disegnare.",
            issues=["bpmn_model_id mancante per questo processo."],
        )

    semantic_model = _semantic_model(snapshot)

    if semantic_model is None and synthesize_missing_plan and snapshot.evidence_count:
        # Il piano non e' ancora materializzato. Costruirlo qui e' il ramo lento e
        # dichiarato: e' la sola parte del comando che chiama un modello, e la
        # materializzazione al commit dell'evidenza esiste per rendere questo ramo
        # raro invece che normale.
        from backend.agents.process_synthesis import ensure_process_plan

        started = perf_counter()
        synthesis = ensure_process_plan(process_id)
        watch.mark("plan_synthesis", started)
        # Quante chiamate e' costata lo dice la sintesi: sono una per fonte
        # piu' il giudizio di qualita', non un numero fisso.
        watch.llm_calls += synthesis.llm_calls
        if synthesis.snapshot is not None:
            snapshot = synthesis.snapshot
        semantic_model = _semantic_model(snapshot)
        if semantic_model is None:
            return failure(
                "plan_synthesis_failed",
                synthesis.reason
                or "Il piano del processo non e' stato costruito dalle fonti registrate.",
                issues=synthesis.blockers
                or [synthesis.reason or "sintesi del piano non riuscita"],
            )

    if semantic_model is None:
        # Nessun piano utilizzabile. Con evidenza agli atti il lavoro che manca e'
        # la materializzazione del piano; senza, e' la discovery. In nessuno dei
        # due casi si disegna start -> end e lo si chiama AS-IS.
        return failure(
            "no_plan_no_evidence",
            "Questo processo non ha ancora un piano strutturato utilizzabile per disegnarlo.",
            issues=[
                "Nessun BPMNSemanticModel canonico disponibile"
                + (
                    f" ({snapshot.evidence_count} elementi di evidenza agli atti: il piano va materializzato)."
                    if snapshot.evidence_count
                    else " e nessuna evidenza registrata."
                )
            ],
        )

    pending = _pending_verification(snapshot)

    started = perf_counter()
    try:
        xml = semantic_model_to_bpmn_xml(semantic_model)
    except Exception as exc:  # noqa: BLE001 - un compilatore che non chiude e' un guasto
        watch.mark("semantic_generation", started)
        logger.warning("compilazione BPMN fallita per il processo %s", process_id, exc_info=True)
        return failure(
            "compilation_failed",
            "La compilazione del BPMN dal piano non e' riuscita.",
            issues=[f"{type(exc).__name__}: {exc}"],
            pending=pending,
        )
    watch.mark("semantic_generation", started)

    def validate(candidate: str) -> tuple[dict, str | None]:
        """Valida, e distingue «non valido» da «non validabile»."""
        phase_started = perf_counter()
        try:
            report = validate_bpmn_xml(candidate)
        except Exception as exc:  # noqa: BLE001 - XML illeggibile: il difetto e' a monte
            watch.mark("validation", phase_started)
            return {}, f"{type(exc).__name__}: {exc}"
        watch.mark("validation", phase_started)
        return report, None

    validation, validation_error = validate(xml)

    if validation_error or validation.get("issues"):
        started = perf_counter()
        try:
            xml = semantic_model_to_bpmn_xml(_recompile_from_plan(snapshot))
            watch.repair_count = MAX_REPAIR_ATTEMPTS
        except Exception as exc:  # noqa: BLE001
            watch.mark("repair", started)
            logger.warning(
                "riparazione BPMN non riuscita per il processo %s", process_id, exc_info=True
            )
            return failure(
                "invalid_bpmn",
                "Il BPMN compilato non e' valido e la ricompilazione dal piano non e' riuscita.",
                issues=[
                    *(validation.get("issues") or []),
                    *([validation_error] if validation_error else []),
                    f"{type(exc).__name__}: {exc}",
                ],
                pending=pending,
            )
        watch.mark("repair", started)

        validation, validation_error = validate(xml)
        if validation_error or validation.get("issues"):
            # Un solo tentativo, e non ha chiuso: il difetto e' strutturale e
            # ritentare non lo cambia.
            return failure(
                "invalid_bpmn",
                "Il BPMN generato dal piano non supera la validazione tecnica.",
                issues=[
                    *(validation.get("issues") or []),
                    *([validation_error] if validation_error else []),
                ],
                pending=pending,
            )

    started = perf_counter()
    try:
        xml, _clean_report = clean_bpmn_visual_metadata_artifacts(xml)
        xml, layout_report = optimize_bpmn_layout(xml)
    except Exception as exc:  # noqa: BLE001
        watch.mark("serialization_di", started)
        logger.warning("layout BPMN fallito per il processo %s", process_id, exc_info=True)
        return failure(
            "layout_failed",
            "La disposizione del diagramma non e' riuscita.",
            issues=[f"{type(exc).__name__}: {exc}"],
            pending=pending,
        )
    watch.mark("serialization_di", started)

    # Un layout imperfetto non annulla una bozza corretta: il disegno esiste, si
    # legge meno bene, e lo si dice. Bloccare qui butterebbe via un modello
    # valido per una questione di geometria.
    if not layout_report.get("valid"):
        pending = [
            *pending,
            "La disposizione del diagramma non e' ottimale: elementi vicini o sovrapposti da sistemare.",
        ]

    # Ogni nodo porta l'esito della verifica sulle fonti. Un passaggio che
    # nessuna intervista regge non si toglie dal disegno - puo' essere il pezzo
    # che rende il flusso coerente - ma non si disegna come se qualcuno lo
    # avesse detto.
    started = perf_counter()
    report = snapshot.provenance
    unverified = report.unverified if report else []
    try:
        xml, _marks = mark_provenance(xml, report.status_by_source_ref() if report else {})
    except (ET.ParseError, ValueError, TypeError):
        # Un disegno senza marcature e' meno informativo, non sbagliato: non si
        # butta un BPMN valido per un attributo di estensione. Il guasto resta
        # nei log e nella nota per chi legge.
        logger.warning(
            "marcatura provenance non riuscita per il processo %s", process_id, exc_info=True
        )
        pending = [
            *pending,
            "Non e' stato possibile segnare sul disegno quali elementi vengono dalle fonti.",
        ]
    watch.mark("provenance_marks", started)
    watch.unverified_elements = len(unverified)
    if unverified:
        labels = ", ".join(item.label or item.element_id for item in unverified[:5])
        more = f" e altri {len(unverified) - 5}" if len(unverified) > 5 else ""
        pending = [
            *pending,
            f"{len(unverified)} elementi del disegno non risultano in nessuna fonte e vanno "
            f"confermati: {labels}{more}.",
        ]

    from backend import workspace_database

    started = perf_counter()
    try:
        model = workspace_database.update_bpmn_model(
            snapshot.bpmn_model_id,
            xml,
            change_summary=change_summary,
            source=source,
        )
    except WriteNotAllowedInMode as exc:
        watch.mark("persistence", started)
        return failure(
            "write_not_allowed_in_mode",
            str(exc),
            status="refused_by_mode",
            pending=pending,
        )
    except Exception as exc:  # noqa: BLE001
        watch.mark("persistence", started)
        logger.warning("salvataggio canvas fallito per il processo %s", process_id, exc_info=True)
        return failure(
            "persistence_failed",
            "Il canvas non e' stato salvato.",
            issues=[f"{type(exc).__name__}: {exc}"],
            pending=pending,
        )
    watch.mark("persistence", started)

    if model is None:
        return failure(
            "model_disappeared",
            "Il modello BPMN di questo processo non esiste piu'.",
            issues=[f"Modello BPMN non trovato: {snapshot.bpmn_model_id}"],
            pending=pending,
        )

    started = perf_counter()
    try:
        verify_bpmn_model_persisted(snapshot.bpmn_model_id, xml)
    except PersistenceVerificationError as exc:
        watch.mark("read_after_write", started)
        return failure(
            "read_after_write_failed",
            "Il canvas risulta scritto ma rileggendolo non coincide: non lo dichiaro salvato.",
            issues=[str(exc)],
            pending=pending,
        )
    watch.mark("read_after_write", started)

    drafted = BpmnDraftResult(
        status="drafted",
        reason_code="drafted",
        process_id=process_id,
        bpmn_model_id=snapshot.bpmn_model_id,
        snapshot_id=snapshot.snapshot_id,
        snapshot_label=snapshot.label,
        xml=xml,
        pending_verification=pending,
        reason=f"Bozza costruita sul piano {snapshot.label} del processo.",
        metrics=watch.as_metrics(snapshot_version=snapshot.version),
    )
    logger.info(
        "bozza BPMN generata per il processo %s (%s) in %sms",
        process_id,
        snapshot.label,
        drafted.metrics["total_ms"],
        extra={"bpmn_draft_metrics": drafted.metrics},
    )
    return drafted
