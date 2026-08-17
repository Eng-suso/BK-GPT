from __future__ import annotations

import json
import re
from functools import lru_cache
from typing import Literal

from langchain_core.messages import HumanMessage, SystemMessage
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from backend.settings import settings


class ProcessActor(BaseModel):
    id: str
    label: str
    kind: Literal["person", "role", "team", "organization", "system", "external_party"]
    source_evidence: list[str] = Field(default_factory=list)


class ProcessEvent(BaseModel):
    id: str
    label: str
    type: Literal["start", "end", "timer", "message", "exception"]
    timing: str | None = None
    source_evidence: list[str] = Field(default_factory=list)


class ProcessStep(BaseModel):
    id: str
    label: str
    description: str | None = None
    actor_ids: list[str] = Field(default_factory=list)
    type: Literal["user_task", "manual_task", "service_task", "subprocess"] = "user_task"
    inputs: list[str] = Field(default_factory=list)
    outputs: list[str] = Field(default_factory=list)
    source_evidence: list[str] = Field(default_factory=list)


class ProcessHandoff(BaseModel):
    id: str
    from_actor_id: str | None = None
    to_actor_id: str | None = None
    artifact: str | None = None
    trigger: str | None = None
    source_evidence: list[str] = Field(default_factory=list)


class ProcessDataObject(BaseModel):
    id: str
    label: str
    kind: Literal["document", "form", "record", "payment", "receipt", "notification", "data", "other"] = "data"
    source_evidence: list[str] = Field(default_factory=list)


class ProcessDecision(BaseModel):
    id: str
    label: str
    question: str | None = None
    outcomes: list[str] = Field(default_factory=list)
    source_evidence: list[str] = Field(default_factory=list)


class ProcessInputOutput(BaseModel):
    step: str
    input: list[str] = Field(default_factory=list)
    output: list[str] = Field(default_factory=list)


class ProcessExceptionPath(BaseModel):
    id: str
    label: str
    trigger: str | None = None
    handling: str | None = None
    is_defined: bool = True


class ProcessUnknown(BaseModel):
    question: str
    affects: str
    severity: Literal["blocking", "non_blocking", "optional_extension"] = "non_blocking"


class ProcessBoundaries(BaseModel):
    trigger: str | None = None
    start_event: str | None = None
    success_end: str | None = None
    failure_ends: list[str] = Field(default_factory=list)
    in_scope: list[str] = Field(default_factory=list)
    out_of_scope: list[str] = Field(default_factory=list)


class ProcessPath(BaseModel):
    id: str
    label: str
    trigger_or_condition: str | None = None
    sequence: list[str] = Field(default_factory=list)
    rejoins_at: str | None = None
    ends_at: str | None = None
    is_confirmed: bool = True


class ProcessLoop(BaseModel):
    id: str
    label: str
    repeated_steps: list[str] = Field(default_factory=list)
    condition: str | None = None
    exit_condition: str | None = None


class ActorRelationship(BaseModel):
    actor_id: str
    organization_id: str | None = None
    relationship: Literal["internal_role", "external_participant", "system", "black_box"]
    bpmn_pool_candidate: bool = False
    bpmn_lane_candidate: bool = False


class BpmnModelingHint(BaseModel):
    element: str
    hint: str
    confidence: Literal["low", "medium", "high"] = "medium"


class ProcessConfidence(BaseModel):
    overall: Literal["low", "medium", "high"]
    weak_points: list[str] = Field(default_factory=list)


