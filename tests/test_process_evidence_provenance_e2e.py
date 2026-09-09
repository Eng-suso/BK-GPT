"""PROCESS-V3 — la provenance regge il percorso vero, dall'intervista alla chat.

Nel test E2E V3 la chat di processo, su tre interviste corpose, ha:

1. attribuito a una persona informazioni provenienti da un'altra;
2. dichiarato che due fonti concordavano su punti presenti in una sola;
3. risposto a "mostrami claim -> fonte -> estratto" con una nuova sintesi;
4. presentato con linguaggio forte cio' che diceva una fonte sola;
5. trasformato un "non conosco la policy" in una contraddizione;
6. dichiarato mancante un'informazione gia' presente nelle evidenze;
7. generalizzato al processo intero una testimonianza della Manutenzione;
8. reso la sintesi piu' forte del testo originale.

Qui si attraversano i path veri - tool di salvataggio dell'agente, mirror
canonical, coda di ingestion, proiezione Neo4j, gateway di lettura, apertura di
un nuovo turno di chat - e si verificano invarianti, non frasi. I nomi del
dataset (Laura, Paolo, Francesca) sono materiale: nessuna asserzione dipende da
chi sono, solo da chi ha detto cosa.

Servono le DSN canonical + workspace + NEO4J_PASSWORD (`cd ops && docker
compose up -d`).
"""

from __future__ import annotations

import json
import time
import uuid
from pathlib import Path

import pytest
from sqlalchemy import create_engine, text

from backend.settings import settings

_NEEDED = (
    settings.workspace_database_url,
    settings.canonical_migrator_url,
    settings.canonical_database_url,
    settings.canonical_worker_url,
    settings.neo4j_password,
)
if not all(_NEEDED):
    pytest.skip(
        "servono WORKSPACE_DATABASE_URL + le DSN canonical + NEO4J_PASSWORD",
        allow_module_level=True,
    )

from backend.memory import provenance  # noqa: E402
from backend.memory.knowledge_graph import neo4j_store  # noqa: E402

MIGRATOR = create_engine(settings.canonical_migrator_url, future=True)
FIXTURES = Path(__file__).parent / "fixtures" / "interviews"


