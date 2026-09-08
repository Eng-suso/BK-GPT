"""Il registro dell'evidenza, reso una volta e letto da tutti.

Il registro esisteva gia' (`load_process_context` -> `evidence_ledger`), ma lo
leggeva un solo nodo: quello che scrive la risposta finale. Il router decideva
al buio, e lo specialista di modellazione apriva la sua passata senza vedere una
riga di cio' che le interviste avevano raccolto - da li' il piano che dichiarava
di conoscere "esclusivamente il titolo del processo" mentre tre fonti erano gia'
agli atti (PROCESS-V2-11), e la divergenza fra chi vedeva le interviste e chi
vedeva solo il titolo (PROCESS-V2-13).

Qui il registro si costruisce e si stampa una volta sola. Chi lo consuma - il
prompt di scope, il router, il nodo di risposta - legge le stesse righe, quindi
"stessa source of truth" smette di essere un proposito e diventa una funzione.
"""

from __future__ import annotations

import re

from backend.memory import provenance


# Quante righe di registro entrano in un prompt. Oltre questa soglia il contesto
# costa piu' di quanto renda: le righe sono ordinate per rilevanza dal ledger.
LEDGER_PROMPT_LIMIT = 60


def turn_evidence_ledger(state: dict) -> list[provenance.LedgerEntry]:
    """Il registro del turno: cio' che era persistito piu' cio' che si e' appena raccolto.

    Due sorgenti, un solo registro. Quello persistito tiene cio' che il processo
    sapeva gia'; `process_claims` tiene cio' che questa passata ha appena
    estratto e che non e' ancora tornato dal knowledge graph. Il grado di
    sostegno si ricalcola sull'unione: e' l'unico modo perche' due voci raccolte
    in momenti diversi contino come due.

    Args:
        state: Stato del turno di processo.

    Returns:
        Le righe del registro, deduplicate per (affermazione, voce).
    """
    persisted = ((state.get("evidence_ledger") or {}).get("claims")) or []
    fresh = state.get("process_claims") or []

    merged: dict[tuple[str, str], dict] = {}
    for item in [*persisted, *fresh]:
        record = provenance.claim_record(item)
        if not record.statement.strip():
            continue
        key = (provenance.normalize(record.statement), provenance.normalize(record.voice))
        merged.setdefault(key, item)

    contested = {
        provenance.topic_key(statement): [item.get("title") or ""]
        for item in (state.get("contradictions") or [])
        if item.get("divergence_type") == "incompatible"
        for statement in (item.get("conflicting_claims") or [])
    }
    return provenance.build_ledger(merged.values(), contested_topics=contested)


def render_ledger_lines(
    entries: list[provenance.LedgerEntry], limit: int = LEDGER_PROMPT_LIMIT
) -> str:
    """Il registro come lo legge un modello: una riga per affermazione."""
    if not entries:
        return "nessuna affermazione registrata per questo processo"
    lines = []
    for entry in entries[:limit]:
        claim = entry.claim
        scope = f" | ambito: {claim.scope_label}" if claim.scope_label.strip() else ""
        # Solo le citazioni riscontrate sul testo della fonte arrivano al
        # modello come "parole originali". Passargli una riformulazione con
        # quell'etichetta e' invitarlo a metterla fra virgolette.
        quote = (
            f' | parole originali: "{claim.quote.strip()}"'
            if claim.quote.strip() and claim.quote_verified
            else " | nessuna citazione riscontrata: non virgolettare"
            if claim.quote.strip()
            else ""
        )
        others = (
            " | anche: " + ", ".join(dict.fromkeys(entry.corroborating_sources))
            if entry.corroborating_sources
            else ""
        )
        # Cio' che dice solo questa voce viaggia separato dal nucleo condiviso:
        # e' l'unico modo perche' una frase attribuita a due fonti non erediti
        # la proprieta' che ne ha detta una.
        only = (
            f" | solo {claim.voice}: " + ", ".join(entry.exclusive_qualifiers)
            if entry.exclusive_qualifiers
            else ""
        )
        shared = (
            " | condiviso: " + ", ".join(entry.shared_qualifiers)
            if entry.shared_qualifiers
            else ""
        )
        lines.append(
            f"- {claim.statement} | voce: {claim.voice or 'non dichiarata'} "
            f"| sostegno: {provenance.SUPPORT_LABEL_IT.get(entry.support, entry.support)}"
            f"{scope}{others}{shared}{only}{quote}"
        )
    return "\n".join(lines)


