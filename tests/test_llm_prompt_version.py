"""L5 — la versione del prompt nel registro dei consumi.

Un cambio di prompt cambia la spesa. Senza una versione, la spesa di prima e
quella di dopo sono la stessa colonna e l'aumento resta inspiegato: e' la
domanda «perche' da martedi' costa il doppio» che non ha risposta.

Due cose si verificano qui, e la seconda e' quella che fa durare la prima:
che la versione sia calcolata in modo onesto, e che **nessun punto di chiamata
si dimentichi di passarla**.
"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest
from pydantic import BaseModel

from backend.llm.prompts import prompt_version, schema_part

RADICE = Path(__file__).resolve().parents[1] / "backend"


class TestComeSiCalcolaUnaVersione:
    def test_lo_stesso_testo_da_la_stessa_versione(self):
        assert prompt_version("compito", "istruzioni") == prompt_version("compito", "istruzioni")

    def test_un_testo_diverso_da_una_versione_diversa(self):
        prima = prompt_version("compito", "istruzioni")
        dopo = prompt_version("compito", "istruzioni piu' lunghe")

        assert prima != dopo
        # Il nome resta leggibile: due righe con lo stesso nome e hash diverso
        # sono lo stesso prompt prima e dopo una modifica.
        assert prima.startswith("compito@") and dopo.startswith("compito@")

    def test_i_fine_riga_di_windows_non_sono_una_modifica(self):
        """Senza questa normalizzazione lo stesso prompt avrebbe due versioni a
        seconda della macchina che l'ha eseguito, e il registro direbbe che e'
        cambiato quando e' cambiato solo git."""
        assert prompt_version("c", "riga1\r\nriga2") == prompt_version("c", "riga1\nriga2")

    def test_le_parti_in_ordine_diverso_sono_prompt_diversi(self):
        assert prompt_version("c", "a", "b") != prompt_version("c", "b", "a")

    def test_due_parti_non_si_confondono_con_una_concatenata(self):
        """Senza un separatore, ('ab', 'c') e ('a', 'bc') darebbero lo stesso
        hash pur essendo due prompt diversi."""
        assert prompt_version("c", "ab", "c") != prompt_version("c", "a", "bc")

    def test_senza_testo_non_si_inventa_una_versione(self):
        with pytest.raises(ValueError):
            prompt_version("compito")


class TestLoSchemaFaParteDelPrompt:
    """Un campo in piu' nella risposta e' un cambio di prompt: si pagano i token
    per riempirlo, e senza questo la spesa in piu' comparirebbe sotto la stessa
    etichetta di prima."""

    def test_un_campo_aggiunto_cambia_la_versione(self):
        class Prima(BaseModel):
            a: str

        class Dopo(BaseModel):
            a: str
            b: str

        assert schema_part(Prima) != schema_part(Dopo)
        assert prompt_version("c", "istruzioni", schema_part(Prima)) != prompt_version(
            "c", "istruzioni", schema_part(Dopo)
        )

    def test_lo_schema_e_stabile_fra_due_letture(self):
        class Schema(BaseModel):
            uno: str
            due: int

        assert schema_part(Schema) == schema_part(Schema)

    def test_senza_schema_non_si_rompe(self):
        assert schema_part(str) == "str"


def _chiamate_al_gateway() -> list[tuple[Path, ast.Call]]:
    """Ogni chiamata a `llm_run(...)` nel prodotto, col file in cui sta.

    Si legge il codice invece di importarlo: molti di questi moduli hanno
    bisogno di una chiave o di un database per essere costruiti, e un test che
    li importa tutti verificherebbe l'ambiente invece del codice.
    """
    trovate: list[tuple[Path, ast.Call]] = []
    for file in RADICE.rglob("*.py"):
        if "__pycache__" in file.parts:
            continue
        albero = ast.parse(file.read_text(encoding="utf-8"), filename=str(file))
        for nodo in ast.walk(albero):
            if not isinstance(nodo, ast.Call):
                continue
            nome = nodo.func.id if isinstance(nodo.func, ast.Name) else None
            if nome == "llm_run":
                trovate.append((file, nodo))
    return trovate


class TestNessunPuntoDiChiamataSiDimentica:
    """Il test che fa durare L5.

    Il cablaggio di oggi non serve a niente se la prossima chiamata al gateway
    nasce senza versione: la colonna tornerebbe a essere NULL a macchia di
    leopardo, che e' peggio di vuota - si legge come «questo prompt non e' mai
    cambiato».
    """

    def test_ce_ne_sono(self):
        """Se questo fallisce, e' cambiato il modo di chiamare il gateway e il
        test sotto sta verificando il vuoto."""
        assert len(_chiamate_al_gateway()) >= 8

    def test_ogni_chiamata_dichiara_la_versione_del_prompt(self):
        senza = [
            f"{file.relative_to(RADICE.parent)}:{chiamata.lineno}"
            for file, chiamata in _chiamate_al_gateway()
            if not any(k.arg == "prompt_version" for k in chiamata.keywords)
        ]

        assert not senza, (
            "Queste chiamate al gateway non dichiarano `prompt_version`, quindi la "
            "loro spesa finira' nel registro senza dire quale prompt l'ha prodotta:\n  "
            + "\n  ".join(senza)
        )
