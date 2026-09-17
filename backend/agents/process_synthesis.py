"""Da cio' che le fonti hanno detto a un piano che si puo' disegnare.

Il difetto che questo modulo chiude non era nel Canvas. Con tre interviste agli
atti, lo stato reale del processo era questo:

    fonti: 3   claim: 0   modello semantico: assente   modelable: no

Il piano del processo - la `ProcessUnderstanding` - vive dentro la review BPMN, e
la review esiste solo se qualcuno la prepara. Preparare la review era un passo
dell'agente: il router doveva scegliere `modeling`, il subagente doveva chiamare
`prepare_process_understanding_review` e doveva riempirne bene l'argomento. Tre
condizioni, tutte affidate a un prompt, per un'invariante che invece e' dura:
**se il processo ha evidenza agli atti, il processo ha un piano.**

Quando quel passo non avveniva, il gate del canvas rifiutava per prerequisito
mancante e il turno finiva in chiarimento. Da li' venivano, tutti insieme,
"nessuna intervista disponibile", "nessun attore", il modello start -> end e le
domande da questionario su trigger, attori e prima attivita': non era il Canvas
che perdeva la conoscenza, era la conoscenza che non era mai stata sintetizzata.

Qui la sintesi diventa un passo deterministico del confine, di proprieta' del
Process Agent. Non inventa: usa l'estrattore che la review gia' usava, sul corpus
autoritativo delle fonti, e le domande non ancorate all'evidenza vengono scartate
dallo stesso filtro di sempre. Il Canvas continua a non poter scrivere il piano.

Il piano dichiara su quale set di fonti e' nato (`evidence_source_set_id`). Cosi'
"il piano e' aggiornato rispetto alle interviste?" e' una domanda con risposta:
una quarta intervista cambia il set, il piano risulta indietro e viene
risintetizzato invece di restare a descrivere un processo di tre fonti fa.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Literal

from backend.agents.process_snapshot import (
    ProcessKnowledgeSnapshot,
    build_process_snapshot,
    plan_ignores_evidence,
)
from backend.process_understanding import (
    ExtractionFailure,
    ProcessUnderstanding,
    ProcessUnderstandingExtractionError,
    ProcessUnderstandingResult,
    build_process_understanding,
)
from backend.workspace_services.write_verification import (
    PersistenceVerificationError,
    verify_review_persisted,
)

logger = logging.getLogger(__name__)

SynthesisAction = Literal[
    "reused",
    "synthesized",
    "no_evidence",
    "synthesis_failed",
    "process_not_found",
]


@dataclass(frozen=True)
class PlanSynthesis:
    """L'esito del passo che porta l'evidenza dentro il piano.

    `action` dice cosa e' successo davvero, non cosa si sperava: `reused` quando
    il piano c'era gia' ed era costruito sulle fonti di adesso, `synthesized`
    quando e' stato costruito ora, `no_evidence` quando non c'e' niente da cui
    costruirlo, `synthesis_failed` quando l'estrazione non ha prodotto un piano
    utilizzabile. Le ultime due non sono lo stesso stato e non si raccontano allo
    stesso modo: la prima e' un processo senza interviste, la seconda e' un
    guasto.
    """

    action: SynthesisAction
    snapshot: ProcessKnowledgeSnapshot | None
    reason: str = ""
    blockers: list[str] = field(default_factory=list)
    # Quante chiamate al modello e' costata questa sintesi. Serve a chi misura
    # il percorso critico: un piano riusato ne costa zero, uno ricostruito ne
    # costa una per fonte piu' il giudizio di qualita'.
    llm_calls: int = 0

    @property
    def has_plan(self) -> bool:
        return bool(self.snapshot and self.snapshot.has_semantic_model)

    def as_log_entry(self) -> dict:
        return {
            "action": self.action,
            "reason": self.reason,
            "snapshot_id": self.snapshot.snapshot_id if self.snapshot else None,
            "snapshot_label": self.snapshot.label if self.snapshot else None,
            "has_plan": self.has_plan,
            "llm_calls": self.llm_calls,
        }


def plan_is_built_on(review: dict | None, source_set_id: str) -> bool:
    """Il piano salvato e' costruito sul set di fonti che c'e' adesso?

    Una review preparata prima che la colonna esistesse non dichiara nulla: e'
    `None`, che significa "non si sa", non "costruita su nessuna fonte". Un piano
    di cui non si sa la provenienza, mentre l'evidenza esiste, va risintetizzato:
    l'alternativa e' fidarsi di un piano che potrebbe ignorare un'intervista.
    """
    if not review:
        return False
    recorded = review.get("evidence_source_set_id")
    return bool(recorded) and str(recorded) == str(source_set_id)


# Quanto testo entra nel corpus della review. Piu' largo del budget di un prompt
# di routing e piu' stretto del testo che l'estrazione legge: qui il testo serve
# a giudicare l'ancoraggio delle domande e a far valutare la qualita' del piano,
# e ogni carattere in piu' entra in quei due prompt.
CORPUS_SOURCE_CHAR_LIMIT = 24_000
CORPUS_TOTAL_CHAR_LIMIT = 80_000


def evidence_corpus(ledger_snapshot: dict) -> str:
    """Il materiale su cui il piano viene costruito, voce per voce.

    Le fonti con il loro testo integrale, e sotto il registro dei claim proiettati
    quando c'e'. I due piani restano separati e dichiarati: la proiezione del
    knowledge graph e' asincrona, e quando e' indietro le interviste valgono
    comunque - contarne zero perche' il grafo non ha ancora ingerito e' il modo in
    cui un processo con tre interviste diventava un processo senza evidenza.
    """
    from backend.agents.evidence_brief import render_ledger_lines, render_source_evidence
    from backend.memory import provenance

    sections = [
        "FONTI AGLI ATTI (autoritative: ogni voce resta separata dalle altre)",
        render_source_evidence(
            ledger_snapshot,
            include_content=True,
            # Piu' largo del budget di un prompt di routing: questo testo diventa
            # il `source_text` della review, ed e' il vocabolario contro cui si
            # giudica se una domanda del piano e' ancorata a una lacuna reale.
            # Quando e' tagliato stretto, una domanda legittima su cio' che la
            # fonte diceva a pagina tre viene scartata come "non ancorata".
            # L'estrazione non passa piu' di qui: quella legge le fonti intere,
            # una per volta.
            source_limit=CORPUS_SOURCE_CHAR_LIMIT,
            total_limit=CORPUS_TOTAL_CHAR_LIMIT,
        ),
    ]

    entries = provenance.build_ledger(ledger_snapshot.get("claims") or [])
    if entries:
        sections += [
            "",
            "REGISTRO DEI CLAIM PROIETTATI (attribuzione e grado di sostegno)",
            render_ledger_lines(entries),
        ]
    elif ledger_snapshot.get("claim_status") not in {"ok", "empty"}:
        sections += [
            "",
            "La proiezione dei claim non e' disponibile in questo momento: "
            "usa il testo delle fonti, non concludere che l'evidenza sia assente.",
        ]

    return "\n".join(sections)


# Quanto testo di UNA fonte entra nella sua estrazione. Il limite del confine
# (12k per fonte, 30k in tutto) serve a far stare piu' fonti in un prompt solo:
# qui la fonte e' una, e tagliarla a un quarto significa costruire il piano sul
# primo quarto dell'intervista. Un'ora di trascrizione sta sotto questa soglia.
SOURCE_EXTRACTION_CHAR_LIMIT = 120_000

# Quante estrazioni contemporanee. Sono chiamate di rete: aspettarle in fila
# moltiplica per il numero di fonti il tempo di una ricostruzione, e quel tempo
# e' quello che separa «il piano c'e' gia'» da «il piano si sta ancora facendo».
MAX_PARALLEL_EXTRACTIONS = 4


def _source_notes(source: dict, process_name: str, reviewer_notes: list[str] | None = None) -> str:
    """Il testo di una fonte come lo legge l'estrattore: una voce sola.

    Le fonti restano separate perche' e' la separazione a portare
    l'informazione: cio' che descrive il reparto di Paolo non e' la regola
    generale, e fondere tre trascrizioni in un blocco unico e' il modo piu'
    diretto per farlo diventare tale.
    """
    participants = ", ".join(str(item) for item in source.get("participants") or [])
    full_text = str(source.get("content") or "").strip()
    content = full_text[:SOURCE_EXTRACTION_CHAR_LIMIT]
    header = [
        f"Processo: {process_name}",
        f"Fonte: {source.get('name') or source.get('id') or 'senza nome'}",
        f"Tipo: {source.get('type') or 'fonte'}",
    ]
    if participants:
        header.append(f"Voci in questa fonte: {participants}")
    summary = str(source.get("summary") or "").strip()
    if summary:
        header.append(f"Sintesi dichiarata: {summary}")
    header.append(
        "Estrai solo cio' che questa fonte dice. Cio' che non dice non e' una "
        "lacuna del processo: e' una cosa che questa voce non copre."
    )
    if reviewer_notes:
        # I rilievi del revisore di conformita' sul piano precedente, con le
        # citazioni gia' verificate nel testo di questa fonte. Non sono fatti
        # nuovi: sono punti del testo che l'estrazione precedente non ha portato
        # nel piano, e restano da estrarre solo se la fonte li dice davvero.
        header.append(
            "Verifica di conformita' sul piano precedente: in questa fonte ci sono "
            "passaggi che quel piano non rappresentava o contraddiceva. Rileggili nel "
            "testo e, se la fonte li afferma, estraili:"
        )
        header.extend(f"- {note}" for note in reviewer_notes)
    # Un taglio si dichiara sempre, anche quando e' improbabile: un testo che
    # finisce senza preavviso fa concludere che il processo finisce li'.
    tail = (
        ["", "(testo troncato: la fonte continua oltre questo punto)"]
        if len(content) < len(full_text)
        else []
    )
    return "\n".join([*header, "", content, *tail])


def warm_provider_imports() -> None:
    """Importa il client del modello nel thread che chiama, prima del pool.

    Il client carica i suoi moduli alla prima chiamata. Con quattro estrazioni
    partite insieme, quattro thread importavano gli stessi moduli nello stesso
    istante e Python rompeva il ciclo con un `_DeadlockError` sul lock del
    modulo (`openai.resources.embeddings`, coda di materializzazione,
    2026-09-17): una fonte persa per un difetto di import, raccontata come
    estrazione fallita. Importare qui, una volta, toglie la gara.

    Idempotente e senza rete.
    """
    import importlib

    for module in ("openai", "openai.resources", "langchain_openai"):
        try:
            importlib.import_module(module)
        except ImportError:  # pragma: no cover - dipendenza opzionale assente
            logger.debug("modulo del provider non disponibile: %s", module)


@dataclass(frozen=True)
class CorpusExtraction:
    """Il piano ricavato dalle fonti, e quanto e' costato ricavarlo."""

    process: ProcessUnderstanding | None
    llm_calls: int
    sources_read: int
    failures: list[str] = field(default_factory=list)


