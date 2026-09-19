"""Ogni elemento del piano, confrontato con le fonti da cui dice di venire.

La validazione del disegno confrontava il canvas con il piano
(`validate_canvas_against_process`), e il piano e' l'output di un estrattore.
Un piano che inventa un passaggio produce un canvas che lo rappresenta
fedelmente, e la validazione dice "tutto coerente": verificava che il disegno
somigliasse all'ipotesi, non che l'ipotesi somigliasse alle interviste.

Il campo `source_evidence` di ogni elemento era testo libero che l'estrattore
riempiva come voleva, e nessuno lo rileggeva. Qui lo si rilegge: per ogni
attore, passaggio, decisione, eccezione, evento e flusso si cerca nelle fonti
cio' che l'elemento dichiara, senza chiamare un modello.

Quattro esiti, e la differenza fra loro e' il punto:

| esito | cosa e' stato trovato |
| --- | --- |
| `verified` | un passaggio dichiarato come evidenza compare nella fonte, parola per parola (punteggiatura a parte) |
| `paraphrased` | l'evidenza dichiarata non compare cosi' com'e', ma una frase della fonte porta le stesse parole |
| `label_grounded` | l'evidenza dichiarata non si trova, ma le parole dell'elemento stanno in una frase della fonte |
| `unverified` | niente di tutto questo: l'elemento e' un'inferenza, e va trattato come tale |

`unverified` non significa "sbagliato": un passaggio necessario a rendere
coerente il flusso puo' non essere stato detto da nessuno. Significa che non si
puo' dire a un cliente che viene dalle sue interviste, e il disegno deve
mostrarlo.

Deterministico e senza LLM: stesso piano, stesse fonti, stesso rapporto.
"""

from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.agents.evidence_brief import content_tokens
from backend.memory.provenance import FoldedText
from backend.process_understanding import ProcessUnderstanding

ProvenanceStatus = Literal["verified", "paraphrased", "label_grounded", "unverified"]
ConsultantDecision = Literal["confirmed", "rejected"]
# L'esito che il disegno mostra: quello della verifica, oppure "confirmed" quando
# un elemento che nessuna fonte regge e' stato confermato da chi conosce il
# processo. La verifica non cambia - la fonte continua a non dirlo - ma
# l'elemento non e' piu' un'inferenza di un modello.
MarkStatus = Literal["verified", "paraphrased", "label_grounded", "unverified", "confirmed"]
ElementKind = Literal["actor", "participant", "step", "decision", "exception", "event", "flow"]

# Quanto di un'evidenza parafrasata deve ritrovarsi in una frase della fonte.
# Alto di proposito: e' la soglia sotto la quale "dice la stessa cosa" diventa
# "parla dello stesso argomento", che non e' una prova.
PARAPHRASE_MIN_OVERLAP = 0.8
# Per l'etichetta la soglia e' piu' bassa, perche' un'etichetta e' corta e
# riformulata per definizione ("Apri richiesta" contro "apro una richiesta"), ed
# e' anche l'esito piu' debole dei tre positivi.
LABEL_MIN_OVERLAP = 0.6
MIN_SHARED_TOKENS = 2
# Radice di confronto: la stessa parola flessa in italiano ("verifica",
# "verifico", "verificare") deve contare come la stessa parola. Una radice
# fissa non e' uno stemmer, ma e' deterministica e non inventa legami.
STEM_CHARS = 5

_SENTENCE_BREAK = re.compile(r"(?<=[.!?;:])\s+|\n+")


class ElementProvenance(BaseModel):
    """Da dove viene un elemento del piano, se viene da qualche parte."""

    kind: ElementKind
    element_id: str
    label: str
    status: ProvenanceStatus
    # Il riferimento con cui il compilatore traccia l'elemento nel BPMN
    # (`steps:apri_richiesta`): e' cio' che lega questo esito al nodo disegnato.
    source_ref: str
    source_id: str = ""
    source_name: str = ""
    # Il passaggio come sta scritto nella fonte: lo span esatto quando
    # `verified`, la frase che porta le parole quando parafrasato o ancorato
    # all'etichetta. Mai il testo che l'estrattore dichiara: quello e' la
    # domanda, non la risposta.
    quote: str = ""
    # Le fonti in cui si ritrova almeno una delle evidenze dichiarate, parola per
    # parola o parafrasata. Un passaggio che due voci raccontano, e che il piano
    # ha unificato portandosi le citazioni di entrambe, deve risultare sostenuto
    # da due fonti: contarne una sola lo farebbe sembrare meno certo di quanto
    # le interviste dicono.
    corroborating_sources: list[str] = Field(default_factory=list)
    # Cosa ne ha deciso il consulente, quando l'ha rivisto. `None` significa
    # "non ancora rivisto", non "accettato".
    consultant_decision: ConsultantDecision | None = None

    @property
    def awaiting_confirmation(self) -> bool:
        """Nessuna fonte lo regge e nessuno lo ha ancora confermato."""
        return self.status == "unverified" and self.consultant_decision != "confirmed"

    @property
    def mark_status(self) -> MarkStatus:
        if self.status == "unverified" and self.consultant_decision == "confirmed":
            return "confirmed"
        return self.status


