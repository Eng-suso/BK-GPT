"""Le invarianti di provenance dell'evidenza, calcolate e non dichiarate.

Questo modulo non parla con il database, non chiama LLM e non ha stato. Tiene
le regole epistemiche che nel test E2E V3 erano affidate al prompt e quindi
non reggevano:

- **da chi viene un'affermazione** (`attributed_to` + `source_name`) e' un dato
  del claim, non una cosa da ricostruire dal testo a valle;
- **quanto e' sostenuta** (`support`) la calcola il runtime contando le fonti
  distinte su uno stesso `topic_key`. Il modello non puo' dichiarare
  "confermato": puo' solo mettere in fila l'evidenza e lasciare che il conto
  esca da solo. Cosi' due fonti non "concordano" finche' due fonti non ci sono
  davvero;
- **fino a dove vale** (`scope_label` / `scope_level`) resta attaccato al claim,
  quindi una testimonianza della Manutenzione non diventa il processo intero;
- **la citazione** (`quote`) deve esistere nel testo sorgente. Se non c'e', il
  claim non e' rifiutato ma marcato `quote_verified=False`: una sintesi puo'
  comprimere il testo, non puo' inventarne la forza;
- **una divergenza non e' automaticamente una contraddizione**: chi dichiara di
  non sapere non contraddice chi sa, e due ambiti diversi non sono
  incompatibili. `classify_divergence` declassa, non promuove mai.

Il punto architetturale: queste funzioni sono l'unico posto dove si decide se
qualcosa e' corroborato, contraddetto o riferito da una sola voce. Prompt e
modelli le leggono, non le riscrivono.
"""

from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass, field
from typing import Any, Iterable, Literal

# --- vocabolario ----------------------------------------------------------

EpistemicStatus = Literal[
    "reported",          # la fonte lo riferisce
    "observed",          # la fonte dice di averlo visto/fatto in prima persona
    "documented",        # sta in un documento allegato alla fonte
    "inferred",          # e' una deduzione dell'analisi, non una dichiarazione
    "declared_unknown",  # la fonte dichiara esplicitamente di non saperlo
]

EPISTEMIC_STATUSES: frozenset[str] = frozenset(
    ("reported", "observed", "documented", "inferred", "declared_unknown")
)

# Le uniche dichiarazioni che contano come sostegno positivo di un topic.
# Una deduzione non corrobora, e un "non lo so" nemmeno.
SUPPORTING_STATUSES: frozenset[str] = frozenset(("reported", "observed", "documented"))

ScopeLevel = Literal["stated_scope", "whole_process"]
SCOPE_LEVELS: frozenset[str] = frozenset(("stated_scope", "whole_process"))

SupportLevel = Literal[
    "corroborated",       # >= 2 fonti distinte dicono la stessa cosa
    "single_source",      # lo dice una sola fonte
    "contradicted",       # su questo topic c'e' una divergenza incompatibile
    "inferred",           # nessuna fonte lo dice: e' una deduzione
    "declared_unknown",   # la fonte dichiara di non saperlo
]

DivergenceType = Literal[
    "incompatible",               # non possono essere vere entrambe
    "scope_difference",           # parlano di ambiti diversi
    "formalization_difference",   # stessa sostanza, grado di formalizzazione diverso
    "knowledge_gap",              # una delle due parti dichiara di non sapere
    "complementary",              # si completano, non si escludono
    "tension_to_explore",         # attrito da approfondire, non ancora un conflitto
    "single_source_uncertainty",  # una sola fonte: non e' una divergenza
]

DIVERGENCE_TYPES: frozenset[str] = frozenset(
    (
        "incompatible",
        "scope_difference",
        "formalization_difference",
        "knowledge_gap",
        "complementary",
        "tension_to_explore",
        "single_source_uncertainty",
    )
)

# Etichette che il consulente legge. Stanno qui e non nel prompt perche' sono
# la conseguenza del conto, non una scelta di stile del modello.
SUPPORT_LABEL_IT: dict[str, str] = {
    "corroborated": "corroborato da piu' fonti",
    "single_source": "riferito da una sola fonte",
    "contradicted": "conteso fra le fonti",
    "inferred": "inferenza, nessuna fonte lo dichiara",
    "declared_unknown": "la fonte dichiara di non saperlo",
}

DIVERGENCE_LABEL_IT: dict[str, str] = {
    "incompatible": "incompatibilita' vera",
    "scope_difference": "ambiti diversi",
    "formalization_difference": "grado di formalizzazione diverso",
    "knowledge_gap": "una parte dichiara di non sapere",
    "complementary": "informazioni complementari",
    "tension_to_explore": "tensione da approfondire",
    "single_source_uncertainty": "una sola fonte, non una divergenza",
}


# --- normalizzazione ------------------------------------------------------

_APOSTROPHES = str.maketrans({"’": "'", "‘": "'", "“": '"', "”": '"', "–": "-", "—": "-"})
_NON_WORD = re.compile(r"[^\w\s]+", re.UNICODE)


def normalize(value: Any) -> str:
    """Testo confrontabile: unicode NFKC, apostrofi/virgolette uniformati,
    spazi collassati, casefold. Non toglie la punteggiatura: serve a
    `quote_is_grounded`, dove la punteggiatura e' parte del testo originale."""
    text = unicodedata.normalize("NFKC", str(value or "")).translate(_APOSTROPHES)
    return " ".join(text.split()).casefold()


