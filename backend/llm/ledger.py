"""Leggere il registro dei consumi: «dove sono andati i soldi ieri».

Il gateway scrive una riga per ogni chiamata (`usage.record`). Questo modulo e'
l'altra meta': le query che rendono quella frase una domanda con una risposta,
invece di un'indagine dentro psql.

**La regola di onestà di questo modulo: un totale non si mostra mai da solo.**
`cost_estimate` e' `NULL` quando il modello non ha un prezzo configurato, e i
modelli senza prezzo esistono per davvero (la trascrizione al minuto, per
dirne una). Sommare i costi noti e stampare il risultato darebbe un numero piu'
basso del vero, dall'aria precisa: il tipo di numero su cui poi si fanno i
budget. Quindi ogni totale porta con se' **quanta parte del volume non aveva un
prezzo** (`righe_senza_prezzo`, `token_senza_prezzo`), e chi legge sa subito se
sta guardando il 3% o il 60% della spesa.

Il denaro si somma in `Decimal` e mai in `float`: `cost_estimate` e' salvato
come stringa decimale proprio per questo, e riconvertirlo in binario qui
vanificherebbe la scelta.

Le finestre temporali si esprimono in ISO UTC, la stessa forma con cui
`record()` scrive `created_at`: il confronto e' lessicografico e funziona
perche' la forma e' fissa. Non e' un caso fortunato, e' il motivo per cui la
colonna e' quella forma li'.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, select

from backend.workspace_storage import WorkspaceLlmUsage, workspace_connection

# `cache_hit` non e' una chiamata: e' una chiamata **evitata**. Tenerla dentro le
# medie le sporcherebbe di zeri e farebbe sembrare che il costo medio scende
# quando in realta' sta solo aumentando il numero di volte che non paghiamo.
ESITO_EVITATA = "cache_hit"
# Un rifiuto non ha nemmeno raggiunto il fornitore: zero token, zero costo.
ESITO_RIFIUTATA = "refused"


@dataclass(frozen=True, slots=True)
class Totale:
    """Il consumo di una fetta di registro, con la sua copertura di prezzo.

    Attributes:
        righe: Quante righe, di qualunque esito.
        chiamate: Le righe che sono arrivate al fornitore (escluse quelle
            evitate dalla cache e quelle rifiutate prima di partire).
        evitate: Le chiamate risparmiate dalla cache. E' il risultato migliore
            che possiamo avere, quindi si conta da solo.
        fallite: Le chiamate finite in errore o timeout. Sono spesa pagata per
            niente, ed e' la prima voce da guardare quando il costo sale.
        input/output/reasoning/cached: I token, nelle stesse quattro categorie
            in cui li registriamo. `reasoning` e' un sottoinsieme di `output`.
        costo_noto: La somma dei costi stimati, sulle sole righe che avevano un
            prezzo configurato.
        righe_senza_prezzo: Quante righe non l'avevano.
        token_senza_prezzo: Quanti token stanno in quelle righe. E' la misura
            vera di quanto il totale e' cieco: dieci righe senza prezzo di
            trascrizione pesano piu' di mille righe di rerank.
    """

    righe: int = 0
    chiamate: int = 0
    evitate: int = 0
    fallite: int = 0
    input: int = 0
    output: int = 0
    reasoning: int = 0
    cached: int = 0
    costo_noto: Decimal = Decimal(0)
    righe_senza_prezzo: int = 0
    token_senza_prezzo: int = 0

    @property
    def token_totali(self) -> int:
        return self.input + self.output

    @property
    def copertura_prezzo(self) -> float | None:
        """Quota di token che un prezzo ce l'aveva, fra 0 e 1.

        `None` quando non ci sono token affatto: una fetta di solo `cache_hit` o
        di soli rifiuti non ha una copertura da dichiarare, e inventarle uno
        `0.0` o un `1.0` direbbe una cosa falsa in tutti e due i versi.
        """
        if self.token_totali == 0:
            return None
        return 1.0 - (self.token_senza_prezzo / self.token_totali)


@dataclass(frozen=True, slots=True)
class Voce:
    """Una riga di un raggruppamento: il valore della dimensione e il suo totale."""

    chiave: str
    totale: Totale


def _finestra(giorni: int | None, since: str | None, until: str | None) -> tuple[str, str]:
    """Da «ultimi N giorni» a due estremi ISO UTC.

    `since` e `until` espliciti vincono su `giorni`: servono a interrogare una
    finestra passata (l'incidente di ieri l'altro) senza contare a mano.
    """
    fine = until or datetime.now(UTC).isoformat()
    if since is not None:
        return since, fine
    quanti = 1 if giorni is None else max(1, giorni)
    inizio = (datetime.now(UTC) - timedelta(days=quanti)).isoformat()
    return inizio, fine


def _condizioni(inizio: str, fine: str, tenant_id: str | None):
    where = [WorkspaceLlmUsage.created_at >= inizio, WorkspaceLlmUsage.created_at < fine]
    if tenant_id is not None:
        where.append(WorkspaceLlmUsage.tenant_id == tenant_id)
    return where


def _somma(righe) -> Totale:
    """Riduce righe grezze a un `Totale`, in Python e non in SQL.

    Il costo e' una **stringa** nel database, di proposito (denaro, non float):
    farlo sommare a Postgres vorrebbe dire un cast per riga, e un cast che
    fallisce su un valore storto ucciderebbe la query invece di saltare la riga.
    I volumi di un registro dei consumi stanno in memoria senza problemi, e
    quando non ci staranno piu' questo e' il posto da cambiare.
    """
    totale = Totale()
    for r in righe:
        evitata = r.outcome == ESITO_EVITATA
        rifiutata = r.outcome == ESITO_RIFIUTATA
        fallita = r.outcome in ("error", "timeout")
        token_riga = r.input_tokens + r.output_tokens

        costo = None
        if r.cost_estimate is not None:
            try:
                costo = Decimal(r.cost_estimate)
            except (ArithmeticError, ValueError):
                # Un valore storto e' un difetto nostro, non un motivo per non
                # rispondere: la riga finisce fra quelle senza prezzo, dove si
                # vede, invece di far cadere tutta la lettura.
                costo = None

        senza_prezzo = costo is None and not evitata and not rifiutata

        totale = Totale(
            righe=totale.righe + 1,
            chiamate=totale.chiamate + (0 if evitata or rifiutata else 1),
            evitate=totale.evitate + (1 if evitata else 0),
            fallite=totale.fallite + (1 if fallita else 0),
            input=totale.input + r.input_tokens,
            output=totale.output + r.output_tokens,
            reasoning=totale.reasoning + r.reasoning_tokens,
            cached=totale.cached + r.cached_input_tokens,
            costo_noto=totale.costo_noto + (costo or Decimal(0)),
            righe_senza_prezzo=totale.righe_senza_prezzo + (1 if senza_prezzo else 0),
            token_senza_prezzo=totale.token_senza_prezzo + (token_riga if senza_prezzo else 0),
        )
    return totale


_COLONNE = (
    WorkspaceLlmUsage.outcome,
    WorkspaceLlmUsage.input_tokens,
    WorkspaceLlmUsage.output_tokens,
    WorkspaceLlmUsage.reasoning_tokens,
    WorkspaceLlmUsage.cached_input_tokens,
    WorkspaceLlmUsage.cost_estimate,
)

DIMENSIONI = {
    "task": WorkspaceLlmUsage.task,
    "model": WorkspaceLlmUsage.model,
    "operation_kind": WorkspaceLlmUsage.operation_kind,
    "outcome": WorkspaceLlmUsage.outcome,
    "reasoning_effort": WorkspaceLlmUsage.reasoning_effort,
    "project_id": WorkspaceLlmUsage.project_id,
    "process_id": WorkspaceLlmUsage.process_id,
    "prompt_version": WorkspaceLlmUsage.prompt_version,
}


def totale(
    *,
    giorni: int | None = None,
    since: str | None = None,
    until: str | None = None,
    tenant_id: str | None = None,
) -> Totale:
    """Il consumo complessivo di una finestra."""
    inizio, fine = _finestra(giorni, since, until)
    with workspace_connection() as session:
        righe = session.execute(
            select(*_COLONNE).where(*_condizioni(inizio, fine, tenant_id))
        ).all()
    return _somma(righe)


def per(
    dimensione: str,
    *,
    giorni: int | None = None,
    since: str | None = None,
    until: str | None = None,
    tenant_id: str | None = None,
) -> list[Voce]:
    """Lo stesso consumo, spezzato per una dimensione, dal piu' caro al meno.

    Args:
        dimensione: Una chiave di `DIMENSIONI`. Sono le colonne con cui ha senso
            leggere la spesa: il compito, il modello, il tipo di lavoro, l'esito,
            il ragionamento chiesto, il progetto, il processo, la versione del
            prompt.

    Raises:
        KeyError: Se la dimensione non esiste. Meglio un errore che un
            raggruppamento silenziosamente sbagliato.
    """
    colonna = DIMENSIONI[dimensione]
    inizio, fine = _finestra(giorni, since, until)

    with workspace_connection() as session:
        righe = session.execute(
            select(colonna.label("chiave"), *_COLONNE).where(*_condizioni(inizio, fine, tenant_id))
        ).all()

    gruppi: dict[str, list] = {}
    for r in righe:
        # `NULL` e' una risposta, non un buco da nascondere: «spesa senza
        # progetto» e' esattamente cio' che si vuole vedere quando si cerca chi
        # non sta attribuendo il proprio lavoro.
        gruppi.setdefault(r.chiave if r.chiave is not None else "(nessuno)", []).append(r)

    voci = [Voce(chiave=k, totale=_somma(v)) for k, v in gruppi.items()]
    return sorted(voci, key=lambda v: (v.totale.costo_noto, v.totale.token_totali), reverse=True)


def per_giorno(
    *,
    giorni: int = 7,
    tenant_id: str | None = None,
) -> list[Voce]:
    """Il consumo giorno per giorno, dal piu' recente.

    E' la forma in cui si guarda «ieri»: un totale solo non dice se la spesa di
    ieri era normale, e la domanda da cui e' nato tutto era proprio quella.
    """
    inizio, fine = _finestra(giorni, None, None)
    with workspace_connection() as session:
        righe = session.execute(
            select(
                func.substr(WorkspaceLlmUsage.created_at, 1, 10).label("chiave"), *_COLONNE
            ).where(*_condizioni(inizio, fine, tenant_id))
        ).all()

    gruppi: dict[str, list] = {}
    for r in righe:
        gruppi.setdefault(r.chiave, []).append(r)
    return [Voce(chiave=k, totale=_somma(gruppi[k])) for k in sorted(gruppi, reverse=True)]


@dataclass(frozen=True, slots=True)
class CostoRitentato:
    """Quanto costano i retry.

    Attributes:
        primi_tentativi: Righe con `attempt = 1`.
        ritentativi: Righe con `attempt > 1`. Ognuna e' una chiamata pagata due
            volte per avere una risposta sola.
        costo_ritentativi: La spesa dei soli ritentativi.
        token_ritentativi: I loro token.
    """

    primi_tentativi: int = 0
    ritentativi: int = 0
    costo_ritentativi: Decimal = Decimal(0)
    token_ritentativi: int = 0


def costo_dei_retry(
    *,
    giorni: int | None = None,
    since: str | None = None,
    until: str | None = None,
    tenant_id: str | None = None,
) -> CostoRitentato:
    """«Quanto costano i retry» come query, che e' il motivo per cui `attempt`
    e' una colonna e non un dettaglio del log."""
    inizio, fine = _finestra(giorni, since, until)
    with workspace_connection() as session:
        righe = session.execute(
            select(WorkspaceLlmUsage.attempt, *_COLONNE).where(
                *_condizioni(inizio, fine, tenant_id)
            )
        ).all()

    ritentati = [r for r in righe if r.attempt > 1]
    somma = _somma(ritentati)
    return CostoRitentato(
        primi_tentativi=len(righe) - len(ritentati),
        ritentativi=len(ritentati),
        costo_ritentativi=somma.costo_noto,
        token_ritentativi=somma.token_totali,
    )


