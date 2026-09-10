"""Una scrittura e' avvenuta quando si rilegge, non quando si e' chiamato il writer.

L'agente diceva "ho aggiornato la review sulla base delle evidenze" e la review
a schermo restava a zero attori; diceva "il canvas e' stato aggiornato e
verificato" avendo prodotto start ed end. In entrambi i casi la frase non era una
bugia del modello: era il runtime che dichiarava successo sulla base
dell'*intenzione* di scrivere. Il writer non aveva sollevato eccezioni, quindi il
turno si chiudeva bene.

Qui la sequenza e' write -> persistence -> read-after-write -> success, e il
terzo passo non e' facoltativo. Se cio' che torna dal database non contiene cio'
che si e' scritto, l'operazione non e' riuscita: alza `PersistenceVerificationError`
e chi sta sopra deve raccontare un fallimento, non un completamento.

Le funzioni qui rileggono dal database, mai dallo stato del grafo: uno stato che
si verifica da solo verifica di aver avuto l'intenzione giusta.
"""

from __future__ import annotations

from backend import workspace_database
from backend.workspace_services.bpmn_canvas_edit import list_bpmn_elements


class PersistenceVerificationError(RuntimeError):
    """Il persistito non contiene cio' che l'operazione dichiara di aver scritto."""


def _plan_content_counts(understanding: dict | None) -> dict[str, int]:
    understanding = understanding or {}
    return {
        "actors": len(understanding.get("actors") or []),
        "participants": len(understanding.get("participants") or []),
        "steps": len(understanding.get("steps") or []),
        "decisions": len(understanding.get("decisions") or []),
    }


def verify_review_persisted(
    bpmn_model_id: str,
    *,
    expect_plan_content: bool = True,
    minimum_version: int | None = None,
) -> dict:
    """Rilegge la review e verifica che contenga davvero un piano.

    Args:
        bpmn_model_id: Il modello a cui la review appartiene.
        expect_plan_content: Se la review debba contenere attori, partecipanti o
            attivita'. Falso solo per una review che dichiara esplicitamente di
            non avere ancora contenuto.
        minimum_version: La versione che la scrittura doveva raggiungere. Serve
            a distinguere "salvata" da "salvata sopra la stessa versione di
            prima", che e' il modo silenzioso in cui una scrittura sparisce.

    Returns:
        La review riletta dal database.

    Raises:
        PersistenceVerificationError: Se la review non esiste, e' indietro di
            versione, o e' vuota mentre doveva contenere un piano.
    """
    review = workspace_database.get_bpmn_review(bpmn_model_id, include_approved=True)
    if review is None:
        raise PersistenceVerificationError(
            f"Review non ritrovata dopo la scrittura per il modello {bpmn_model_id}: "
            "l'operazione non e' stata persistita."
        )

    version = int(review.get("version") or 0)
    if minimum_version is not None and version < minimum_version:
        raise PersistenceVerificationError(
            f"La review riletta e' alla versione {version}, attesa almeno "
            f"{minimum_version}: la scrittura non e' arrivata al database."
        )

    if expect_plan_content:
        counts = _plan_content_counts(review.get("process_understanding"))
        if not (counts["actors"] or counts["participants"] or counts["steps"]):
            raise PersistenceVerificationError(
                "La review persistita non contiene attori, partecipanti ne' "
                f"attivita' (versione {version}): non c'e' un piano da dichiarare "
                "aggiornato."
            )

    return review


def bpmn_content_signature(xml: str) -> dict:
    """Cosa c'e' davvero dentro un BPMN, in una forma confrontabile.

    Non il testo del documento: due serializzazioni della stessa topologia
    differiscono per spazi e ordine degli attributi, e confrontare stringhe
    farebbe fallire scritture riuscite. Contano gli elementi e i loro nomi.
    """
    elements = list_bpmn_elements(xml or "")
    return {
        "element_ids": sorted(
            str(item.get("id") or "") for item in elements if item.get("id")
        ),
        "element_names": sorted(
            " ".join(str(item.get("name") or "").split()).casefold()
            for item in elements
            if str(item.get("name") or "").strip()
        ),
        "element_count": len(elements),
    }


def verify_bpmn_model_persisted(bpmn_model_id: str, expected_xml: str) -> dict:
    """Rilegge il modello salvato e verifica che sia quello che si e' scritto.

    Args:
        bpmn_model_id: Il modello.
        expected_xml: L'XML che l'operazione dichiara di aver salvato.

    Returns:
        Il modello riletto dal database.

    Raises:
        PersistenceVerificationError: Se il modello non esiste, e' vuoto, o la
            topologia riletta non coincide con quella scritta.
    """
    model = workspace_database.get_bpmn_model(bpmn_model_id)
    if model is None:
        raise PersistenceVerificationError(
            f"Modello BPMN non ritrovato dopo il salvataggio: {bpmn_model_id}."
        )

    saved_xml = str(model.get("xml") or "")
    if not saved_xml.strip():
        raise PersistenceVerificationError(
            f"Il modello {bpmn_model_id} risulta salvato ma rileggendolo e' vuoto."
        )

    try:
        expected = bpmn_content_signature(expected_xml)
        actual = bpmn_content_signature(saved_xml)
    except Exception as exc:  # noqa: BLE001 - non leggibile e' comunque non verificato
        raise PersistenceVerificationError(
            f"Il modello {bpmn_model_id} non e' rileggibile dopo il salvataggio: {exc}"
        ) from exc

    if expected["element_ids"] != actual["element_ids"]:
        missing = sorted(set(expected["element_ids"]) - set(actual["element_ids"]))
        extra = sorted(set(actual["element_ids"]) - set(expected["element_ids"]))
        raise PersistenceVerificationError(
            "Il canvas riletto non coincide con quello scritto "
            f"(mancano {len(missing)} elementi, ne compaiono {len(extra)} non attesi): "
            "l'operazione non e' completata."
        )

    return model
