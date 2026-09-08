"""PROCESS-V3 — le invarianti di provenance, senza database e senza modello.

Nel test E2E V3 la chat di processo ha attribuito a una persona cio' che aveva
detto un'altra, ha dichiarato accordo fra due fonti su un punto presente in una
sola, ha trasformato un "non lo so" in una contraddizione, ha generalizzato la
testimonianza di un reparto al processo intero e ha risposto a una richiesta di
audit con una nuova sintesi.

Ognuno di quei comportamenti era possibile perche' la regola stava nel prompt.
Qui si verifica che ora stia nel codice: `backend.memory.provenance` conta le
voci, riscontra le citazioni e declassa le divergenze senza chiedere niente a
nessun LLM. Le asserzioni sono sulle invarianti, non sui nomi delle persone del
dataset - Laura, Paolo e Francesca sono materiale, non logica.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from backend.memory import provenance

FIXTURES = Path(__file__).parent / "fixtures" / "interviews"


def _source(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


def _claim(**kwargs) -> dict:
    """Un claim come lo produce l'estrazione, con i default del contratto."""
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


# --- la citazione deve esistere nel testo, e non puo' essere piu' forte ----


def test_a_verbatim_span_is_grounded_in_its_source():
    text = _source("a3_francesca_neri_acquisti.md")

    assert provenance.quote_is_grounded(
        "Sopra una certa cifra devo chiedere una autorizzazione al mio responsabile",
        text,
    )


def test_a_span_copied_without_its_punctuation_is_still_the_same_span():
    """Ricopiare togliendo una virgola resta ricopiare."""
    text = _source("a2_paolo_marchetti_manutenzione.md")

    assert provenance.quote_is_grounded(
        "chiamo direttamente il fornitore mi faccio mandare il pezzo",
        text,
    )


def test_a_stronger_rewrite_is_not_a_quote():
    """Il difetto V3 sulla fedelta' semantica.

    La fonte dice che un passaggio esiste ma di non conoscerne i termini. Una
    sintesi puo' comprimerlo; se lo trasforma in un obbligo, non sta piu'
    citando - e il runtime deve poterlo dire, non fidarsi.
    """
    text = _source("a1_laura_conti_ufficio_tecnico.md")

    assert provenance.quote_is_grounded("sopra una certa cifra serve un passaggio in piu'", text)
    assert not provenance.quote_is_grounded(
        "sopra una certa cifra il responsabile deve confermare la spesa", text
    )


def test_a_word_is_not_a_citation():
    assert not provenance.quote_is_grounded("mail", _source("a2_paolo_marchetti_manutenzione.md"))


def test_a_quote_without_a_source_text_is_never_grounded():
    """Meglio dichiarare di non aver riscontrato che fingere di aver riscontrato."""
    assert not provenance.quote_is_grounded("qualsiasi cosa detta da qualcuno", "")


# --- il sostegno si conta, non si dichiara --------------------------------


def test_one_voice_on_a_topic_is_a_single_source():
    entries = provenance.build_ledger(
        [
            _claim(
                claim="Nelle urgenze si chiama direttamente il fornitore.",
                topic="gestione urgenze",
                source_name="Intervista A",
                attributed_to="Capo Manutenzione",
            )
        ]
    )

    assert [entry.support for entry in entries] == ["single_source"]


def test_two_distinct_voices_on_the_same_proposition_are_corroborated():
    entries = provenance.build_ledger(
        [
            _claim(
                claim="La richiesta passa all'ufficio acquisti via mail.",
                topic="passaggio ad acquisti",
                assertion="la richiesta arriva ad acquisti via mail",
                source_name="Intervista A",
                attributed_to="Responsabile Ufficio Tecnico",
            ),
            _claim(
                claim="Le richieste arrivano via mail dall'ufficio tecnico.",
                topic="passaggio ad acquisti",
                assertion="la richiesta arriva ad acquisti via mail",
                source_name="Intervista B",
                attributed_to="Ufficio Acquisti",
            ),
        ]
    )

    assert {entry.support for entry in entries} == {"corroborated"}
    assert all(entry.corroborating_sources for entry in entries)