def extract_plan_from_sources(
    process_name: str,
    sources: list[dict],
    reviewer_notes: dict[str, list[str]] | None = None,
) -> CorpusExtraction:
    """Una estrazione per fonte, a testo intero, poi un merge deterministico.

    L'estrazione unica leggeva un corpus tagliato a 12k caratteri per fonte e 30k
    in tutto: con tre interviste vere il piano nasceva da circa il primo terzo di
    ognuna, e i passaggi raccontati a meta' colloquio non arrivavano al disegno.
    Nessun prompt puo' recuperare un testo che non ha letto.

    Qui ogni fonte viene letta intera e da sola, e i piani parziali si fondono
    con la stessa regola deterministica che governa gli emendamenti del piano
    (`merge_process_understanding`): niente LLM nel merge, identita' stabile per
    le liste, e cio' che una fonte non ripete non viene cancellato.

    L'ordine del merge e' quello delle fonti nel registro - stabile, per nome -
    quindi due ricostruzioni sulle stesse fonti danno lo stesso piano.

    Args:
        process_name: Il nome del processo, per l'estrattore.
        sources: Le fonti del registro, con il loro testo.
        reviewer_notes: I rilievi verificati del revisore di conformita', per id
            di fonte, quando l'estrazione ripara un piano gia' verificato.

    Returns:
        Il piano fuso (o `None` se nessuna fonte ha prodotto niente), il numero
        di chiamate al modello spese e i guasti per fonte.

    Side effects:
        Chiama il modello, una volta per fonte, in parallelo.
    """
    from concurrent.futures import ThreadPoolExecutor

    from backend.agents.process_plan import merge_process_understanding

    readable = [source for source in sources if str(source.get("content") or "").strip()]
    if not readable:
        return CorpusExtraction(process=None, llm_calls=0, sources_read=0)

    def _extract(source: dict) -> ProcessUnderstandingResult:
        try:
            return build_process_understanding(
                process_name,
                _source_notes(
                    source,
                    process_name,
                    (reviewer_notes or {}).get(str(source.get("id") or "")),
                ),
                # Il giudizio di qualita' si da' sul piano intero, non su ogni
                # pezzo: chiederlo per fonte moltiplicherebbe le chiamate per
                # giudicare frammenti che nessuno usera' da soli.
                with_quality_report=False,
            )
        except Exception as exc:  # noqa: BLE001
            # Una fonte che esplode e' una fonte persa, non l'estrazione persa.
            # Senza questo, un'eccezione non classificata dentro `pool.map`
            # risalirebbe e porterebbe via anche le fonti gia' estratte.
            return ProcessUnderstandingResult(
                status="failed",
                failure=ExtractionFailure(
                    kind="provider_error",
                    message=f"{type(exc).__name__}: {exc}",
                    retryable=True,
                    attempt=1,
                ),
            )

    workers = max(1, min(MAX_PARALLEL_EXTRACTIONS, len(readable)))
    if workers > 1:
        warm_provider_imports()
    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="plan-extract") as pool:
        # `map` conserva l'ordine dell'input: il merge resta deterministico anche
        # se le chiamate finiscono in ordine diverso.
        results = list(pool.map(_extract, readable))

    # Un guasto temporaneo del provider - timeout, rate limit - non deve costare
    # un'intervista al piano. Sul caso Esaote l'estrazione di Francesca e' andata
    # in timeout e il piano e' nato su due voci su tre, dichiarato costruito. Un
    # secondo tentativo, in fila per non ripetere la raffica che ha causato il
    # guasto, e poi quello che resta fallito resta fallito.
    retried = 0
    for index, result in enumerate(results):
        failure = result.failure
        if result.status == "success" or failure is None or not failure.retryable:
            continue
        retried += 1
        results[index] = _extract(readable[index])

    merged = None
    failures: list[str] = []
    for source, result in zip(readable, results):
        name = str(source.get("name") or source.get("id") or "fonte senza nome")
        if result.status != "success" or result.process is None:
            reason = result.failure.message if result.failure else "estrazione non riuscita"
            failures.append(f"{name}: {reason}")
            continue
        # `append` e non `replace`: ogni intervista descrive il pezzo di processo
        # che ha visto, e nessuna descrive il percorso intero. Sostituire il
        # percorso a ogni fonte lascerebbe nel piano solo i passaggi dell'ultima
        # voce letta - che e' un ordine arbitrario, non un processo.
        merged, _diff = merge_process_understanding(
            merged, result.process, ordered_sequences="append"
        )

    return CorpusExtraction(
        process=merged,
        llm_calls=len(readable) + retried,
        sources_read=len(readable),
        failures=failures,
    )


