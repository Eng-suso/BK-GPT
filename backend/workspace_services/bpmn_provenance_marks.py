"""Il disegno dice quali elementi vengono dalle fonti e quali no.

Il rapporto di provenance (`agents/plan_provenance.py`) sa, elemento per
elemento, se il piano regge sulle interviste o e' un'inferenza. Tenerlo solo nel
rapporto significa che chi guarda il canvas - il consulente, e poi il cliente -
vede un passaggio inventato disegnato esattamente come uno che tre persone hanno
descritto. Qui l'esito entra nel BPMN, come attributo dell'elemento.

Un attributo di estensione (`delir:provenance`) e non un'annotazione visibile:
il canvas resta una vista operativa BPMN 2.0 valida, gli strumenti che non
conoscono l'estensione la ignorano, e chi la conosce - l'editor di DeliR - puo'
mostrare la differenza senza sporcare il diagramma.

Il legame fra elemento del piano e nodo disegnato e' quello che il compilatore
scrive gia' nella documentazione di ogni nodo (`DeliR traceability`, con i
`source_refs`): nessuna seconda mappa da tenere allineata.
"""

from __future__ import annotations

import json
import xml.etree.ElementTree as ET

from backend.workspace_services.bpmn_canvas_edit import BPMN_NS

DELIR_NS = "https://delir.app/schema/bpmn/provenance"
ET.register_namespace("delir", DELIR_NS)

PROVENANCE_ATTRIBUTE = f"{{{DELIR_NS}}}provenance"

_TRACEABILITY_MARKER = "DeliR traceability:"

# Dal piu' debole al piu' forte. Un nodo che rappresenta piu' elementi del piano
# - un compito di recupero legato a un passaggio e a un'eccezione - vale quanto
# il suo elemento meno provato: dichiararlo verificato perche' meta' di cio' che
# rappresenta lo e' sarebbe una promozione.
_STRENGTH = {"unverified": 0, "label_grounded": 1, "confirmed": 2, "paraphrased": 2, "verified": 3}


def _source_refs(element: ET.Element) -> list[str]:
    documentation = element.find(f"{{{BPMN_NS}}}documentation")
    text = documentation.text if documentation is not None else ""
    if not text or _TRACEABILITY_MARKER not in text:
        return []
    payload = text.split(_TRACEABILITY_MARKER, 1)[1].strip()
    try:
        refs = json.loads(payload).get("source_refs") or []
    except (json.JSONDecodeError, AttributeError):
        return []
    return [str(ref) for ref in refs if ref]


def mark_provenance(xml: str, statuses: dict[str, str]) -> tuple[str, dict[str, int]]:
    """Scrive su ogni nodo tracciato l'esito della verifica sulle fonti.

    Args:
        xml: Il BPMN compilato dal piano.
        statuses: L'esito per riferimento di tracciabilita' (`steps:id` ->
            `verified`), dal rapporto di provenance.

    Returns:
        L'XML con gli attributi e quanti nodi hanno ricevuto ciascun esito. Un
        nodo senza riferimenti tracciati - lo start sintetico, un gateway di
        ricongiungimento - resta senza attributo: non c'e' un'affermazione di
        cui chiedere la prova.
    """
    if not statuses:
        return xml, {}

    root = ET.fromstring(xml.strip())
    counts: dict[str, int] = {}
    for element in root.iter():
        refs = [ref for ref in _source_refs(element) if ref in statuses]
        if not refs:
            continue
        weakest = min((statuses[ref] for ref in refs), key=lambda value: _STRENGTH.get(value, 0))
        element.set(PROVENANCE_ATTRIBUTE, weakest)
        counts[weakest] = counts.get(weakest, 0) + 1

    return ET.tostring(root, encoding="unicode"), counts