def _loose(value: Any) -> str:
    """Come `normalize`, ma senza punteggiatura: per il confronto di una
    citazione che l'estrattore ha ricopiato togliendo una virgola."""
    return " ".join(_NON_WORD.sub(" ", normalize(value)).split())


def topic_key(value: Any) -> str:
    """Chiave stabile di un tema di evidenza.

    E' la chiave su cui si conta la corroborazione: due claim con lo stesso
    `topic_key` parlano della stessa cosa. Chi estrae la assegna; qui la si
    normalizza soltanto, cosi' "Autorizzazione spesa" e "autorizzazione-spesa"
    non diventano due temi diversi.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", _loose(value)).strip("-")
    return slug[:80]


def statement_hash(value: Any) -> str:
    return hashlib.sha256(normalize(value).encode("utf-8")).hexdigest()[:32]


# --- ancoraggio della citazione al testo sorgente -------------------------

# Sotto questa lunghezza una "citazione" non ancora niente: e' una parola.
MIN_QUOTE_CHARS = 12


def _fold(text: str, *, drop_punctuation: bool = False) -> tuple[str, list[int]]:
    """Testo confrontabile + la mappa che riporta ogni carattere all'originale.

    Serve per ritagliare dal sorgente il passaggio VERO. Confrontare su testo
    normalizzato e poi restituire quel testo normalizzato significa mostrare fra
    virgolette una versione minuscola e ripulita di cio' che la persona ha
    detto: sembra un verbatim e non lo e'. Qui ogni carattere prodotto sa da
    quale posizione dell'originale viene, quindi la citazione si taglia sul
    testo originale.
    """
    folded: list[str] = []
    offsets: list[int] = []
    pending_space = False
    for index, char in enumerate(str(text or "")):
        piece = unicodedata.normalize("NFKC", char).translate(_APOSTROPHES).casefold()
        if drop_punctuation and piece and _NON_WORD.fullmatch(piece):
            piece = " "
        if piece.isspace() or piece == "":
            pending_space = bool(folded) or pending_space
            continue
        if pending_space and folded:
            folded.append(" ")
            offsets.append(index)
        pending_space = False
        for produced in piece:
            folded.append(produced)
            offsets.append(index)
    return "".join(folded), offsets


def locate_span(quote: Any, source_text: Any) -> tuple[int, int] | None:
    """Dove sta questo passaggio nel testo originale, se ci sta.

    Args:
        quote: Il passaggio dichiarato da chi estrae, non affidabile.
        source_text: Il testo della fonte.

    Returns:
        `(inizio, fine)` come offset nel testo ORIGINALE, oppure ``None``.
        Prima si cerca il passaggio cosi' com'e', poi ignorando la
        punteggiatura: ricopiare togliendo una virgola resta ricopiare.
    """
    text = str(source_text or "")
    if len(normalize(quote)) < MIN_QUOTE_CHARS or not text:
        return None
    for loose in (False, True):
        haystack, offsets = _fold(text, drop_punctuation=loose)
        needle, _ = _fold(str(quote or ""), drop_punctuation=loose)
        if not needle or not haystack:
            continue
        at = haystack.find(needle)
        if at == -1:
            continue
        return offsets[at], offsets[at + len(needle) - 1] + 1
    return None


def quote_is_grounded(quote: Any, source_text: Any) -> bool:
    """La citazione compare davvero nel testo sorgente?

    Una citazione troppo corta, o un sorgente assente, non e' ancorata: si
    preferisce dichiararlo che fingere una verifica.
    """
    return locate_span(quote, source_text) is not None


def exact_span(quote: Any, source_text: Any) -> str:
    """Il passaggio come sta scritto nella fonte, non come e' stato ricopiato.

    E' questo che va mostrato fra virgolette. Chi estrae riformula anche solo
    nella punteggiatura o nelle maiuscole, e una citazione riscritta - fosse
    pure di poco - non e' piu' la prova di niente. Stringa vuota se il
    passaggio nel testo non c'e'.
    """
    found = locate_span(quote, source_text)
    return str(source_text or "")[found[0] : found[1]] if found else ""


def excerpt_around(quote: Any, source_text: Any, *, window: int = 320) -> str:
    """Il passaggio con un po' del suo contorno, dal testo originale.

    Serve all'audit: leggere la frase nel contesto in cui e' stata detta. Il
    testo torna con le sue maiuscole, la sua punteggiatura e i suoi a capo -
    e' la fonte, non una sua riscrittura.
    """
    found = locate_span(quote, source_text)
    if not found:
        return ""
    text = str(source_text or "")
    pad = max(0, window) // 2
    left, right = max(0, found[0] - pad), min(len(text), found[1] + pad)
    prefix = "…" if left > 0 else ""
    suffix = "…" if right < len(text) else ""
    return f"{prefix}{text[left:right].strip()}{suffix}"


# --- il claim come unita' di provenance -----------------------------------


@dataclass(frozen=True)
class ClaimRecord:
    """Un'affermazione con tutto cio' che serve per verificarla.

    `source_name` e' il documento/l'intervista; `attributed_to` e' chi parla.
    Sono due cose diverse: un verbale di workshop ha una fonte sola e piu'
    voci, e attribuire a una voce cio' che ha detto un'altra e' esattamente il
    difetto V3 numero uno.

    Tre campi separano cose che il primo giro di fix teneva insieme:

    - `topic` e' il **soggetto** ("autorizzazione della spesa"): serve a
      navigare, a mettere vicino cio' che parla della stessa cosa;
    - `assertion` e' la **proposizione** ("l'ordine sopra soglia passa da
      un'autorizzazione"): e' su questa che si conta la corroborazione. Due
      fonti che parlano dello stesso soggetto non stanno dicendo la stessa
      cosa, e trattarle come se lo facessero e' il modo in cui una regola di
      una fonte finiva attribuita anche all'altra;
    - `qualifiers` sono gli **attributi che questa fonte aggiunge**
      ("fornitore gia' conosciuto", "verifica formale prima dell'ordine"). Se
      li dice una sola fonte, restano suoi: possono comparire attribuiti a lei,
      mai dentro una frase attribuita a piu' fonti.
    """

    statement: str
    source_name: str = ""
    attributed_to: str = ""
    topic: str = ""
    assertion: str = ""
    qualifiers: tuple[str, ...] = ()
    quote: str = ""
    quote_verified: bool = False
    scope_label: str = ""
    scope_level: str = "stated_scope"
    epistemic_status: str = "reported"
    process_area: str = "other"
    claim_id: str | None = None
    source_id: str | None = None

    @property
    def key(self) -> str:
        """La chiave su cui si conta la corroborazione: la proposizione.

        Senza `assertion` dichiarata si ricade sull'enunciato: due formulazioni
        diverse restano due affermazioni diverse. Fail closed - meglio due
        `single_source` che una corroborazione che nessuno ha dichiarato.
        """
        return topic_key(self.assertion or self.statement)

    @property
    def subject(self) -> str:
        """Il soggetto, per raggruppare cio' che parla della stessa cosa."""
        return topic_key(self.topic or self.statement)

    @property
    def voice(self) -> str:
        """Chi risponde di questa affermazione. La persona se e' nota, altrimenti
        il documento: non esiste un claim senza qualcuno che lo sostenga."""
        return (self.attributed_to or "").strip() or (self.source_name or "").strip()

    @property
    def supports_topic(self) -> bool:
        return self.epistemic_status in SUPPORTING_STATUSES


