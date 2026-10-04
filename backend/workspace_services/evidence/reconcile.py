"""Il confronto fra le affermazioni di file diversi (P1.13, Reconciliation Layer).

Un file appena estratto si confronta con le affermazioni degli altri file
confermati dello stesso processo. Il modello vede le affermazioni nuove (`[N2]`)
e quelle che c'erano gia' (`[E5]`, con il file da cui vengono) e dice quali
coppie parlano dello stesso fatto: o lo dicono uguale (corroborazione), o
divergono.

Il modello propone, il codice decide:

- una coppia con un numero che non corrisponde a niente si scarta;
- il tipo di divergenza passa da `provenance.classify_divergence`, che puo' solo
  indebolirlo: una parte che dichiara di non sapere fa una lacuna, due ambiti
  diversi fanno una differenza di perimetro, e il modello non riesce a far
  diventare incompatibile cio' che le regole non permettono;
- una divergenza che le regole riducono a "una sola fonte" non e' una
  divergenza, e non si registra.

Nessun conflitto si risolve qui: si registra, con le due affermazioni e le loro
porzioni, e lo guarda il consulente.

Uso:
    from backend.workspace_services.evidence.reconcile import reconcile_claims
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Literal

from pydantic import BaseModel, Field

from backend.llm import LlmTask
from backend.llm import run as llm_run
from backend.memory.provenance import classify_divergence

# Le affermazioni gia' presenti possono essere tante (un processo con dieci
# file): oltre il tetto si confronta con le prime e si dice quante ne restano.
MAX_INPUT_CHARS = 60_000
MAX_RELATIONS = 120

SYSTEM = """Sei l'analista dei processi di DeliR. Ti do le affermazioni estratte
da un documento nuovo [N#] e quelle gia' estratte da altri documenti dello
stesso processo [E#], ognuna con il documento da cui viene.

Trova le coppie (una nuova, una gia' presente) che parlano dello STESSO fatto
del processo: la stessa attivita', regola, soglia, ruolo, sistema o tempo.

Per ogni coppia:
- `relation` = "same" se dicono la stessa cosa, anche con parole diverse;
  "diverge" se dicono cose diverse sullo stesso fatto.
- Per "diverge", `divergence_type`:
  - "incompatible": non possono essere vere entrambe;
  - "formalization_difference": stessa sostanza, una e' piu' formale o precisa;
  - "scope_difference": valgono per ambiti diversi (reparti, sedi, casi);
  - "knowledge_gap": una delle due dichiara di non sapere;
  - "complementary": si completano, non si escludono;
  - "tension_to_explore": attrito da approfondire, non ancora un conflitto.
- `new_scope` / `existing_scope`: l'ambito che l'affermazione dichiara
  (un reparto, una sede, un tipo di caso), vuoto se non ne dichiara.
- `unknown_side`: "new" o "existing" se quell'affermazione dichiara di non
  sapere, altrimenti "none".
- `explanation`: una frase in italiano che dice in cosa sono uguali o diverse.

Non accoppiare affermazioni che parlano di fatti diversi solo perche' usano
parole simili. Se nessuna coppia parla dello stesso fatto, lista vuota.
"""

DivergenceDeclared = Literal[
    "incompatible",
    "formalization_difference",
    "scope_difference",
    "knowledge_gap",
    "complementary",
    "tension_to_explore",
]


class _Pair(BaseModel):
    new: int = Field(description="Il numero [N#] dell'affermazione nuova.")
    existing: int = Field(description="Il numero [E#] dell'affermazione gia' presente.")
    relation: Literal["same", "diverge"]
    divergence_type: DivergenceDeclared = Field(
        default="tension_to_explore", description="Solo per diverge."
    )
    new_scope: str = ""
    existing_scope: str = ""
    unknown_side: Literal["none", "new", "existing"] = "none"
    explanation: str = Field(description="Una frase: in cosa sono uguali o diverse.")


class Reconciliation(BaseModel):
    pairs: list[_Pair] = Field(default_factory=list, max_length=MAX_RELATIONS)


@dataclass(frozen=True)
class ClaimRelation:
    """Due affermazioni di file diversi sullo stesso fatto."""

    claim_id: int
    other_claim_id: int
    # `corroboration`: dicono la stessa cosa. `divergence`: dicono altro.
    kind: Literal["corroboration", "divergence"]
    declared_type: str | None
    divergence_type: str | None
    reasons: tuple[str, ...]
    explanation: str


@dataclass(frozen=True)
class ReconcileResult:
    relations: list[ClaimRelation]
    prompt_version: str
    # Affermazioni gia' presenti rimaste fuori dal confronto per la lunghezza.
    existing_left_out: int
    # Coppie scartate: numeri inesistenti, o ridotte a "una sola fonte".
    discarded: int


@lru_cache(maxsize=1)
def reconcile_prompt_version() -> str:
    """La versione del prompt: template di sistema e schema di risposta (L5)."""
    from backend.llm.prompts import prompt_version

    schema = json.dumps(Reconciliation.model_json_schema(), sort_keys=True)
    return prompt_version("source_reconcile", SYSTEM, schema)


def render_claims(
    new: list[dict[str, Any]], existing: list[dict[str, Any]]
) -> tuple[str, dict[int, dict[str, Any]], dict[int, dict[str, Any]], int]:
    """Le affermazioni come le legge il modello.

    Le nuove entrano tutte (sono al piu' quelle di un file); le presenti fino
    al tetto, nell'ordine in cui arrivano.

    Returns:
        Il testo, le nuove e le presenti mostrate per numero, quante presenti
        sono rimaste fuori.
    """
    shown_new = {position: claim for position, claim in enumerate(new, start=1)}
    lines = ["Documento nuovo:"]
    lines += [f"[N{n}] {claim['statement']}" for n, claim in shown_new.items()]
    lines.append("")
    lines.append("Gia' presenti:")
    used = sum(len(line) + 1 for line in lines)
    shown_existing: dict[int, dict[str, Any]] = {}
    for position, claim in enumerate(existing, start=1):
        line = f"[E{position}] ({claim['source_name']}) {claim['statement']}"
        if used + len(line) > MAX_INPUT_CHARS:
            return "\n".join(lines), shown_new, shown_existing, len(existing) - position + 1
        used += len(line) + 1
        lines.append(line)
        shown_existing[position] = claim
    return "\n".join(lines), shown_new, shown_existing, 0


def _stance(claim: dict[str, Any], *, scope: str, unknown: bool) -> dict[str, Any]:
    # La voce e' il file: due file con lo stesso nome restano due voci.
    return {
        "source_name": claim["source_name"],
        "attributed_to": f"{claim['source_name']} [{claim['source_id']}]",
        "statement": claim["statement"],
        "scope_label": scope,
        "epistemic_status": "declared_unknown" if unknown else "reported",
    }


def reconcile_claims(
    new: list[dict[str, Any]],
    existing: list[dict[str, Any]],
) -> ReconcileResult:
    """Confronta le affermazioni di un file con quelle degli altri file.

    Args:
        new: Le affermazioni del file appena estratto: `id`, `statement`,
            `source_id`, `source_name`.
        existing: Quelle degli altri file confermati, stesse chiavi.

    Raises:
        OperationNotOpen: Se il chiamante non ha aperto un'operazione (L2).
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    version = reconcile_prompt_version()
    if not new or not existing:
        return ReconcileResult(relations=[], prompt_version=version, existing_left_out=0, discarded=0)

    rendered, shown_new, shown_existing, left_out = render_claims(new, existing)
    result: Reconciliation = llm_run(
        task=LlmTask.SOURCE_RECONCILE,
        messages=[SystemMessage(content=SYSTEM), HumanMessage(content=rendered)],
        output=Reconciliation,
        input_characters=len(rendered),
        prompt_version=version,
    )

    relations: list[ClaimRelation] = []
    seen: set[tuple[int, int]] = set()
    discarded = 0
    for pair in result.pairs:
        mine, theirs = shown_new.get(pair.new), shown_existing.get(pair.existing)
        if mine is None or theirs is None or mine["source_id"] == theirs["source_id"]:
            discarded += 1
            continue
        key = (int(mine["id"]), int(theirs["id"]))
        if key in seen:
            continue
        seen.add(key)
        explanation = pair.explanation.strip()
        if pair.relation == "same":
            relations.append(
                ClaimRelation(key[0], key[1], "corroboration", None, None, (), explanation)
            )
            continue
        verdict = classify_divergence(
            pair.divergence_type,
            [
                _stance(mine, scope=pair.new_scope, unknown=pair.unknown_side == "new"),
                _stance(theirs, scope=pair.existing_scope, unknown=pair.unknown_side == "existing"),
            ],
        )
        if verdict.effective == "single_source_uncertainty":
            discarded += 1
            continue
        relations.append(
            ClaimRelation(
                key[0], key[1], "divergence", verdict.declared, verdict.effective,
                verdict.reasons, explanation,
            )
        )
    return ReconcileResult(
        relations=relations, prompt_version=version, existing_left_out=left_out, discarded=discarded
    )