class ProvenanceReport(BaseModel):
    """Il piano confrontato con le fonti, elemento per elemento."""

    elements: list[ElementProvenance] = Field(default_factory=list)
    sources_checked: int = 0
    # Fonti con un testo da cui nessun elemento del piano risulta venire. Un
    # piano che non prende niente da un'intervista l'ha ignorata, o l'ha
    # riformulata al punto da non poterlo piu' dimostrare.
    unused_sources: list[str] = Field(default_factory=list)

    def count(self, status: ProvenanceStatus) -> int:
        return sum(1 for item in self.elements if item.status == status)

    @property
    def unverified(self) -> list[ElementProvenance]:
        return [item for item in self.elements if item.status == "unverified"]

    @property
    def awaiting_confirmation(self) -> list[ElementProvenance]:
        """Cio' che resta da rivedere: inferenze che nessuno ha ancora confermato."""
        return [item for item in self.elements if item.awaiting_confirmation]

    @property
    def grounded_ratio(self) -> float:
        """Quota di elementi con un appiglio nelle fonti, di qualunque forza."""
        if not self.elements:
            return 0.0
        return round(1 - len(self.unverified) / len(self.elements), 3)

    def summary(self) -> dict[str, Any]:
        return {
            "total": len(self.elements),
            "verified": self.count("verified"),
            "paraphrased": self.count("paraphrased"),
            "label_grounded": self.count("label_grounded"),
            "unverified": self.count("unverified"),
            "awaiting_confirmation": len(self.awaiting_confirmation),
            "corroborated": sum(1 for item in self.elements if len(item.corroborating_sources) > 1),
            "grounded_ratio": self.grounded_ratio,
            "sources_checked": self.sources_checked,
            "unused_sources": list(self.unused_sources),
        }

    def status_by_source_ref(self) -> dict[str, MarkStatus]:
        return {item.source_ref: item.mark_status for item in self.elements}

    def with_decisions(self, decisions: dict[str, dict]) -> "ProvenanceReport":
        """Il rapporto con le decisioni del consulente accanto a ogni elemento.

        Una decisione vale per l'elemento che aveva quell'etichetta: un piano
        ricostruito puo' riusare lo stesso id per un passaggio diverso, e
        applicarle una conferma data a un altro passaggio sarebbe una conferma
        inventata.
        """
        if not decisions:
            return self
        elements = []
        for item in self.elements:
            recorded = decisions.get(item.source_ref) or {}
            same_element = str(recorded.get("label") or "") == item.label
            decision = recorded.get("decision") if same_element else None
            elements.append(
                item.model_copy(
                    update={
                        "consultant_decision": decision
                        if decision in ("confirmed", "rejected")
                        else None
                    }
                )
            )
        return self.model_copy(update={"elements": elements})


class _Sentence:
    __slots__ = ("text", "stems")

    def __init__(self, text: str) -> None:
        self.text = text
        self.stems = _stems(text)


class _IndexedSource:
    """Una fonte preparata una volta per tutte le ricerche del rapporto."""

    __slots__ = ("id", "name", "folded", "sentences")

    def __init__(self, source: dict) -> None:
        text = str(source.get("content") or "")
        self.id = str(source.get("id") or "")
        self.name = str(source.get("name") or self.id)
        self.folded = FoldedText(text)
        self.sentences = [
            _Sentence(part.strip())
            for part in _SENTENCE_BREAK.split(text)
            if part and part.strip()
        ]


# Le preposizioni articolate elise ("dell'ordine", "nell'ufficio") perdono
# l'apostrofo e diventano parole di quattro lettere che nessuno ha detto come
# contenuto: contarle farebbe fallire una parafrasi fedele per colpa di come si
# scrive l'italiano.
_ELIDED_FUNCTION_WORDS = frozenset(
    {"dell", "dall", "nell", "sull", "coll", "degl", "negl", "sugl", "dagl", "quell"}
)