def synthesize_process_plan(
    process_id: str,
    *,
    reviewer_notes: dict[str, list[str]] | None = None,
) -> PlanSynthesis:
    """Costruisce il piano del processo dall'evidenza agli atti e lo persiste.

    Il piano che ne esce e' preliminare per costruzione: porta con se' le lacune
    che le fonti non chiudono, e quelle diventano domande del piano invece di
    diventare un divieto di disegnarlo. Cio' che le fonti non dicono non entra:
    l'estrattore lavora sul corpus, e il filtro di ancoraggio che governa gia' le
    domande del piano scarta cio' che non cita una lacuna reale.

    Args:
        process_id: Il processo, non affidabile.

    Returns:
        L'esito, con lo snapshot aggiornato quando il piano e' stato scritto.

    Side effects:
        Scrive una nuova versione della review, e la rilegge per verificare che
        contenga davvero un piano prima di dichiarare la sintesi riuscita.
    """
    from backend import workspace_database
    from backend.graphs.process.nodes import evidence_count, load_evidence_ledger

    process = workspace_database.get_process(process_id)
    if process is None:
        return PlanSynthesis(
            action="process_not_found",
            snapshot=None,
            reason=f"Processo non trovato: {process_id}",
        )

    ledger = load_evidence_ledger(process.get("project_id"), process_id)
    if evidence_count(ledger) == 0:
        return PlanSynthesis(
            action="no_evidence",
            snapshot=build_process_snapshot(process_id),
            reason=(
                "Il processo non ha ancora fonti ne' claim agli atti: non c'e' "
                "evidenza da cui costruire un piano."
            ),
            blockers=["Nessuna evidenza registrata per questo processo."],
        )

    corpus = evidence_corpus(ledger)
    # Una estrazione per fonte, a testo intero. Il corpus resta il testo della
    # review - e' il materiale contro cui si giudica se una domanda del piano e'
    # ancorata all'evidenza - ma non e' piu' cio' su cui si estrae: li' le fonti
    # sono tagliate per stare tutte in un prompt solo.
    extraction = extract_plan_from_sources(
        process["name"], ledger.get("sources") or [], reviewer_notes=reviewer_notes
    )
    llm_calls = extraction.llm_calls
    understanding = extraction.process

    if understanding is None and extraction.sources_read:
        # Le fonti c'erano e nessuna estrazione ha prodotto un piano: e' un
        # guasto - rate limit, provider giu' - e ritentare qui su un corpus
        # tagliato spenderebbe un'altra chiamata per fallire di nuovo. La coda
        # di materializzazione riprova piu' tardi, con il suo backoff.
        reason = "; ".join(extraction.failures) or "Estrazione del piano non riuscita."
        logger.warning("sintesi piano fallita per il processo %s: %s", process_id, reason)
        return PlanSynthesis(
            action="synthesis_failed",
            snapshot=build_process_snapshot(process_id),
            reason=reason,
            blockers=list(extraction.failures) or [reason],
            llm_calls=llm_calls,
        )

    if understanding is None:
        # Nessuna fonte con un testo leggibile: restano nomi, sintesi e claim
        # proiettati, e su quelli si estrae una volta sola. E' il caso di un
        # processo le cui interviste non hanno trascrizione, non un guasto.
        result = build_process_understanding(process["name"], corpus)
        llm_calls += 2  # estrazione + quality report dell'estrattore
        if result.status != "success" or result.process is None:
            failure = result.failure
            reason = failure.message if failure else "Estrazione del piano non riuscita."
            logger.warning("sintesi piano fallita per il processo %s: %s", process_id, reason)
            return PlanSynthesis(
                action="synthesis_failed",
                snapshot=build_process_snapshot(process_id),
                reason=reason,
                blockers=[reason],
                llm_calls=llm_calls,
            )
        understanding = result.process
    elif extraction.failures:
        # Una fonte con un testo che non si e' riusciti a leggere, anche dopo un
        # secondo tentativo. Un piano costruito senza di lei e dichiarato
        # "costruito sulle fonti" e' un piano che non coincide con le fonti: il
        # disegno che ne esce contraddice un'intervista che il consulente ha
        # fatto. Si chiude come guasto, e la coda riprova con il suo backoff.
        reason = "Fonti non lette: " + "; ".join(extraction.failures)
        logger.warning("estrazione parziale per il processo %s: %s", process_id, reason)
        return PlanSynthesis(
            action="synthesis_failed",
            snapshot=build_process_snapshot(process_id),
            reason=reason,
            blockers=list(extraction.failures),
            llm_calls=llm_calls,
        )

    result = ProcessUnderstandingResult(status="success", process=understanding)

    # La regola del confine vale anche per la sintesi: un piano senza attori,
    # partecipanti ne' attivita' su un processo che ha fonti agli atti non e'
    # prudenza, e' evidenza che non e' arrivata fino al piano. Salvarlo lo
    # renderebbe lo stato ufficiale del processo, e tutto cio' che viene dopo
    # leggerebbe quel vuoto invece delle interviste.
    ignored = plan_ignores_evidence(result.process, evidence_count(ledger))
    if ignored:
        logger.warning("sintesi piano vuota per il processo %s: %s", process_id, ignored)
        return PlanSynthesis(
            action="synthesis_failed",
            snapshot=build_process_snapshot(process_id),
            reason=ignored,
            blockers=[ignored],
            llm_calls=llm_calls,
        )

    previous = workspace_database.get_bpmn_review(
        process["bpmn_model_id"], include_approved=True
    )
    previous_version = int((previous or {}).get("version") or 0)

    try:
        workspace_database.prepare_bpmn_review(
            bpmn_model_id=process["bpmn_model_id"],
            process_description=corpus,
            process_understanding=result.process.model_dump(mode="json"),
            evidence_source_set_id=str(ledger.get("source_set_id") or ""),
        )
        # Write -> persistence -> read-after-write. Un piano che il database non
        # ha non e' un piano, e dichiararlo scritto e' esattamente il difetto che
        # faceva dire "review aggiornata" davanti a una review a zero attori.
        verify_review_persisted(
            process["bpmn_model_id"],
            expect_plan_content=True,
            minimum_version=previous_version + 1,
        )
    except (ProcessUnderstandingExtractionError, PersistenceVerificationError, ValueError) as exc:
        logger.warning(
            "piano non persistito per il processo %s: %s", process_id, exc, exc_info=True
        )
        return PlanSynthesis(
            action="synthesis_failed",
            snapshot=build_process_snapshot(process_id),
            reason=str(exc),
            blockers=[str(exc)],
            llm_calls=llm_calls,
        )

    # Il giudizio di qualita' lo da' `prepare_bpmn_review` sul piano intero, una
    # volta sola: e' la chiamata che l'estrazione per fonte non fa piu' su ogni
    # pezzo.
    llm_calls += 1
    snapshot = build_process_snapshot(process_id)
    return PlanSynthesis(
        action="synthesized",
        snapshot=snapshot,
        reason=(
            f"Piano costruito su {len(ledger.get('sources') or [])} fonti "
            f"(set {ledger.get('source_set_id')})."
        ),
        llm_calls=llm_calls,
    )


