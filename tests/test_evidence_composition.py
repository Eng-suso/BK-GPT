"""FOLLOW-UP V3 — cosa una frase attribuita a piu' fonti puo' contenere.

Il primo giro di fix ha sistemato l'attribuzione, la provenance, lo scope e la
classificazione delle divergenze. Restava un difetto di **composizione**: la
corroborazione si contava sul soggetto, quindi due fonti che parlavano di
autorizzazione risultavano concordi sull'autorizzazione, e la sintesi ne
scriveva una frase sola attribuita a entrambe - ereditando proprieta' che ne
aveva detta una:

- "prima dell'ordine Acquisti verifica che la spesa sia autorizzata" attribuito
  anche a chi dichiarava di non conoscere la policy;
- "puo' contattare direttamente un fornitore conosciuto" attribuito anche a chi
  aveva parlato solo di contatto diretto;
- "non esistono tempi medi del processo" da due assenze di dato locali.

Le tre invarianti qui sotto sono quelle che lo impediscono, e sono
deterministiche: gli attributi sono dichiarati sul claim, non dedotti dal testo
a valle. Nessuna asserzione dipende da chi siano le persone del dataset.
"""

from __future__ import annotations

from backend.memory import provenance


def _stance(**kwargs) -> dict:
    base = {
        "source_name": "",
        "attributed_to": "",
        "statement": "",
        "epistemic_status": "reported",
        "scope_label": "",
        "qualifiers": [],
    }
    return {**base, **kwargs}


def _claim(**kwargs) -> dict:
    base = {
        "claim": "",
        "process_area": "activity",
        "source_name": "",
        "attributed_to": "",
        "topic": "",
        "assertion": "",
        "qualifiers": [],
        "quote": "",
        "scope_label": "",
        "scope_level": "stated_scope",
        "epistemic_status": "reported",
    }
    return {**base, **kwargs}


# --- A. Autorizzazione: una proprieta' la dice una fonte sola --------------


def test_a_property_only_one_source_states_is_not_credited_to_both():
    """Due fonti parlano di autorizzazione; una sola dice che la verifica
    formale avviene prima dell'ordine. Quella proprieta' non puo' comparire in
    una frase attribuita a entrambe."""
    verdict = provenance.verify_corroboration(
        "autorizzazione della spesa",
        "corroborated",
        [
            _stance(
                attributed_to="Ufficio Acquisti",
                statement="Sopra soglia chiedo l'autorizzazione al responsabile.",
                scope_label="Ufficio Acquisti",
                qualifiers=["verifica formale prima dell'ordine"],
            ),
            _stance(
                attributed_to="Capo Manutenzione",
                statement="Sulle piccole spese l'autorizzazione e' informale.",
                scope_label="Manutenzione",
            ),
        ],
        shared_statement=(
            "Prima dell'ordine Acquisti verifica formalmente che la spesa sia autorizzata."
        ),
    )

    assert not verdict.composition_ok
    assert verdict.rejected
    leaked = verdict.composition.leaked
    assert list(leaked) == ["Ufficio Acquisti"]
    assert "verifica formale prima dell'ordine" in leaked["Ufficio Acquisti"]


def test_the_shared_part_of_the_same_subject_can_still_be_corroborated():
    """Il controllo non deve impedire di dire cio' che entrambe dicono."""
    verdict = provenance.verify_corroboration(
        "autorizzazione della spesa",
        "corroborated",
        [
            _stance(
                attributed_to="Ufficio Acquisti",
                scope_label="Ufficio Acquisti",
                qualifiers=["verifica formale prima dell'ordine"],
            ),
            _stance(attributed_to="Capo Manutenzione", scope_label="Manutenzione"),
        ],
        shared_statement="Sopra una certa soglia esiste un passaggio autorizzativo.",
    )

    assert verdict.composition_ok
    assert verdict.effective_support == "corroborated"