def content_stems(text: str) -> set[str]:
    """Le radici delle parole di contenuto: la misura con cui due testi dicono la stessa cosa.

    Pubblica perche' chi deve decidere se due etichette del piano parlano dello
    stesso passaggio deve usare lo stesso metro di chi le confronta con le
    fonti: due misure diverse darebbero due risposte diverse sullo stesso testo.
    """
    return {
        token[:STEM_CHARS]
        for token in content_tokens(text)
        if token not in _ELIDED_FUNCTION_WORDS
    }


_stems = content_stems


def _best_sentence(
    stems: set[str], sources: list[_IndexedSource]
) -> tuple[_IndexedSource, _Sentence, float, int] | None:
    """La frase che porta la quota piu' alta delle parole date.

    A parita' vince la prima nell'ordine delle fonti e delle frasi: il rapporto
    deve essere lo stesso a ogni lettura, e un pareggio risolto a caso non lo
    sarebbe.
    """
    if not stems:
        return None
    best = None
    for source in sources:
        for sentence in source.sentences:
            shared = len(stems & sentence.stems)
            if not shared:
                continue
            ratio = shared / len(stems)
            if best is None or ratio > best[2]:
                best = (source, sentence, ratio, shared)
    return best


def _passes(
    match, min_ratio: float, stems: set[str], *, allow_single_word: bool = False
) -> bool:
    """La frase migliore regge davvero, o condivide solo una parola?

    Il rilassamento a una parola vale solo per l'etichetta: un'etichetta di una
    parola sola ("Collaudo") non ha due parole da condividere. Un'evidenza di una
    parola sola invece non prova niente - "fornitore" sta in meta' delle frasi di
    un'intervista sugli acquisti - e dichiararla parafrasata sarebbe una prova
    inventata.
    """
    if match is None:
        return False
    _source, _sentence, ratio, shared = match
    needed = min(MIN_SHARED_TOKENS, len(stems)) if allow_single_word else MIN_SHARED_TOKENS
    return ratio >= min_ratio and shared >= needed


def _source_carries_evidence(snippets: list[str], source: _IndexedSource) -> bool:
    """Una delle evidenze dichiarate sta in questa fonte, letterale o parafrasata?

    Solo le evidenze, non l'etichetta: l'etichetta di un passaggio comune
    ("inviare la richiesta") si ritrova in ogni intervista, e contarla come
    conferma farebbe risultare corroborato cio' che una sola voce ha detto.
    """
    for snippet in snippets:
        if source.folded.locate(snippet) is not None:
            return True
        stems = _stems(snippet)
        if _passes(_best_sentence(stems, [source]), PARAPHRASE_MIN_OVERLAP, stems):
            return True
    return False


def _judge(
    *,
    kind: ElementKind,
    field: str,
    element_id: str,
    label: str,
    evidence: list[str],
    extra_text: str,
    sources: list[_IndexedSource],
) -> ElementProvenance:
    base = {
        "kind": kind,
        "element_id": element_id,
        "label": label,
        "source_ref": f"{field}:{element_id}",
    }

    snippets = [str(item or "").strip().strip("\"'«»“”") for item in evidence]
    snippets = [item for item in snippets if item]
    base["corroborating_sources"] = [
        source.name for source in sources if _source_carries_evidence(snippets, source)
    ]

    for snippet in snippets:
        for source in sources:
            span = source.folded.locate(snippet)
            if span is not None:
                return ElementProvenance(
                    **base,
                    status="verified",
                    source_id=source.id,
                    source_name=source.name,
                    quote=source.folded.text[span[0] : span[1]],
                )

    for snippet in snippets:
        stems = _stems(snippet)
        match = _best_sentence(stems, sources)
        if match is not None and _passes(match, PARAPHRASE_MIN_OVERLAP, stems):
            source, sentence, _ratio, _shared = match
            return ElementProvenance(
                **base,
                status="paraphrased",
                source_id=source.id,
                source_name=source.name,
                quote=sentence.text,
            )

    stems = _stems(f"{label} {extra_text}")
    match = _best_sentence(stems, sources)
    if match is not None and _passes(match, LABEL_MIN_OVERLAP, stems, allow_single_word=True):
        source, sentence, _ratio, _shared = match
        return ElementProvenance(
            **base,
            status="label_grounded",
            source_id=source.id,
            source_name=source.name,
            quote=sentence.text,
        )

    return ElementProvenance(**base, status="unverified")


