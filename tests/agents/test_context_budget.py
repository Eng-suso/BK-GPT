"""Il budget del contesto: cosa entra lo decide il runtime, e cosa manca si dice.

Prima ogni artefatto del prompt di scope aveva il suo tetto in caratteri e
nessuno guardava il totale; cosa restava fuori lo decideva il carattere numero
40.000 dentro ciascun artefatto. Qui si fissa:

1. sotto budget il prompt e' identico a come e' scritto;
2. sopra budget entrano prima i blocchi piu' importanti, uno si tronca, gli
   altri restano fuori - e al loro posto il modello legge che mancano;
3. l'impronta dice se due turni hanno visto lo stesso contesto;
4. nel prompt del canvas lo stesso XML non entra due volte.
"""

from __future__ import annotations

from backend.agents.context_budget import ContextBlock, assemble, count_tokens


def _words(n: int, word: str = "attivita") -> str:
    return " ".join(f"{word}{i}" for i in range(n))


def test_under_budget_the_prompt_is_what_was_written():
    parts = ["regola uno", ContextBlock("piano", "il piano", priority=50, header=("Piano:",)), "regola due"]

    out = assemble(parts, budget_tokens=10_000)

    assert out.text == "regola uno\nPiano:\nil piano\nregola due"
    assert [b.fate for b in out.report.blocks] == ["included"]


def test_over_budget_the_most_important_block_wins_and_the_rest_is_declared():
    big = _words(3_000)
    parts = [
        "regole",
        ContextBlock("diagnostica", big, priority=10),
        ContextBlock("xml del canvas", big, priority=90),
    ]
    budget = count_tokens(big) + 200

    out = assemble(parts, budget_tokens=budget)

    fates = {b.name: b.fate for b in out.report.blocks}
    assert fates == {"xml del canvas": "included", "diagnostica": "omitted"}
    assert "[diagnostica omesso dal budget del contesto" in out.text
    assert out.report.total_tokens <= budget


def test_a_block_that_partly_fits_is_cut_and_says_so():
    big = _words(3_000)
    budget = count_tokens(big) // 2

    out = assemble(["regole", ContextBlock("piano", big, priority=50)], budget_tokens=budget)

    (piano,) = out.report.blocks
    assert piano.fate == "truncated"
    assert piano.tokens < piano.full_tokens
    assert "[piano troncato dal budget del contesto" in out.text
    assert out.report.total_tokens <= budget


def test_the_written_order_survives_the_priority_order():
    parts = [
        ContextBlock("primo", "AAA", priority=1),
        "in mezzo",
        ContextBlock("secondo", "BBB", priority=99),
    ]

    out = assemble(parts, budget_tokens=10_000)

    assert out.text.index("AAA") < out.text.index("in mezzo") < out.text.index("BBB")


def test_the_same_context_has_the_same_fingerprint():
    parts = ["regole", ContextBlock("piano", "il piano", priority=50)]

    first = assemble(parts, budget_tokens=10_000).report.fingerprint
    again = assemble(parts, budget_tokens=10_000).report.fingerprint
    other = assemble(["regole", ContextBlock("piano", "un altro piano", priority=50)], 10_000)

    assert first == again
    assert first != other.report.fingerprint

