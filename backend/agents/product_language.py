"""PROCESS-V2-01: la chat parla al consulente, non al debugger.

Difetto osservato nella chat di processo: alla domanda "a che punto siamo?"
l'agente rispondeva con `ProcessUnderstanding`, `readiness 0%`, "XML validato
semanticamente", id di fonte e nomi di record del workspace. Tecnicamente
corretto, ma e' il sistema che stampa il proprio stato interno invece di un
assistente che parla a un consulente.

Il principio: dentro DeliR le strutture restano tecniche quanto serve; fuori,
nella prosa rivolta al consulente, vanno tradotte in linguaggio di consulenza.
Il dettaglio interno (XML, punteggi, id, diagnostica) e' materiale da vista
Evidence/Audit, o da risposta esplicita quando il consulente lo chiede.

Questo modulo tiene insieme le due meta' del fix:

- `PRODUCT_LANGUAGE_CONTRACT`, la regola messa nel prompt di scope, cosi' vale
  per ogni chat (consultant, progetto, processo, canvas) e non solo dove
  qualcuno si e' ricordato di scriverla;
- `internal_language_leaks`, il rilevatore deterministico usato dai test e dal
  contatore di degradazione: senza un rilevatore, "la chat parla da prodotto"
  resta un'opinione e non un'asserzione.
"""

from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass(frozen=True)
class InternalTerm:
    """Un pezzo di vocabolario interno che non deve finire nella prosa.

    Attributes:
        label: Nome della famiglia, usato nei test e nel dettaglio del contatore.
        pattern: Regex che riconosce il termine nel testo.
        say_instead: Cosa dire al suo posto, riportato nel contratto di prompt.
    """

    label: str
    pattern: re.Pattern[str]
    say_instead: str


def _term(label: str, expression: str, say_instead: str) -> InternalTerm:
    return InternalTerm(label, re.compile(expression, re.IGNORECASE), say_instead)


# Il vocabolario e' volutamente stretto: ogni voce e' un termine che il
# consulente non ha motivo di leggere, non ogni parola tecnica esistente.
# "BPMN", "processo", "As-Is", "evidenza" restano linguaggio di consulenza e
# non sono qui dentro.
INTERNAL_VOCABULARY: tuple[InternalTerm, ...] = (
    _term(
        "internal_artifact",
        r"ProcessUnderstanding|BPMNSemanticModel|CompilationPlan|"
        r"sourceProcessUnderstanding|semantic model|modello semantico",
        "di' 'quello che sappiamo del processo' e 'il modello del processo'",
    ),
    # `readiness` senza qualificatori: nella prosa italiana della chat e' sempre
    # il campo, mai una parola di consulenza. La controprova lo ha mostrato in
    # tre forme diverse ("readiness 0%", "readiness registrata: 0%",
    # "readiness_score"), e inseguirle una a una lasciava passare la successiva.
    _term(
        "readiness_score",
        r"\breadiness\b",
        "di' a parole quanto e' affidabile l'As-Is e cosa manca per renderlo tale",
    ),
    _term(
        "raw_score",
        r"\bconfidence\b|\bscore\b|\bsoglia di confidenza\b",
        "di' 'l'evidenza e' debole / solida' invece di un numero",
    ),
    _term(
        "bpmn_xml",
        r"\bXML\b",
        "parla del diagramma o del modello, non del suo formato di file",
    ),
    _term(
        "internal_identifier",
        r"\b(?:process|project|client|source|episode|bpmn_model|entity|thread|scope|model)_id\b|"
        r"\b[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\b|"
        r"\b(?:proc|proj|src|ep|bm|cli)-[0-9a-z]{6,}\b",
        "nomina la cosa per nome ('l'intervista con Operations'), non per id",
    ),
    _term(
        "internal_storage",
        r"workspace db|workspace database|database del workspace|"
        r"record del workspace|nello state\b|nel workspace\b",
        "di' 'l'ho messo agli atti del progetto'",
    ),
    # "schema" e "tool" da soli restano italiano di consulenza - uno schema
    # preliminare, i tool che il cliente usa davvero - quindi qui c'e' solo il
    # meccanismo dell'agente, non ogni parola che gli somiglia.
    _term(
        "internal_machinery",
        r"\bsubgraph\b|sottografo|macro agent|tool call|\btoolset\b|"
        r"chiamat[ao]\s+(?:al|del)\s+tool|LangGraph|\bcheckpoint\b|"
        r"\bpayload\b|\bendpoint\b|\bJSON\b",
        "descrivi il lavoro fatto, non il meccanismo che lo ha fatto",
    ),
    _term(
        "internal_validation",
        r"validat[oaie]\s+semanticamente|validazione semantica|semanticamente valid|"
        r"quality report|\bdiagnostic\w*\b",
        "di' cosa regge e cosa no nel processo, non che controllo e' passato",
    ),
)


def _contract_translation_lines() -> str:
    return "\n".join(f"- {term.say_instead}." for term in INTERNAL_VOCABULARY)


PRODUCT_LANGUAGE_CONTRACT = f"""
Lingua del prodotto.

Scrivi al consulente come un collega senior di consulenza, non come un sistema
che stampa il proprio stato. Le strutture interne di DeliR sono strumenti tuoi:
il consulente ne legge il risultato, non il nome.

Mai nella risposta, se non richiesto: nomi di artefatti interni, punteggi
grezzi, id di record, XML, diagnostica, nomi di tool, di nodi o di campi di
stato. Traduci:
{_contract_translation_lines()}

Quando il consulente chiede a che punto e' un processo, rispondi in tre mosse,
in prosa:
1. cosa e' gia' fermo (perimetro, inizio e fine, obiettivo dichiarato);
2. cosa non sappiamo ancora e perche' questo non e' ancora un As-Is affidabile
   (ruoli, attivita', approvazioni, sistemi, eccezioni, tempi, criticita');
3. qual e' il prossimo passo concreto di consulenza, con chi e per ottenere cosa.

Un modello vuoto si dice "non abbiamo ancora abbastanza per disegnarlo", non
"readiness 0%". Una fonte salvata si dice "l'ho messa agli atti", con il suo
nome, non con il suo id.

L'eccezione e' esplicita: se il consulente chiede il dettaglio tecnico - l'XML,
un id, un punteggio, il contenuto di un record - daglielo senza giri di parole.
E' un default di linguaggio, non una censura.
""".strip()


def internal_language_leaks(text: str, *, consultant_asked: str = "") -> list[str]:
    """Elenca le famiglie di vocabolario interno finite nella prosa al consulente.

    Args:
        text: Testo rivolto al consulente (risposta dell'agente).
        consultant_asked: Messaggio del consulente in questo turno. Se il
            consulente usa lui per primo un termine di una famiglia, quella
            famiglia non e' una fuga: gliel'ha chiesta.

    Returns:
        list[str]: Etichette delle famiglie trovate, in ordine di dichiarazione
            e senza ripetizioni. Lista vuota quando il testo parla da prodotto.
    """
    if not text:
        return []

    asked = consultant_asked or ""
    return [
        term.label
        for term in INTERNAL_VOCABULARY
        if term.pattern.search(text) and not term.pattern.search(asked)
    ]
