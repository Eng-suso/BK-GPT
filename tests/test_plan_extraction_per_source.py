"""Il piano nasce da ogni fonte intera, non dal primo terzo di tutte.

L'estrazione leggeva un corpus unico tagliato a 12.000 caratteri per fonte e
30.000 in tutto. Con interviste vere - un'ora di trascrizione sono 40-60.000
caratteri - il piano nasceva da circa il primo terzo di ognuna, e cio' che veniva
raccontato a meta' colloquio non arrivava mai al disegno. Nessun prompt puo'
recuperare un testo che non e' stato letto.

Qui si verifica il rimedio, che ha tre proprieta' distinte:

1. ogni fonte viene letta **intera** e **da sola**;
2. i piani parziali si fondono in modo **deterministico** - stesso input, stesso
   piano - e senza LLM nel merge;
3. una fonte che non si riesce a estrarre non annulla le altre, e non sparisce
   in silenzio.

Niente database e nessun modello: l'estrattore e' sostituito, perche' qui si
verifica il rimedio e non la bravura dell'LLM.
"""

from __future__ import annotations

import pytest

from backend.agents.process_synthesis import (
    SOURCE_EXTRACTION_CHAR_LIMIT,
    extract_plan_from_sources,
)
from backend.process_understanding import (
    ExtractionFailure,
    ProcessActor,
    ProcessStep,
    ProcessUnderstanding,
    ProcessUnderstandingResult,
)


def _source(name: str, content: str, participants: list[str] | None = None) -> dict:
    return {
        "id": name.lower().replace(" ", "-"),
        "name": name,
        "type": "Intervista",
        "participants": participants or [],
        "summary": "",
        "content": content,
        "has_content": True,
    }


def _plan(actor: str, step: str) -> ProcessUnderstandingResult:
    return ProcessUnderstandingResult(
        status="success",
        process=ProcessUnderstanding(
            title="Ciclo passivo",
            actors=[ProcessActor(id=actor, label=actor.title(), kind="team")],
            steps=[ProcessStep(id=step, label=step.replace("_", " "), actor_ids=[actor])],
        ),
    )


@pytest.fixture()
def extractor(monkeypatch):
    """Sostituisce l'estrattore e registra il testo che gli arriva, fonte per fonte."""
    seen: list[str] = []

    def _fake(title: str, source_text: str, *, with_quality_report: bool = True):
        seen.append(source_text)
        assert not with_quality_report, (
            "il giudizio di qualita' si da' sul piano intero, non su ogni fonte"
        )
        if "laura" in source_text.casefold():
            return _plan("ufficio_tecnico", "apri_richiesta")
        if "paolo" in source_text.casefold():
            return _plan("manutenzione", "chiama_fornitore")
        return _plan("acquisti", "crea_ordine")

    monkeypatch.setattr(
        "backend.agents.process_synthesis.build_process_understanding", _fake
    )
    return seen


def test_every_source_is_read_whole_and_alone(extractor):
    """Una estrazione per fonte, e dentro c'e' solo quella fonte."""
    # La coda del testo e' la prova che serve: un taglio a 12.000 caratteri la
    # farebbe sparire, e con lei l'ultimo passaggio raccontato dall'intervista.
    tail = "E alla fine firma il direttore acquisti."
    sources = [
        _source(
            "Intervista Laura",
            "Laura Conti apre la richiesta di acquisto. " * 400 + tail,
        ),
        _source("Intervista Paolo", "Paolo Marchetti chiama il fornitore. " * 400),
    ]

    result = extract_plan_from_sources("Ciclo passivo", sources)

    assert result.llm_calls == 2
    assert result.sources_read == 2
    assert len(extractor) == 2
    laura_notes, paolo_notes = extractor
    assert "Paolo" not in laura_notes, "le voci non si fondono in un prompt unico"
    assert "Laura" not in paolo_notes
    assert len(laura_notes) > 12_000
    assert tail in laura_notes, "la fine dell'intervista deve arrivare all'estrattore"
    assert "troncato" not in laura_notes, "un testo intero non si dichiara tagliato"


def test_a_source_longer_than_the_limit_is_cut_and_says_so(extractor):
    """Oltre il limite si taglia, e il taglio si dichiara.

    Un testo che finisce senza preavviso fa concludere che il processo finisce
    li': la riga di troncamento e' cio' che separa "la fonte dice solo questo"
    da "di questa fonte ho letto la prima parte".
    """
    huge = _source("Intervista lunga", "parola " * 40_000)

    extract_plan_from_sources("Ciclo passivo", [huge])

    notes = extractor[0]
    body = notes.split("\n\n", 1)[1]
    assert len(body.replace("(testo troncato: la fonte continua oltre questo punto)", "")) <= (
        SOURCE_EXTRACTION_CHAR_LIMIT + 2
    )
    assert "troncato" in notes


