import re
from typing import Annotated, Literal

from langchain_core.tools import InjectedToolCallId, tool
from langgraph.types import Command
from pydantic import BaseModel, Field

from backend.graphs.process.tools import process_workspace_payload
from backend.memory import provenance
from backend.memory.episodic import episodic_store
from backend.toolsets.process_memory import (
    extract_process_graph_from_evidence,
    index_process_evidence_graph,
    manage_process_evidence,
)
from backend.toolsets.workspace import enterprise_state_write, enterprise_tool_result


ProcessArea = Literal[
    "scope",
    "actor",
    "activity",
    "decision",
    "handoff",
    "system",
    "data",
    "exception",
    "control",
    "timing",
]


def _jsonable_items(items: list) -> list[dict]:
    return [
        item.model_dump(mode="json") if hasattr(item, "model_dump") else item
        for item in items
    ]


class ProcessClaim(BaseModel):
    """One source's contribution, described honestly enough to be checked.

    You do not declare how well supported a claim is: `support` is counted by
    the runtime from the number of distinct voices on a `topic`. What you own
    is who said it, in which scope, in which epistemic mode, and with which
    exact words.
    """

    claim: str = Field(description="Single process claim extracted from evidence.")
    process_area: ProcessArea = Field(description="Process area described by the claim.")
    source_name: str = Field(description="Source document/interview this claim comes from.")
    attributed_to: str = Field(
        default="",
        description=(
            "Who states it inside that source: person, role or team. Never "
            "attribute to one speaker what another said."
        ),
    )
    topic: str = Field(
        default="",
        description=(
            "The SUBJECT, e.g. 'autorizzazione della spesa'. It groups related "
            "claims. Sharing a subject is not agreeing."
        ),
    )
    assertion: str = Field(
        default="",
        description=(
            "The PROPOSITION asserted, e.g. \"sopra soglia l'ordine passa da "
            "un'autorizzazione\". Corroboration is counted on this - give "
            "identical wording to claims from different sources that really "
            "assert the same thing, and different wording when they do not. "
            "Empty means the claim stands alone."
        ),
    )
    qualifiers: list[str] = Field(
        default_factory=list,
        description=(
            "What THIS source adds on top of the proposition, e.g. \"fornitore "
            "gia' conosciuto\", \"verifica formale prima dell'ordine\". Put here "
            "anything only this source says: it stays attributed to this source "
            "and may not appear in a sentence credited to several."
        ),
    )
    quote: str = Field(
        default="",
        description=(
            "Verbatim words from the source that support this claim. Copy, do "
            "not paraphrase and do not strengthen - the runtime checks the span "
            "occurs in the source text."
        ),
    )
    scope_label: str = Field(
        default="",
        description=(
            "Department, role or context the claim actually covers, e.g. "
            "'Manutenzione'. A statement about one department is not a statement "
            "about the process."
        ),
    )
    scope_level: Literal["stated_scope", "whole_process"] = Field(
        default="stated_scope",
        description="whole_process only when the source explicitly speaks for the whole process.",
    )
    epistemic_status: Literal[
        "reported", "observed", "documented", "inferred", "declared_unknown"
    ] = Field(
        default="reported",
        description=(
            "declared_unknown when the source says it does not know: that is "
            "information about the source, not a gap in the process."
        ),
    )
    confidence: Literal["low", "medium", "high", "unknown"] = Field(description="Evidence confidence.")
    status: Literal["confirmed", "partial", "contradicted", "inferred", "unsupported"] = Field(
        description="Support status for this claim."
    )
    linked_element_hint: str | None = Field(
        default=None,
        description="Optional actor/activity/decision/handoff id or name this claim may map to.",
    )


class ExtractClaimsInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    project_id: str = Field(
        default="",
        description="Current project id. Needed to check the quotes against the stored source.",
    )
    source_name: str = Field(description="Source being processed.")
    claims: list[ProcessClaim] = Field(description="Atomic process claims extracted from the source.")
    extraction_notes: list[str] = Field(default_factory=list, description="Notes about ambiguity or source quality.")