@dataclass(frozen=True, slots=True)
class PesoDelRagionamento:
    """Quanto dell'uscita di un compito e' ragionamento.

    E' la misura che serve al primo esperimento con il registro in mano: il
    default `medium` vale per sette compiti diversi, e due di loro rispondono
    dentro uno schema strict, dove lo schema fa il lavoro che il ragionamento
    farebbe. Se la quota e' alta e la qualita' non cambia, l'effort scende.

    Attributes:
        task: Il compito.
        reasoning_effort: Il livello chiesto, come sta nel profilo.
        output_tokens: I token di uscita, ragionamento compreso.
        reasoning_tokens: Quanti di quelli erano ragionamento.
        quota: `reasoning / output`, o `None` se non c'e' uscita da dividere.
    """

    task: str
    reasoning_effort: str | None
    output_tokens: int
    reasoning_tokens: int

    @property
    def quota(self) -> float | None:
        if self.output_tokens == 0:
            return None
        return self.reasoning_tokens / self.output_tokens


def peso_del_ragionamento(
    *,
    giorni: int | None = None,
    since: str | None = None,
    until: str | None = None,
    tenant_id: str | None = None,
) -> list[PesoDelRagionamento]:
    """Quanto ragionamento paga ogni compito, dal piu' pesante."""
    inizio, fine = _finestra(giorni, since, until)
    with workspace_connection() as session:
        righe = session.execute(
            select(
                WorkspaceLlmUsage.task,
                WorkspaceLlmUsage.reasoning_effort,
                func.sum(WorkspaceLlmUsage.output_tokens).label("output"),
                func.sum(WorkspaceLlmUsage.reasoning_tokens).label("reasoning"),
            )
            .where(*_condizioni(inizio, fine, tenant_id))
            .group_by(WorkspaceLlmUsage.task, WorkspaceLlmUsage.reasoning_effort)
        ).all()

    pesi = [
        PesoDelRagionamento(
            task=r.task,
            reasoning_effort=r.reasoning_effort,
            output_tokens=int(r.output or 0),
            reasoning_tokens=int(r.reasoning or 0),
        )
        for r in righe
    ]
    return sorted(pesi, key=lambda p: p.reasoning_tokens, reverse=True)