def claim_record(value: Any) -> ClaimRecord:
    """Adatta un claim (dict del tool, riga canonical, modello pydantic) a
    `ClaimRecord`, tollerando i nomi di campo storici."""
    if isinstance(value, ClaimRecord):
        return value
    get = value.get if isinstance(value, dict) else (lambda k, d=None: getattr(value, k, d))
    epistemic = str(get("epistemic_status", "") or "reported").strip().lower()
    scope_level = str(get("scope_level", "") or "stated_scope").strip().lower()
    return ClaimRecord(
        statement=str(get("statement", None) or get("claim", "") or ""),
        source_name=str(get("source_name", "") or ""),
        attributed_to=str(get("attributed_to", "") or ""),
        topic=str(get("topic", "") or ""),
        assertion=str(get("assertion", "") or ""),
        qualifiers=normalize_qualifiers(get("qualifiers", ()) or ()),
        quote=str(get("quote", "") or ""),
        quote_verified=bool(get("quote_verified", False)),
        scope_label=str(get("scope_label", "") or ""),
        scope_level=scope_level if scope_level in SCOPE_LEVELS else "stated_scope",
        epistemic_status=epistemic if epistemic in EPISTEMIC_STATUSES else "reported",
        process_area=str(get("process_area", "") or "other"),
        claim_id=(str(get("claim_id", "")) or None) if get("claim_id", None) else None,
        source_id=(str(get("source_id", "")) or None) if get("source_id", None) else None,
    )


def normalize_qualifiers(values: Any) -> tuple[str, ...]:
    """Attributi puliti e deduplicati, nell'ordine dichiarato."""
    if isinstance(values, str):
        values = [values]
    out: list[str] = []
    seen: set[str] = set()
    for value in values or ():
        text = " ".join(str(value or "").split())
        key = normalize(text)
        if text and key not in seen:
            seen.add(key)
            out.append(text)
    return tuple(out)


# --- il conto: quanto e' sostenuta ogni affermazione ----------------------


@dataclass(frozen=True)
class LedgerEntry:
    claim: ClaimRecord
    support: str
    corroborating_sources: tuple[str, ...] = ()
    contested_by: tuple[str, ...] = ()
    # Attributi che questa fonte aggiunge e che le altre voci della stessa
    # proposizione NON dicono. Restano suoi: una frase attribuita a piu' fonti
    # non puo' contenerli.
    exclusive_qualifiers: tuple[str, ...] = ()
    shared_qualifiers: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "claim_id": self.claim.claim_id,
            "statement": self.claim.statement,
            "attributed_to": self.claim.attributed_to,
            "source_name": self.claim.source_name,
            "source_id": self.claim.source_id,
            "topic": self.claim.subject,
            "assertion": self.claim.key,
            "qualifiers": list(self.claim.qualifiers),
            "shared_qualifiers": list(self.shared_qualifiers),
            "exclusive_qualifiers": list(self.exclusive_qualifiers),
            "quote": self.claim.quote,
            "quote_verified": self.claim.quote_verified,
            "scope_label": self.claim.scope_label,
            "scope_level": self.claim.scope_level,
            "epistemic_status": self.claim.epistemic_status,
            "process_area": self.claim.process_area,
            "support": self.support,
            "support_label": SUPPORT_LABEL_IT.get(self.support, self.support),
            "corroborating_sources": list(self.corroborating_sources),
            "contested_by": list(self.contested_by),
        }


# --- cosa una frase attribuita a piu' fonti puo' contenere -----------------