class EvidenceStance(BaseModel):
    """One voice's position on a topic."""

    source_name: str = Field(default="", description="Source holding this position.")
    attributed_to: str = Field(default="", description="Person or role stating it.")
    statement: str = Field(default="", description="What this voice actually says.")
    epistemic_status: Literal[
        "reported", "observed", "documented", "inferred", "declared_unknown"
    ] = Field(default="reported", description="declared_unknown when this voice says it does not know.")
    scope_label: str = Field(default="", description="Department or role this voice speaks for.")
    qualifiers: list[str] = Field(
        default_factory=list,
        description=(
            "What only this voice adds, e.g. \"fornitore gia' conosciuto\". The "
            "runtime checks that none of these ends up inside a sentence "
            "credited to several voices."
        ),
    )


class SynthesisFinding(BaseModel):
    """One conclusion of the synthesis, with the voices that back it.

    Two checkable claims live here. `asserted_support="corroborated"` needs at
    least two distinct voices in `stances`. And `statement`, when it is
    credited to several voices, may only contain what all of them support: put
    what one voice alone adds in that voice's `qualifiers` and say it
    separately. The runtime downgrades both otherwise.
    """

    topic: str = Field(description="Subject this finding is about, matching the claim topics.")
    statement: str = Field(
        description=(
            "What you conclude, in the consultant's words. When several voices "
            "back it, this sentence must contain ONLY the part all of them "
            "support."
        )
    )
    asserted_support: Literal[
        "corroborated", "single_source", "contradicted", "inferred", "declared_unknown"
    ] = Field(
        default="single_source",
        description="corroborated requires two distinct voices in stances.",
    )
    asserted_scope_level: Literal["stated_scope", "whole_process"] = Field(
        default="stated_scope",
        description=(
            "whole_process only when the evidence covers the whole process. Two "
            "people each missing a datum for their own area do not show the "
            "process lacks it."
        ),
    )
    stances: list[EvidenceStance] = Field(
        default_factory=list, description="The sources backing this finding."
    )


class EvidenceSynthesisInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    source_list: list[str] = Field(description="Sources considered in this synthesis.")
    findings: list[SynthesisFinding] = Field(
        default_factory=list,
        description=(
            "The synthesis itself, one entry per topic, each with the voices "
            "behind it. Prefer this over the free-text lists below."
        ),
    )
    confirmed_claims: list[str] = Field(default_factory=list, description="Claims supported well enough to model.")
    hypotheses: list[str] = Field(default_factory=list, description="Claims plausible but not confirmed.")
    contradictions: list[str] = Field(default_factory=list, description="Conflicting claims or source disagreement.")
    open_questions: list[str] = Field(default_factory=list, description="Questions needed before modeling or validation.")
    recommended_next_evidence: list[str] = Field(default_factory=list, description="Sources to collect next.")


class ContradictionInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    operation: Literal["identify", "resolve"] = Field(
        description=(
            "identify: record a newly found contradiction. resolve: record what you "
            "concluded about a contradiction you already recorded."
        )
    )
    divergence_type: Literal[
        "incompatible",
        "scope_difference",
        "formalization_difference",
        "knowledge_gap",
        "complementary",
        "tension_to_explore",
    ] = Field(
        default="tension_to_explore",
        description=(
            "What kind of disagreement this is. incompatible only when both "
            "sides positively assert things that cannot both be true. Use "
            "knowledge_gap when one side declares it does not know, "
            "scope_difference when they speak for different departments, "
            "formalization_difference when it is the same practice at a "
            "different degree of formality. The runtime re-checks this against "
            "the stances and can only weaken it."
        ),
    )
    stances: list[EvidenceStance] = Field(
        default_factory=list,
        description="identify: the positions in play, one per voice. Needed to type the divergence.",
    )
    title: str = Field(description="Short contradiction title, for people to read.")
    contradiction_id: str | None = Field(
        default=None,
        description=(
            "resolve: the contradiction_id that identify returned. Pass it - it is how "
            "the runtime matches a resolution to its contradiction. Without it the id is "
            "re-derived from the title, so a reworded title will not match and the "
            "contradiction stays open."
        ),
    )
    conflicting_claims: list[str] = Field(
        default_factory=list, description="identify: claims that cannot all be true."
    )
    affected_process_area: ProcessArea | None = Field(
        default=None, description="identify: process area affected by the contradiction."
    )
    source_names: list[str] = Field(default_factory=list, description="Sources involved in the contradiction.")
    resolution_needed: str = Field(default="", description="identify: what must be checked to resolve it.")
    severity: Literal["low", "medium", "high", "blocking"] = "medium"
    resolution: Literal["resolved", "not_material", "still_blocking"] | None = Field(
        default=None,
        description=(
            "resolve: your judgment. resolved = the conflict is settled by evidence. "
            "not_material = it stands but does not change the model you are building. "
            "still_blocking = it must be closed before modeling can proceed."
        ),
    )
    rationale: str = Field(
        default="", description="resolve: why this conclusion - what settled it, or why it still blocks."
    )
    supporting_sources: list[str] = Field(
        default_factory=list,
        description="resolve: sources that support clearing the contradiction. Required to clear one.",
    )


