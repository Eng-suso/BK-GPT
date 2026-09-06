"""Cosa vale un campo di workspace quando non lo sappiamo, e chi decide che lo sappiamo.

`status="Prospect"` era il default hard-coded di ogni punto di ingresso: input
schema dei tool, schema HTTP, firma di `create_client`. Ma un default e' una
risposta, e quella risposta e' sbagliata quando l'utente ha appena detto "ho
acquisito un nuovo cliente": un prospect e' qualcuno che stai *ancora* cercando
di acquisire, quindi il record nasceva in contraddizione con la frase che lo ha
creato (bug CLIENT-01).

Qui "non lo so" e' esplicito - `None` - e il placeholder si applica una volta
sola, al confine col database. Al modello resta una scelta vera da fare: se il
linguaggio dell'utente rende evidente lo stato, lo valorizza; altrimenti lascia
il campo vuoto e il placeholder dice, onestamente, che nessuno lo ha deciso.
"""

from typing import Literal

UNKNOWN_SECTOR = "Non specificato"
UNKNOWN_OWNER = "Da assegnare"
UNKNOWN_CLIENT_STATUS = "Prospect"

ClientStatus = Literal["Attivo", "Da seguire", "Prospect"]

CLIENT_STATUSES: tuple[str, ...] = ("Attivo", "Da seguire", "Prospect")

CLIENT_STATUS_DESCRIPTION = (
    "Client status, set it whenever the user's own words make it evident. "
    '"Attivo" for a client already acquired or actively worked with ("ho acquisito", '
    '"e\' nostro cliente", "lavoro per", "seguo"). '
    '"Da seguire" for an existing relationship waiting on a follow-up. '
    '"Prospect" only for someone still being pursued ("lead", "potenziale", '
    '"sto cercando di acquisire", "abbiamo mandato un\'offerta"). '
    "Leave unset only when the status is genuinely unknown: unset is recorded as "
    '"Prospect", so never leave it unset for a client the user says they already have.'
)

# Forme libere che l'utente (o il modello) usa per gli stessi tre stati. Non e'
# inferenza dal linguaggio naturale - quella la fa il modello, che ha il contesto
# della frase - ma canonicalizzazione di valori gia' scelti, cosi' "attivo",
# "Cliente" e "ACTIVE" non diventano tre stati diversi nel database.
_CLIENT_STATUS_ALIASES: dict[str, str] = {
    "attivo": "Attivo",
    "attiva": "Attivo",
    "active": "Attivo",
    "cliente": "Attivo",
    "cliente attivo": "Attivo",
    "acquisito": "Attivo",
    "da seguire": "Da seguire",
    "follow up": "Da seguire",
    "follow-up": "Da seguire",
    "prospect": "Prospect",
    "lead": "Prospect",
    "potenziale": "Prospect",
}


def normalize_client_status(raw: str | None) -> str | None:
    """Lo stato in forma canonica, o `None` se non e' stato dichiarato.

    Un valore fuori vocabolario viene restituito ripulito, non scartato: il
    backend tiene lo stato free-form e il frontend lo normalizza comunque.
    """
    if raw is None:
        return None

    cleaned = " ".join(raw.split())
    if not cleaned:
        return None

    return _CLIENT_STATUS_ALIASES.get(cleaned.casefold(), cleaned)


def resolve_client_status(raw: str | None) -> str:
    """Lo stato da scrivere a database: quello dichiarato, o il placeholder."""
    return normalize_client_status(raw) or UNKNOWN_CLIENT_STATUS


def is_unknown_client_status(value: str | None) -> bool:
    """Vero quando il campo porta ancora il placeholder, non una decisione."""
    return normalize_client_status(value) in (None, UNKNOWN_CLIENT_STATUS)


# --- progetto ---------------------------------------------------------------
#
# Fase e stato erano stringhe libere con un default nella firma di ogni punto di
# ingresso: "Discovery"/"Bozza" comparivano nello schema HTTP, nella firma di
# `create_project` e nell'input schema del tool. Tre copie della stessa risposta,
# e nessun posto dove leggere *cosa significhi* una fase. Qui il vocabolario e'
# uno solo, ha una definizione per ogni voce (che il modello legge nel prompt del
# tool e il consulente legge nella UI) e il placeholder si applica al confine col
# database.

DEFAULT_PROJECT_PHASE = "Discovery"
DEFAULT_PROJECT_STATUS = "Bozza"
UNKNOWN_NEXT_STEP = "Definire perimetro e fonti iniziali"

ProjectPhase = Literal["Discovery", "AS-IS", "Validazione", "TO-BE", "Simulazione", "Delivery"]
ProjectStatus = Literal["Bozza", "In corso", "A rischio", "In pausa", "Completato"]

# Le fasi sono in ordine di avanzamento: e' il ciclo di vita di un incarico di
# process consulting, dallo scoping alla consegna.
PROJECT_PHASES: tuple[str, ...] = (
    "Discovery",
    "AS-IS",
    "Validazione",
    "TO-BE",
    "Simulazione",
    "Delivery",
)