# Quante lettere bastano per riconoscere la stessa parola sotto una flessione
# diversa: "formale" e "formalmente" condividono "formal". Non e' uno stemmer,
# e non deve esserlo - deve solo impedire che riformulare basti a far passare
# l'attributo di una fonte dentro una frase di due.
_STEM_CHARS = 6


def _stem(word: str) -> str:
    return word[:_STEM_CHARS]


def _qualifier_in_text(qualifier: str, text: str) -> bool:
    """L'attributo compare in questa frase?

    Prima come sottostringa normalizzata, poi parola per parola, confrontando
    le radici: la sintesi riformula, e "verifica formale prima dell'ordine"
    arriva come "prima dell'ordine verifica formalmente". Il controllo e'
    volutamente generoso - sbagliare per eccesso qui significa segnalare un
    attributo di troppo, sbagliare per difetto significa lasciar passare cio'
    che ha detto una sola fonte in bocca a due.
    """
    needle, haystack = normalize(qualifier), normalize(text)
    if not needle or not haystack:
        return False
    if needle in haystack:
        return True
    words = [w for w in _loose(qualifier).split() if len(w) > 3]
    if not words:
        return False
    stems = {_stem(w) for w in _loose(text).split()}
    return all(_stem(word) in stems for word in words)


@dataclass(frozen=True)
class SharedCore:
    """Cosa un gruppo di claim sulla stessa proposizione condivide davvero."""

    voices: tuple[str, ...] = ()
    shared: tuple[str, ...] = ()
    exclusive: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def corroborated(self) -> bool:
        return len(self.voices) >= 2

    def as_dict(self) -> dict[str, Any]:
        return {
            "voices": list(self.voices),
            "shared_qualifiers": list(self.shared),
            "source_specific_qualifiers": {k: list(v) for k, v in self.exclusive.items()},
        }


def shared_core(claims: Iterable[Any]) -> SharedCore:
    """Il nucleo condiviso di un gruppo, e cio' che resta di ciascuno.

    Un attributo e' condiviso solo se ogni voce del gruppo lo dichiara.
    L'unione non serve a niente qui: e' proprio unendo che una proprieta' di
    una fonte finiva dentro una frase attribuita a due.
    """
    records = [claim_record(item) for item in claims]
    supporting = [r for r in records if r.supports_topic]
    by_voice: dict[str, list[str]] = {}
    for record in supporting:
        voice = record.voice.strip()
        if voice:
            by_voice.setdefault(voice, []).extend(record.qualifiers)

    if not by_voice:
        return SharedCore()

    normalized = {
        voice: {normalize(q): q for q in quals} for voice, quals in by_voice.items()
    }
    common_keys = set.intersection(*(set(v) for v in normalized.values())) if normalized else set()
    first = next(iter(normalized.values()))
    shared = tuple(first[key] for key in first if key in common_keys)
    exclusive = {
        voice: tuple(quals[key] for key in quals if key not in common_keys)
        for voice, quals in normalized.items()
    }
    return SharedCore(
        voices=tuple(by_voice),
        shared=shared,
        exclusive={voice: quals for voice, quals in exclusive.items() if quals},
    )


@dataclass(frozen=True)
class CompositionVerdict:
    """Verdetto su una frase che attribuisce qualcosa a piu' fonti."""

    statement: str
    voices: tuple[str, ...] = ()
    leaked: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def valid(self) -> bool:
        return not self.leaked

    def as_dict(self) -> dict[str, Any]:
        return {
            "statement": self.statement,
            "voices": list(self.voices),
            "valid": self.valid,
            "source_specific_in_shared_statement": {
                voice: list(quals) for voice, quals in self.leaked.items()
            },
            "violations": [
                f"«{q}» lo dice solo {voice}: non puo' stare in una frase "
                f"attribuita a {', '.join(self.voices)}"
                for voice, quals in self.leaked.items()
                for q in quals
            ],
        }


def verify_shared_statement(statement: str, claims: Iterable[Any]) -> CompositionVerdict:
    """Una frase attribuita a piu' fonti contiene solo cio' che tutte reggono?

    E' l'invariante di composizione: la parte condivisa puo' essere
    corroborata, gli attributi di una sola fonte restano suoi. Il controllo e'
    deterministico perche' gli attributi sono dichiarati sul claim, non dedotti
    dal testo: se un attributo esclusivo compare nella frase condivisa, la
    frase sta attribuendo a tutti cio' che ha detto uno.
    """
    core = shared_core(claims)
    leaked = {
        voice: tuple(q for q in quals if _qualifier_in_text(q, statement))
        for voice, quals in core.exclusive.items()
    }
    return CompositionVerdict(
        statement=statement,
        voices=core.voices,
        leaked={voice: quals for voice, quals in leaked.items() if quals},
    )


def _distinct_voices(claims: Iterable[ClaimRecord]) -> list[str]:
    """Le voci distinte che sostengono un topic, nell'ordine in cui compaiono.

    "Distinte" per persona quando la persona e' nota, altrimenti per documento:
    due estrazioni dalla stessa intervista non fanno due fonti, ed e' cosi' che
    nasce una corroborazione inventata.
    """
    seen: list[str] = []
    for claim in claims:
        if not claim.supports_topic:
            continue
        voice = normalize(claim.voice)
        if voice and voice not in seen:
            seen.append(voice)
    return seen


