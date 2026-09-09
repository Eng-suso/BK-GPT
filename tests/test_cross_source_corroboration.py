"""V3 residuo — parlare dello stesso argomento non e' concordare.

Il giro precedente aveva separato soggetto, proposizione e attributi sul claim,
e aveva messo il controllo di composizione sulla risposta finale. Restava
scoperto il passaggio in mezzo: la proposizione la scrive l'estrattore, e
bastava che raggruppasse per argomento perche' due fonti risultassero d'accordo
su qualcosa che nessuna delle due aveva detto insieme all'altra. Nel test V3 il
consulente ha letto "Paolo + Francesca | Corroborato" su:

- il trigger del processo, dove Paolo parla del fabbisogno di reparto e
  Francesca del momento in cui Acquisti prende in carico;
- i canali della richiesta, dove telefono e voce li dice solo Francesca;
- la responsabilita' autorizzativa obbligatoria, che e' una regola di Acquisti
  mentre la Manutenzione descrive una prassi meno formalizzata.

Due invarianti, entrambe verificate qui senza modello e senza database:

1. una fonte corrobora una proposizione solo se le sue parole la reggono;
2. una risposta che dichiara un accordo deve poterlo mostrare nel registro.

Il materiale ha nomi e frasi realistici, ma nessuna asserzione dipende da loro:
le stesse regole valgono per qualunque dataset.
"""

from __future__ import annotations

import pytest

from backend.memory import provenance


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
        "quote_verified": False,
        "scope_label": "",
        "scope_level": "stated_scope",
        "epistemic_status": "reported",
    }
    return {**base, **kwargs}


def _entry(entries: list[provenance.LedgerEntry], voice: str) -> provenance.LedgerEntry:
    return next(item for item in entries if item.claim.voice == voice)


# --- 1. sovrapposizione parziale: il nucleo si corrobora, l'estensione no ---


CHANNELS = (
    _claim(
        claim="La richiesta di acquisto arriva per email.",
        assertion="la richiesta di acquisto arriva per email",
        attributed_to="Paolo Rinaldi",
        source_name="Intervista Manutenzione",
        scope_label="Manutenzione",
    ),
    _claim(
        claim="La richiesta di acquisto arriva per email, e a volte per telefono.",
        assertion="la richiesta di acquisto arriva per email",
        attributed_to="Francesca Bianchi",
        source_name="Intervista Acquisti",
        qualifiers=["anche per telefono"],
        scope_label="Ufficio Acquisti",
    ),
)


def test_the_shared_channel_is_corroborated_while_the_extra_one_stays_owned():
    """Email la dicono entrambi; il telefono lo dice una sola."""
    entries = provenance.build_ledger(CHANNELS)

    assert {item.support for item in entries} == {"corroborated"}
    assert _entry(entries, "Francesca Bianchi").exclusive_qualifiers == ("anche per telefono",)
    assert _entry(entries, "Paolo Rinaldi").exclusive_qualifiers == ()
    assert all(item.shared_qualifiers == () for item in entries)


def test_the_extra_channel_cannot_be_said_in_a_sentence_that_names_both():
    entries = provenance.build_ledger(CHANNELS)

    violations = provenance.audit_answer(
        "Paolo Rinaldi e Francesca Bianchi riferiscono che la richiesta arriva "
        "per email e anche per telefono.",
        entries,
    )

    assert [item.kind for item in violations] == ["attribute_leak"]
    assert violations[0].owner == "Francesca Bianchi"


def test_the_shared_channel_alone_passes_the_audit():
    """Il controllo non deve impedire di dire cio' che e' davvero condiviso."""
    entries = provenance.build_ledger(CHANNELS)

    assert (
        provenance.audit_answer(
            "Paolo Rinaldi e Francesca Bianchi riferiscono che la richiesta "
            "arriva per email.",
            entries,
        )
        == []
    )


# --- 2. stesso argomento, proposizione diversa -----------------------------


AUTHORISATION = (
    _claim(
        claim="Deve esistere una responsabilita' autorizzativa anche per importi piccoli.",
        # L'estrattore ha messo le due voci sotto lo stesso enunciato: e' il
        # raggruppamento per argomento che il runtime deve poter smentire.
        assertion="deve esistere una responsabilita autorizzativa anche per importi piccoli",
        attributed_to="Francesca Bianchi",
        source_name="Intervista Acquisti",
        scope_label="Ufficio Acquisti",
    ),
    _claim(
        claim="Sulle spese piccole la Manutenzione procede senza passaggi formali.",
        assertion="deve esistere una responsabilita autorizzativa anche per importi piccoli",
        attributed_to="Paolo Rinaldi",
        source_name="Intervista Manutenzione",
        scope_label="Manutenzione",
    ),
)