class CoverageItem(BaseModel):
    process_area: ProcessArea = Field(description="Process area being assessed.")
    coverage: Literal["none", "weak", "partial", "good"] = Field(description="Evidence coverage level.")
    supporting_sources: list[str] = Field(default_factory=list, description="Sources supporting this area.")
    gaps: list[str] = Field(default_factory=list, description="Missing evidence for this area.")


class EvidenceCoverageInput(BaseModel):
    process_id: str = Field(description="Current process id.")
    coverage_items: list[CoverageItem] = Field(description="Coverage by process area.")
    modeling_blockers: list[str] = Field(default_factory=list, description="Evidence gaps blocking modeling.")


@tool
def get_process_evidence_brief(process_id: str) -> str:
    """
    Read process sources, decisions and current review gaps for evidence
    synthesis. Use before extracting claims or assessing coverage.
    """
    payload = process_workspace_payload(process_id)
    return enterprise_tool_result(
        status="ok",
        action="get_process_evidence_brief",
        entity_type="process_evidence_brief",
        entity_id=process_id,
        summary=f"Evidence brief for {payload['process']['name']}",
        payload={
            "process": payload["process"],
            "sources": payload["sources"],
            "decisions": payload["decisions"],
            "missing_information": payload["review"].get("missing_information") if payload["review"] else [],
        },
    )


def _stored_source_text(project_id: str, process_id: str, source_name: str) -> str:
    """Il testo grezzo della fonte gia' salvata su questo processo.

    Serve a riscontrare le citazioni: senza il testo originale, "questa e' la
    frase che l'ha detto" e' un'affermazione dell'estrattore su se stesso.
    Fuori da un workspace (test unitari, chiamate isolate) torna vuoto e la
    verifica dichiara di non aver potuto riscontrare — non finge di aver
    riscontrato.
    """
    if not project_id or not source_name.strip():
        return ""
    try:
        episodes = episodic_store.list_episode_memory(
            project=project_id, process_id=process_id, status="active", limit=100
        )
    except Exception:  # noqa: BLE001 — l'estrazione non deve fallire per la verifica
        return ""
    wanted = provenance.normalize(source_name)
    for episode in episodes:
        if provenance.normalize(episode.get("title")) != wanted:
            continue
        full = episodic_store.get_episode_memory(
            episode_id=episode["episode_id"], include_source_text=True
        )
        return (full or {}).get("source_text") or ""
    return ""