def render_divergences(state: dict) -> str:
    """Le divergenze registrate, con il tipo che il runtime ha riconosciuto."""
    items = state.get("contradictions") or []
    if not items:
        return "nessuna"
    lines = []
    for item in items:
        label = item.get("divergence_label") or provenance.DIVERGENCE_LABEL_IT.get(
            item.get("divergence_type") or "", "da classificare"
        )
        voices = ", ".join(item.get("source_names") or item.get("voices") or [])
        lines.append(
            f"- {item.get('title') or 'senza titolo'} [{label}]" + (f" — {voices}" if voices else "")
        )
    return "\n".join(lines)


# Cio' che il registro dichiara di sapere e che quindi non si torna a chiedere in
# forma di categoria. Le chiavi sono le categorie che una domanda "a campo
# aperto" nomina; i valori dicono quale contenuto del registro le copre.
_COVERED_BY_LEDGER = "attori, attivita', regole, documenti, sistemi, eccezioni"


def evidence_prompt_block(state: dict) -> list[str]:
    """Le righe di registro da mettere nel prompt di scope di un processo.

    Restituisce una lista vuota quando lo scope non e' un processo: fuori dal
    processo il registro non e' definito e stamparlo sarebbe rumore.
    """
    if str(state.get("scope_type") or "") != "process":
        return []

    entries = turn_evidence_ledger(state)
    summary = provenance.summarize_ledger(entries)
    voices = ", ".join(summary.voices) or "nessuna"

    lines = [
        "",
        "REGISTRO DELL'EVIDENZA di questo processo. E' cio' che il processo sa "
        "gia', con chi lo dice e quanto e' sostenuto. Vale come stato di fatto: "
        "non e' materiale opzionale da rileggere solo se ti serve.",
        render_ledger_lines(entries),
        "",
        f"Voci sentite finora: {voices}",
        f"Divergenze registrate:\n{render_divergences(state)}",
    ]

    if entries:
        lines.extend(
            [
                "",
                "Come si usa il registro, prima di dichiarare che manca qualcosa:",
                f"- Cio' che il registro contiene ({_COVERED_BY_LEDGER}) e' noto. "
                "Non dichiararlo mancante e non ripartire dal solo nome del "
                "processo: se una voce sola lo dice, e' evidenza da corroborare, "
                "non un buco.",
                "- Una domanda di chiarimento deve citare la lacuna o la "
                "contraddizione concreta che l'ha generata, nominando la voce e "
                "cio' che ha detto. \"Quali sono gli attori?\" non e' una "
                "domanda: gli attori sono qui sopra.",
                "- Proponi alternative solo quando il registro le sostiene. Se le "
                "opzioni non escono dalle fonti, la domanda resta aperta.",
            ]
        )

    return lines


# Le forme che chiedono una categoria intera invece di una lacuna. Non sono
# "domande brutte" in assoluto: lo diventano quando il registro su quella
# categoria e' gia' pieno, ed e' esattamente il caso che il consulente ha visto
# (PROCESS-V2-15).
_CATCH_ALL_SHAPES: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"\bqual[ei]\s+(?:sono\s+)?(?:gli?|le|i)?\s*"
        r"(attori|ruoli|attivita|attivit|task|passaggi|step|regole|vincoli|"
        r"documenti|sistemi|applicativi|eccezioni|controlli|decisioni|criteri|"
        r"soglie|approvazioni)\b"
    ),
    re.compile(r"\bchi\s+(?:sono\s+gli?\s+attori|fa\s+cosa|partecipa)\b"),
    re.compile(r"\bcome\s+funziona\s+(?:il\s+)?processo\b"),
    re.compile(r"\bqual\s*e\s+il\s+processo\b"),
    re.compile(r"\bdescriv\w*\s+(?:il\s+)?processo\b"),
)

