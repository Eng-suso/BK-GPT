"""Il giudice degli eval L2, senza modello: cosa gli si chiede e come si misura.

Il giudizio vero si misura a L2 col modello dei test. Qui si verifica cio' che
non dipende dal modello: il giudice passa dal gateway col suo compito, riceve
domanda, materiale ed elemento, e l'accordo con un umano si calcola giusto.
"""

from __future__ import annotations

import pytest

import tests.evals.judge as judge
from backend.llm import LlmTask


@pytest.fixture()
def chiamate(monkeypatch):
    """Il gateway sostituito: si registra la chiamata e si risponde a mano."""
    registro: list[dict] = []

    def finto_run(**kwargs):
        registro.append(kwargs)
        output = kwargs["output"]
        if output is judge.BoundedVerdict:
            return judge.BoundedVerdict(answer="si", confidence=0.9, reason="lo dice Laura")
        return judge.RubricVerdict(score=4, reason="chiaro")

    monkeypatch.setattr(judge, "llm_run", finto_run)
    return registro


def test_una_domanda_chiusa_passa_dal_gateway_con_tutto_il_materiale(chiamate):
    verdetto = judge.judge_bounded(
        question="La domanda e' gia' risposta dalle fonti?",
        context="Laura: la soglia e' di 5.000 euro.",
        item="Qual e' la soglia di approvazione?",
    )

    assert verdetto.yes
    chiamata = chiamate[0]
    assert chiamata["task"] is LlmTask.EVAL_JUDGE
    testo = chiamata["messages"][1].content
    assert "gia' risposta dalle fonti" in testo
    assert "5.000 euro" in testo
    assert "Qual e' la soglia" in testo
    assert chiamata["prompt_version"].startswith("eval_judge_bounded@")


def test_un_criterio_arriva_al_giudice_con_i_suoi_passi_in_ordine(chiamate):
    criterio = judge.Criterion(
        name="Chiarezza per il cliente",
        description="La domanda e' comprensibile per chi non conosce BPMN.",
        steps=("Leggi la domanda come un responsabile di funzione.", "Cerca gergo tecnico."),
    )

    verdetto = judge.judge_rubric(criterion=criterio, context="-", item="Il gateway XOR e' esclusivo?")

    assert verdetto.score == 4
    testo = chiamate[0]["messages"][1].content
    assert testo.index("1. Leggi la domanda") < testo.index("2. Cerca gergo")
    assert chiamate[0]["prompt_version"].startswith("eval_judge_rubric@")


def test_un_voto_fuori_scala_non_e_un_voto():
    with pytest.raises(ValueError):
        judge.RubricVerdict(score=6, reason="-")


def test_l_accordo_pieno_e_il_caso():
    assert judge.agreement([True, False, True], [True, False, True]) == {"accuracy": 1.0, "kappa": 1.0}


def test_un_giudice_che_dice_sempre_si_non_inganna_il_kappa():
    """Accuracy alta su un campione sbilanciato, kappa a zero: non ha capito niente."""
    umano = [True] * 9 + [False]
    sempre_si = [True] * 10

    risultato = judge.agreement(sempre_si, umano)

    assert risultato["accuracy"] == 0.9
    assert risultato["kappa"] == 0.0
