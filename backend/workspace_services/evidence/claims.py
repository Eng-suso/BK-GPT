"""Le affermazioni di un file caricato, ognuna legata alla porzione da cui viene (P1.12).

E' il Semantic Layer della pipeline di ingestione: sopra l'Evidence Bucket,
dove le porzioni hanno gia' un'ancora (`Ordini!B7`, `#/texts/12`), un modello
legge e dice cosa il documento afferma. La regola e' una: **ogni affermazione
cita una porzione**, e senza porzione non esiste.

Il modello vede le porzioni numerate (`[S3]`) e per ogni affermazione risponde
con il numero della porzione e le parole che la sostengono. Il codice, non il
modello, decide cosa tenere:

- un numero che non corrisponde a nessuna porzione mostrata: l'affermazione si
  scarta, perche' citerebbe il vuoto;
- una citazione che non si ritrova parola per parola nella porzione: resta,
  marcata `quote_verified = False`. E' un dato da guardare, non un errore.

Uso:
    from backend.workspace_services.evidence.claims import extract_claims
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from typing import Any

from pydantic import BaseModel, Field

from backend.llm import LlmTask
from backend.llm import run as llm_run
from backend.memory.provenance import exact_span

# Una porzione lunga (una tabella intera, un paragrafo fiume) si tronca: per
# capire cosa afferma bastano le prime righe, e il resto costerebbe token senza
# cambiare l'affermazione. Il documento intero ha un tetto, e oltre si dice.
MAX_SEGMENT_CHARS = 1_200
MAX_INPUT_CHARS = 60_000
MAX_CLAIMS = 60

SYSTEM = """Sei l'analista dei processi di DeliR. Ti do le porzioni di un documento
di un cliente, ognuna con il suo numero [S#] e la sua posizione nel documento.

Estrai le affermazioni che il documento fa su come si lavora: chi fa cosa,
quando, con quali regole, soglie, approvazioni, sistemi, tempi e problemi.

Regole:
- Ogni affermazione e' una frase sola, in italiano, autosufficiente: si capisce
  senza leggere il documento.
- Ogni affermazione cita UNA porzione: il suo numero in `segment`.
- In `quote` copia, parola per parola, il passaggio della porzione che la
  sostiene. Non riassumere e non correggere la citazione.
- Non inventare e non dedurre oltre il testo. Se una porzione non dice niente
  su come si lavora (un indice, un'intestazione, un numero di pagina), saltala.
- Se il documento non afferma niente sul lavoro, restituisci una lista vuota.
"""


class _ExtractedClaim(BaseModel):
    statement: str = Field(description="L'affermazione, una frase autosufficiente.")
    segment: int = Field(description="Il numero [S#] della porzione che la sostiene.")
    quote: str = Field(description="Il passaggio della porzione, copiato parola per parola.")


class ClaimExtraction(BaseModel):
    claims: list[_ExtractedClaim] = Field(default_factory=list, max_length=MAX_CLAIMS)


@dataclass(frozen=True)
class AnchoredClaim:
    statement: str
    segment_ordinal: int
    anchor_ref: str
    quote: str
    quote_verified: bool


@dataclass(frozen=True)
class ClaimsResult:
    claims: list[AnchoredClaim]
    prompt_version: str
    # Porzioni rimaste fuori perche' il documento superava il tetto.
    segments_left_out: int
    # Affermazioni scartate perche' citavano una porzione inesistente.
    discarded: int


@lru_cache(maxsize=1)
def claims_prompt_version() -> str:
    """La versione del prompt: template di sistema e schema di risposta (L5)."""
    from backend.llm.prompts import prompt_version

    schema = json.dumps(ClaimExtraction.model_json_schema(), sort_keys=True)
    return prompt_version("source_claims", SYSTEM, schema)


def render_segments(segments: list[dict[str, Any]]) -> tuple[str, dict[int, dict[str, Any]], int]:
    """Le porzioni come le legge il modello, e quelle effettivamente mostrate.

    Returns:
        Il testo, le porzioni mostrate per numero, quante ne sono rimaste fuori.
    """
    shown: dict[int, dict[str, Any]] = {}
    lines: list[str] = []
    used = 0
    readable = [segment for segment in segments if str(segment.get("text") or "").strip()]
    for position, segment in enumerate(readable):
        clipped = str(segment.get("text") or "").strip()[:MAX_SEGMENT_CHARS]
        line = f"[S{segment['ordinal']}] ({segment.get('ref') or segment.get('anchor_ref')}) {clipped}"
        if used + len(line) > MAX_INPUT_CHARS:
            # Si smette qui: le porzioni mostrate restano un tratto continuo del
            # documento, senza buchi che il modello non saprebbe di avere.
            return "\n".join(lines), shown, len(readable) - position
        used += len(line) + 1
        lines.append(line)
        shown[int(segment["ordinal"])] = segment
    return "\n".join(lines), shown, 0


def extract_claims(
    segments: list[dict[str, Any]],
    *,
    source_name: str,
) -> ClaimsResult:
    """Chiede al modello le affermazioni e tiene solo quelle ancorate.

    Args:
        segments: Le porzioni della fonte, come `list_evidence_segments`.
        source_name: Il nome del file, per il contesto del modello.

    Raises:
        OperationNotOpen: Se il chiamante non ha aperto un'operazione (L2).
    """
    from langchain_core.messages import HumanMessage, SystemMessage

    version = claims_prompt_version()
    rendered, shown, left_out = render_segments(segments)
    if not shown:
        return ClaimsResult(claims=[], prompt_version=version, segments_left_out=left_out, discarded=0)

    user = f"Documento: {source_name}\n\nPorzioni:\n{rendered}"
    result: ClaimExtraction = llm_run(
        task=LlmTask.SOURCE_CLAIMS,
        messages=[SystemMessage(content=SYSTEM), HumanMessage(content=user)],
        output=ClaimExtraction,
        input_characters=len(user),
        prompt_version=version,
    )

    claims: list[AnchoredClaim] = []
    seen: set[str] = set()
    discarded = 0
    for item in result.claims:
        statement = item.statement.strip()
        segment = shown.get(item.segment)
        if segment is None or not statement:
            discarded += 1
            continue
        key = statement.casefold()
        if key in seen:
            continue
        seen.add(key)
        text = str(segment.get("text") or "")
        # La citazione come sta scritta nella porzione, non come e' stata
        # ricopiata: e' questa la prova.
        grounded = exact_span(item.quote, text) if item.quote.strip() else ""
        claims.append(
            AnchoredClaim(
                statement=statement,
                segment_ordinal=int(segment["ordinal"]),
                anchor_ref=str(segment.get("ref") or segment.get("anchor_ref") or ""),
                quote=grounded or item.quote.strip(),
                quote_verified=bool(grounded),
            )
        )
    return ClaimsResult(claims=claims, prompt_version=version, segments_left_out=left_out, discarded=discarded)