class ProcessUnderstanding(BaseModel):
    schema_version: str = "process_understanding.v1"
    language: Literal["it", "en"] = "it"
    title: str
    objective: str | None = None
    scope: str | None = None
    actors: list[ProcessActor] = Field(default_factory=list)
    events: list[ProcessEvent] = Field(default_factory=list)
    steps: list[ProcessStep] = Field(default_factory=list)
    sequence: list[str] = Field(default_factory=list)
    decisions: list[ProcessDecision] = Field(default_factory=list)
    handoffs: list[ProcessHandoff] = Field(default_factory=list)
    data_objects: list[ProcessDataObject] = Field(default_factory=list)
    input_outputs: list[ProcessInputOutput] = Field(default_factory=list)
    exceptions: list[ProcessExceptionPath] = Field(default_factory=list)
    business_rules: list[str] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unknowns: list[ProcessUnknown] = Field(default_factory=list)
    narrative_focus: list[str] = Field(default_factory=list)
    boundaries: ProcessBoundaries | None = None
    main_success_path: list[str] = Field(default_factory=list)
    alternative_paths: list[ProcessPath] = Field(default_factory=list)
    loops: list[ProcessLoop] = Field(default_factory=list)
    actor_relationships: list[ActorRelationship] = Field(default_factory=list)
    bpmn_modeling_hints: list[BpmnModelingHint] = Field(default_factory=list)
    confidence: ProcessConfidence | None = None


def build_process_understanding(title: str, source_text: str) -> ProcessUnderstanding:
    if settings.openai_api_key:
        try:
            return _understanding_llm().invoke(
                [
                    SystemMessage(content=_PROCESS_UNDERSTANDING_PROMPT),
                    HumanMessage(
                        content=json.dumps(
                            {
                                "process_title": title,
                                "raw_notes": source_text,
                            },
                            ensure_ascii=False,
                        )
                    ),
                ]
            )
        except Exception as exc:
            fallback = build_fallback_understanding(title, source_text)
            fallback.assumptions.append(f"Estrazione LLM non riuscita; usata estrazione locale: {exc}")
            return fallback

    return build_fallback_understanding(title, source_text)


def build_fallback_understanding(title: str, source_text: str) -> ProcessUnderstanding:
    steps = _extract_steps(source_text)
    actors = _extract_actors(source_text)
    decisions = _extract_decisions(source_text)
    data_objects = _extract_data_objects(source_text)
    exceptions = _extract_exceptions(source_text)
    start_label = f"Avvio {title}"
    end_label = f"{title} completato"

    return ProcessUnderstanding(
        title=title,
        objective=None,
        scope="Bozza AS-IS derivata dalle note disponibili.",
        actors=actors,
        events=[
            ProcessEvent(id="StartEvent_1", label=start_label, type="start"),
            ProcessEvent(id="EndEvent_1", label=end_label, type="end"),
        ],
        steps=steps,
        sequence=[step.id for step in steps],
        decisions=decisions,
        data_objects=data_objects,
        input_outputs=[
            ProcessInputOutput(step=step.label, input=step.inputs, output=step.outputs)
            for step in steps
            if step.inputs or step.outputs
        ],
        exceptions=exceptions,
        unknowns=_extract_unknowns(source_text, steps, decisions),
        boundaries=ProcessBoundaries(start_event=start_label, success_end=end_label),
        main_success_path=[step.id for step in steps],
        alternative_paths=[
            ProcessPath(
                id=f"AltPath_{index}",
                label=item.label,
                trigger_or_condition=item.trigger,
                is_confirmed=item.is_defined,
            )
            for index, item in enumerate(exceptions, start=1)
        ],
        confidence=ProcessConfidence(
            overall="medium" if len(steps) >= 3 else "low",
            weak_points=["Estrazione locale senza interpretazione semantica completa."],
        ),
    )


def render_process_review(process: ProcessUnderstanding) -> str:
    lines = [
        f"## {process.title}",
        "",
        process.scope or "Review AS-IS prima della generazione BPMN.",
        "",
        "Flusso principale:",
    ]

    step_by_id = {step.id: step for step in process.steps}
    sequence = process.main_success_path or process.sequence or [step.id for step in process.steps]
    for index, step_id in enumerate(sequence, start=1):
        step = step_by_id.get(step_id)
        if step:
            actor = _actor_labels(process, step.actor_ids)
            suffix = f" ({', '.join(actor)})" if actor else ""
            lines.append(f"{index}. {step.label}{suffix}")

    if process.decisions:
        lines.extend(["", "Decisioni/gateway:"])
        for decision in process.decisions:
            outcomes = f" Esiti: {', '.join(decision.outcomes)}." if decision.outcomes else ""
            lines.append(f"- {decision.label}.{outcomes}".replace("..", "."))

    if process.exceptions or process.alternative_paths:
        lines.extend(["", "Eccezioni e percorsi alternativi:"])
        for item in process.exceptions:
            handling = item.handling or "gestione non definita"
            lines.append(f"- {item.label}: {handling}")

    if process.data_objects:
        lines.extend(["", "Documenti/input/output rilevanti:"])
        for item in process.data_objects[:8]:
            lines.append(f"- {item.label}")

    if process.unknowns:
        lines.extend(["", "Domande aperte:"])
        for item in process.unknowns:
            lines.append(f"- {item.question}")

    return "\n".join(lines)