def test_the_owner_of_each_exclusive_attribute_is_reported_back():
    """Non basta rifiutare: chi chiama deve sapere di chi e' l'attributo, per
    poterlo dire attribuito invece di toglierlo."""
    verdict = provenance.verify_corroboration(
        "autorizzazione della spesa",
        "corroborated",
        [
            _stance(attributed_to="A", qualifiers=["verifica formale"]),
            _stance(attributed_to="B", qualifiers=["autorizzazione a voce"]),
        ],
        shared_statement="Esiste un passaggio autorizzativo.",
    )

    assert verdict.attribute_owners["A"] == ("verifica formale",)
    assert verdict.attribute_owners["B"] == ("autorizzazione a voce",)


# --- B. Urgenze: nucleo corroborato, attributo di chi lo dice --------------


def test_a_shared_core_is_corroborated_while_an_extra_attribute_stays_owned():
    stances = [
        _stance(
            attributed_to="Capo Manutenzione",
            statement="Chiamo direttamente un fornitore che conosco.",
            qualifiers=["fornitore gia' conosciuto"],
        ),
        _stance(
            attributed_to="Ufficio Acquisti",
            statement="Capita che il reparto contatti direttamente il fornitore.",
        ),
    ]

    core = provenance.shared_core(stances)
    shared_ok = provenance.verify_corroboration(
        "percorso urgente",
        "corroborated",
        stances,
        shared_statement="Il reparto puo' contattare direttamente il fornitore.",
    )
    leaked = provenance.verify_corroboration(
        "percorso urgente",
        "corroborated",
        stances,
        shared_statement=(
            "Il reparto puo' contattare direttamente un fornitore gia' conosciuto."
        ),
    )

    assert core.shared == ()
    assert core.exclusive["Capo Manutenzione"] == ("fornitore gia' conosciuto",)
    assert shared_ok.composition_ok
    assert shared_ok.effective_support == "corroborated"
    assert not leaked.composition_ok
    assert leaked.composition.leaked["Capo Manutenzione"]


def test_an_attribute_both_sources_state_is_shared_and_may_be_said_together():
    stances = [
        _stance(attributed_to="A", qualifiers=["contatto telefonico"]),
        _stance(attributed_to="B", qualifiers=["contatto telefonico", "senza ordine"]),
    ]

    core = provenance.shared_core(stances)
    verdict = provenance.verify_corroboration(
        "percorso urgente",
        "corroborated",
        stances,
        shared_statement="Il contatto telefonico con il fornitore e' la prassi.",
    )

    assert core.shared == ("contatto telefonico",)
    assert core.exclusive == {"B": ("senza ordine",)}
    assert verdict.composition_ok


def test_a_reworded_exclusive_attribute_is_still_caught():
    """La sintesi riformula: il controllo non puo' fermarsi alla sottostringa."""
    verdict = provenance.verify_corroboration(
        "percorso urgente",
        "corroborated",
        [
            _stance(attributed_to="A", qualifiers=["fornitore gia' conosciuto"]),
            _stance(attributed_to="B"),
        ],
        shared_statement="Si contatta un fornitore conosciuto dal reparto.",
    )

    assert not verdict.composition_ok


def test_an_attribute_of_a_voice_that_does_not_support_the_topic_is_ignored():
    """Chi dichiara di non sapere non porta attributi dentro il nucleo."""
    core = provenance.shared_core(
        [
            _stance(attributed_to="A", qualifiers=["fornitore conosciuto"]),
            _stance(
                attributed_to="B",
                epistemic_status="declared_unknown",
                qualifiers=["contratto quadro"],
            ),
        ]
    )

    assert core.voices == ("A",)
    assert "B" not in core.exclusive


# --- C. Tempi: un'assenza locale non e' un'assenza di processo -------------


