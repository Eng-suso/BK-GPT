"""Il testo integrale di una fonte, non la nota che la riassume.

Il pannello Fonti mostrava per ogni fonte il solo campo `meta`: una nota di
poche righe, troncata a 240 caratteri quando l'evidenza arrivava dalla chat.
Chi apre una fonte pero' non vuole il sommario - vuole leggere l'intervista, e
per verificare un'affermazione ha bisogno delle parole originali, non
dell'etichetta.

Il testo grezzo esiste gia': lo tiene la memoria episodica
(`episodic_store`), che lo salva insieme all'episodio quando l'agente registra
un'intervista. Manca il ponte. Il legame passa da (progetto, processo, titolo):
`_register_evidence_source` crea la fonte con lo stesso titolo dell'episodio, e
`ensure_project_source` deduplica per nome dentro il processo, quindi
l'accoppiamento e' univoco. Nessuna colonna nuova sul workspace: il giorno in
cui la fonte portera' l'`episode_id`, questa risoluzione diventa un lookup
diretto e il resto non cambia.
"""

from __future__ import annotations

import json
import logging

from backend import workspace_database
from backend.memory import provenance
from backend.memory.episodic import episodic_store

logger = logging.getLogger(__name__)


def _matching_episode(project_id: str, process_id: str | None, name: str) -> dict | None:
    """L'episodio che ha dato origine a questa fonte, se c'e'.

    Args:
        project_id: Progetto della fonte.
        process_id: Processo della fonte, quando l'evidenza e' di un processo.
        name: Nome della fonte come il consulente lo legge.

    Returns:
        L'episodio corrispondente, o ``None`` per una fonte che non viene dalla
        chat (un documento caricato a mano, per esempio).
    """
    wanted = provenance.normalize(name)
    if not wanted:
        return None
    try:
        episodes = episodic_store.list_episode_memory(
            project=project_id,
            process_id=process_id,
            status="any",
            limit=200,
        )
    except Exception:  # noqa: BLE001 — una fonte senza testo resta apribile
        logger.warning("episodi non leggibili per il progetto %s", project_id, exc_info=True)
        return None
    for episode in episodes:
        if provenance.normalize(episode.get("title")) == wanted:
            return episode
    return None


def _people(value: object) -> list[str]:
    """I presenti, comunque siano stati salvati.

    L'episodio li tiene come JSON in una colonna di testo; le evidenze piu'
    vecchie li tengono come elenco separato da virgole. Un `["Paolo"]` mostrato
    cosi' com'e' nel pannello sarebbe il formato di serializzazione stampato in
    faccia a chi legge.
    """
    if isinstance(value, str) and value.strip().startswith("["):
        try:
            decoded = json.loads(value)
        except json.JSONDecodeError:
            decoded = value
        if isinstance(decoded, list):
            return [" ".join(str(item).split()) for item in decoded if str(item).strip()]
        value = decoded
    return episodic_store.normalize_list(value if isinstance(value, (str, list)) else None)


def source_document(source_id: str) -> dict | None:
    """La fonte con la sua sintesi e il suo testo integrale.

    Args:
        source_id: Id della fonte, non affidabile.

    Returns:
        Il documento della fonte, o ``None`` se la fonte non esiste nel tenant
        corrente. Una fonte senza testo grezzo torna comunque, con
        ``has_content=False``: il pannello deve poterlo dire invece di mostrare
        una sezione vuota.

    Sola lettura.
    """
    source = workspace_database.get_project_source(source_id)
    if source is None:
        return None

    episode = _matching_episode(
        source["project_id"], source.get("process_id"), source["name"]
    )
    detail = (
        episodic_store.get_episode_memory(
            episode_id=episode["episode_id"], include_source_text=True
        )
        if episode
        else None
    ) or {}
    content = str(detail.get("source_text") or "").strip()

    return {
        "id": source["id"],
        "project_id": source["project_id"],
        "process_id": source.get("process_id"),
        "name": source["name"],
        "type": source["type"],
        # La sintesi dell'episodio quando c'e', altrimenti la nota della fonte:
        # sono la stessa cosa vista da due lati, e la nota e' troncata.
        "summary": str(detail.get("summary") or source.get("meta") or "").strip(),
        "participants": _people(detail.get("participants")),
        "occurred_at": detail.get("occurred_at"),
        "episode_id": detail.get("episode_id"),
        "content": content,
        "has_content": bool(content),
    }