def test_the_partial_plans_are_merged_without_losing_anyone(extractor):
    """Tre voci, tre reparti: nel piano fuso ci sono tutti e tre."""
    sources = [
        _source("Intervista Laura", "Laura Conti, Ufficio Tecnico."),
        _source("Intervista Paolo", "Paolo Marchetti, Manutenzione."),
        _source("Intervista Francesca", "Francesca Neri, Acquisti."),
    ]

    result = extract_plan_from_sources("Ciclo passivo", sources)

    actors = {actor.id for actor in result.process.actors}
    steps = {step.id for step in result.process.steps}
    assert actors == {"ufficio_tecnico", "manutenzione", "acquisti"}
    assert steps == {"apri_richiesta", "chiama_fornitore", "crea_ordine"}


def test_the_merge_is_deterministic(extractor):
    """Stesse fonti, stesso piano: due ricostruzioni non devono divergere."""
    sources = [
        _source("Intervista Laura", "Laura Conti, Ufficio Tecnico."),
        _source("Intervista Paolo", "Paolo Marchetti, Manutenzione."),
    ]

    first = extract_plan_from_sources("Ciclo passivo", sources)
    second = extract_plan_from_sources("Ciclo passivo", sources)

    assert first.process.model_dump(mode="json") == second.process.model_dump(mode="json")


def test_a_source_that_fails_does_not_cancel_the_others(monkeypatch):
    """Una fonte illeggibile e' una fonte in meno, non un piano in meno."""

    def _fake(title: str, source_text: str, *, with_quality_report: bool = True):
        if "Paolo" in source_text:
            return ProcessUnderstandingResult(
                status="failed",
                failure=ExtractionFailure(
                    kind="rate_limit",
                    message="429 Too Many Requests",
                    retryable=True,
                    attempt=1,
                ),
            )
        return _plan("ufficio_tecnico", "apri_richiesta")

    monkeypatch.setattr(
        "backend.agents.process_synthesis.build_process_understanding", _fake
    )

    result = extract_plan_from_sources(
        "Ciclo passivo",
        [
            _source("Intervista Laura", "Laura Conti, Ufficio Tecnico."),
            _source("Intervista Paolo", "Paolo Marchetti, Manutenzione."),
        ],
    )

    assert result.process is not None
    assert {actor.id for actor in result.process.actors} == {"ufficio_tecnico"}
    # E la fonte persa non sparisce in silenzio.
    assert any("Paolo" in failure for failure in result.failures)
    assert any("429" in failure for failure in result.failures)


def test_the_main_path_keeps_every_voice(monkeypatch):
    """Il percorso non e' quello dell'ultima intervista letta.

    Ogni fonte descrive il pezzo che ha visto: se il merge sostituisse il
    percorso a ogni fonte, nel piano resterebbero solo i passaggi di chi ha
    parlato per ultimo, in un ordine deciso dall'ordine di lettura.
    """

    def _fake(title: str, source_text: str, *, with_quality_report: bool = True):
        if "Laura" in source_text:
            return ProcessUnderstandingResult(
                status="success",
                process=ProcessUnderstanding(
                    title="Ciclo passivo",
                    steps=[ProcessStep(id="apri_richiesta", label="Apri richiesta")],
                    sequence=["apri_richiesta"],
                    main_success_path=["apri_richiesta"],
                ),
            )
        return ProcessUnderstandingResult(
            status="success",
            process=ProcessUnderstanding(
                title="Ciclo passivo",
                steps=[ProcessStep(id="crea_ordine", label="Crea ordine")],
                sequence=["crea_ordine"],
                main_success_path=["crea_ordine"],
            ),
        )

    monkeypatch.setattr(
        "backend.agents.process_synthesis.build_process_understanding", _fake
    )

    result = extract_plan_from_sources(
        "Ciclo passivo",
        [
            _source("Intervista Laura", "Laura Conti apre la richiesta."),
            _source("Intervista Francesca", "Francesca Neri crea l'ordine."),
        ],
    )

    assert result.process.sequence == ["apri_richiesta", "crea_ordine"]
    assert result.process.main_success_path == ["apri_richiesta", "crea_ordine"]


def test_every_source_failing_is_reported_as_a_failure(monkeypatch):
    """Se nessuna fonte e' stata letta, il piano non c'e' e si dice perche'."""

    def _all_down(title: str, source_text: str, *, with_quality_report: bool = True):
        return ProcessUnderstandingResult(
            status="failed",
            failure=ExtractionFailure(
                kind="provider_error",
                message="provider non raggiungibile",
                retryable=True,
                attempt=1,
            ),
        )

    monkeypatch.setattr(
        "backend.agents.process_synthesis.build_process_understanding", _all_down
    )

    result = extract_plan_from_sources(
        "Ciclo passivo",
        [
            _source("Intervista Laura", "Laura Conti, Ufficio Tecnico."),
            _source("Intervista Paolo", "Paolo Marchetti, Manutenzione."),
        ],
    )

    assert result.process is None
    assert result.sources_read == 2, (
        "le fonti erano leggibili: distingue un guasto da un processo senza trascrizioni"
    )
    assert len(result.failures) == 2


def test_sources_without_text_are_not_extracted(extractor):
    """Una fonte senza trascrizione non e' una chiamata al modello da spendere."""
    result = extract_plan_from_sources(
        "Ciclo passivo",
        [
            _source("Fonte senza testo", ""),
            {"id": "s2", "name": "Solo nome", "content": None},
        ],
    )

    assert result.process is None
    assert result.llm_calls == 0
    assert extractor == []
