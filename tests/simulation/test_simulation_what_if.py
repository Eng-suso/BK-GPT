"""SIM-23: la frase del consulente tradotta in modifiche tipizzate dello scenario."""

import pytest

from backend.settings import settings
from backend.simulation.whatif import (
    SimulationWhatIfRequest,
    WhatIfFailed,
    WhatIfTranslation,
    WhatIfUnavailable,
    parse,
    render,
    translate,
)

REQUEST = SimulationWhatIfRequest.model_validate({
    "sentence": "Un approvatore in piu' e Verifica dura il 30% in meno",
    "activities": [{"id": "T_check", "name": "Verifica fattura"}, {"id": "T_pay", "name": "Paga"}],
    "resources": [{"id": "approver", "name": "Approvatore", "units": 2}, {"id": "clerk", "name": "Impiegato", "units": 1}],
})


def _answer(changes: list[dict], not_understood: str = "") -> WhatIfTranslation:
    return WhatIfTranslation.model_validate({"changes": changes, "not_understood": not_understood})


@pytest.fixture()
def fake_llm(monkeypatch):
    """Un gateway finto: ogni chiamata finisce nella lista e torna la risposta data."""
    import backend.llm as llm

    calls: list[dict] = []
    answer: dict = {"result": _answer([])}

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


def test_the_model_sees_numbered_activities_roles_and_the_sentence():
    text = render(REQUEST)

    assert "[A0] Verifica fattura" in text
    assert "[R0] Approvatore (2)" in text
    assert text.endswith("Frase del consulente: Un approvatore in piu' e Verifica dura il 30% in meno")


def test_ids_become_the_real_ones_and_a_delta_becomes_the_final_count():
    result = parse(_answer([
        {"kind": "resource_units", "target": "R0", "mode": "delta", "value": 1},
        {"kind": "activity_duration", "target": "A0", "mode": "factor", "value": 0.7},
    ]), REQUEST)

    assert [c.model_dump() for c in result.changes] == [
        {"kind": "resource_units", "resource_id": "approver", "units": 3},
        {"kind": "activity_duration", "element_id": "T_check", "factor": 0.7, "mean_minutes": None},
    ]
    assert (result.rejected, result.not_understood) == (0, None)


def test_every_kind_has_its_shape():
    result = parse(_answer([
        {"kind": "resource_units", "target": "R1", "mode": "set", "value": 4},
        {"kind": "activity_duration", "target": "A1", "mode": "set", "value": 90},
        {"kind": "skip_activity", "target": "A0", "mode": "percent", "value": 100},
        {"kind": "demand", "target": "", "mode": "factor", "value": 1.2},
        {"kind": "resource_cost", "target": "R0", "mode": "set", "value": 45},
    ]), REQUEST)

    assert [c.model_dump(exclude_none=True) for c in result.changes] == [
        {"kind": "resource_units", "resource_id": "clerk", "units": 4},
        {"kind": "activity_duration", "element_id": "T_pay", "mean_minutes": 90},
        {"kind": "skip_activity", "element_id": "T_check", "percent": 100},
        {"kind": "demand", "factor": 1.2},
        {"kind": "resource_cost", "resource_id": "approver", "cost_per_hour": 45},
    ]


@pytest.mark.parametrize("change", [
    {"kind": "resource_units", "target": "R9", "mode": "delta", "value": 1},  # ruolo non mostrato
    {"kind": "resource_units", "target": "R0", "mode": "delta", "value": -2},  # zero persone
    {"kind": "resource_units", "target": "R0", "mode": "set", "value": 2.5},  # mezza persona
    {"kind": "resource_units", "target": "R0", "mode": "set", "value": 2},  # nessun cambio
    {"kind": "activity_duration", "target": "A7", "mode": "factor", "value": 0.7},  # attivita' inventata
    {"kind": "activity_duration", "target": "A0", "mode": "factor", "value": 0},  # durata zero
    {"kind": "activity_duration", "target": "A0", "mode": "delta", "value": 10},  # modo che non esiste per le durate
    {"kind": "skip_activity", "target": "A0", "mode": "percent", "value": 140},
    {"kind": "demand", "target": "", "mode": "factor", "value": 50},
    {"kind": "resource_cost", "target": "R0", "mode": "set", "value": -5},
])
def test_a_change_that_cannot_be_trusted_is_dropped_and_counted(change):
    result = parse(_answer([change]), REQUEST)

    assert (result.changes, result.rejected) == ([], 1)


def test_one_change_per_element_the_first_wins():
    result = parse(_answer([
        {"kind": "activity_duration", "target": "A0", "mode": "factor", "value": 0.7},
        {"kind": "activity_duration", "target": "A0", "mode": "factor", "value": 0.5},
    ]), REQUEST)

    assert [c.model_dump(exclude_none=True)["factor"] for c in result.changes] == [0.7]
    assert result.rejected == 1


def test_what_the_model_could_not_translate_comes_back_as_is():
    result = parse(_answer([], not_understood="  lavorare anche il sabato "), REQUEST)

    assert result.not_understood == "lavorare anche il sabato"


def test_the_call_opens_its_operation(fake_llm):
    calls, answer = fake_llm
    answer["result"] = _answer([{"kind": "demand", "target": "", "mode": "factor", "value": 1.5}])

    result = translate("proc-1", REQUEST)

    assert [c.kind for c in result.changes] == ["demand"]
    assert calls[0]["operation"].kind == "simulation_what_if"
    assert calls[0]["operation"].process_id == "proc-1"
    assert calls[0]["prompt_version"].startswith("simulation_what_if@")


def test_without_a_key_the_model_is_never_called(fake_llm, monkeypatch):
    calls, _ = fake_llm
    monkeypatch.setattr(settings, "openai_api_key", "")

    with pytest.raises(WhatIfUnavailable):
        translate("proc-1", REQUEST)
    assert calls == []


def test_a_failure_of_the_model_is_said_not_hidden(fake_llm):
    _, answer = fake_llm
    answer["result"] = RuntimeError("429")

    with pytest.raises(WhatIfFailed):
        translate("proc-1", REQUEST)