def process_open_questions(process: ProcessUnderstanding) -> list[str]:
    return [item.question for item in process.unknowns if item.question.strip()]


def readiness_from_understanding(process: ProcessUnderstanding) -> int:
    score = 4
    score += min(len(process.steps), 4)
    if process.actors:
        score += 1
    if process.boundaries and process.boundaries.success_end:
        score += 1
    if any(item.severity == "blocking" for item in process.unknowns):
        score -= 2
    return max(1, min(score, 10))


@lru_cache(maxsize=1)
def _understanding_llm() -> ChatOpenAI:
    kwargs = {
        "api_key": settings.openai_api_key,
        "model": settings.openai_model,
        "temperature": 0,
        "max_tokens": 6000,
        "timeout": settings.model_timeout_seconds,
        "max_retries": settings.model_max_retries,
        "streaming": False,
        "disable_streaming": True,
    }
    if _supports_reasoning_controls(settings.openai_model):
        kwargs["reasoning_effort"] = "medium"
        kwargs["verbosity"] = "low"
    return ChatOpenAI(**kwargs).with_structured_output(ProcessUnderstanding)


def _supports_reasoning_controls(model: str) -> bool:
    return model.lower().startswith(("gpt-5", "o1", "o3", "o4"))


def _safe_id(value: str, prefix: str) -> str:
    clean = re.sub(r"[^A-Za-z0-9_]+", "_", value.strip()).strip("_")
    if not clean:
        clean = prefix
    if not clean[0].isalpha():
        clean = f"{prefix}_{clean}"
    return clean[:64]


def _extract_steps(text: str) -> list[ProcessStep]:
    raw_parts = re.split(r"(?:\r?\n|;|\.|\bpoi\b|\bquindi\b|\bthen\b)", text, flags=re.IGNORECASE)
    steps: list[ProcessStep] = []
    seen: set[str] = set()

    for index, part in enumerate(raw_parts, start=1):
        clean = " ".join(part.strip(" -:\t").split())
        if len(clean) < 3:
            continue
        if clean.lower().startswith(("approva", "approvo", "ok", "genera")):
            continue
        label = clean[:90]
        key = label.casefold()
        if key in seen:
            continue
        seen.add(key)
        steps.append(ProcessStep(id=f"Task_{index}", label=label, source_evidence=[clean]))

    if not steps:
        steps = [
            ProcessStep(id="Task_1", label="Raccogli informazioni"),
            ProcessStep(id="Task_2", label="Valida informazioni"),
            ProcessStep(id="Task_3", label="Concludi processo"),
        ]

    return steps[:12]


def _extract_actors(text: str) -> list[ProcessActor]:
    candidates = [
        ("cliente", "Cliente", "external_party"),
        ("fornitore", "Fornitore", "external_party"),
        ("ufficio acquisti", "Ufficio acquisti", "team"),
        ("amministrazione", "Amministrazione", "team"),
        ("responsabile", "Responsabile", "role"),
        ("manager", "Manager", "role"),
        ("sistema", "Sistema", "system"),
        ("operatore", "Operatore", "role"),
    ]
    actors = []
    normalized = text.lower()
    for raw, label, kind in candidates:
        if raw in normalized:
            actors.append(ProcessActor(id=_safe_id(label, "Actor"), label=label, kind=kind))
    return actors