def test_a_rule_and_a_practice_on_the_same_subject_are_not_corroboration():
    """Parlare di autorizzazioni non e' confermare la regola sulle autorizzazioni."""
    entries = provenance.build_ledger(AUTHORISATION)

    assert {item.support for item in entries} == {"single_source"}
    assert all(item.corroborating_sources == () for item in entries)


def test_the_voice_that_talks_about_it_without_confirming_stays_visible():
    """Lo scarto non e' una cancellazione: resta come prospettiva vicina."""
    entries = provenance.build_ledger(AUTHORISATION)

    assert _entry(entries, "Francesca Bianchi").same_topic_voices == ("Paolo Rinaldi",)


def test_an_answer_cannot_declare_that_agreement_anyway():
    entries = provenance.build_ledger(AUTHORISATION)

    violations = provenance.audit_answer(
        "| Autorizzazione | Deve esistere una responsabilita' autorizzativa | "
        "Paolo Rinaldi, Francesca Bianchi | Corroborato |",
        entries,
    )

    assert [item.kind for item in violations] == ["unsupported_agreement"]
    assert set(violations[0].voices_named) == {"Paolo Rinaldi", "Francesca Bianchi"}


def test_naming_two_voices_to_contrast_them_is_not_a_violation():
    """Mettere due posizioni una accanto all'altra e' esattamente cio' che serve."""
    entries = provenance.build_ledger(AUTHORISATION)

    assert (
        provenance.audit_answer(
            "Francesca Bianchi descrive una regola formale; Paolo Rinaldi "
            "descrive una prassi meno formalizzata.",
            entries,
        )
        == []
    )


# --- 3. ambiti funzionali diversi ------------------------------------------


TRIGGER = (
    _claim(
        claim="Il processo nasce da un fabbisogno operativo del reparto.",
        assertion="il processo nasce da un fabbisogno operativo del reparto",
        attributed_to="Paolo Rinaldi",
        source_name="Intervista Manutenzione",
        scope_label="Manutenzione",
    ),
    _claim(
        claim="Per Acquisti comincia quando arriva una richiesta abbastanza chiara da prendere in carico.",
        assertion="il processo nasce da un fabbisogno operativo del reparto",
        attributed_to="Francesca Bianchi",
        source_name="Intervista Acquisti",
        scope_label="Ufficio Acquisti",
    ),
)


def test_two_entry_points_of_two_departments_are_not_one_trigger():
    """Dove nasce e dove viene preso in carico sono due momenti, non un accordo."""
    entries = provenance.build_ledger(TRIGGER)

    assert {item.support for item in entries} == {"single_source"}
    assert _entry(entries, "Paolo Rinaldi").claim.scope_label == "Manutenzione"
    assert _entry(entries, "Francesca Bianchi").claim.scope_label == "Ufficio Acquisti"


# --- 4. attributo di una sola fonte ----------------------------------------


URGENCY = (
    _claim(
        claim="In urgenza il reparto contatta direttamente il fornitore.",
        assertion="in urgenza il reparto contatta direttamente il fornitore",
        attributed_to="Paolo Rinaldi",
        source_name="Intervista Manutenzione",
        qualifiers=["fornitore gia' conosciuto"],
        scope_label="Manutenzione",
    ),
    _claim(
        claim="Capita che in urgenza il reparto contatti direttamente il fornitore.",
        assertion="in urgenza il reparto contatta direttamente il fornitore",
        attributed_to="Laura Conti",
        source_name="Intervista Ufficio Tecnico",
        scope_label="Ufficio Tecnico",
    ),
)


def test_the_urgent_contact_is_corroborated_on_its_shared_core():
    entries = provenance.build_ledger(URGENCY)

    assert {item.support for item in entries} == {"corroborated"}


def test_the_known_supplier_stays_with_the_voice_that_said_it():
    entries = provenance.build_ledger(URGENCY)

    assert _entry(entries, "Paolo Rinaldi").exclusive_qualifiers == ("fornitore gia' conosciuto",)
    violations = provenance.audit_answer(
        "Paolo Rinaldi e Laura Conti concordano: in urgenza il reparto chiama "
        "un fornitore gia' conosciuto.",
        entries,
    )

    assert [item.kind for item in violations] == ["attribute_leak"]