# Parole troppo comuni per provare che una domanda parla davvero del registro.
_STOPWORDS: frozenset[str] = frozenset(
    """
    a ad agli ai al alla alle allo anche c che chi ci co come con cosa cui da dai
    dal dalla dalle dallo degli dei del della delle dello di e ed gli ha hanno i
    il in la le lo ma mi ne nei nel nella nelle non o per piu quale quali quando
    quanto che se si sono su sui sul sulla sulle tra un una uno vi
    processo attore attori attivita ruolo ruoli regola regole documento documenti
    sistema sistemi passaggio passaggi
    """.split()
)

_MIN_TOKEN_CHARS = 4
_PUNCTUATION = re.compile(r"[^\w\s]+", re.UNICODE)

# Quante parole del registro deve nominare una domanda in forma di categoria per
# valere comunque. Una sola non basta: "quali soglie di approvazione servono per
# il sourcing?" tocca "approvazione" e resta una domanda di settore. Due o piu'
# significano che la domanda porta con se' il caso concreto - le voci, l'importo,
# il documento - e allora la forma larga e' solo il modo di chiudere la frase.
_CATCH_ALL_MIN_OVERLAP = 2


def content_tokens(text: str) -> set[str]:
    """Le parole di un testo che possono provare che due testi parlano della stessa cosa.

    Fuori restano le parole di servizio e i nomi delle categorie di processo:
    "attori" compare in ogni domanda generica, quindi non prova nulla. La
    punteggiatura cade con loro, perche' "fornitore." e "fornitore" sono la
    stessa parola e un confronto che li distingue non prova niente.
    """
    return {
        token
        for token in _PUNCTUATION.sub(" ", provenance.normalize(text)).split()
        if len(token) >= _MIN_TOKEN_CHARS and token not in _STOPWORDS
    }


def ledger_vocabulary(entries: list[provenance.LedgerEntry]) -> set[str]:
    """Le parole con cui il registro parla: voci, ambiti e affermazioni.

    Serve per stabilire, senza chiamare un modello, se una domanda si aggancia a
    cio' che sappiamo o se e' un template calato dall'alto.
    """
    vocabulary: set[str] = set()
    for entry in entries:
        claim = entry.claim
        vocabulary |= content_tokens(claim.statement)
        vocabulary |= content_tokens(claim.voice)
        vocabulary |= content_tokens(claim.scope_label)
    return vocabulary


def is_catch_all_question(question: str) -> bool:
    """La domanda chiede una categoria intera invece di una lacuna precisa."""
    normalized = provenance.normalize(question)
    return any(shape.search(normalized) for shape in _CATCH_ALL_SHAPES)


def question_is_grounded(
    question: str,
    vocabulary: set[str],
    *,
    grounded_in: str = "",
) -> bool:
    """La domanda cita qualcosa che il registro contiene davvero.

    Tre passaggi, in quest'ordine.

    Senza registro non c'e' niente rispetto a cui una domanda possa essere
    generica: la prima intervista si apre per forza con domande larghe, e
    bloccarle sarebbe peggio del difetto.

    Con un registro, la via maestra e' dichiarare la lacuna: se `grounded_in`
    nomina qualcosa che nel registro esiste, la domanda regge - anche se la sua
    forma e' larga, perche' ha detto da dove nasce.

    Senza dichiarazione resta il testo della domanda, e quanto pesca dal
    registro. Una domanda che non tocca nemmeno una parola del registro parla di
    un altro processo: e' il template di settore - sourcing, budget, conformita'
    - che nessuna fonte ha mai nominato. Una domanda in forma di categoria
    ("quali attori?") deve pescarne di piu', perche' la forma larga si giustifica
    solo se il contenuto e' stretto: "Paolo e Francesca divergono
    sull'approvazione per importi piccoli: quale descrive il processo effettivo?"
    nomina il conflitto prima di chiedere, e passa; "quali soglie di approvazione
    servono per il sourcing?" sfiora una parola sola, e non passa.

    Args:
        question: Il testo della domanda.
        vocabulary: Le parole del registro, da `ledger_vocabulary`.
        grounded_in: La lacuna o contraddizione dichiarata dall'estrattore.

    Returns:
        True se la domanda e' ancorata o se non c'e' registro su cui giudicarla.
    """
    if not vocabulary:
        return True
    if content_tokens(grounded_in) & vocabulary:
        return True
    overlap = len(content_tokens(question) & vocabulary)
    return overlap >= (
        _CATCH_ALL_MIN_OVERLAP if is_catch_all_question(question) else 1
    )