PROJECT_PHASE_MEANINGS: dict[str, str] = {
    "Discovery": "Perimetro, stakeholder e fonti: si decide cosa entra nell'incarico.",
    "AS-IS": "Ricostruzione del processo esistente dalle fonti e dalle interviste.",
    "Validazione": "L'AS-IS viene confermato dagli stakeholder che lo eseguono.",
    "TO-BE": "Progettazione del processo target e delle sue alternative.",
    "Simulazione": "Il modello gira: si misurano KPI, scenari e impatti.",
    "Delivery": "Consegna di risultati e raccomandazioni, chiusura dell'incarico.",
}

PROJECT_STATUSES: tuple[str, ...] = (
    "Bozza",
    "In corso",
    "A rischio",
    "In pausa",
    "Completato",
)

PROJECT_STATUS_MEANINGS: dict[str, str] = {
    "Bozza": "Registrato ma non ancora avviato: manca il via del cliente o lo scoping.",
    "In corso": "Lavoro attivo, che avanza secondo il piano.",
    "A rischio": "Attivo ma con un blocco su tempi, perimetro o disponibilita' del cliente.",
    "In pausa": "Sospeso per decisione del cliente o del team, non abbandonato.",
    "Completato": "Deliverable consegnati e incarico chiuso.",
}

PROJECT_OBJECTIVE_DESCRIPTION = (
    "The engagement objective in the consultant's own words: why this project "
    "exists and what outcome closes it (for example \"ricostruire l'AS-IS del "
    "ciclo ordini, validarlo con gli stakeholder, simularlo e misurare i KPI di "
    "lead time\"). Fill it whenever the user states the assignment - it is the "
    "only field that survives the conversation, and the Project Chat reads it "
    "back as its brief. Leave unset only when the user gave a name and nothing "
    "else."
)

PROJECT_PHASE_DESCRIPTION = (
    "Current phase of the engagement, one of: "
    + "; ".join(f"{phase} = {meaning}" for phase, meaning in PROJECT_PHASE_MEANINGS.items())
    + f". Leave unset when unknown: unset is recorded as \"{DEFAULT_PROJECT_PHASE}\"."
)

PROJECT_STATUS_DESCRIPTION = (
    "Delivery status of the engagement, one of: "
    + "; ".join(f"{status} = {meaning}" for status, meaning in PROJECT_STATUS_MEANINGS.items())
    + f". Leave unset when unknown: unset is recorded as \"{DEFAULT_PROJECT_STATUS}\"."
)

_PROJECT_PHASE_ALIASES: dict[str, str] = {
    "discovery": "Discovery",
    "scoping": "Discovery",
    "kickoff": "Discovery",
    "as-is": "AS-IS",
    "as is": "AS-IS",
    "asis": "AS-IS",
    "mappatura": "AS-IS",
    "validazione": "Validazione",
    "validation": "Validazione",
    "to-be": "TO-BE",
    "to be": "TO-BE",
    "tobe": "TO-BE",
    "redesign": "TO-BE",
    "simulazione": "Simulazione",
    "simulation": "Simulazione",
    "delivery": "Delivery",
    "consegna": "Delivery",
    "chiusura": "Delivery",
}

_PROJECT_STATUS_ALIASES: dict[str, str] = {
    "bozza": "Bozza",
    "draft": "Bozza",
    "in corso": "In corso",
    "attivo": "In corso",
    "in progress": "In corso",
    "active": "In corso",
    "a rischio": "A rischio",
    "at risk": "A rischio",
    "rischio": "A rischio",
    "in pausa": "In pausa",
    "sospeso": "In pausa",
    "on hold": "In pausa",
    "paused": "In pausa",
    "completato": "Completato",
    "concluso": "Completato",
    "chiuso": "Completato",
    "done": "Completato",
    "completed": "Completato",
}


def _normalize_vocabulary(raw: str | None, aliases: dict[str, str]) -> str | None:
    """La voce in forma canonica, o `None` se non e' stata dichiarata.

    Un valore fuori vocabolario viene restituito ripulito, non scartato: i campi
    restano free-form nel database e il frontend normalizza comunque.
    """
    if raw is None:
        return None

    cleaned = " ".join(raw.split())
    if not cleaned:
        return None

    return aliases.get(cleaned.casefold(), cleaned)


def normalize_project_phase(raw: str | None) -> str | None:
    return _normalize_vocabulary(raw, _PROJECT_PHASE_ALIASES)


def normalize_project_status(raw: str | None) -> str | None:
    return _normalize_vocabulary(raw, _PROJECT_STATUS_ALIASES)


def resolve_project_phase(raw: str | None) -> str:
    """La fase da scrivere a database: quella dichiarata, o il placeholder."""
    return normalize_project_phase(raw) or DEFAULT_PROJECT_PHASE


def resolve_project_status(raw: str | None) -> str:
    """Lo stato da scrivere a database: quello dichiarato, o il placeholder."""
    return normalize_project_status(raw) or DEFAULT_PROJECT_STATUS
