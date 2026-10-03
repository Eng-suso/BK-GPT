"""Il set di calibrazione del giudice e' un metro utilizzabile.

Un set con una sola classe non misura niente (il kappa di un giudice che dice
sempre la stessa cosa sarebbe indefinito), e un'etichetta senza il suo perche'
non si puo' rileggere: un consulente che valida il set deve vedere su cosa si
regge ogni risposta.
"""

from __future__ import annotations

import json
from pathlib import Path

EVALS = Path(__file__).resolve().parents[1]
DATA = json.loads((EVALS / "l2_semantic" / "calibration_discovery.json").read_text(encoding="utf-8"))
GOLDEN = EVALS.parent / "golden"


def test_every_item_points_to_a_golden_case_and_says_why():
    for item in DATA["items"]:
        assert (GOLDEN / item["case"] / "sources").is_dir(), item["case"]
        assert isinstance(item["necessary"], bool), item["question"]
        assert item["why"].strip(), item["question"]


def test_both_answers_are_represented_in_every_case():
    for case in {item["case"] for item in DATA["items"]}:
        labels = {item["necessary"] for item in DATA["items"] if item["case"] == case}
        assert labels == {True, False}, f"{case}: serve almeno una domanda necessaria e una no"


def test_the_set_is_draft_until_a_consultant_signs_it():
    assert DATA["status"] in {"draft_da_validare", "validated"}