def test_sharing_a_subject_is_not_agreeing_on_a_proposition():
    """Il difetto residuo V3: due fonti parlano di autorizzazione, ma non
    dicono la stessa cosa. Il soggetto in comune non le rende concordi."""
    entries = provenance.build_ledger(
        [
            _claim(
                claim="Acquisti verifica l'autorizzazione prima di emettere l'ordine.",
                topic="autorizzazione spesa",
                assertion="acquisti verifica l'autorizzazione prima dell'ordine",
                source_name="Intervista A",
                attributed_to="Ufficio Acquisti",
            ),
            _claim(
                claim="In Manutenzione le piccole spese si autorizzano a voce.",
                topic="autorizzazione spesa",
                assertion="in manutenzione le piccole spese si autorizzano a voce",
                source_name="Intervista B",
                attributed_to="Capo Manutenzione",
            ),
        ]
    )

    assert {entry.support for entry in entries} == {"single_source"}
    assert all(not entry.corroborating_sources for entry in entries)


def test_without_a_declared_proposition_two_claims_do_not_merge():
    """Fail closed: senza `assertion` due formulazioni restano due affermazioni."""
    entries = provenance.build_ledger(
        [
            _claim(claim="Le richieste arrivano via mail.", topic="canale", attributed_to="X"),
            _claim(claim="Il canale e' la posta elettronica.", topic="canale", attributed_to="Y"),
        ]
    )

    assert {entry.support for entry in entries} == {"single_source"}


def test_two_extractions_from_the_same_voice_are_not_two_sources():
    """La sovrapposizione inventata nasce qui: due righe, una voce sola."""
    entries = provenance.build_ledger(
        [
            _claim(
                claim="Sopra una certa cifra serve una autorizzazione.",
                topic="autorizzazione spesa",
                assertion="sopra soglia serve una autorizzazione",
                source_name="Intervista B",
                attributed_to="Ufficio Acquisti",
            ),
            _claim(
                claim="L'autorizzazione e' una mail che si aspetta.",
                topic="autorizzazione spesa",
                assertion="sopra soglia serve una autorizzazione",
                source_name="Intervista B",
                attributed_to="Ufficio Acquisti",
            ),
        ]
    )

    assert {entry.support for entry in entries} == {"single_source"}


def test_a_declared_unknown_never_corroborates_and_is_not_a_gap():
    """Chi dichiara di non sapere porta informazione su di se', non sostegno."""
    entries = provenance.build_ledger(
        [
            _claim(
                claim="Chi firma l'autorizzazione non e' noto a questa fonte.",
                topic="autorizzazione spesa",
                assertion="sopra soglia serve una autorizzazione",
                source_name="Intervista A",
                attributed_to="Responsabile Ufficio Tecnico",
                epistemic_status="declared_unknown",
            ),
            _claim(
                claim="Sopra una certa cifra serve una autorizzazione del responsabile.",
                topic="autorizzazione spesa",
                assertion="sopra soglia serve una autorizzazione",
                source_name="Intervista B",
                attributed_to="Ufficio Acquisti",
            ),
        ]
    )
    by_status = {entry.claim.epistemic_status: entry.support for entry in entries}

    assert by_status["declared_unknown"] == "declared_unknown"
    assert by_status["reported"] == "single_source"


def test_an_inference_is_labelled_as_one():
    entries = provenance.build_ledger(
        [_claim(claim="Esiste un controllo di budget.", epistemic_status="inferred")]
    )

    assert entries[0].support == "inferred"


def test_only_a_real_incompatibility_makes_a_claim_contested():
    claim = _claim(
        claim="L'ordine lo apre l'ufficio acquisti.",
        topic="chi regolarizza le urgenze",
        assertion="l'ordine a posteriori lo apre acquisti",
        source_name="Intervista B",
        attributed_to="Ufficio Acquisti",
    )

    contested = provenance.build_ledger(
        [claim],
        contested_topics={"l'ordine a posteriori lo apre acquisti": ["Chi apre l'ordine"]},
    )
    untouched = provenance.build_ledger([claim])

    assert contested[0].support == "contradicted"
    assert untouched[0].support == "single_source"


# --- lo scope resta attaccato all'affermazione ----------------------------