@dataclass(frozen=True, slots=True)
class CostoPerValidazione:
    """Il KPI di punta del piano: quanto costa arrivare a un AS-IS validato.

    La validazione e' l'approvazione di una review BPMN
    (`approve_bpmn_review`), che lascia una riga di versione con
    `status="approved"`: c'e' gia', non e' stato necessario inventarla.

    Il costo di un AS-IS e' la spesa registrata **su quel processo fino al
    momento in cui e' stato approvato**. Non la spesa totale del processo: cio'
    che viene dopo l'approvazione e' manutenzione, e mescolarla renderebbe il
    numero piu' alto ogni volta che si torna su un processo vecchio, senza che
    sia cambiato niente su quanto costa produrne uno.

    Attributes:
        validazioni: Quante approvazioni sono misurabili nella finestra.
        non_misurabili: Le approvazioni avvenute **prima** della prima riga del
            registro. Non sono zero-costo, sono spesa che non abbiamo: contarle
            al denominatore abbasserebbe la media raccontando un risparmio che
            non e' avvenuto.
        costo_noto: La spesa attribuita, sui modelli che avevano un prezzo.
        token: I token attribuiti.
        righe_senza_prezzo: Quante righe attribuite non avevano prezzo.
        senza_attribuzione: Righe nella finestra senza `process_id`. Non entrano
            nel KPI e sono il suo margine di errore: se sono tante, il costo per
            AS-IS e' sottostimato e il numero da sistemare e' l'attribuzione,
            non il KPI.
    """

    validazioni: int = 0
    non_misurabili: int = 0
    costo_noto: Decimal = Decimal(0)
    token: int = 0
    righe_senza_prezzo: int = 0
    senza_attribuzione: int = 0

    @property
    def costo_medio(self) -> Decimal | None:
        """La media, o `None` se non c'e' niente di misurabile da dividere."""
        if self.validazioni == 0:
            return None
        return self.costo_noto / Decimal(self.validazioni)


