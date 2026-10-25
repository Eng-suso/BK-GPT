"""SIM-24b: la lettura di un'alternativa redatta per il cliente, senza numeri inventati."""

import pytest

from backend.settings import settings
from backend.simulation.narrative import (
    NarrativeDraft,
    NarrativeRejected,
    NarrativeUnavailable,
    SimulationNarrativeRequest,
    render,
    verify,
    write,
)

REQUEST = SimulationNarrativeRequest.model_validate({
    "language": "it",
    "as_is_name": "AS-IS",
    "scenario_name": "A · +1 Approvatore",
    "kpis": [
        {"label": "Durata media del caso", "value": "−1 h 20 min ± 12 min", "verdict": "better"},
        {"label": "Costo per caso", "value": "+4,10 € ± 0,80 €", "verdict": "worse"},
        {"label": "Attesa media", "value": "−5 min ± 9 min", "verdict": "unclear"},
    ],
    "reading": ["Il vincolo si sposta da Approva a Paga: attesa davanti ad Approva 2 h → 40 min."],
    "names": ["Approva", "Paga", "Verifica 2"],
})


@pytest.fixture()
def fake_llm(monkeypatch):
    """Un gateway finto: ogni chiamata finisce nella lista e torna la risposta data."""
    import backend.llm as llm

    calls: list[dict] = []
    answer: dict = {"result": NarrativeDraft(text="")}

    def run(**kwargs):
        from backend.llm import current_operation

        calls.append({**kwargs, "operation": current_operation()})
        if isinstance(answer["result"], Exception):
            raise answer["result"]
        return answer["result"]

    monkeypatch.setattr(llm, "run", run)
    monkeypatch.setattr(settings, "openai_api_key", "sk-test")
    monkeypatch.setattr(settings, "delir_fake_llm", False)
    return calls, answer


def test_the_model_sees_kpis_by_id_and_verdict_but_no_numbers():
    text = render(REQUEST)

    assert "[K1] Durata media del caso: differenza migliore" in text
    assert "[K3] Attesa media: differenza non certa" in text
    assert "Il vincolo si sposta da Approva a Paga" in text
    # Ne' i valori dei KPI ne' le durate della lettura arrivano al modello: non li puo' copiare.
    assert "20 min" not in text and "40 min" not in text and "4,10" not in text


def test_placeholders_become_the_values_of_the_runs():
    draft = NarrativeDraft(text="Con un approvatore in piu' un caso dura [K1] in meno, ma costa [K2] in piu'. L'attesa media non cambia in modo certo ([K3]).")

    result = verify(draft, REQUEST)

    assert result.text == (
        "Con un approvatore in piu' un caso dura −1 h 20 min ± 12 min in meno, "
        "ma costa +4,10 € ± 0,80 € in piu'. L'attesa media non cambia in modo certo (−5 min ± 9 min)."
    )
    assert result.cited == ["K1", "K2", "K3"]


def test_digits_inside_process_names_are_not_invented_numbers():
    result = verify(NarrativeDraft(text="Il lavoro si accumula ora su Verifica 2, non piu' su Approva."), REQUEST)

    assert result.cited == []


@pytest.mark.parametrize("text", [
    "Un caso dura 80 minuti in meno.",  # una cifra del modello
    "Il costo sale di [K2], cioe' circa 4 euro.",  # una cifra accanto al segnaposto
    "Un caso dura [K9] in meno.",  # un KPI che non esiste
    "   ",  # niente testo
    "x" * 901,  # troppo lungo
])
def test_a_text_that_cannot_be_verified_is_rejected(text):
    with pytest.raises(NarrativeRejected):
        verify(NarrativeDraft(text=text), REQUEST)


def test_the_call_opens_its_operation(fake_llm):
    calls, answer = fake_llm
    answer["result"] = NarrativeDraft(text="Un caso dura [K1] in meno.")

    result = write("proc-1", REQUEST)

    assert result.text == "Un caso dura −1 h 20 min ± 12 min in meno."
    assert calls[0]["operation"].kind == "simulation_narrative"
    assert calls[0]["prompt_version"].startswith("simulation_narrative@")


def test_without_a_key_the_model_is_never_called(fake_llm, monkeypatch):
    calls, _ = fake_llm
    monkeypatch.setattr(settings, "openai_api_key", "")

    with pytest.raises(NarrativeUnavailable):
        write("proc-1", REQUEST)
    assert calls == []


def test_a_failure_of_the_model_is_said(fake_llm):
    _, answer = fake_llm
    answer["result"] = RuntimeError("timeout")

    with pytest.raises(NarrativeRejected):
        write("proc-1", REQUEST)


def _url(bpmn_model_id: str) -> str:
    return f"/v1/workspace/bpmn-models/{bpmn_model_id}/simulation-narrative"


def test_the_route_returns_the_verified_text(api_client, new_bpmn_model, fake_llm):
    _, answer = fake_llm
    answer["result"] = NarrativeDraft(text="Un caso dura [K1] in meno.")

    response = api_client.post(_url(new_bpmn_model()), json=REQUEST.model_dump())

    assert response.status_code == 200
    assert response.json() == {"text": "Un caso dura −1 h 20 min ± 12 min in meno.", "cited": ["K1"]}


def test_the_route_rejects_a_text_with_its_own_numbers(api_client, new_bpmn_model, fake_llm):
    _, answer = fake_llm
    answer["result"] = NarrativeDraft(text="Un caso dura 80 minuti in meno.")

    response = api_client.post(_url(new_bpmn_model()), json=REQUEST.model_dump())

    assert response.status_code == 502
    assert "numeri non verificabili" in response.json()["error"]["message"]


def test_the_route_says_when_the_model_is_missing(api_client, new_bpmn_model, fake_llm, monkeypatch):
    monkeypatch.setattr(settings, "openai_api_key", "")

    assert api_client.post(_url(new_bpmn_model()), json=REQUEST.model_dump()).status_code == 503


def test_the_route_needs_a_known_model_and_at_least_one_kpi(api_client, new_bpmn_model, fake_llm):
    assert api_client.post(_url("missing"), json=REQUEST.model_dump()).status_code == 404
    assert api_client.post(_url(new_bpmn_model()), json={**REQUEST.model_dump(), "kpis": []}).status_code == 422