def test_the_scope_of_a_testimony_survives_the_ledger():
    entries = provenance.build_ledger(
        [
            _claim(
                claim="Le richieste partono da un giro impianti giornaliero.",
                topic="origine della richiesta",
                source_name="Intervista A",
                attributed_to="Capo Manutenzione",
                scope_label="Manutenzione",
            )
        ]
    )

    assert entries[0].claim.scope_label == "Manutenzione"
    assert entries[0].claim.scope_level == "stated_scope"
    assert "Manutenzione" in provenance.render_provenance_section(entries)


def test_whole_process_scope_is_only_the_declared_one():
    entry = provenance.claim_record(_claim(claim="x", scope_level="tutto"))

    assert entry.scope_level == "stated_scope"


# --- una divergenza non e' automaticamente una contraddizione -------------


def test_a_side_that_declares_it_does_not_know_is_not_a_contradiction():
    """Il caso V3: una parte non conosce la prassi, l'altra la descrive.

    Non e' un'incompatibilita': e' una lacuna di conoscenza. Il runtime
    declassa anche quando chi analizza ha dichiarato `incompatible`.
    """
    verdict = provenance.classify_divergence(
        "incompatible",
        [
            {
                "attributed_to": "Capo Manutenzione",
                "statement": "Non so chi regolarizzi la pratica dopo.",
                "epistemic_status": "declared_unknown",
            },
            {
                "attributed_to": "Ufficio Acquisti",
                "statement": "L'ordine lo apro io a posteriori.",
                "epistemic_status": "reported",
            },
        ],
    )

    assert verdict.effective == "knowledge_gap"
    assert verdict.downgraded
    assert not verdict.blocks_modeling


def test_two_departments_describing_their_own_practice_are_not_incompatible():
    verdict = provenance.classify_divergence(
        "incompatible",
        [
            {"attributed_to": "Capo Manutenzione", "scope_label": "Manutenzione"},
            {"attributed_to": "Ufficio Acquisti", "scope_label": "Acquisti"},
        ],
    )

    assert verdict.effective == "scope_difference"
    assert not verdict.blocks_modeling


def test_one_voice_alone_is_not_a_divergence_at_all():
    verdict = provenance.classify_divergence(
        "incompatible",
        [
            {"attributed_to": "Ufficio Acquisti", "statement": "a"},
            {"attributed_to": "Ufficio Acquisti", "statement": "b"},
        ],
    )

    assert verdict.effective == "single_source_uncertainty"


def test_a_real_incompatibility_survives_the_check():
    """Il declassamento non deve svuotare la funzione: due affermazioni
    positive, stesso ambito, restano incompatibili."""
    verdict = provenance.classify_divergence(
        "incompatible",
        [
            {
                "attributed_to": "Ufficio Acquisti",
                "statement": "Ogni ordine sopra soglia passa dal responsabile.",
                "epistemic_status": "reported",
                "scope_label": "Acquisti",
            },
            {
                "attributed_to": "Direzione",
                "statement": "Nessun ordine indiretto richiede una autorizzazione.",
                "epistemic_status": "reported",
                "scope_label": "Acquisti",
            },
        ],
    )

    assert verdict.effective == "incompatible"
    assert verdict.blocks_modeling
    assert not verdict.downgraded


def test_the_runtime_never_promotes_a_difference_to_a_contradiction():
    verdict = provenance.classify_divergence(
        "complementary",
        [
            {"attributed_to": "A", "statement": "x", "epistemic_status": "reported"},
            {"attributed_to": "B", "statement": "y", "epistemic_status": "reported"},
        ],
    )

    assert verdict.effective == "complementary"


# --- "le due fonti concordano" e' verificabile ----------------------------


def test_asserted_corroboration_without_two_voices_is_refused():
    verdict = provenance.verify_corroboration(
        "autorizzazione spesa",
        "corroborated",
        [{"attributed_to": "Ufficio Acquisti", "epistemic_status": "reported"}],
    )

    assert verdict.effective_support == "single_source"
    assert verdict.rejected
    assert verdict.reasons


def test_asserted_corroboration_backed_by_two_voices_stands():
    verdict = provenance.verify_corroboration(
        "passaggio ad acquisti",
        "corroborated",
        [
            {"attributed_to": "Ufficio Tecnico", "epistemic_status": "reported"},
            {"attributed_to": "Ufficio Acquisti", "epistemic_status": "reported"},
        ],
    )

    assert verdict.effective_support == "corroborated"
    assert not verdict.rejected


