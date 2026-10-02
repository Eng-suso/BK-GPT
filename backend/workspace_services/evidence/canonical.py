"""Rappresentazione canonica di una fonte: il livello Evidence Bucket.

Tra il file com'e' arrivato (Source Bucket, immutabile, identificato dal suo
`content_hash`) e qualunque lettura fatta da un modello c'e' questo livello:
porzioni precise della fonte, ognuna con un'ancora alla posizione originale.
Una cella `Ordini!B7`, un paragrafo, una slide, un intervallo di tempo
nell'audio. Lo producono solo parser deterministici: nessun modello decide
cosa c'e' scritto in una fonte, al massimo cosa significa, e quel giudizio
deve poter citare l'ancora da cui parte.

Il formato e' lo stesso per ogni tipo di file, cosi' i livelli sopra (semantic,
reconciliation) non sanno da quale parser arriva un'evidenza.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal

CANONICAL_SCHEMA_VERSION = 1

# `partial`: una parte della fonte non e' stata acquisita, e la fonte lo dice.
# `info`: nulla e' andato perso, ma chi legge deve saperlo (es. valori di
# formule che puntano a file esterni, salvati come erano all'ultimo calcolo).
IssueSeverity = Literal["partial", "info"]


@dataclass(frozen=True)
class Anchor:
    """Dove sta un'evidenza nella fonte originale.

    `ref` e' la forma leggibile e univoca nella fonte (`Ordini!B7`); `locator`
    ne porta le parti strutturate per chi deve ritrovarla senza interpretare
    una stringa (`{"sheet": "Ordini", "row": 7, "column": 2}`).
    """

    kind: str
    ref: str
    locator: dict[str, Any]


@dataclass(frozen=True)
class EvidenceSegment:
    anchor: Anchor
    # Come la fonte lo mostra: e' il testo che un'affermazione puo' citare.
    text: str
    value_type: str
    # Il valore tipato (numero, data ISO, booleano...), quando esiste.
    value: Any = None
    attributes: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AcquisitionIssue:
    code: str
    severity: IssueSeverity
    message: str
    ref: str | None = None


@dataclass(frozen=True)
class CanonicalSource:
    format: str
    parser: str
    segments: tuple[EvidenceSegment, ...]
    structure: dict[str, Any]
    issues: tuple[AcquisitionIssue, ...] = ()
    schema_version: int = CANONICAL_SCHEMA_VERSION

    @property
    def status(self) -> Literal["complete", "partial"]:
        """`partial` quando una parte della fonte non e' stata acquisita."""
        return "partial" if any(issue.severity == "partial" for issue in self.issues) else "complete"

    def segment(self, ref: str) -> EvidenceSegment | None:
        return next((item for item in self.segments if item.anchor.ref == ref), None)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "format": self.format,
            "parser": self.parser,
            "status": self.status,
            "structure": self.structure,
            "issues": [
                {"code": issue.code, "severity": issue.severity, "message": issue.message, "ref": issue.ref}
                for issue in self.issues
            ],
            "segments": [
                {
                    "anchor": {
                        "kind": segment.anchor.kind,
                        "ref": segment.anchor.ref,
                        "locator": segment.anchor.locator,
                    },
                    "text": segment.text,
                    "value_type": segment.value_type,
                    "value": segment.value,
                    "attributes": segment.attributes,
                }
                for segment in self.segments
            ],
        }