def _extract_decisions(text: str) -> list[ProcessDecision]:
    decisions = []
    patterns = [
        (r"\bse\b[^.;\n]+", "Decisione condizionale"),
        (r"\b(verifica|controlla|valuta|approva|valid[a-z]*)\b[^.;\n]*", "Verifica esito"),
    ]
    for index, (pattern, fallback) in enumerate(patterns, start=1):
        match = re.search(pattern, text, re.IGNORECASE)
        if match:
            label = " ".join(match.group(0).strip().split())[:80]
            decisions.append(
                ProcessDecision(
                    id=f"Gateway_{index}",
                    label=label or fallback,
                    question=f"{label or fallback}?",
                    outcomes=["Si", "No"],
                    source_evidence=[match.group(0).strip()],
                )
            )
    return decisions[:3]


def _extract_data_objects(text: str) -> list[ProcessDataObject]:
    terms = {
        "ordine": "record",
        "fattura": "document",
        "documento": "document",
        "email": "notification",
        "conferma": "notification",
        "richiesta": "form",
        "pagamento": "payment",
        "ricevuta": "receipt",
        "modulo": "form",
    }
    found = []
    normalized = text.lower()
    for term, kind in terms.items():
        if term in normalized:
            label = term.capitalize()
            found.append(ProcessDataObject(id=_safe_id(label, "Data"), label=label, kind=kind))
    return found


def _extract_exceptions(text: str) -> list[ProcessExceptionPath]:
    exceptions = []
    patterns = ["errore", "manca", "non disponibile", "rifiut", "annulla", "eccezione"]
    normalized = text.lower()
    for index, pattern in enumerate(patterns, start=1):
        if pattern in normalized:
            exceptions.append(
                ProcessExceptionPath(
                    id=f"Exception_{index}",
                    label=f"Gestione {pattern}",
                    trigger=pattern,
                    handling=None,
                    is_defined=False,
                )
            )
    return exceptions


def _extract_unknowns(text: str, steps: list[ProcessStep], decisions: list[ProcessDecision]) -> list[ProcessUnknown]:
    unknowns = []
    if len(steps) < 2:
        unknowns.append(
            ProcessUnknown(
                question="Quali sono almeno due passaggi confermati del processo?",
                affects="Sequenza principale",
                severity="blocking",
            )
        )
    if decisions and not re.search(r"\b(si|no|positivo|negativo|approvato|rifiutato)\b", text, re.IGNORECASE):
        unknowns.append(
            ProcessUnknown(
                question="Quali sono gli esiti della decisione e dove portano?",
                affects="Gateway e percorsi alternativi",
                severity="non_blocking",
            )
        )
    if not re.search(r"\b(fine|termina|conclude|chiude|output|esito|completato)\b", text, re.IGNORECASE):
        unknowns.append(
            ProcessUnknown(
                question="Qual e l'esito finale confermato del processo?",
                affects="Evento finale",
                severity="non_blocking",
            )
        )
    return unknowns


def _actor_labels(process: ProcessUnderstanding, actor_ids: list[str]) -> list[str]:
    by_id = {actor.id: actor.label for actor in process.actors}
    return [by_id[actor_id] for actor_id in actor_ids if actor_id in by_id]


_PROCESS_UNDERSTANDING_PROMPT = """Sei un consulente BPMN senior.

Estrai una ProcessUnderstanding strutturata dalle note grezze del processo.
Usa solo fatti presenti nelle note. Non inventare attori, step, documenti, decisioni, eccezioni o percorsi.

Regole:
- Usa italiano.
- Mantieni le attivita atomiche.
- Estrai attori/ruoli, eventi, step, decisioni/gateway, eccezioni, handoff, documenti, input/output, alternative path, loop, regole, assunzioni e unknowns.
- Usa id XML-safe con lettere, numeri e underscore.
- Metti in unknowns cio che manca; usa blocking solo se impedisce una bozza BPMN minima.
- Se un'eccezione e citata ma la gestione manca, usa is_defined=false.
- Distingui ruoli interni da partecipanti esterni negli actor_relationships.
- Non produrre XML e non rispondere in markdown: restituisci solo lo schema strutturato richiesto.
"""