def build_ledger(
    claims: Iterable[Any],
    *,
    contested_topics: dict[str, list[str]] | None = None,
) -> list[LedgerEntry]:
    """Il registro dell'evidenza: ogni claim con il suo grado di sostegno.

    `contested_topics` mappa `topic_key -> fonti in conflitto` e viene da
    `classify_divergence`: solo una divergenza classificata `incompatible`
    rende `contradicted` un claim. Una differenza di ambito o un "non lo so"
    non declassano niente, perche' non tolgono nulla a cio' che la fonte ha
    effettivamente detto - e' il difetto V3 numero cinque.
    """
    records = [claim_record(item) for item in claims]
    contested = {topic_key(k): list(v or []) for k, v in (contested_topics or {}).items()}

    # Il raggruppamento e' per PROPOSIZIONE (`record.key`), non per soggetto.
    # Due fonti che parlano di autorizzazione non stanno dicendo la stessa cosa
    # sull'autorizzazione: raggruppare per soggetto e' cio' che faceva ereditare
    # a una fonte la regola dell'altra.
    by_assertion: dict[str, list[ClaimRecord]] = {}
    for record in records:
        by_assertion.setdefault(record.key, []).append(record)

    entries: list[LedgerEntry] = []
    for record in records:
        peers = by_assertion.get(record.key, [])
        voices = _distinct_voices(peers)
        # Una divergenza puo' essere registrata sul soggetto o sull'enunciato:
        # entrambi contano, altrimenti la classificazione non arriva mai qui.
        contested_by = tuple(contested.get(record.key, ()) or contested.get(record.subject, ()))
        core = shared_core(peers)

        if record.epistemic_status == "declared_unknown":
            support = "declared_unknown"
        elif record.epistemic_status == "inferred":
            support = "inferred"
        elif contested_by:
            support = "contradicted"
        elif len(voices) >= 2:
            support = "corroborated"
        else:
            support = "single_source"

        others = tuple(
            claim.voice
            for claim in peers
            if claim.supports_topic and normalize(claim.voice) != normalize(record.voice)
        )
        exclusive = (
            core.exclusive.get(record.voice.strip(), ())
            if support == "corroborated"
            # Fuori da un gruppo corroborato ogni attributo e' della sua fonte:
            # dirlo esplicitamente evita che a valle si assuma il contrario.
            else record.qualifiers
        )
        entries.append(
            LedgerEntry(
                claim=record,
                support=support,
                corroborating_sources=others if support == "corroborated" else (),
                contested_by=contested_by,
                exclusive_qualifiers=tuple(exclusive),
                shared_qualifiers=core.shared if support == "corroborated" else (),
            )
        )
    return entries


def ledger_payload(entries: Iterable[LedgerEntry]) -> list[dict[str, Any]]:
    return [entry.as_dict() for entry in entries]


# --- divergenze: cosa e' davvero una contraddizione -----------------------


@dataclass(frozen=True)
class Stance:
    """La posizione di una fonte dentro una divergenza o dietro una sintesi.

    `qualifiers` sono gli attributi che QUESTA voce aggiunge. Servono al
    controllo di composizione: una frase attribuita a piu' voci non puo'
    contenere l'attributo di una sola.
    """

    source_name: str = ""
    attributed_to: str = ""
    statement: str = ""
    epistemic_status: str = "reported"
    scope_label: str = ""
    qualifiers: tuple[str, ...] = ()

    @property
    def voice(self) -> str:
        return (self.attributed_to or "").strip() or (self.source_name or "").strip()

    @property
    def supports_topic(self) -> bool:
        return self.epistemic_status in SUPPORTING_STATUSES


def stance_record(value: Any) -> Stance:
    if isinstance(value, Stance):
        return value
    get = value.get if isinstance(value, dict) else (lambda k, d=None: getattr(value, k, d))
    epistemic = str(get("epistemic_status", "") or "reported").strip().lower()
    return Stance(
        source_name=str(get("source_name", "") or ""),
        attributed_to=str(get("attributed_to", "") or ""),
        statement=str(get("statement", "") or get("claim", "") or ""),
        epistemic_status=epistemic if epistemic in EPISTEMIC_STATUSES else "reported",
        scope_label=str(get("scope_label", "") or ""),
        qualifiers=normalize_qualifiers(get("qualifiers", ()) or ()),
    )


@dataclass(frozen=True)
class DivergenceVerdict:
    declared: str
    effective: str
    reasons: tuple[str, ...] = ()
    voices: tuple[str, ...] = ()

    @property
    def downgraded(self) -> bool:
        return self.declared != self.effective

    @property
    def blocks_modeling(self) -> bool:
        return self.effective == "incompatible"

    def as_dict(self) -> dict[str, Any]:
        return {
            "declared_divergence_type": self.declared,
            "divergence_type": self.effective,
            "divergence_label": DIVERGENCE_LABEL_IT.get(self.effective, self.effective),
            "downgraded": self.downgraded,
            "downgrade_reasons": list(self.reasons),
            "voices": list(self.voices),
            "blocks_modeling": self.blocks_modeling,
        }


# Ordine di severita': `classify_divergence` puo' solo scendere lungo questa
# scala, mai salire. Una divergenza si indebolisce con le prove che mancano;
# non si rafforza perche' il modello l'ha descritta con parole piu' forti.
_SEVERITY_ORDER: tuple[str, ...] = (
    "incompatible",
    "tension_to_explore",
    "formalization_difference",
    "scope_difference",
    "complementary",
    "knowledge_gap",
    "single_source_uncertainty",
)