def ensure_process_plan(process_id: str, *, force: bool = False) -> PlanSynthesis:
    """Il processo ha un piano costruito sull'evidenza che ha adesso.

    E' il passo che il confine Process -> Canvas attraversa prima di ogni run di
    modellazione. Deterministico su *quando* sintetizzare: il piano si rifa' solo
    se non c'e', o se e' nato su un set di fonti diverso da quello corrente.
    Rifarlo a ogni giro cancellerebbe le risposte che il consulente ha gia' dato,
    che sono conoscenza e non ipotesi.

    Args:
        process_id: Il processo.
        force: Risintetizza anche se il piano risulta allineato. Serve quando il
            consulente chiede esplicitamente di ricostruire dalle fonti.

    Returns:
        L'esito, con lo snapshot che il Canvas dovra' leggere.
    """
    from backend import workspace_database
    from backend.graphs.process.nodes import evidence_count, load_evidence_ledger

    process = workspace_database.get_process(process_id)
    if process is None:
        return PlanSynthesis(
            action="process_not_found",
            snapshot=None,
            reason=f"Processo non trovato: {process_id}",
        )

    ledger = load_evidence_ledger(process.get("project_id"), process_id)
    review = workspace_database.get_bpmn_review(
        process["bpmn_model_id"], include_approved=True
    )
    snapshot = build_process_snapshot(process_id)

    if evidence_count(ledger) == 0:
        # Senza evidenza non si sintetizza, ma un piano scritto a mano resta
        # valido: e' conoscenza del consulente, non un residuo da cancellare.
        return PlanSynthesis(
            action="reused" if (snapshot and snapshot.has_semantic_model) else "no_evidence",
            snapshot=snapshot,
            reason="Nessuna evidenza agli atti per questo processo.",
            blockers=[]
            if (snapshot and snapshot.has_semantic_model)
            else ["Nessuna evidenza registrata per questo processo."],
        )

    source_set_id = str(ledger.get("source_set_id") or "")
    plan_current = (
        snapshot is not None
        and snapshot.has_semantic_model
        and plan_is_built_on(review, source_set_id)
    )
    if plan_current and not force:
        return PlanSynthesis(
            action="reused",
            snapshot=snapshot,
            reason=f"Il piano {snapshot.label} e' gia' costruito sul set di fonti corrente.",
        )

    if ledger.get("source_status") in {"error", "stale"} and snapshot and snapshot.has_semantic_model:
        # Il registro non e' stato riletto in questo turno: risintetizzare su un
        # set che potrebbe essere parziale farebbe sparire dal piano cio' che non
        # si e' riusciti a leggere. Meglio il piano di prima, dichiarato.
        return PlanSynthesis(
            action="reused",
            snapshot=snapshot,
            reason=(
                "Il set di fonti non e' leggibile in questo turno: tengo il piano "
                f"{snapshot.label} invece di ricostruirlo su un'evidenza parziale."
            ),
        )

    return synthesize_process_plan(process_id)