def verify_plan_provenance(
    understanding: ProcessUnderstanding | dict | None,
    sources: list[dict],
) -> ProvenanceReport:
    """Confronta ogni elemento del piano con il testo delle fonti.

    Args:
        understanding: Il piano, persistito o appena estratto.
        sources: Le fonti del registro, con il loro testo **integrale**. Un testo
            tagliato fa risultare inventato cio' che la fonte dice dopo il
            taglio, quindi chi chiama non deve passare gli estratti del confine.

    Returns:
        Il rapporto, elemento per elemento, nell'ordine in cui il piano li
        dichiara.

    Sola lettura, nessun LLM.
    """
    if understanding is None:
        return ProvenanceReport(sources_checked=0)

    plan = (
        understanding
        if isinstance(understanding, ProcessUnderstanding)
        else ProcessUnderstanding.model_validate(understanding)
    )
    indexed = [
        _IndexedSource(source)
        for source in sources
        if str(source.get("content") or "").strip()
    ]

    elements: list[ElementProvenance] = []

    def add(**kwargs) -> None:
        elements.append(_judge(sources=indexed, **kwargs))

    for actor in plan.actors:
        add(kind="actor", field="actors", element_id=actor.id, label=actor.label,
            evidence=actor.source_evidence, extra_text="")
    for participant in plan.participants:
        add(kind="participant", field="participants", element_id=participant.id,
            label=participant.label, evidence=participant.source_evidence, extra_text="")
    for step in plan.steps:
        add(kind="step", field="steps", element_id=step.id, label=step.label,
            evidence=step.source_evidence, extra_text=step.description or "")
    for decision in plan.decisions:
        add(kind="decision", field="decisions", element_id=decision.id, label=decision.label,
            evidence=decision.source_evidence, extra_text=decision.question or "")
    for exception in plan.exceptions:
        # Le eccezioni non dichiarano evidenza nello schema: si giudicano da cio'
        # che dicono di se', cioe' etichetta, innesco e gestione.
        add(kind="exception", field="exceptions", element_id=exception.id,
            label=exception.label, evidence=[],
            extra_text=" ".join(filter(None, [exception.trigger, exception.handling])))
    for event in plan.events:
        add(kind="event", field="events", element_id=event.id, label=event.label,
            evidence=event.source_evidence, extra_text="")
    for edge in plan.flow_edges:
        # Un flusso senza evidenza dichiarata e' quasi sempre la conseguenza di
        # due passaggi, non un'affermazione di qualcuno: contarlo inflazionerebbe
        # gli "inventati" con archi che nessuno deve provare.
        if not edge.source_evidence:
            continue
        add(kind="flow", field="flow_edges", element_id=edge.id, label=edge.label,
            evidence=edge.source_evidence, extra_text=edge.condition or "")

    return ProvenanceReport(
        elements=elements,
        sources_checked=len(indexed),
        unused_sources=_unused_sources(plan, elements, indexed),
    )


def _unused_sources(
    plan: ProcessUnderstanding,
    elements: list[ElementProvenance],
    sources: list[_IndexedSource],
) -> list[str]:
    """Le fonti da cui nessun elemento del piano puo' venire.

    Non basta guardare a quale fonte e' stato attribuito ogni elemento: a parita'
    di frase vince la prima fonte, e due voci che raccontano lo stesso passaggio
    lo attribuiscono alla prima letta. Contare solo quella farebbe dichiarare
    "ignorata" un'intervista che il piano usa per intero - e quella frase arriva
    a chi legge il canvas. Una fonte e' usata se **almeno un** elemento regge su
    di lei, attribuito o no.
    """
    attributed = {item.source_id for item in elements if item.status != "unverified"}
    probes: list[tuple[list[str], str]] = []
    for item in plan.actors:
        probes.append((item.source_evidence, item.label))
    for item in plan.participants:
        probes.append((item.source_evidence, item.label))
    for item in plan.steps:
        probes.append((item.source_evidence, f"{item.label} {item.description or ''}"))
    for item in plan.decisions:
        probes.append((item.source_evidence, f"{item.label} {item.question or ''}"))
    for item in plan.exceptions:
        probes.append(([], " ".join(filter(None, [item.label, item.trigger, item.handling]))))
    for item in plan.events:
        probes.append((item.source_evidence, item.label))

    unused: list[str] = []
    for source in sources:
        if source.id in attributed:
            continue
        if not any(_supports(evidence, text, source) for evidence, text in probes):
            unused.append(source.name)
    return unused


def _supports(evidence: list[str], text: str, source: _IndexedSource) -> bool:
    """Questa fonte regge l'elemento, con una qualunque delle forme di prova?"""
    for snippet in evidence:
        snippet = str(snippet or "").strip()
        if not snippet:
            continue
        if source.folded.locate(snippet) is not None:
            return True
        stems = _stems(snippet)
        if _passes(_best_sentence(stems, [source]), PARAPHRASE_MIN_OVERLAP, stems):
            return True
    stems = _stems(text)
    return _passes(
        _best_sentence(stems, [source]), LABEL_MIN_OVERLAP, stems, allow_single_word=True
    )