def _cap(current: str, ceiling: str) -> str:
    """Il piu' debole fra i due, secondo `_SEVERITY_ORDER`."""
    order = {value: index for index, value in enumerate(_SEVERITY_ORDER)}
    return current if order.get(current, 0) >= order.get(ceiling, 0) else ceiling


def classify_divergence(declared: Any, stances: Iterable[Any]) -> DivergenceVerdict:
    """Che cosa e' davvero questa divergenza, viste le posizioni in campo.

    Le regole, in ordine di applicazione - ognuna puo' solo indebolire:

    1. meno di due voci distinte -> `single_source_uncertainty`. Una fonte da
       sola non contraddice nessuno;
    2. almeno una parte dichiara di non sapere -> al massimo `knowledge_gap`.
       "Non conosco la policy" non e' l'opposto di "la policy esiste": e' il
       caso V3 di Paolo e Francesca, dove una lacuna era diventata un
       conflitto;
    3. le parti dichiarano ambiti diversi -> al massimo `scope_difference`.
       Due reparti che descrivono la propria prassi non si smentiscono;
    4. altrimenti vale il tipo dichiarato da chi analizza.

    Il tipo dichiarato non e' ignorato: se e' gia' piu' debole del tetto
    calcolato, resta quello. Il runtime non promuove mai una differenza a
    contraddizione.
    """
    declared_type = str(declared or "").strip().lower()
    if declared_type not in DIVERGENCE_TYPES:
        declared_type = "tension_to_explore"

    records = [stance_record(item) for item in stances]
    voices: list[str] = []
    for record in records:
        voice = record.voice.strip()
        if voice and normalize(voice) not in {normalize(v) for v in voices}:
            voices.append(voice)

    effective = declared_type
    reasons: list[str] = []

    if len(voices) < 2:
        effective = "single_source_uncertainty"
        reasons.append(
            "meno di due voci distinte: una fonte sola non contraddice nessuno"
        )
        return DivergenceVerdict(declared_type, effective, tuple(reasons), tuple(voices))

    unknown_voices = [r.voice for r in records if r.epistemic_status == "declared_unknown"]
    if unknown_voices:
        capped = _cap(effective, "knowledge_gap")
        if capped != effective:
            reasons.append(
                "una parte dichiara di non sapere ("
                + ", ".join(sorted(set(unknown_voices)))
                + "): e' una lacuna di conoscenza, non un'incompatibilita'"
            )
        effective = capped

    scopes = {normalize(r.scope_label) for r in records if r.scope_label.strip()}
    if len(scopes) >= 2:
        capped = _cap(effective, "scope_difference")
        if capped != effective:
            reasons.append(
                "le posizioni dichiarano ambiti diversi: descrivono prassi di "
                "perimetri differenti, non lo stesso fatto in due modi"
            )
        effective = capped

    return DivergenceVerdict(declared_type, effective, tuple(reasons), tuple(voices))


# --- corroborazione asserita: si dimostra, non si dichiara ----------------


@dataclass(frozen=True)
class CorroborationVerdict:
    topic: str
    asserted_support: str
    effective_support: str
    voices: tuple[str, ...] = ()
    reasons: tuple[str, ...] = ()
    composition: CompositionVerdict | None = None
    attribute_owners: dict[str, tuple[str, ...]] = field(default_factory=dict)

    @property
    def rejected(self) -> bool:
        """Il verdetto corregge cio' che era stato dichiarato.

        Non solo quando cambia il grado di sostegno: anche una frase condivisa
        che porta dentro l'attributo di una fonte sola, o una conclusione
        allargata oltre l'evidenza, sono correzioni che devono arrivare a chi
        ha chiamato — altrimenti restano scritte e non lette.
        """
        return bool(self.reasons) or self.asserted_support != self.effective_support

    @property
    def composition_ok(self) -> bool:
        return self.composition is None or self.composition.valid

    def as_dict(self) -> dict[str, Any]:
        payload = {
            "topic": self.topic,
            "asserted_support": self.asserted_support,
            "support": self.effective_support,
            "support_label": SUPPORT_LABEL_IT.get(
                self.effective_support, self.effective_support
            ),
            "voices": list(self.voices),
            "downgraded": self.rejected,
            "downgrade_reasons": list(self.reasons),
            "source_specific_attributes": {
                voice: list(quals) for voice, quals in self.attribute_owners.items()
            },
        }
        if self.composition is not None:
            payload["composition"] = self.composition.as_dict()
        return payload