def costo_per_as_is_validato(
    *,
    giorni: int | None = None,
    since: str | None = None,
    until: str | None = None,
    tenant_id: str | None = None,
) -> CostoPerValidazione:
    """«Quanto ci costa un AS-IS validato», come query.

    Ogni processo conta una volta sola anche se e' stato approvato piu' volte:
    si prende la **prima** approvazione, perche' e' quella che chiude il lavoro
    di produrlo. Le successive sono revisioni di qualcosa che esisteva gia'.
    """
    from backend.workspace_storage import WorkspaceBpmnReviewVersion

    inizio, fine = _finestra(giorni, since, until)

    with workspace_connection() as session:
        where_validazioni = [
            WorkspaceBpmnReviewVersion.status == "approved",
            WorkspaceBpmnReviewVersion.created_at >= inizio,
            WorkspaceBpmnReviewVersion.created_at < fine,
        ]
        if tenant_id is not None:
            where_validazioni.append(WorkspaceBpmnReviewVersion.tenant_id == tenant_id)

        approvazioni = session.execute(
            select(
                WorkspaceBpmnReviewVersion.process_id,
                func.min(WorkspaceBpmnReviewVersion.created_at).label("quando"),
            )
            .where(*where_validazioni)
            .group_by(WorkspaceBpmnReviewVersion.process_id)
        ).all()

        prima_riga = session.execute(select(func.min(WorkspaceLlmUsage.created_at))).scalar()

        senza_attribuzione = (
            session.execute(
                select(func.count())
                .select_from(WorkspaceLlmUsage)
                .where(
                    *_condizioni(inizio, fine, tenant_id),
                    WorkspaceLlmUsage.process_id.is_(None),
                )
            ).scalar()
            or 0
        )

        misurabili = [a for a in approvazioni if prima_riga is not None and a.quando >= prima_riga]

        righe = []
        for approvazione in misurabili:
            righe.extend(
                session.execute(
                    select(*_COLONNE).where(
                        WorkspaceLlmUsage.process_id == approvazione.process_id,
                        WorkspaceLlmUsage.created_at <= approvazione.quando,
                        *([WorkspaceLlmUsage.tenant_id == tenant_id] if tenant_id else []),
                    )
                ).all()
            )

    somma = _somma(righe)
    return CostoPerValidazione(
        validazioni=len(misurabili),
        non_misurabili=len(approvazioni) - len(misurabili),
        costo_noto=somma.costo_noto,
        token=somma.token_totali,
        righe_senza_prezzo=somma.righe_senza_prezzo,
        senza_attribuzione=int(senza_attribuzione),
    )