def test_a_voice_that_declares_it_does_not_know_does_not_count_towards_agreement():
    verdict = provenance.verify_corroboration(
        "autorizzazione spesa",
        "corroborated",
        [
            {"attributed_to": "Ufficio Tecnico", "epistemic_status": "declared_unknown"},
            {"attributed_to": "Ufficio Acquisti", "epistemic_status": "reported"},
        ],
    )

    assert verdict.effective_support == "single_source"


# --- la sezione di provenance e' stampata, non raccontata -----------------


def test_the_provenance_section_shows_claim_voice_and_original_words():
    entries = provenance.build_ledger(
        [
            _claim(
                claim="La parte amministrativa viene sistemata dopo.",
                topic="gestione urgenze",
                source_name="Intervista A",
                attributed_to="Capo Manutenzione",
                quote="la parte amministrativa viene sistemata dopo",
                quote_verified=True,
            )
        ]
    )
    section = provenance.render_provenance_section(entries)

    assert "La parte amministrativa viene sistemata dopo." in section
    assert "Capo Manutenzione" in section
    assert "la parte amministrativa viene sistemata dopo" in section
    assert provenance.SUPPORT_LABEL_IT["single_source"] in section


def test_an_unverified_quote_is_never_rendered_as_a_quotation():
    """Un passaggio riformulato messo fra virgolette sembra una prova e non lo
    e': meglio dichiarare che e' una riformulazione."""
    quote = "il responsabile deve confermare ogni spesa"
    entries = provenance.build_ledger(
        [
            _claim(
                claim="Il responsabile deve confermare ogni spesa.",
                source_name="Intervista A",
                attributed_to="Ufficio Tecnico",
                quote=quote,
                quote_verified=False,
            )
        ]
    )
    section = provenance.render_provenance_section(entries)

    assert f'"{quote}"' not in section
    assert "riformulazione" in section


def test_the_ledger_summary_counts_what_the_answer_may_claim():
    entries = provenance.build_ledger(
        [
            _claim(claim="a", assertion="p1", attributed_to="X"),
            _claim(claim="b", assertion="p1", attributed_to="Y"),
            _claim(claim="c", assertion="p2", attributed_to="X"),
            _claim(claim="d", assertion="p3", attributed_to="X", epistemic_status="declared_unknown"),
        ]
    )
    summary = provenance.summarize_ledger(entries)

    assert summary.total == 4
    assert summary.corroborated == 2
    assert summary.single_source == 1
    assert summary.declared_unknown == 1
    assert sorted(summary.voices) == ["X", "Y"]


# --- l'unita' di provenance non confonde la fonte con la voce -------------


def test_a_source_with_several_speakers_keeps_them_apart():
    """Un verbale di workshop e' una fonte sola con piu' voci.

    Contare per documento invece che per persona farebbe corroborare due
    affermazioni della stessa persona; contare per persona quando la persona
    non c'e' farebbe sparire il documento. Il record tiene entrambi.
    """
    first = provenance.claim_record(
        _claim(claim="a", source_name="Workshop 12/09", attributed_to="Capoturno")
    )
    second = provenance.claim_record(
        _claim(claim="b", source_name="Workshop 12/09", attributed_to="Magazzino")
    )
    anonymous = provenance.claim_record(_claim(claim="c", source_name="Procedura interna"))

    assert first.voice != second.voice
    assert anonymous.voice == "Procedura interna"


def test_the_topic_key_is_stable_across_wording_of_the_same_label():
    assert provenance.topic_key("Autorizzazione spesa") == provenance.topic_key(
        "  autorizzazione, spesa  "
    )


@pytest.mark.parametrize(
    "status", ["reported", "observed", "documented", "inferred", "declared_unknown"]
)
def test_every_epistemic_status_survives_the_record(status):
    assert provenance.claim_record(_claim(claim="x", epistemic_status=status)).epistemic_status == status


def test_an_unknown_epistemic_status_falls_back_to_reported():
    assert provenance.claim_record(_claim(claim="x", epistemic_status="certo")).epistemic_status == "reported"