def verify_corroboration(
    topic: Any,
    asserted_support: Any,
    stances: Iterable[Any],
    *,
    shared_statement: str = "",
    asserted_scope_level: str = "stated_scope",
) -> CorroborationVerdict:
    """"Le due fonti concordano" e' un'affermazione verificabile: si contano.

    Tre controlli, tutti deterministici:

    1. **quante voci.** Senza due voci distinte che sostengono davvero il tema,
       `corroborated` scende a `single_source`. E' il difetto V3 della
       sovrapposizione dichiarata su qualcosa che diceva una fonte sola.
    2. **cosa contiene la frase condivisa.** Se `shared_statement` porta dentro
       un attributo che dichiara una sola voce, la composizione e' invalida: la
       parte condivisa puo' essere corroborata, l'attributo di uno resta suo.
       E' il caso del "fornitore gia' conosciuto" attribuito a due fonti quando
       lo dice una.
    3. **fin dove arriva.** Una conclusione dichiarata valida per l'intero
       processo, sostenuta solo da posizioni che parlano del proprio reparto,
       viene riportata al perimetro che ha davvero: un'assenza di dati locale
       non e' un'assenza di dati di processo.
    """
    asserted = str(asserted_support or "").strip().lower()
    if asserted not in SUPPORT_LABEL_IT:
        asserted = "single_source"

    records = [stance_record(item) for item in stances]
    voices: list[str] = []
    for record in records:
        if record.epistemic_status not in SUPPORTING_STATUSES:
            continue
        voice = record.voice.strip()
        if voice and normalize(voice) not in {normalize(v) for v in voices}:
            voices.append(voice)

    effective = asserted
    reasons: list[str] = []
    if asserted == "corroborated" and len(voices) < 2:
        effective = "single_source" if voices else "inferred"
        reasons.append(
            "corroborazione non dimostrata: "
            f"{len(voices)} voce/i distinte sostengono questo tema, ne servono almeno due"
        )

    composition = (
        verify_shared_statement(shared_statement, records) if shared_statement.strip() else None
    )
    if composition is not None and not composition.valid:
        reasons.extend(composition.as_dict()["violations"])

    core = shared_core(records)
    if _generalizes_beyond_evidence(asserted_scope_level, records):
        reasons.append(
            "conclusione dichiarata valida per l'intero processo ma sostenuta solo "
            "da posizioni di perimetro dichiarato ("
            + ", ".join(sorted({r.scope_label for r in records if r.scope_label.strip()}))
            + "): vale li', non ovunque"
        )

    return CorroborationVerdict(
        topic=topic_key(topic),
        asserted_support=asserted,
        effective_support=effective,
        voices=tuple(voices),
        reasons=tuple(reasons),
        composition=composition,
        attribute_owners=core.exclusive,
    )


def _generalizes_beyond_evidence(asserted_scope_level: Any, stances: list["Stance"]) -> bool:
    """Una conclusione di processo poggiata solo su testimonianze di reparto.

    Due persone che dicono, ciascuna per il proprio pezzo, di non avere un dato
    non dimostrano che il dato non esista nel processo: dimostrano che loro non
    ce l'hanno. Il difetto V3 residuo sui tempi nasce esattamente qui.
    """
    if str(asserted_scope_level or "").strip().lower() != "whole_process":
        return False
    declared = [r for r in stances if r.scope_label.strip()]
    return bool(declared) and len(declared) == len(stances)


# --- il controllo sulla risposta consegnata -------------------------------
#
# Il controllo di composizione viveva solo dentro il tool di sintesi, che
# l'agente puo' non chiamare e il cui esito non arriva alla prosa finale.
# Risultato: la frase multi-fonte tornava a formarsi nell'ultimo passaggio,
# dove nessuno la guardava piu'. Qui si guarda li'.

# Come si dichiara un accordo in italiano. Non serve capire la frase: serve
# accorgersi che sta attribuendo qualcosa a piu' di una voce.
_PLURAL_ATTRIBUTION = re.compile(
    # Solo forme plurali: "conferma" al singolare e' un'attribuzione a una
    # voce sola, e trattarla come accordo farebbe scattare il controllo su
    # frasi corrette.
    r"\b(pi[uù]'? fonti|entrambi|entrambe|tutt[ei] (?:e )?(?:le |i )?"
    r"(?:fonti|intervistati|voci)|concordano|convergono|confermano|"
    r"le fonti)\b"
)
# Solo fine di frase e a capo. Due punti e punto e virgola CONTINUANO
# l'enunciato ("Paolo e Francesca concordano: ... anche per importi ridotti"),
# e spezzare li' separerebbe l'attribuzione dal suo attributo - cioe'
# esattamente le due cose che il controllo deve vedere insieme.
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+|\n+")


@dataclass(frozen=True)
class AnswerViolation:
    """Una frase della risposta che attribuisce a piu' voci cio' che ne dice una."""

    sentence: str
    qualifier: str
    owner: str
    voices_named: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "sentence": self.sentence,
            "qualifier": self.qualifier,
            "owner": self.owner,
            "voices_named": list(self.voices_named),
            "message": (
                f"«{self.qualifier}» lo dice solo {self.owner}: la frase "
                f"«{self.sentence.strip()}» lo attribuisce a piu' fonti. "
                f"Dillo separato, attribuito a {self.owner}."
            ),
        }


def _sentences(text: str) -> list[str]:
    return [part for part in _SENTENCE_SPLIT.split(str(text or "")) if part.strip()]


def _named_voices(sentence: str, voices: Iterable[str]) -> tuple[str, ...]:
    """Quali voci del registro questa frase nomina.

    Anche per solo nome o solo cognome: la prosa dice "Paolo", il registro dice
    "Paolo Marchetti", e trattarli come due cose diverse renderebbe il
    controllo inutile proprio dove serve.
    """
    haystack = _loose(sentence)
    named: list[str] = []
    for voice in voices:
        parts = [p for p in _loose(voice).split() if len(p) > 2]
        if parts and any(f" {part} " in f" {haystack} " for part in parts):
            named.append(voice)
    return tuple(named)