@dataclass(frozen=True, slots=True)
class ModelloDaPrezzare:
    """Un modello che ha girato davvero, e se il listino sa quanto costa.

    Attributes:
        model: Il nome, come lo registra il fornitore.
        righe: Quante chiamate sono passate di li' nella finestra.
        token: Quanti token. E' l'ordine con cui conviene riempire il listino:
            il modello che ha bruciato piu' token e' quello che rende cieco il
            totale.
        prezzato: Se `LLM_PRICES_JSON` ha una voce per questo modello.
    """

    model: str
    righe: int
    token: int
    prezzato: bool


def modelli_da_prezzare(
    *,
    giorni: int | None = None,
    since: str | None = None,
    until: str | None = None,
    tenant_id: str | None = None,
) -> list[ModelloDaPrezzare]:
    """Quali modelli hanno girato, e quali di loro il listino non sa valorizzare.

    Serve a chiudere il cerchio della misura. Il registro conta i token sempre,
    ma senza `LLM_PRICES_JSON` il costo e' `NULL` su ogni riga: si sa quanto si
    e' consumato, non quanto si e' speso. Questa lista dice **esattamente quali
    prezzi mancano**, in ordine di quanto pesano, cosi' configurarli e' un
    lavoro di cinque minuti invece di una caccia.
    """
    from backend.llm.prices import price_for

    inizio, fine = _finestra(giorni, since, until)
    with workspace_connection() as session:
        righe = session.execute(
            select(
                WorkspaceLlmUsage.model,
                func.count().label("righe"),
                func.sum(WorkspaceLlmUsage.input_tokens + WorkspaceLlmUsage.output_tokens).label(
                    "token"
                ),
            )
            .where(*_condizioni(inizio, fine, tenant_id))
            .group_by(WorkspaceLlmUsage.model)
        ).all()

    modelli = [
        ModelloDaPrezzare(
            model=r.model,
            righe=int(r.righe or 0),
            token=int(r.token or 0),
            prezzato=price_for(r.model) is not None,
        )
        for r in righe
    ]
    return sorted(modelli, key=lambda m: (m.prezzato, -m.token))
