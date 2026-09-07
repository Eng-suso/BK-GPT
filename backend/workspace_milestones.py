"""Milestone di progetto: il traguardo *e* se è stato raggiunto.

Una milestone era una riga di testo. Il record diceva quindi cosa era stato
promesso e mai se fosse successo, e la UI compensava inventando lo stato
dall'ordine della lista: la prima voce disegnata come raggiunta, la seconda
come in corso, le altre come future. Un consulente non poteva segnare nulla, e
quello che leggeva non veniva dai dati.

Qui la milestone porta il proprio stato e la data in cui è stata raggiunta. Le
liste di sole stringhe già salvate restano leggibili: si aprono come milestone
ancora da raggiungere.
"""

from datetime import UTC, datetime

MILESTONE_PLANNED = "planned"
MILESTONE_DONE = "done"
MILESTONE_STATUSES = (MILESTONE_PLANNED, MILESTONE_DONE)


def _clean_text(value: object) -> str:
    return " ".join(str(value or "").split())


def normalise_milestone(value: object) -> dict | None:
    """Normalize one milestone entry into its stored shape.

    Args:
        value: Untrusted milestone entry: a plain title, or a mapping with
            ``title``, ``status`` and ``completed_at``.

    Returns:
        dict | None: The milestone as ``{title, status, completed_at}``, or
        ``None`` when the entry carries no title.
    """
    if isinstance(value, dict):
        title = _clean_text(value.get("title") or value.get("name"))
        status = str(value.get("status") or MILESTONE_PLANNED).strip().lower()
        completed_at = value.get("completed_at") or None
    else:
        title = _clean_text(value)
        status = MILESTONE_PLANNED
        completed_at = None

    if not title:
        return None

    if status not in MILESTONE_STATUSES:
        status = MILESTONE_PLANNED

    if status == MILESTONE_DONE:
        # Raggiunta senza data: la data è ora. Il contrario — una data su una
        # milestone non raggiunta — sarebbe una traccia di uno stato che non c'è.
        completed_at = str(completed_at) if completed_at else datetime.now(UTC).isoformat()
    else:
        completed_at = None

    return {"title": title, "status": status, "completed_at": completed_at}


def normalise_milestones(values: list | None) -> list[dict]:
    """Normalize a milestone list, dropping entries without a title.

    Args:
        values: Untrusted milestone entries, as titles or mappings.

    Returns:
        list[dict]: The normalized milestones, in the order received.
    """
    if not values:
        return []

    return [entry for entry in (normalise_milestone(value) for value in values) if entry]


def merge_milestones(stored: list[dict], incoming: list | None) -> list[dict]:
    """Replace the milestone list while keeping the state of entries kept by title.

    The consultant's form and the agent both send milestones as plain titles:
    they edit *what* the project promises, not what has already happened. Taken
    literally that would reset every milestone to "not reached" on each edit, so
    a title that is still in the list keeps the state it already had unless the
    caller states a new one.

    Args:
        stored: The milestones currently persisted for the project.
        incoming: Untrusted replacement list, as titles or mappings.

    Returns:
        list[dict]: The merged milestones, in the order received.
    """
    previous = {entry["title"]: entry for entry in stored}
    merged: list[dict] = []

    for value in incoming or []:
        entry = normalise_milestone(value)
        if entry is None:
            continue

        states_status = isinstance(value, dict) and "status" in value
        known = previous.get(entry["title"])
        if known is not None and not states_status:
            entry = {**entry, "status": known["status"], "completed_at": known["completed_at"]}

        merged.append(entry)

    return merged


def milestones_reached(values: list[dict]) -> int:
    """Count the milestones already reached.

    Args:
        values: Normalized milestones.

    Returns:
        int: How many entries are marked as reached.
    """
    return sum(1 for entry in values if entry["status"] == MILESTONE_DONE)