def _read(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


# --- il dataset: tre interviste da 600-900 parole, con la loro provenance ---
#
# Ogni claim porta chi lo dice, il tema su cui si conta la corroborazione, il
# passaggio verbatim e il perimetro che copre. Le citazioni sono ricopiate dal
# testo: quelle che NON lo sono stanno qui apposta, per verificare che il
# runtime le riconosca.

TECH_LEAD = "Laura Conti"
MAINTENANCE_LEAD = "Paolo Marchetti"
PURCHASING = "Francesca Neri"

TITLE_TECH = "Intervista Laura Conti - Ufficio Tecnico"
TITLE_MAINTENANCE = "Intervista Paolo Marchetti - Manutenzione"
TITLE_PURCHASING = "Intervista Francesca Neri - Acquisti"

# I temi (SOGGETTI) su cui si gioca il test, e le proposizioni su cui si conta
# l'accordo. Sono due cose diverse: parlare di autorizzazione non e' dire la
# stessa cosa sull'autorizzazione, ed e' su questa distinzione che si reggono i
# casi di composizione multi-fonte.
TOPIC_HANDOVER = "passaggio ad acquisti"
TOPIC_VISIBILITY = "visibilita sullo stato della richiesta"
TOPIC_URGENCY = "gestione urgenze"
TOPIC_ARRIVAL = "arrivo della merce"
TOPIC_WHO_REGULARISES = "chi regolarizza le urgenze"
TOPIC_AUTHORISATION = "autorizzazione spesa"

SAYS_HANDOVER = "la richiesta passa dall'ufficio tecnico ad acquisti via mail"
SAYS_NO_VISIBILITY = "chi ha fatto la richiesta non ne vede lo stato"
SAYS_DIRECT_SUPPLIER = "in urgenza il reparto ordina direttamente dal fornitore"
SAYS_NO_ARRIVAL_NOTICE = "l'arrivo della merce non genera un avviso automatico"
SAYS_PURCHASING_OPENS_ORDER = "l'ordine a posteriori lo apre l'ufficio acquisti"
SAYS_AUTHORISATION_EXISTS = "sopra soglia serve una autorizzazione del responsabile"

# L'attributo che dice UNA sola voce, in due casi diversi. Non deve mai finire
# in una frase attribuita a piu' fonti.
ONLY_MAINTENANCE_SAYS = "fornitore gia' conosciuto"
ONLY_PURCHASING_SAYS = "verifica formale prima dell'ordine"


INTERVIEWS = (
    {
        "title": TITLE_TECH,
        "file": "a1_laura_conti_ufficio_tecnico.md",
        "participants": [TECH_LEAD],
        "entities": [TECH_LEAD, "Ufficio Tecnico", "Richiesta di acquisto"],
        "claims": [
            {
                "claim": "Le richieste arrivano all'Ufficio Tecnico per mail, messaggio o a voce.",
                "process_area": "activity",
                "source_name": TITLE_TECH,
                "attributed_to": TECH_LEAD,
                "topic": "canale di arrivo della richiesta",
                "quote": "arriva in tre modi diversi a seconda di chi la manda",
                "scope_label": "Ufficio Tecnico",
                "epistemic_status": "observed",
                "confidence": "high",
                "status": "partial",
            },
            {
                "claim": "L'Ufficio Tecnico passa la richiesta ad Acquisti via mail.",
                "process_area": "handoff",
                "source_name": TITLE_TECH,
                "attributed_to": TECH_LEAD,
                "topic": TOPIC_HANDOVER,
                "assertion": SAYS_HANDOVER,
                "quote": "La passo ad Acquisti.",
                "scope_label": "Ufficio Tecnico",
                "epistemic_status": "observed",
                "confidence": "high",
                "status": "partial",
            },
            {
                "claim": "Chi c'e' a monte non ha visibilita' sullo stato della richiesta.",
                "process_area": "system",
                "source_name": TITLE_TECH,
                "attributed_to": TECH_LEAD,
                "topic": TOPIC_VISIBILITY,
                "assertion": SAYS_NO_VISIBILITY,
                "quote": "Non ho un posto dove guardare per sapere se hanno ordinato",
                "scope_label": "Ufficio Tecnico",
                "epistemic_status": "observed",
                "confidence": "high",
                "status": "partial",
            },
            {
                "claim": "L'Ufficio Tecnico non sa quale sia la soglia ne' chi firmi l'autorizzazione.",
                "process_area": "control",
                "source_name": TITLE_TECH,
                "attributed_to": TECH_LEAD,
                "topic": TOPIC_AUTHORISATION,
                "assertion": SAYS_AUTHORISATION_EXISTS,
                "quote": "quale sia la cifra e chi firmi non te lo so dire",
                "scope_label": "Ufficio Tecnico",
                "epistemic_status": "declared_unknown",
                "confidence": "high",
                "status": "partial",
            },
            {
                "claim": "L'Ufficio Tecnico non sa chi regolarizzi la pratica dopo un'urgenza.",
                "process_area": "exception",
                "source_name": TITLE_TECH,
                "attributed_to": TECH_LEAD,
                "topic": TOPIC_WHO_REGULARISES,
                "assertion": SAYS_PURCHASING_OPENS_ORDER,
                "quote": "la parte di carta viene messa a posto dopo, ma non so da chi",
                "scope_label": "Ufficio Tecnico",
                "epistemic_status": "declared_unknown",
                "confidence": "high",
                "status": "partial",
            },
        ],
    },
    {
        "title": TITLE_MAINTENANCE,
        "file": "a2_paolo_marchetti_manutenzione.md",
        "participants": [MAINTENANCE_LEAD],
        "entities": [MAINTENANCE_LEAD, "Manutenzione", "Richiesta urgente"],
        "claims": [
            {
                "claim": "In caso di linea ferma la Manutenzione chiama direttamente il fornitore.",
                "process_area": "exception",
                "source_name": TITLE_MAINTENANCE,
                "attributed_to": MAINTENANCE_LEAD,
                "topic": TOPIC_URGENCY,
                "assertion": SAYS_DIRECT_SUPPLIER,
                # Il "conosciuto" lo dice solo la Manutenzione: e' un attributo
                # suo, non parte di cio' che le due fonti condividono.
                "qualifiers": [ONLY_MAINTENANCE_SAYS],
                "quote": (
                    "chiamo direttamente il fornitore, mi faccio mandare il pezzo e poi "
                    "la parte amministrativa viene sistemata dopo"
                ),
                "scope_label": "Manutenzione",
                "epistemic_status": "observed",
                "confidence": "high",
                "status": "partial",
            },
            {
                "claim": "La Manutenzione non sa chi apra l'ordine dopo un acquisto in urgenza.",
                "process_area": "exception",
                "source_name": TITLE_MAINTENANCE,
                "attributed_to": MAINTENANCE_LEAD,
                "topic": TOPIC_WHO_REGULARISES,
                "assertion": SAYS_PURCHASING_OPENS_ORDER,
                "quote": "Se mi chiedi chi materialmente lo fa, non lo so",
                "scope_label": "Manutenzione",
                "epistemic_status": "declared_unknown",
                "confidence": "high",
                "status": "partial",
            },
            {
                "claim": "Chi c'e' a monte non ha visibilita' sullo stato della richiesta.",
                "process_area": "system",
                "source_name": TITLE_MAINTENANCE,
                "attributed_to": MAINTENANCE_LEAD,
                "topic": TOPIC_VISIBILITY,
                "assertion": SAYS_NO_VISIBILITY,
                "quote": "Non ricevo una conferma che la richiesta e' stata presa in carico",
                "scope_label": "Manutenzione",
                "epistemic_status": "observed",
                "confidence": "high",
                "status": "partial",
            },
            {
                "claim": "L'arrivo della merce in magazzino non genera un avviso.",
                "process_area": "system",
                "source_name": TITLE_MAINTENANCE,
                "attributed_to": MAINTENANCE_LEAD,
                "topic": TOPIC_ARRIVAL,
                "assertion": SAYS_NO_ARRIVAL_NOTICE,
                "quote": "Non c'e' un avviso automatico.",
                "scope_label": "Manutenzione",
                "epistemic_status": "observed",
                "confidence": "high",
                "status": "partial",
            },
        ],
    },
    {
        "title": TITLE_PURCHASING,
        "file": "a3_francesca_neri_acquisti.md",
        "participants": [PURCHASING],
        "entities": [PURCHASING, "Ufficio Acquisti", "Autorizzazione di spesa"],
        "claims": [
            {
                "claim": "Le richieste arrivano ad Acquisti via mail, quasi sempre dall'Ufficio Tecnico.",
                "process_area": "handoff",
                "source_name": TITLE_PURCHASING,
                "attributed_to": PURCHASING,
                "topic": TOPIC_HANDOVER,
                "assertion": SAYS_HANDOVER,
                "quote": "Mi arrivano via mail, quasi sempre da Laura.",
                "scope_label": "Ufficio Acquisti",
                "epistemic_status": "observed",
                "confidence": "high",
                "status": "partial",
            },
            {
                "claim": "L'ordine a posteriori di un acquisto in urgenza lo apre l'Ufficio Acquisti.",
                "process_area": "exception",
                "source_name": TITLE_PURCHASING,
                "attributed_to": PURCHASING,
                "topic": TOPIC_WHO_REGULARISES,
                "assertion": SAYS_PURCHASING_OPENS_ORDER,
                "quote": "La parte di ordine si', la faccio io.",
                "scope_label": "Ufficio Acquisti",
                "epistemic_status": "observed",
                "confidence": "high",
                "status": "partial",
            },
            {
                "claim": "Sopra una certa cifra Acquisti chiede una autorizzazione al proprio responsabile.",
                "process_area": "control",
                "source_name": TITLE_PURCHASING,
                "attributed_to": PURCHASING,
                "topic": TOPIC_AUTHORISATION,
                "assertion": SAYS_AUTHORISATION_EXISTS,
                # Solo Acquisti descrive la verifica formale: chi non conosce
                # la policy non la sta confermando.
                "qualifiers": [ONLY_PURCHASING_SAYS],
                "quote": "Sopra una certa cifra devo chiedere una autorizzazione al mio responsabile",
                "scope_label": "Ufficio Acquisti",
                "epistemic_status": "reported",
                "confidence": "medium",
                "status": "partial",
            },
            {
                "claim": "Acquisti vede l'acquisto urgente solo dopo, dal riferimento dell'ordine.",
                "process_area": "exception",
                "source_name": TITLE_PURCHASING,
                "attributed_to": PURCHASING,
                "topic": TOPIC_URGENCY,
                "assertion": SAYS_DIRECT_SUPPLIER,
                "quote": "Paolo mi manda la mail con il riferimento dell'ordine che ha fatto lui",
                "scope_label": "Ufficio Acquisti",
                "epistemic_status": "observed",
                "confidence": "high",
                "status": "partial",
            },
            # Deliberatamente piu' forte del testo: la fonte dice che il
            # passaggio esiste ma non ne conosce i termini, questa citazione lo
            # trasforma in un obbligo generale. Deve arrivare a valle marcata
            # come non riscontrata.
            {
                "claim": "Il responsabile deve confermare ogni acquisto indiretto.",
                "process_area": "control",
                "source_name": TITLE_PURCHASING,
                "attributed_to": PURCHASING,
                "topic": "obbligo di conferma del responsabile",
                "quote": "il responsabile deve confermare ogni acquisto indiretto",
                "scope_label": "Ufficio Acquisti",
                "epistemic_status": "reported",
                "confidence": "low",
                "status": "partial",
            },
        ],
    },
)

# Il processo vicino, stesso cliente, altro incarico: la sua Laura Conti fa un
# altro mestiere. Se il suo ruolo entra nel registro del processo A, la
# provenance non e' un confine ma un'etichetta.
OTHER_PROCESS_INTERVIEW = {
    "title": "Intervista Laura Conti - Facility",
    "file": "b1_laura_conti_facility.md",
    "participants": [TECH_LEAD],
    "entities": [TECH_LEAD, "Facility Manager", "Zentrix Impianti"],
    "claims": [
        {
            "claim": "Sopra 5.000 euro il Facility Manager raccoglie due offerte.",
            "process_area": "control",
            "source_name": "Intervista Laura Conti - Facility",
            "attributed_to": TECH_LEAD,
            "topic": TOPIC_AUTHORISATION,
            "quote": "",
            "scope_label": "Facility",
            "epistemic_status": "reported",
            "confidence": "high",
            "status": "partial",
        }
    ],
}


# --- il percorso vero -------------------------------------------------------


def _bind_process_chat(project_id: str, process_id: str):
    from backend.agents.scope_guard import bind_active_scope
    from backend.schemas.chat import ProcessChatScope

    return bind_active_scope(
        ProcessChatScope(type="process", project_id=project_id, process_id=process_id)
    )


def _tool_payload(result: str) -> dict:
    return json.loads(result.split("\n", 1)[1])["payload"]


def _tool_envelope(result: str) -> dict:
    return json.loads(result.split("\n", 1)[1])


def _save_interviews(project_id: str, process_id: str, interviews) -> None:
    """Salva passando dal tool vero dell'agente, come in una chat."""
    from backend.toolsets.process_memory import manage_process_evidence

    for interview in interviews:
        manage_process_evidence.invoke(
            {
                "operation": "save_interview",
                "project_id": project_id,
                "process_id": process_id,
                "title": interview["title"],
                "raw_content": _read(interview["file"]),
                "summary": interview["title"],
                "participants": interview["participants"],
                "entities": interview["entities"],
                "claims": interview["claims"],
            }
        )


def _drain_pass() -> int:
    from backend.workers.graph_worker import drain_once as drain_graph
    from backend.workers.ingest_worker import drain_once as drain_ingest

    processed = drain_ingest(limit=50)
    drain_graph(limit=200)
    return processed


def _drain_until(landed, *, expected: int, tries: int = 40, delay: float = 0.5) -> int:
    """Drena e aspetta finche' l'evidenza attesa non e' atterrata.

    L'ingestione e' asincrona anche in produzione, e la coda e' per consulente:
    un worker in-process (o un altro drenatore) puo' aver gia' preso in carico
    un job, che quindi non e' piu' reclamabile ma nemmeno ancora scritto. Un
    numero fisso di passate rende il test una scommessa su chi arriva prima;
    qui si aspetta il risultato, che e' l'unica cosa che conta davvero.
    """
    count = 0
    for _ in range(tries):
        _drain_pass()
        count = landed()
        if count >= expected:
            return count
        time.sleep(delay)
    return count


@pytest.fixture()
def workspace():
    from backend import workspace_database as wd
    from backend.security import reset_current_tenant_id, set_current_tenant_id

    token = set_current_tenant_id(f"t-{uuid.uuid4().hex[:8]}")
    suffix = uuid.uuid4().hex[:8]
    client = wd.create_client(name=f"Contoso Manifattura {suffix}")
    project = wd.create_project(client_id=client["id"], name=f"Acquisti indiretti {suffix}")
    process = wd.create_process(
        project_id=project["id"], name="Gestione acquisto materiali indiretti e servizi"
    )
    other_project = wd.create_project(client_id=client["id"], name=f"Facility sede {suffix}")
    other_process = wd.create_process(
        project_id=other_project["id"], name="Gestione segnalazioni tecniche"
    )

    scope = {
        "project": project["id"],
        "process": process["id"],
        "other_project": other_project["id"],
        "other_process": other_process["id"],
    }
    try:
        yield scope
    finally:
        from backend.memory import scope as canonical_scope

        canonical_client = canonical_scope.resolve_client_id(project["id"])
        _forget_episodes([project["id"], other_project["id"]])
        reset_current_tenant_id(token)
        if canonical_client:
            with MIGRATOR.begin() as conn:
                conn.execute(text("DELETE FROM client WHERE id = :i"), {"i": canonical_client})
            neo4j_store.purge_client(canonical_client)


def _forget_episodes(project_ids: list[str]) -> None:
    from backend.memory.episodic import episodic_store

    with episodic_store.episodic_connection() as session:
        session.execute(
            text("DELETE FROM episodes WHERE project = ANY(:p)"), {"p": project_ids}
        )


EXPECTED_CLAIMS = sum(len(interview["claims"]) for interview in INTERVIEWS)


@pytest.fixture()
def three_interviews(workspace):
    """Tre interviste corpose salvate come le salva l'agente, poi ingerite.

    L'ingestione e' asincrona anche in produzione: qui si drena e poi si
    verifica che l'evidenza sia davvero atterrata, cosi' un test che fallisce
    dice quale invariante non regge invece di far scoprire a valle che il
    registro era mezzo vuoto.
    """
    with _bind_process_chat(workspace["project"], workspace["process"]):
        _save_interviews(workspace["project"], workspace["process"], INTERVIEWS)
    with _bind_process_chat(workspace["other_project"], workspace["other_process"]):
        _save_interviews(
            workspace["other_project"], workspace["other_process"], [OTHER_PROCESS_INTERVIEW]
        )

    # Si aspettano entrambi i processi: il confine si verifica da tutti e due i
    # lati, e un registro vicino ancora vuoto non dimostrerebbe isolamento ma
    # solo che l'ingestione non aveva finito.
    def _both() -> int:
        return len(_ledger(workspace)) + len(
            _ledger(workspace, project_key="other_project", process_key="other_process")
        )

    expected = EXPECTED_CLAIMS + len(OTHER_PROCESS_INTERVIEW["claims"])
    landed = _drain_until(_both, expected=expected)
    assert landed == expected, f"evidenza non ingerita: {landed} claim su {expected}"
    return workspace


def _ledger(ws: dict, *, process_key: str = "process", project_key: str = "project") -> list[dict]:
    from backend.toolsets.process_memory import manage_process_evidence

    with _bind_process_chat(ws[project_key], ws[process_key]):
        result = manage_process_evidence.invoke(
            {
                "operation": "ledger",
                "project_id": ws[project_key],
                "process_id": ws[process_key],
                "limit": 50,
            }
        )
    return _tool_payload(result)["claims"]


def _provenance(ws: dict, query: str = "") -> dict:
    from backend.toolsets.process_memory import manage_process_evidence

    with _bind_process_chat(ws["project"], ws["process"]):
        result = manage_process_evidence.invoke(
            {
                "operation": "provenance",
                "project_id": ws["project"],
                "process_id": ws["process"],
                "query": query,
                "limit": 50,
            }
        )
    return _tool_envelope(result)


def _by_topic(claims: list[dict], topic: str) -> list[dict]:
    """I claim che parlano di un soggetto. Parlarne non e' concordarci."""
    key = provenance.topic_key(topic)
    return [claim for claim in claims if claim["topic"] == key]


def _by_assertion(claims: list[dict], assertion: str) -> list[dict]:
    """I claim che asseriscono la stessa proposizione: e' qui che si conta
    l'accordo, ed e' questa la chiave che il primo giro di fix non aveva."""
    key = provenance.topic_key(assertion)
    return [claim for claim in claims if claim["assertion"] == key]


def _voices(claims: list[dict]) -> set[str]:
    return {claim["attributed_to"] for claim in claims if claim["attributed_to"]}


# --- 1. ogni affermazione resta della voce che l'ha pronunciata ------------


def test_every_claim_keeps_the_voice_that_stated_it(three_interviews):
    """L'attribuzione incrociata del V3: nessun claim cambia bocca.

    Il controllo non e' "Paolo ha detto le cose di Paolo": e' che la voce di
    ogni claim sia fra i partecipanti della fonte da cui quel claim proviene.
    Vale per qualunque dataset.
    """
    participants_by_source = {
        interview["title"]: set(interview["participants"]) for interview in INTERVIEWS
    }

    claims = _ledger(three_interviews)
    assert claims

    for claim in claims:
        assert claim["attributed_to"], f"claim senza voce: {claim['statement']}"
        assert claim["attributed_to"] in participants_by_source[claim["source_name"]], (
            f"{claim['statement']!r} attribuito a {claim['attributed_to']} "
            f"ma proviene da {claim['source_name']}"
        )


def test_no_claim_of_one_source_carries_the_words_of_another(three_interviews):
    """Le parole originali di un claim devono stare nel testo della sua fonte."""
    from backend.toolsets.process_memory import manage_process_evidence

    texts = {}
    with _bind_process_chat(three_interviews["project"], three_interviews["process"]):
        listing = _tool_payload(
            manage_process_evidence.invoke(
                {
                    "operation": "list",
                    "project_id": three_interviews["project"],
                    "process_id": three_interviews["process"],
                    "limit": 50,
                }
            )
        )["evidence"]
        for item in listing:
            detail = _tool_payload(
                manage_process_evidence.invoke(
                    {
                        "operation": "inspect",
                        "project_id": three_interviews["project"],
                        "process_id": three_interviews["process"],
                        "episode_id": item["episode_id"],
                        "include_source_text": True,
                    }
                )
            )["evidence"]
            texts[item["title"]] = detail.get("source_text") or ""

    for claim in _ledger(three_interviews):
        if not claim["quote_verified"]:
            continue
        assert provenance.quote_is_grounded(claim["quote"], texts[claim["source_name"]])


# --- 2/3. corroborazione reale vs sovrapposizione inventata ----------------


def test_a_topic_two_sources_really_share_comes_back_corroborated(three_interviews):
    claims = _by_topic(_ledger(three_interviews), TOPIC_HANDOVER)

    assert len(_voices(claims)) >= 2
    assert {claim["support"] for claim in claims} == {"corroborated"}
    assert all(claim["corroborating_sources"] for claim in claims)


def test_two_complementary_sources_are_corroborated_without_being_merged(three_interviews):
    """Due fonti concordano sul tema, ciascuna con le proprie parole.

    Corroborare non vuol dire fondere: ogni riga resta la propria, con la
    propria voce e la propria citazione.
    """
    claims = _by_topic(_ledger(three_interviews), TOPIC_VISIBILITY)

    assert len(_voices(claims)) >= 2
    assert {claim["support"] for claim in claims} == {"corroborated"}
    assert len({claim["quote"] for claim in claims}) == len(claims)
    assert len({claim["scope_label"] for claim in claims}) >= 2


def test_a_topic_only_one_source_speaks_to_stays_single_source(three_interviews):
    """L'informazione presente in una fonte sola non diventa un accordo."""
    claims = _by_topic(_ledger(three_interviews), TOPIC_ARRIVAL)

    assert len(_voices(claims)) == 1
    assert {claim["support"] for claim in claims} == {"single_source"}
    assert all(not claim["corroborating_sources"] for claim in claims)


def test_a_source_that_declares_it_does_not_know_does_not_create_agreement(three_interviews):
    """Sul tema dell'autorizzazione una fonte descrive, l'altra dichiara di non
    sapere. Non fa due voci concordi: resta una sola fonte."""
    claims = _by_topic(_ledger(three_interviews), TOPIC_AUTHORISATION)
    stated = [claim for claim in claims if claim["epistemic_status"] != "declared_unknown"]
    unknown = [claim for claim in claims if claim["epistemic_status"] == "declared_unknown"]

    assert stated and unknown
    assert {claim["support"] for claim in stated} == {"single_source"}
    assert {claim["support"] for claim in unknown} == {"declared_unknown"}


# --- 4. cio' che dice una fonte sola si presenta per quello che e' ---------


def test_the_support_level_is_computed_not_declared(three_interviews):
    """Ogni riga porta un'etichetta di sostegno leggibile, calcolata dal
    runtime: e' quella che la risposta deve usare."""
    claims = _ledger(three_interviews)

    assert claims
    for claim in claims:
        assert claim["support"] in provenance.SUPPORT_LABEL_IT
        assert claim["support_label"] == provenance.SUPPORT_LABEL_IT[claim["support"]]


def test_nothing_reaches_the_ledger_as_confirmed_just_because_it_was_saved_so(
    three_interviews,
):
    """Le interviste dichiarano `status` sui claim; il registro non lo usa come
    grado di sostegno. Un claim di una sola voce e' `single_source` comunque."""
    claims = _by_topic(_ledger(three_interviews), TOPIC_ARRIVAL)

    assert claims
    assert all(claim["support"] != "corroborated" for claim in claims)


# --- 5. una differenza non e' automaticamente una contraddizione -----------


def test_a_knowledge_gap_declared_as_a_contradiction_is_reclassified(three_interviews):
    """Il caso V3: una parte non conosce la prassi, l'altra la descrive.

    Passa dal tool vero dell'agente, che chiede il tipo di divergenza e poi lo
    riverifica contro le posizioni in campo.
    """
    from backend.graphs.process.subgraphs.evidence.tools import manage_process_contradiction

    with _bind_process_chat(three_interviews["project"], three_interviews["process"]):
        command = manage_process_contradiction.invoke(
            {
                "process_id": three_interviews["process"],
                "operation": "identify",
                "title": "Chi regolarizza l'acquisto in urgenza",
                "divergence_type": "incompatible",
                "severity": "blocking",
                "conflicting_claims": [
                    "La Manutenzione non sa chi apra l'ordine.",
                    "L'Ufficio Acquisti apre l'ordine a posteriori.",
                ],
                "stances": [
                    {
                        "attributed_to": MAINTENANCE_LEAD,
                        "statement": "Non so chi materialmente lo faccia.",
                        "epistemic_status": "declared_unknown",
                        "scope_label": "Manutenzione",
                    },
                    {
                        "attributed_to": PURCHASING,
                        "statement": "La parte di ordine la faccio io.",
                        "epistemic_status": "reported",
                        "scope_label": "Ufficio Acquisti",
                    },
                ],
                "tool_call_id": "call-divergence",
            }
        )

    recorded = command.update["contradictions"][0]
    assert recorded["divergence_type"] == "knowledge_gap"
    assert recorded["declared_divergence_type"] == "incompatible"
    assert recorded["downgraded"]
    assert not recorded["blocks_modeling"]
    assert recorded["severity"] != "blocking"


def test_a_genuine_incompatibility_is_not_softened_away(three_interviews):
    """Il declassamento non deve svuotare la funzione."""
    from backend.graphs.process.subgraphs.evidence.tools import manage_process_contradiction

    with _bind_process_chat(three_interviews["project"], three_interviews["process"]):
        command = manage_process_contradiction.invoke(
            {
                "process_id": three_interviews["process"],
                "operation": "identify",
                "title": "Esiste o no un passaggio autorizzativo",
                "divergence_type": "incompatible",
                "severity": "blocking",
                "stances": [
                    {
                        "attributed_to": PURCHASING,
                        "statement": "Sopra una certa cifra serve una autorizzazione.",
                        "epistemic_status": "reported",
                        "scope_label": "Ufficio Acquisti",
                    },
                    {
                        "attributed_to": "Direzione",
                        "statement": "Nessun acquisto indiretto richiede autorizzazione.",
                        "epistemic_status": "reported",
                        "scope_label": "Ufficio Acquisti",
                    },
                ],
                "tool_call_id": "call-real-conflict",
            }
        )

    recorded = command.update["contradictions"][0]
    assert recorded["divergence_type"] == "incompatible"
    assert recorded["blocks_modeling"]
    assert not recorded["downgraded"]


def test_a_reclassified_divergence_persists_as_what_it_is(three_interviews):
    """La classificazione non resta nello stato del turno: arriva al canonical.

    Un turno successivo che rilegge il grafo deve trovare una lacuna di
    conoscenza, non una contraddizione.
    """
    from backend.memory import scope as canonical_scope
    from backend.toolsets.process_memory import manage_process_evidence

    with _bind_process_chat(three_interviews["project"], three_interviews["process"]):
        manage_process_evidence.invoke(
            {
                "operation": "save_episode",
                "project_id": three_interviews["project"],
                "process_id": three_interviews["process"],
                "episode_type": "note",
                "title": "Nota su chi regolarizza le urgenze",
                "raw_content": "Verifica incrociata fra Manutenzione e Acquisti.",
                "contradictions": [
                    {
                        "title": "Chi regolarizza l'acquisto in urgenza",
                        "conflicting_claims": [TOPIC_WHO_REGULARISES],
                        "divergence_type": "incompatible",
                        "resolution_question": "Chi apre l'ordine a posteriori?",
                        "severity": "high",
                        "stances": [
                            {
                                "attributed_to": MAINTENANCE_LEAD,
                                "epistemic_status": "declared_unknown",
                            },
                            {"attributed_to": PURCHASING, "epistemic_status": "reported"},
                        ],
                    }
                ],
            }
        )

    s = canonical_scope.resolve(three_interviews["project"], three_interviews["process"])
    from backend.db import canonical_session

    def _divergence_types() -> list[str]:
        with canonical_session(s.consultant_id, s.client_id) as session:
            return [
                row.divergence_type
                for row in session.execute(
                    text(
                        "SELECT divergence_type FROM kg_contradiction "
                        "WHERE client_id = :c AND process_id = :p"
                    ),
                    {"c": s.client_id, "p": s.process_id},
                ).all()
            ]

    _drain_until(lambda: len(_divergence_types()), expected=1)
    rows = _divergence_types()

    assert rows
    assert set(rows) == {"knowledge_gap"}


def test_a_weak_divergence_does_not_contest_the_claims_it_touches(three_interviews):
    """Una divergenza declassata non toglie sostegno a nessuno.

    Chi ha parlato ha parlato: il suo claim resta cio' che e', riferito da una
    fonte, non "conteso".
    """
    claims = _by_topic(_ledger(three_interviews), TOPIC_WHO_REGULARISES)
    stated = [claim for claim in claims if claim["epistemic_status"] != "declared_unknown"]

    assert stated
    assert all(claim["support"] != "contradicted" for claim in stated)


# --- composizione multi-fonte: A / B / C del follow-up --------------------


def test_a_shared_subject_does_not_make_two_sources_agree(three_interviews):
    """A. Due fonti parlano di autorizzazione, ma non dicono la stessa cosa.

    Il registro le tiene sullo stesso soggetto e su proposizioni distinte, e
    nessuna delle due risulta corroborata dall'altra.
    """
    claims = _by_topic(_ledger(three_interviews), TOPIC_AUTHORISATION)
    stated = [c for c in claims if c["epistemic_status"] != "declared_unknown"]

    assert len(claims) >= 2
    assert stated
    assert all(c["support"] != "corroborated" for c in stated)
    assert all(not c["corroborating_sources"] for c in stated)


def test_a_rule_only_one_source_states_is_never_marked_as_shared(three_interviews):
    """A. La verifica formale prima dell'ordine la dice una fonte sola.

    Nel registro resta un attributo esclusivo di quella voce: non compare fra
    gli attributi condivisi di nessuno, quindi non c'e' nulla da cui una frase
    multi-fonte possa ereditarla.
    """
    claims = _by_assertion(_ledger(three_interviews), SAYS_AUTHORISATION_EXISTS)
    owners = {
        c["attributed_to"] for c in claims if ONLY_PURCHASING_SAYS in c["exclusive_qualifiers"]
    }

    assert len(owners) == 1
    assert all(ONLY_PURCHASING_SAYS not in c["shared_qualifiers"] for c in claims)


def test_a_multi_source_sentence_carrying_a_single_source_rule_is_refused(
    three_interviews,
):
    """A. Il controllo passa dal tool vero della sintesi.

    Una frase che attribuisce a entrambe le fonti la regola che ne dice una
    sola viene rifiutata, e il tool dice di chi e' quella regola.
    """
    from backend.graphs.process.subgraphs.evidence.tools import synthesize_process_evidence

    with _bind_process_chat(three_interviews["project"], three_interviews["process"]):
        envelope = _tool_envelope(
            synthesize_process_evidence.invoke(
                {
                    "process_id": three_interviews["process"],
                    "source_list": [TITLE_PURCHASING, TITLE_MAINTENANCE],
                    "findings": [
                        {
                            "topic": TOPIC_AUTHORISATION,
                            "statement": (
                                "Prima dell'ordine Acquisti verifica formalmente "
                                "che la spesa sia autorizzata."
                            ),
                            "asserted_support": "corroborated",
                            "stances": [
                                {
                                    "attributed_to": PURCHASING,
                                    "scope_label": "Ufficio Acquisti",
                                    "qualifiers": [ONLY_PURCHASING_SAYS],
                                },
                                {
                                    "attributed_to": MAINTENANCE_LEAD,
                                    "scope_label": "Manutenzione",
                                },
                            ],
                        }
                    ],
                }
            )
        )

    finding = envelope["payload"]["findings"][0]
    assert envelope["status"] == "review_required"
    assert finding["downgraded"]
    assert finding["composition"]["source_specific_in_shared_statement"][PURCHASING]
    assert envelope["warnings"]


def test_the_shared_core_of_two_sources_is_corroborated(three_interviews):
    """B. Il contatto diretto col fornitore lo dicono entrambe: e' corroborato."""
    claims = _by_assertion(_ledger(three_interviews), SAYS_DIRECT_SUPPLIER)

    assert len(_voices(claims)) >= 2
    assert {c["support"] for c in claims} == {"corroborated"}


def test_an_attribute_of_one_source_stays_with_that_source(three_interviews):
    """B. "gia' conosciuto" lo dice una sola voce.

    Il nucleo e' condiviso, l'attributo no: resta attaccato a chi lo ha detto e
    non entra fra gli attributi condivisi del gruppo.
    """
    claims = _by_assertion(_ledger(three_interviews), SAYS_DIRECT_SUPPLIER)
    owners = {
        c["attributed_to"]
        for c in claims
        if ONLY_MAINTENANCE_SAYS in c["exclusive_qualifiers"]
    }

    assert len(owners) == 1
    assert all(not c["shared_qualifiers"] for c in claims)
    assert any(not c["exclusive_qualifiers"] for c in claims)


def test_a_multi_source_sentence_carrying_a_single_source_attribute_is_refused(
    three_interviews,
):
    """B. Il nucleo condiviso passa, la frase che si porta dietro l'attributo no."""
    from backend.graphs.process.subgraphs.evidence.tools import synthesize_process_evidence

    stances = [
        {"attributed_to": MAINTENANCE_LEAD, "qualifiers": [ONLY_MAINTENANCE_SAYS]},
        {"attributed_to": PURCHASING},
    ]

    def _synthesize(statement: str) -> dict:
        with _bind_process_chat(three_interviews["project"], three_interviews["process"]):
            return _tool_envelope(
                synthesize_process_evidence.invoke(
                    {
                        "process_id": three_interviews["process"],
                        "source_list": [TITLE_MAINTENANCE, TITLE_PURCHASING],
                        "findings": [
                            {
                                "topic": TOPIC_URGENCY,
                                "statement": statement,
                                "asserted_support": "corroborated",
                                "stances": stances,
                            }
                        ],
                    }
                )
            )

    core = _synthesize("Il reparto puo' contattare direttamente il fornitore.")
    leaked = _synthesize(
        "Il reparto puo' contattare direttamente un fornitore gia' conosciuto."
    )

    assert core["payload"]["findings"][0]["support"] == "corroborated"
    assert not core["payload"]["findings"][0]["downgraded"]
    assert leaked["payload"]["findings"][0]["downgraded"]
    assert leaked["payload"]["findings"][0]["composition"][
        "source_specific_in_shared_statement"
    ][MAINTENANCE_LEAD]


def test_two_local_absences_are_not_generalized_to_the_process(three_interviews):
    """C. Ognuno non ha un dato per il proprio pezzo.

    Non e' un'assenza di dati del processo, e il tool lo dice invece di
    lasciarla passare.
    """
    from backend.graphs.process.subgraphs.evidence.tools import synthesize_process_evidence

    with _bind_process_chat(three_interviews["project"], three_interviews["process"]):
        envelope = _tool_envelope(
            synthesize_process_evidence.invoke(
                {
                    "process_id": three_interviews["process"],
                    "source_list": [TITLE_TECH, TITLE_MAINTENANCE],
                    "findings": [
                        {
                            "topic": "tempi e volumi",
                            "statement": "Non esistono tempi medi del processo.",
                            "asserted_support": "declared_unknown",
                            "asserted_scope_level": "whole_process",
                            "stances": [
                                {
                                    "attributed_to": TECH_LEAD,
                                    "statement": "Non ho i tempi di verifica delle fatture.",
                                    "scope_label": "Ufficio Tecnico",
                                },
                                {
                                    "attributed_to": MAINTENANCE_LEAD,
                                    "statement": "Non so quante urgenze facciamo in un mese.",
                                    "scope_label": "Manutenzione",
                                },
                            ],
                        }
                    ],
                }
            )
        )

    finding = envelope["payload"]["findings"][0]
    assert finding["downgraded"]
    assert any("intero processo" in reason for reason in finding["downgrade_reasons"])


def test_two_declared_unknowns_about_different_things_do_not_merge(three_interviews):
    """C, lato registro: due lacune diverse restano due righe distinte.

    Ognuna con la sua voce e il suo perimetro: e' cio' che impedisce di
    sommarle in un'unica assenza di processo.
    """
    unknowns = [
        c for c in _ledger(three_interviews) if c["epistemic_status"] == "declared_unknown"
    ]
    by_assertion: dict[str, set[str]] = {}
    for claim in unknowns:
        by_assertion.setdefault(claim["assertion"], set()).add(claim["scope_label"])

    assert len(unknowns) >= 2
    assert all(claim["support"] == "declared_unknown" for claim in unknowns)
    assert all(claim["scope_level"] == "stated_scope" for claim in unknowns)
    assert len(by_assertion) >= 2


# --- 6. cio' che e' registrato non puo' diventare "mancante" ---------------


def test_information_backed_by_one_source_is_evidence_not_a_gap(three_interviews):
    """Il difetto V3 sulla perdita di informazione.

    Il tema di chi regolarizza le urgenze e' documentato da una fonte. Nel
    registro deve esistere, con la sua voce, e non come informazione assente.
    """
    claims = _by_topic(_ledger(three_interviews), TOPIC_WHO_REGULARISES)
    stated = [claim for claim in claims if claim["epistemic_status"] != "declared_unknown"]

    assert stated, "l'informazione e' sparita dal registro"
    assert {claim["support"] for claim in stated} == {"single_source"}
    assert all(claim["quote"] for claim in stated)


def test_a_declared_unknown_is_information_about_the_source(three_interviews):
    """Chi dichiara di non sapere non e' un buco del processo: e' un dato."""
    claims = [
        claim
        for claim in _ledger(three_interviews)
        if claim["epistemic_status"] == "declared_unknown"
    ]

    assert claims
    assert {claim["support"] for claim in claims} == {"declared_unknown"}
    assert all(claim["attributed_to"] for claim in claims)


# --- 7. lo scope di una testimonianza non si allarga -----------------------


def test_a_department_testimony_keeps_its_department(three_interviews):
    claims = _by_topic(_ledger(three_interviews), TOPIC_ARRIVAL)

    assert claims
    for claim in claims:
        assert claim["scope_label"] == "Manutenzione"
        assert claim["scope_level"] == "stated_scope"


def test_no_claim_is_silently_promoted_to_the_whole_process(three_interviews):
    """Nessuna riga guadagna un perimetro che chi l'ha detta non ha dichiarato."""
    declared = {
        claim["claim"]: claim.get("scope_level", "stated_scope")
        for interview in INTERVIEWS
        for claim in interview["claims"]
    }

    for claim in _ledger(three_interviews):
        assert claim["scope_level"] == declared[claim["statement"]]


# --- 8. la sintesi non puo' essere piu' forte del testo --------------------


def test_a_faithful_quote_comes_back_verified(three_interviews):
    claims = _by_topic(_ledger(three_interviews), TOPIC_URGENCY)
    assert len(claims) >= 2

    assert claims
    assert all(claim["quote_verified"] for claim in claims)


def test_a_quote_stronger_than_the_source_is_marked_unverified(three_interviews):
    """La citazione che trasforma una possibilita' in un obbligo non regge."""
    claims = _by_topic(_ledger(three_interviews), "obbligo di conferma del responsabile")

    assert claims
    assert all(not claim["quote_verified"] for claim in claims)


def test_the_write_path_reports_how_many_quotes_it_could_not_ground(three_interviews):
    """Il conto non resta muto: chi scrive l'evidenza lo vede."""
    from backend.memory.knowledge_graph import canonical
    from backend.memory import scope as canonical_scope

    s = canonical_scope.resolve(three_interviews["project"], three_interviews["process"])
    counts = canonical.write_evidence(
        consultant_id=s.consultant_id,
        client_id=s.client_id,
        project_id=s.project_id,
        process_id=s.process_id,
        process_name=s.process_name,
        claims=[
            {
                "statement": "Il responsabile deve confermare ogni spesa.",
                "process_area": "control",
                "quote": "il responsabile deve confermare ogni spesa",
                "attributed_to": PURCHASING,
                "topic": "conferma obbligatoria",
            },
            {
                "statement": "Le richieste arrivano via mail.",
                "process_area": "handoff",
                "quote": "le richieste arrivano via mail",
                "attributed_to": PURCHASING,
                "topic": "canale",
            },
        ],
        source_title="Nota di verifica",
        source_text="Le richieste arrivano via mail e vengono lavorate da Acquisti.",
    )

    assert counts["claims"] == 2
    assert counts["unverified_quotes"] == 1


# --- 9. l'audit di provenance arriva all'estratto originale ----------------


def test_provenance_returns_claim_source_and_the_original_excerpt(three_interviews):
    """La richiesta "mostrami claim -> fonte -> estratto" non si risponde con
    una sintesi: si risponde con il testo che c'e' nella fonte."""
    envelope = _provenance(three_interviews)
    trail = envelope["payload"]["trail"]

    assert trail
    proven = [row for row in trail if row["quote_verified"]]
    assert proven
    for row in proven:
        assert row["attributed_to"]
        assert row["source_name"]
        assert row["excerpt_found"], f"nessun estratto per {row['statement']!r}"
        assert provenance.normalize(row["quote"]) in provenance.normalize(
            row["original_excerpt"]
        )


def test_the_excerpt_is_the_interview_own_text_not_a_normalized_copy(three_interviews):
    """Il lineage deve arrivare al testo grezzo, non fermarsi al claim.

    L'audit ritagliava sul testo normalizzato: mostrava fra virgolette una
    versione minuscola e ripulita di cio' che la persona aveva detto. Sembrava
    un verbatim e non lo era.
    """
    sources = {interview["title"]: _read(interview["file"]) for interview in INTERVIEWS}
    trail = [
        row for row in _provenance(three_interviews)["payload"]["trail"] if row["excerpt_found"]
    ]

    assert trail
    for row in trail:
        # Il taglio esiste, carattere per carattere, dentro l'intervista.
        assert row["original_excerpt"].strip("…").strip() in sources[row["source_name"]]


def test_the_stored_quote_is_the_span_of_the_interview(three_interviews):
    """Quello che il registro riporta come citazione e' il testo della fonte,
    non la copia che chi ha estratto ha ricopiato a memoria."""
    sources = {interview["title"]: _read(interview["file"]) for interview in INTERVIEWS}

    verified = [claim for claim in _ledger(three_interviews) if claim["quote_verified"]]
    assert verified
    for claim in verified:
        assert claim["quote"] in sources[claim["source_name"]]


def test_provenance_says_when_it_cannot_prove_a_claim(three_interviews):
    """Un audit che non trova l'estratto lo dichiara, non lo riscrive."""
    envelope = _provenance(three_interviews, query="obbligo di conferma del responsabile")
    trail = envelope["payload"]["trail"]

    assert trail
    assert all(not row["excerpt_found"] for row in trail)
    assert envelope["warnings"]


def test_provenance_can_be_narrowed_to_one_voice(three_interviews):
    envelope = _provenance(three_interviews, query=MAINTENANCE_LEAD)
    trail = envelope["payload"]["trail"]

    assert trail
    assert {row["attributed_to"] for row in trail} == {MAINTENANCE_LEAD}


def test_the_provenance_section_is_rendered_not_narrated(three_interviews):
    section = _provenance(three_interviews)["payload"]["provenance_section"]

    assert section
    assert "Da dove viene" in section
    for voice in (TECH_LEAD, MAINTENANCE_LEAD, PURCHASING):
        assert voice in section


# --- 11. nessuna contaminazione fra processi -------------------------------


def test_the_ledger_of_a_process_holds_only_its_own_evidence(three_interviews):
    """Stesso cliente, altro incarico, stessa persona con un altro ruolo."""
    claims = _ledger(three_interviews)
    sources = {claim["source_name"] for claim in claims}

    assert sources == {interview["title"] for interview in INTERVIEWS}
    assert OTHER_PROCESS_INTERVIEW["title"] not in sources
    assert all("5.000" not in claim["statement"] for claim in claims)
    assert all("Facility" not in (claim["scope_label"] or "") for claim in claims)


def test_the_other_process_still_reads_its_own_ledger(three_interviews):
    """Isolare non deve svuotare: il confine e' bidirezionale."""
    claims = _ledger(three_interviews, project_key="other_project", process_key="other_process")

    assert {claim["source_name"] for claim in claims} == {OTHER_PROCESS_INTERVIEW["title"]}


# --- 12. una chat nuova riparte dall'evidenza gia' raccolta ----------------


def test_a_new_process_chat_opens_with_the_evidence_already_collected(three_interviews):
    """Il registro e' persistito, quindi un turno successivo non riparte da zero.

    Senza questo, cio' che una fonte aveva gia' detto tornava a essere
    "informazione mancante" alla chat dopo.
    """
    from backend.graphs.process.nodes import load_process_context

    with _bind_process_chat(three_interviews["project"], three_interviews["process"]):
        context = load_process_context({"process_id": three_interviews["process"]})

    ledger = context["evidence_ledger"]
    assert ledger["status"] == "ok"
    assert ledger["count"] >= sum(len(i["claims"]) for i in INTERVIEWS)
    assert len(ledger["summary"]["voices"]) == 3


def test_the_answer_the_consultant_reads_carries_the_provenance(three_interviews):
    """L'ultimo miglio: la risposta porta il registro stampato dal runtime.

    La prosa la scrive il modello; la sezione "Da dove viene" no - e' l'unica
    parte che non puo' diventare piu' forte di quanto la fonte dica.
    """
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage, HumanMessage

    from backend.graphs.process.graph import build_process_report
    from backend.graphs.process.nodes import load_process_context

    with _bind_process_chat(three_interviews["project"], three_interviews["process"]):
        context = load_process_context({"process_id": three_interviews["process"]})

    report = build_process_report(
        GenericFakeChatModel(messages=iter([AIMessage(content="Ecco cosa e' emerso.")]))
    )
    result = report(
        {
            "messages": [HumanMessage(content="Riassumi cosa e' emerso dalle interviste.")],
            "process_name": "Gestione acquisto materiali indiretti e servizi",
            "specialist_findings": [{"owner": "evidence", "finding": "Tre interviste lette."}],
            "evidence_ledger": context["evidence_ledger"],
            "process_claims": [],
            "contradictions": [],
            "missing_information": [],
        },
        None,
    )
    answer = result["messages"][0].content

    assert "Da dove viene" in answer
    for voice in (TECH_LEAD, MAINTENANCE_LEAD, PURCHASING):
        assert voice in answer
    assert provenance.SUPPORT_LABEL_IT["corroborated"] in answer
    assert provenance.SUPPORT_LABEL_IT["single_source"] in answer


# --- 9. V3 residuo: fondere due voci non le mette d'accordo ----------------
#
# Le fonti venivano recuperate, distinte e citate correttamente, ma la sintesi
# multi-fonte raggruppava per argomento: "Paolo + Francesca | Corroborato" su
# una regola che dice Acquisti, su un trigger che le due descrivono da due
# punti di ingresso diversi, e su una soglia che una delle due dichiara di non
# conoscere. Qui si verifica sul registro davvero ingerito.


def _entries(ws: dict) -> list:
    """Il registro persistito, ricostruito come lo legge chi risponde."""
    return provenance.build_ledger(_ledger(ws))


def test_no_voice_corroborates_an_assertion_its_own_words_do_not_carry(three_interviews):
    """L'invariante, su tutto il registro: chi conferma lo dice con parole sue."""
    claims = _ledger(three_interviews)
    by_assertion: dict[str, list[dict]] = {}
    for claim in claims:
        by_assertion.setdefault(claim["assertion"], []).append(claim)

    for claim in claims:
        if claim["support"] != "corroborated":
            continue
        group = by_assertion[claim["assertion"]]
        carrying = [
            item
            for item in group
            if provenance.statement_carries_assertion(item["assertion"], item["statement"])
        ]
        # O nessuno regge l'enunciato dichiarato - e allora il raggruppamento
        # dell'estrattore e' tutto cio' che c'e' - oppure chi corrobora e' fra
        # quelli che lo reggono.
        assert not carrying or claim in carrying, claim["statement"]


def test_no_source_that_declares_it_does_not_know_ends_up_corroborating(three_interviews):
    """Un "non lo so" non entra fra le fonti che sostengono quella proposizione.

    Il vincolo e' per proposizione, non per persona: chi dichiara di non sapere
    una cosa continua a sostenere tutto il resto che ha detto.
    """
    claims = _ledger(three_interviews)
    unknown_by_assertion: dict[str, set[str]] = {}
    for claim in claims:
        if claim["epistemic_status"] == "declared_unknown" and claim["attributed_to"]:
            unknown_by_assertion.setdefault(claim["assertion"], set()).add(
                claim["attributed_to"]
            )

    assert unknown_by_assertion, "il dataset deve contenere almeno una non-conoscenza"
    for claim in claims:
        ignorant = unknown_by_assertion.get(claim["assertion"], set())
        assert not (ignorant & set(claim["corroborating_sources"])), claim["statement"]


def test_a_rule_of_one_department_is_not_corroborated_by_the_other(three_interviews):
    """La responsabilita' autorizzativa la dichiara Acquisti, non entrambe."""
    claims = _by_assertion(_ledger(three_interviews), SAYS_AUTHORISATION_EXISTS)
    corroborated = [claim for claim in claims if claim["support"] == "corroborated"]

    assert claims, "il tema deve essere nel registro"
    assert not corroborated
    assert all(MAINTENANCE_LEAD not in claim["corroborating_sources"] for claim in claims)


def test_the_urgency_core_stays_corroborated_while_its_details_do_not(three_interviews):
    """Il nucleo condiviso regge; l'attributo di una voce resta suo."""
    claims = _by_assertion(_ledger(three_interviews), SAYS_DIRECT_SUPPLIER)
    owners = {
        claim["attributed_to"]
        for claim in claims
        if ONLY_MAINTENANCE_SAYS in claim["exclusive_qualifiers"]
    }

    assert {claim["support"] for claim in claims} == {"corroborated"}
    assert owners == {MAINTENANCE_LEAD}


def test_a_matrix_that_declares_an_agreement_the_ledger_does_not_have_is_refused(
    three_interviews,
):
    """La matrice "Area | Sintesi | Fonte/i | Valutazione" e' verificabile."""
    violations = provenance.audit_answer(
        f"| Autorizzazione | Deve esistere una responsabilita' autorizzativa "
        f"anche per importi piccoli | {MAINTENANCE_LEAD}, {PURCHASING} | Corroborato |",
        _entries(three_interviews),
    )

    assert [item.kind for item in violations] == ["unsupported_agreement"]


def test_a_matrix_row_that_carries_a_single_source_detail_is_refused(three_interviews):
    """Il nucleo urgenza si puo' corroborare; "gia' conosciuto" no."""
    violations = provenance.audit_answer(
        f"| Urgenze | In urgenza il reparto ordina direttamente da un "
        f"{ONLY_MAINTENANCE_SAYS} | {MAINTENANCE_LEAD}, {PURCHASING} | Corroborato |",
        _entries(three_interviews),
    )

    assert "attribute_leak" in {item.kind for item in violations}
    assert all(item.owner in {"", MAINTENANCE_LEAD} for item in violations)


def test_a_matrix_that_keeps_every_voice_where_it_belongs_passes(three_interviews):
    """Il controllo non impedisce di dire cio' che le fonti reggono davvero."""
    entries = _entries(three_interviews)

    assert (
        provenance.audit_answer(
            f"| Urgenze | In urgenza il reparto ordina direttamente dal fornitore "
            f"| {MAINTENANCE_LEAD}, {PURCHASING} | Corroborato |\n"
            f"| Autorizzazione | Sopra soglia serve l'autorizzazione del responsabile "
            f"| {PURCHASING} | Riferito da una sola fonte |",
            entries,
        )
        == []
    )


def test_the_answer_node_annotates_the_merge_it_could_not_correct(three_interviews):
    """Percorso vero: se la prosa insiste, il consulente legge di chi e' cosa."""
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage, HumanMessage

    from backend.graphs.process.graph import build_process_report
    from backend.graphs.process.nodes import load_process_context

    merged = (
        f"{MAINTENANCE_LEAD} e {PURCHASING} concordano: deve esistere una "
        "responsabilita' autorizzativa anche per importi piccoli."
    )
    with _bind_process_chat(three_interviews["project"], three_interviews["process"]):
        context = load_process_context({"process_id": three_interviews["process"]})

    report = build_process_report(
        GenericFakeChatModel(
            messages=iter([AIMessage(content=merged), AIMessage(content=merged)])
        )
    )
    answer = report(
        {
            "messages": [HumanMessage(content="Dammi la matrice delle evidenze.")],
            "process_name": "Gestione acquisto materiali indiretti e servizi",
            "specialist_findings": [{"owner": "evidence", "finding": "Tre interviste lette."}],
            "evidence_ledger": context["evidence_ledger"],
            "process_claims": [],
            "contradictions": [],
            "missing_information": [],
        },
        None,
    )["messages"][0].content

    assert "Precisazione sull'attribuzione" in answer
    assert "non le riporta d'accordo" in answer