def test_two_local_absences_do_not_become_a_process_wide_absence():
    """Ognuno dice di non avere un dato per il proprio pezzo. Non dimostra che
    il processo non ce l'abbia."""
    verdict = provenance.verify_corroboration(
        "tempi e volumi",
        "declared_unknown",
        [
            _stance(
                attributed_to="Responsabile Ufficio Tecnico",
                statement="Non ho i tempi di verifica delle fatture.",
                scope_label="Ufficio Tecnico",
            ),
            _stance(
                attributed_to="Capo Manutenzione",
                statement="Non so quante urgenze facciamo in un mese.",
                scope_label="Manutenzione",
            ),
        ],
        shared_statement="Non esistono tempi medi del processo.",
        asserted_scope_level="whole_process",
    )

    assert verdict.rejected
    assert any("intero processo" in reason for reason in verdict.reasons)


def test_a_conclusion_kept_inside_its_scope_is_not_flagged():
    verdict = provenance.verify_corroboration(
        "tempi e volumi",
        "declared_unknown",
        [
            _stance(attributed_to="A", scope_label="Ufficio Tecnico"),
            _stance(attributed_to="B", scope_label="Manutenzione"),
        ],
        shared_statement="Nessuno dei due reparti misura i propri tempi.",
        asserted_scope_level="stated_scope",
    )

    assert not verdict.rejected


def test_a_process_wide_conclusion_backed_by_process_wide_evidence_stands():
    """Il guardrail non deve impedire una conclusione davvero di processo."""
    verdict = provenance.verify_corroboration(
        "tempi e volumi",
        "corroborated",
        [
            _stance(attributed_to="A", statement="Il gestionale non traccia i tempi."),
            _stance(attributed_to="B", statement="Nessun sistema misura i tempi."),
        ],
        shared_statement="Nessun sistema misura i tempi del processo.",
        asserted_scope_level="whole_process",
    )

    assert not verdict.rejected


# --- il registro tiene separato il nucleo dagli attributi di ciascuno ------


def test_the_ledger_separates_shared_core_from_source_specific_attributes():
    entries = provenance.build_ledger(
        [
            _claim(
                claim="Il reparto contatta direttamente il fornitore.",
                assertion="il reparto contatta direttamente il fornitore",
                attributed_to="Capo Manutenzione",
                source_name="Intervista A",
                qualifiers=["fornitore gia' conosciuto"],
            ),
            _claim(
                claim="Capita che il reparto chiami il fornitore da solo.",
                assertion="il reparto contatta direttamente il fornitore",
                attributed_to="Ufficio Acquisti",
                source_name="Intervista B",
            ),
        ]
    )
    by_voice = {entry.claim.voice: entry for entry in entries}

    assert {entry.support for entry in entries} == {"corroborated"}
    assert by_voice["Capo Manutenzione"].exclusive_qualifiers == ("fornitore gia' conosciuto",)
    assert by_voice["Ufficio Acquisti"].exclusive_qualifiers == ()
    assert all(entry.shared_qualifiers == () for entry in entries)


def test_the_rendered_section_attributes_an_extra_attribute_to_its_source():
    entries = provenance.build_ledger(
        [
            _claim(
                claim="Il reparto contatta direttamente il fornitore.",
                assertion="contatto diretto col fornitore",
                attributed_to="Capo Manutenzione",
                qualifiers=["fornitore gia' conosciuto"],
            ),
            _claim(
                claim="Capita che il reparto chiami il fornitore.",
                assertion="contatto diretto col fornitore",
                attributed_to="Ufficio Acquisti",
            ),
        ]
    )
    section = provenance.render_provenance_section(entries)

    assert "solo Capo Manutenzione: fornitore gia' conosciuto" in section
    assert "solo Ufficio Acquisti" not in section


def test_a_single_source_claim_keeps_its_attributes_attached_to_it():
    """Fuori da un gruppo corroborato ogni attributo e' della sua fonte, e va
    detto: cosi' a valle non si assume che sia condiviso."""
    entries = provenance.build_ledger(
        [
            _claim(
                claim="Si chiama un fornitore noto.",
                assertion="contatto diretto col fornitore",
                attributed_to="Capo Manutenzione",
                qualifiers=["fornitore gia' conosciuto"],
            )
        ]
    )

    assert entries[0].support == "single_source"
    assert entries[0].exclusive_qualifiers == ("fornitore gia' conosciuto",)