@tool(args_schema=ExtractClaimsInput)
def extract_process_claims(
    process_id: str,
    source_name: str,
    claims: list[dict],
    project_id: str = "",
    extraction_notes: list[str] | None = None,
    *,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Command:
    """
    Structure atomic process claims from one source.

    Every claim keeps who states it (`attributed_to`), the scope it covers
    (`scope_label`), how the source knows it (`epistemic_status`) and the exact
    words behind it (`quote`). The runtime checks each quote against the stored
    source text and computes the support level by counting distinct voices per
    topic - you do not declare that something is confirmed.
    """
    claim_payload = _jsonable_items(claims)
    source_text = _stored_source_text(project_id, process_id, source_name)

    # La verifica avviene qui, sull'input del modello, non a valle: un claim la
    # cui citazione non compare nel testo e' un claim riformulato, e chi legge
    # deve poterlo distinguere da uno citato.
    unverified: list[str] = []
    for claim in claim_payload:
        claim.setdefault("source_name", source_name)
        declared = str(claim.get("quote") or "")
        # Il passaggio che resta e' quello della fonte, con le sue maiuscole e
        # la sua punteggiatura: una citazione ricopiata a memoria non e' la
        # prova di niente, e a valle finirebbe fra virgolette come se lo fosse.
        grounded = provenance.exact_span(declared, source_text) if source_text else ""
        claim["quote"] = grounded or declared
        claim["quote_verified"] = bool(grounded)
        if declared and not grounded:
            unverified.append(str(claim.get("claim") or "")[:160])

    entries = provenance.build_ledger(claim_payload)
    ledger = provenance.ledger_payload(entries)
    summary = provenance.summarize_ledger(entries)

    warnings: list[str] = []
    if unverified:
        warnings.append(
            "Citazione non riscontrata nel testo della fonte per: "
            + "; ".join(unverified[:5])
            + ". Riporta queste affermazioni come riformulazioni, non come citazioni."
        )
    if not source_text and any(str(c.get("quote") or "") for c in claim_payload):
        warnings.append(
            "Testo della fonte non disponibile: nessuna citazione e' stata "
            "riscontrata. Salva prima l'evidenza con manage_process_evidence."
        )

    return enterprise_state_write(
        tool_call_id=tool_call_id,
        state={"process_claims": claim_payload},
        status="prepared",
        action="extract_process_claims",
        entity_type="process_claims",
        entity_id=process_id,
        summary=(
            f"{len(claim_payload)} claims extracted from {source_name} "
            f"({summary.corroborated} corroborated, {summary.single_source} single source)."
        ),
        payload={
            "process_id": process_id,
            "project_id": project_id,
            "source_name": source_name,
            "claims": claim_payload,
            "ledger": ledger,
            "ledger_summary": summary.as_dict(),
            "extraction_notes": extraction_notes or [],
            "graph_rag_ready": True,
        },
        warnings=warnings,
    )


@tool(args_schema=EvidenceSynthesisInput)
def synthesize_process_evidence(
    process_id: str,
    source_list: list[str],
    findings: list[dict] | None = None,
    confirmed_claims: list[str] | None = None,
    hypotheses: list[str] | None = None,
    contradictions: list[str] | None = None,
    open_questions: list[str] | None = None,
    recommended_next_evidence: list[str] | None = None,
) -> str:
    """
    Produce the canonical evidence synthesis for one process. Use before
    modeling so the ProcessUnderstanding is based on evidence, not free text.

    Three things are checked, and you must report what comes back rather than
    what you asked for:

    - a finding marked `corroborated` needs at least two distinct voices;
    - a statement credited to several voices may not contain an attribute only
      one of them states - that attribute stays that voice's, said separately;
    - a conclusion declared valid for the whole process cannot rest only on
      voices speaking for their own department.
    """
    verdicts = []
    for finding in _jsonable_items(findings or []):
        statement = finding.get("statement") or ""
        verdict = provenance.verify_corroboration(
            finding.get("topic") or statement,
            finding.get("asserted_support") or "single_source",
            finding.get("stances") or [],
            shared_statement=statement,
            asserted_scope_level=finding.get("asserted_scope_level") or "stated_scope",
        )
        item = verdict.as_dict()
        item["statement"] = statement
        verdicts.append(item)

    downgraded = [item for item in verdicts if item["downgraded"]]
    return enterprise_tool_result(
        status="review_required" if downgraded else "prepared",
        action="synthesize_process_evidence",
        entity_type="process_evidence_synthesis",
        entity_id=process_id,
        summary=f"Evidence synthesis from {len(source_list)} sources.",
        payload={
            "process_id": process_id,
            "source_list": source_list,
            "findings": verdicts,
            "confirmed_claims": confirmed_claims or [],
            "hypotheses": hypotheses or [],
            "contradictions": contradictions or [],
            "open_questions": open_questions or [],
            "recommended_next_evidence": recommended_next_evidence or [],
        },
        warnings=[
            f"«{item['statement'] or item['topic']}»: {'; '.join(item['downgrade_reasons'])}. "
            f"Vale come {item['support_label']}."
            for item in downgraded
        ],
    )


def _softened(severity: str) -> str:
    """La severita' che resta a una divergenza declassata.

    Una differenza di ambito o una lacuna di conoscenza non bloccano il
    modello: restano da approfondire. Alzare la severita' non e' previsto.
    """
    return "medium" if severity in {"blocking", "high"} else severity


def contradiction_key(title: str) -> str:
    """Stable id for a contradiction, derived from its title.

    identify returns it and resolve should pass it back, so a resolution still
    matches when the agent rewords the human-readable title.
    """
    return re.sub(r"[^a-z0-9]+", "-", " ".join(str(title or "").split()).casefold()).strip("-")[:60]


@tool(args_schema=ContradictionInput)
def manage_process_contradiction(
    process_id: str,
    operation: str,
    title: str,
    divergence_type: str = "tension_to_explore",
    stances: list[dict] | None = None,
    contradiction_id: str | None = None,
    conflicting_claims: list[str] | None = None,
    affected_process_area: str | None = None,
    source_names: list[str] | None = None,
    resolution_needed: str = "",
    severity: str = "medium",
    resolution: str | None = None,
    rationale: str = "",
    supporting_sources: list[str] | None = None,
    *,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Command:
    """
    Record a divergence between sources, or record what you concluded about one.

    Not every difference is a contradiction. Say which kind it is
    (`divergence_type`) and give the positions in play (`stances`): the runtime
    re-checks the type against them and can only weaken it. A side that says it
    does not know does not contradict a side that knows; two departments
    describing their own practice are not incompatible. Only a divergence that
    stays `incompatible` keeps modeling closed - report the type that comes
    back, not the one you asked for.

    Use operation=resolve once you have settled it, or decided it does not
    affect the model you are building. The runtime does not judge the
    conclusion; it checks that it carries a reason, and that clearing one cites
    a source.
    """
    conflicting_claims = conflicting_claims or []
    source_names = source_names or []
    supporting_sources = supporting_sources or []
    stance_payload = _jsonable_items(stances or [])

    if operation == "identify":
        # Senza posizioni esplicite si ricade sui nomi delle fonti: meglio un
        # conteggio delle voci basato su cio' che c'e' che nessun conteggio -
        # una divergenza con una sola voce non e' una divergenza.
        effective_stances = stance_payload or [
            {"source_name": name} for name in source_names
        ]
        verdict = provenance.classify_divergence(divergence_type, effective_stances)
        identified = {
            "process_id": process_id,
            "contradiction_id": contradiction_key(title),
            "title": title,
            "conflicting_claims": conflicting_claims,
            "affected_process_area": affected_process_area,
            "source_names": source_names or list(verdict.voices),
            "stances": stance_payload,
            "resolution_needed": resolution_needed,
            # Una divergenza declassata non puo' restare bloccante: la severita'
            # segue il tipo effettivo, altrimenti il modello resta chiuso su una
            # differenza di prospettiva.
            "severity": severity if verdict.blocks_modeling else _softened(severity),
            **verdict.as_dict(),
        }
        return enterprise_state_write(
            tool_call_id=tool_call_id,
            # The gate folds identifications and resolutions by contradiction_id,
            # so both land in the same accumulator.
            state={"contradictions": [identified]},
            status="prepared" if not verdict.downgraded else "reclassified",
            action="manage_process_contradiction",
            entity_type="process_contradiction",
            entity_id=process_id,
            summary=f"{title} — {identified['divergence_label']}",
            payload=identified,
            warnings=(
                [
                    f"Registrata come «{identified['divergence_label']}», non come "
                    f"«{provenance.DIVERGENCE_LABEL_IT.get(verdict.declared, verdict.declared)}»: "
                    + "; ".join(verdict.reasons)
                ]
                if verdict.downgraded
                else []
            ),
        )

    if operation != "resolve":
        raise ValueError(f"Operazione contraddizione non supportata: {operation}")

    invariant_violations: list[str] = []
    if resolution is None:
        invariant_violations.append("resolution_missing: operation=resolve requires a resolution")
    if not rationale.strip():
        invariant_violations.append("rationale_missing: a resolution requires a rationale")
    if resolution in {"resolved", "not_material"} and not supporting_sources:
        invariant_violations.append(
            "unsupported_resolution: clearing a contradiction requires at least one supporting source"
        )

    resolved_id = contradiction_id or contradiction_key(title)
    warnings = list(invariant_violations)
    if not contradiction_id:
        # Still matches when the title is unchanged, but say so rather than
        # reporting a clean resolution the gate may not be able to pair up.
        warnings.append(
            "contradiction_id_derived: no contradiction_id supplied, matched on the title instead"
        )

    # A contradiction cannot be cleared on no stated basis: an inconsistent
    # conclusion falls back to the safe reading, it does not silently unblock.
    effective_resolution = resolution or "still_blocking"
    if invariant_violations:
        effective_resolution = "still_blocking"

    resolved = {
        "process_id": process_id,
        "contradiction_id": resolved_id,
        "title": title,
        "resolution": effective_resolution,
        "proposed_resolution": resolution,
        "rationale": rationale,
        "supporting_sources": supporting_sources,
        "invariant_violations": invariant_violations,
    }
    return enterprise_state_write(
        tool_call_id=tool_call_id,
        state={"contradictions": [resolved]},
        status=effective_resolution,
        action="manage_process_contradiction",
        entity_type="process_contradiction_resolution",
        entity_id=process_id,
        summary=f"Contradiction '{title}': {effective_resolution}.",
        payload=resolved,
        warnings=warnings,
    )


@tool(args_schema=EvidenceCoverageInput)
def prepare_evidence_coverage_matrix(
    process_id: str,
    coverage_items: list[dict],
    modeling_blockers: list[str] | None = None,
    *,
    tool_call_id: Annotated[str, InjectedToolCallId] = "",
) -> Command:
    """
    Prepare an evidence coverage matrix by process area. Use as the gate between
    evidence synthesis and ProcessUnderstanding modeling.

    """
    coverage_payload = _jsonable_items(coverage_items)
    weak_areas = [
        item.get("process_area")
        for item in coverage_payload
        if item.get("coverage") in {"none", "weak"}
    ]
    blockers = modeling_blockers or []
    status = "ready_for_modeling" if not blockers and len(weak_areas) <= 2 else "evidence_required"
    coverage = {
        "process_id": process_id,
        "status": status,
        "coverage_items": coverage_payload,
        "weak_areas": weak_areas,
        "modeling_blockers": blockers,
    }

    return enterprise_state_write(
        tool_call_id=tool_call_id,
        # One coverage matrix per process: the latest assessment replaces the previous.
        state={"evidence_coverage": coverage},
        status=status,
        action="prepare_evidence_coverage_matrix",
        entity_type="process_evidence_coverage",
        entity_id=process_id,
        summary=f"Evidence coverage assessed across {len(coverage_items)} process areas.",
        payload=coverage,
        warnings=blockers,
    )


EVIDENCE_TOOL_POLICY = """
Process Evidence subagent tools.

The Evidence subagent owns source custody, claim extraction, confidence,
contradictions, hypotheses and evidence coverage. It prepares and indexes
enterprise Knowledge Graph artifacts for process-scoped GraphRAG retrieval.

Provenance is not a writing style here, it is a data contract:

- every claim carries who states it, the scope it covers, how the source knows
  it, and the verbatim words behind it. One source, one voice: never move a
  statement from the speaker who made it to another;
- a claim has a SUBJECT (`topic`), a PROPOSITION (`assertion`) and the
  ATTRIBUTES that source adds (`qualifiers`). Two sources talking about the
  same subject are not agreeing: give the same `assertion` only to claims that
  really assert the same thing;
- how well supported something is (single source / corroborated / contested /
  inferred / declared unknown) is COMPUTED by the runtime from the number of
  distinct voices on a proposition. Read it back from the tool result; do not
  assert it yourself, and never say two sources agree on something only one of
  them said;
- a sentence credited to several voices may contain ONLY what all of them
  support. What one voice adds stays that voice's and is said separately:
  "entrambi riferiscono X; <voce> aggiunge Y". The runtime refuses the ones
  that mix the two and tells you which attribute belongs to whom;
- two people each missing a datum for their own area do not show the process
  lacks it. Keep a conclusion inside the scope its evidence covers;
- a source saying "I do not know this" is evidence about that source. It is not
  a gap in the process, and it does not contradict a source that does know;
- not every difference is a contradiction. Type it, and accept the runtime's
  reclassification;
- when asked where a statement comes from, answer with
  audit_process_evidence(operation="provenance"), not with a new synthesis.
""".strip()


evidence_tools = [
    get_process_evidence_brief,
    manage_process_evidence,
    extract_process_claims,
    synthesize_process_evidence,
    manage_process_contradiction,
    prepare_evidence_coverage_matrix,
    extract_process_graph_from_evidence,
    index_process_evidence_graph,
]