# --- 5. una dichiarazione di non conoscenza non e' evidenza ----------------


THRESHOLDS = (
    _claim(
        claim="Sopra i cinquemila euro serve la firma del direttore acquisti.",
        assertion="sopra i cinquemila euro serve la firma del direttore acquisti",
        attributed_to="Francesca Bianchi",
        source_name="Intervista Acquisti",
        scope_label="Ufficio Acquisti",
    ),
    _claim(
        claim="Non conosco le soglie di autorizzazione.",
        assertion="sopra i cinquemila euro serve la firma del direttore acquisti",
        attributed_to="Paolo Rinaldi",
        source_name="Intervista Manutenzione",
        epistemic_status="declared_unknown",
        scope_label="Manutenzione",
    ),
)


def test_a_declared_unknown_neither_corroborates_nor_contradicts():
    entries = provenance.build_ledger(THRESHOLDS)

    assert _entry(entries, "Francesca Bianchi").support == "single_source"
    assert _entry(entries, "Paolo Rinaldi").support == "declared_unknown"
    assert all(item.contested_by == () for item in entries)


def test_a_declared_unknown_cannot_be_presented_as_agreement():
    """"Non lo so" non e' una posizione a sostegno di chi lo sa."""
    entries = provenance.build_ledger(THRESHOLDS)

    violations = provenance.audit_answer(
        "Paolo Rinaldi e Francesca Bianchi confermano la soglia dei cinquemila euro.",
        entries,
    )

    assert [item.kind for item in violations] == ["unsupported_agreement"]


def test_a_local_unknown_is_not_generalized_to_the_whole_process():
    verdict = provenance.verify_corroboration(
        "soglie di autorizzazione",
        "declared_unknown",
        [
            {"attributed_to": "Paolo Rinaldi", "scope_label": "Manutenzione"},
            {"attributed_to": "Laura Conti", "scope_label": "Ufficio Tecnico"},
        ],
        shared_statement="Il processo non ha soglie di autorizzazione.",
        asserted_scope_level="whole_process",
    )

    assert verdict.rejected
    assert any("intero processo" in reason for reason in verdict.reasons)


# --- la regola in se': quando una fonte regge davvero una proposizione -----


@pytest.mark.parametrize(
    ("assertion", "statement", "carried"),
    [
        (
            "sopra soglia serve una autorizzazione",
            "Sopra una certa soglia serve una autorizzazione del responsabile.",
            True,
        ),
        (
            "sopra soglia serve una autorizzazione",
            "Sulle piccole spese l'autorizzazione e' meno formalizzata.",
            False,
        ),
        # Una riformulazione che porta le stesse parole regge: il controllo non
        # chiede la frase identica, chiede che le parole ci siano.
        (
            "il reparto contatta direttamente il fornitore",
            "Capita che il reparto contatti direttamente un fornitore.",
            True,
        ),
        # Senza proposizione dichiarata non c'e' niente da smentire.
        ("", "Qualunque cosa la fonte abbia detto.", True),
    ],
)
def test_a_source_carries_an_assertion_only_when_its_words_do(assertion, statement, carried):
    assert provenance.statement_carries_assertion(assertion, statement) is carried


def test_an_abstract_assertion_nobody_words_keeps_the_declared_grouping():
    """Il controllo discrimina o si astiene: non deve spaccare una sintesi.

    Se l'enunciato e' una compressione che nessuna delle due fonti pronuncia,
    non c'e' segnale per dire quale delle due lo regge: resta il raggruppamento
    dichiarato, e la corroborazione la governano le altre regole.
    """
    entries = provenance.build_ledger(
        (
            _claim(
                claim="Chiamo il fornitore e mi faccio mandare il pezzo.",
                assertion="il percorso ordinario viene scavalcato",
                attributed_to="Paolo Rinaldi",
                source_name="Intervista Manutenzione",
            ),
            _claim(
                claim="Vedo l'acquisto solo dopo, dalla mail con il riferimento.",
                assertion="il percorso ordinario viene scavalcato",
                attributed_to="Francesca Bianchi",
                source_name="Intervista Acquisti",
            ),
        )
    )

    assert {item.support for item in entries} == {"corroborated"}