def repair_plan_from_audit(process_id: str, report) -> PlanSynthesis:
    """Ricostruisce il piano portando nell'estrazione i rilievi del revisore.

    E' il ritorno del loop di verifica: il revisore ha trovato in una fonte
    passaggi che il piano non rappresenta, o che contraddice, e ne ha portato le
    parole esatte - gia' ritrovate nel testo dal runtime. Si rilegge ogni fonte
    intera con quei punti segnalati, e il piano che ne esce prende il posto del
    precedente come nuova versione.

    Non e' prompt tuning e non e' un secondo tentativo alla cieca: l'input nuovo
    e' un fatto verificato sul testo, e la riparazione avviene al massimo il
    numero di volte che chi chiama concede.

    Args:
        process_id: Il processo.
        report: Il `ConformanceReport` con i rilievi da chiudere.

    Returns:
        L'esito della sintesi; `synthesized` quando il piano nuovo e' scritto.
    """
    from backend.agents.conformance_audit import reviewer_notes_by_source

    notes = reviewer_notes_by_source(report)
    if not notes:
        return PlanSynthesis(
            action="reused",
            snapshot=build_process_snapshot(process_id),
            reason="Nessun rilievo sulle fonti da riportare nel piano.",
        )
    return synthesize_process_plan(process_id, reviewer_notes=notes)