def audit_answer(text: str, entries: Iterable[LedgerEntry]) -> list[AnswerViolation]:
    """Le frasi della risposta che fondono indebitamente piu' fonti.

    Una frase e' "multi-fonte" quando nomina almeno due voci del registro,
    oppure quando dichiara un accordo senza nominarne nessuna ("piu' fonti
    concordano", "entrambi riferiscono"). In una frase cosi' non puo' comparire
    un attributo che il registro assegna a una voce sola.

    Il controllo e' deterministico perche' gli attributi sono dichiarati sul
    claim: non si prova a capire la frase, si verifica che non porti dentro
    qualcosa che una sola fonte sostiene.

    Args:
        text: La risposta prodotta, non affidabile.
        entries: Il registro dell'evidenza su cui e' stata scritta.

    Returns:
        Le violazioni trovate, una per attributo fuori posto.
    """
    ledger = list(entries)
    voices = [entry.claim.voice for entry in ledger if entry.claim.voice.strip()]
    owned: list[tuple[str, str]] = [
        (qualifier, entry.claim.voice)
        for entry in ledger
        for qualifier in entry.exclusive_qualifiers
        if qualifier.strip() and entry.claim.voice.strip()
    ]
    if not owned:
        return []

    violations: list[AnswerViolation] = []
    for sentence in _sentences(text):
        named = _named_voices(sentence, dict.fromkeys(voices))
        shared_claim = len(named) >= 2 or (
            bool(_PLURAL_ATTRIBUTION.search(_loose(sentence))) and len(named) <= 1
        )
        if not shared_claim:
            continue
        for qualifier, owner in owned:
            # Se la frase nomina soltanto il proprietario dell'attributo, sta
            # attribuendo correttamente: non e' una fusione.
            if named and set(named) == {owner}:
                continue
            if _qualifier_in_text(qualifier, sentence):
                violations.append(
                    AnswerViolation(
                        sentence=sentence,
                        qualifier=qualifier,
                        owner=owner,
                        voices_named=named,
                    )
                )
    return violations


def render_attribution_notice(violations: Iterable[AnswerViolation]) -> str:
    """La correzione che il runtime allega quando la prosa non si e' corretta.

    Meglio una nota esplicita in fondo che una frase che resta sbagliata: il
    consulente deve poter vedere di chi e' davvero cio' che ha letto.
    """
    items = list(violations)
    if not items:
        return ""
    lines = ["**Precisazione sull'attribuzione**", ""]
    for owner in dict.fromkeys(item.owner for item in items):
        attributes = dict.fromkeys(
            item.qualifier for item in items if item.owner == owner
        )
        lines.append(f"- {', '.join(attributes)}: lo riferisce solo {owner}.")
    return "\n".join(lines)


# --- resa leggibile -------------------------------------------------------


def render_provenance_section(
    entries: Iterable[LedgerEntry],
    *,
    limit: int = 24,
    heading: str = "Da dove viene",
) -> str:
    """La sezione che il consulente puo' verificare riga per riga.

    Non la scrive il modello: la stampa il runtime dal registro. E' l'unica
    risposta possibile alla richiesta "mostrami claim -> fonte -> estratto",
    perche' una sintesi che riscrive l'estratto non dimostra niente.
    """
    items = list(entries)[: max(1, limit)]
    if not items:
        return ""
    lines = [f"**{heading}**", ""]
    for entry in items:
        claim = entry.claim
        voice = claim.voice or "fonte non dichiarata"
        scope = f", ambito: {claim.scope_label}" if claim.scope_label.strip() else ""
        lines.append(
            f"- {claim.statement} — {voice} "
            f"({SUPPORT_LABEL_IT.get(entry.support, entry.support)}{scope})"
        )
        # Fra virgolette ci va solo cio' che nella fonte c'e' davvero. Un
        # passaggio riformulato messo fra virgolette e' peggio di nessuna
        # citazione: sembra una prova e non lo e'.
        if claim.quote.strip() and claim.quote_verified:
            lines.append(f'  > "{claim.quote.strip()}"')
        elif claim.quote.strip():
            lines.append(
                "  (riformulazione di chi ha estratto, non un passaggio della "
                "fonte: non citarla come tale)"
            )
        if entry.corroborating_sources:
            lines.append(
                "  anche: " + ", ".join(dict.fromkeys(entry.corroborating_sources))
            )
        # Cio' che aggiunge solo questa voce si legge attaccato a lei, non
        # dentro la riga condivisa: e' la differenza fra "concordano" e
        # "concordano, e uno dei due aggiunge".
        if entry.exclusive_qualifiers:
            lines.append(
                f"  solo {voice}: " + ", ".join(entry.exclusive_qualifiers)
            )
    return "\n".join(lines)


@dataclass
class LedgerSummary:
    """Cosa il registro dice nel suo insieme, per il nodo che scrive la risposta."""

    total: int = 0
    corroborated: int = 0
    single_source: int = 0
    contradicted: int = 0
    inferred: int = 0
    declared_unknown: int = 0
    unverified_quotes: int = 0
    voices: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "total": self.total,
            "corroborated": self.corroborated,
            "single_source": self.single_source,
            "contradicted": self.contradicted,
            "inferred": self.inferred,
            "declared_unknown": self.declared_unknown,
            "unverified_quotes": self.unverified_quotes,
            "voices": list(self.voices),
        }


def summarize_ledger(entries: Iterable[LedgerEntry]) -> LedgerSummary:
    summary = LedgerSummary()
    seen: list[str] = []
    for entry in entries:
        summary.total += 1
        if entry.support in SUPPORT_LABEL_IT:
            setattr(summary, entry.support, getattr(summary, entry.support) + 1)
        if entry.claim.quote.strip() and not entry.claim.quote_verified:
            summary.unverified_quotes += 1
        voice = entry.claim.voice.strip()
        if voice and normalize(voice) not in {normalize(v) for v in seen}:
            seen.append(voice)
    summary.voices = seen
    return summary
