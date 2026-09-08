"""FOLLOW-UP V3 bis — il controllo arriva fino alla frase che il consulente legge.

Il giro precedente aveva messo l'invariante di composizione dentro
`synthesize_process_evidence`. Non bastava: quel tool l'agente puo' non
chiamarlo, e la prosa finale la scrive un altro nodo. La frase multi-fonte
tornava a formarsi all'ultimo passaggio, dove nessuno la guardava:

- "Piu' fonti concordano sul fatto che un'autorizzazione debba esserci, anche
  per importi ridotti" - l'"anche per importi ridotti" lo dice una sola voce;
- l'intero blocco delle urgenze attribuito a due voci quando la seconda ne
  sostiene solo una parte.

E un terzo difetto, diverso: cio' che compariva fra virgolette non era il
verbatim dell'intervista ma la copia normalizzata del claim. Una citazione
riscritta non e' la prova di niente.

Qui si verificano le tre cose sul testo prodotto, senza database e senza LLM.
"""

from __future__ import annotations

from pathlib import Path

from backend.memory import provenance

FIXTURES = Path(__file__).parent / "fixtures" / "interviews"


def _source(name: str) -> str:
    return (FIXTURES / name).read_text(encoding="utf-8")


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


AUTHORISATION = (
    _claim(
        claim="Sopra una certa cifra serve una autorizzazione del responsabile.",
        assertion="sopra soglia serve una autorizzazione",
        attributed_to="Francesca Neri",
        source_name="Intervista Acquisti",
        # Solo Acquisti dice che vale anche sugli importi ridotti.
        qualifiers=["anche per importi ridotti"],
        scope_label="Ufficio Acquisti",
    ),
    _claim(
        claim="Sulle piccole spese l'autorizzazione e' meno formalizzata.",
        assertion="sopra soglia serve una autorizzazione",
        attributed_to="Paolo Marchetti",
        source_name="Intervista Manutenzione",
        scope_label="Manutenzione",
    ),
)

URGENCY = (
    _claim(
        claim="In urgenza il reparto chiama direttamente il fornitore.",
        assertion="in urgenza il reparto chiama direttamente il fornitore",
        attributed_to="Paolo Marchetti",
        source_name="Intervista Manutenzione",
        qualifiers=["ordine dei coinvolgimenti variabile"],
        scope_label="Manutenzione",
    ),
    _claim(
        claim="Capita che il reparto ordini da solo e si sistemi dopo.",
        assertion="in urgenza il reparto chiama direttamente il fornitore",
        attributed_to="Laura Conti",
        source_name="Intervista Ufficio Tecnico",
        scope_label="Ufficio Tecnico",
    ),
)


# --- A. una frase multi-fonte non puo' portarsi dentro l'attributo di una ---


def test_a_plural_claim_carrying_a_single_source_attribute_is_caught():
    """Il caso letterale del report: "piu' fonti concordano ... anche per
    importi ridotti", quando l'"anche per importi ridotti" lo dice una sola."""
    ledger = provenance.build_ledger(AUTHORISATION)

    violations = provenance.audit_answer(
        "Piu' fonti concordano sul fatto che un'autorizzazione debba esserci, "
        "anche per importi ridotti.",
        ledger,
    )

    assert violations
    assert violations[0].owner == "Francesca Neri"
    assert violations[0].qualifier == "anche per importi ridotti"


def test_the_shared_part_alone_passes():
    """Il controllo non deve impedire di dire cio' che entrambe dicono."""
    ledger = provenance.build_ledger(AUTHORISATION)

    assert not provenance.audit_answer(
        "Entrambi riferiscono che un passaggio autorizzativo esiste.", ledger
    )


def test_the_attribute_said_of_its_own_source_passes():
    """Attribuito a chi lo dice, l'attributo e' legittimo."""
    ledger = provenance.build_ledger(AUTHORISATION)

    assert not provenance.audit_answer(
        "Francesca Neri aggiunge che vale anche per importi ridotti.", ledger
    )


def test_naming_two_voices_counts_as_a_shared_claim():
    """Senza marcatori, ma con due nomi: e' comunque una frase di entrambi."""
    ledger = provenance.build_ledger(AUTHORISATION)

    violations = provenance.audit_answer(
        "Paolo Marchetti e Francesca Neri descrivono un'autorizzazione dovuta "
        "anche per importi ridotti.",
        ledger,
    )

    assert violations
    assert violations[0].owner == "Francesca Neri"


def test_a_first_name_is_enough_to_recognise_a_voice():
    """La prosa dice "Paolo", il registro "Paolo Marchetti"."""
    ledger = provenance.build_ledger(AUTHORISATION)

    assert provenance.audit_answer(
        "Paolo e Francesca concordano: l'autorizzazione serve anche per "
        "importi ridotti.",
        ledger,
    )


# --- B. il blocco delle urgenze: attribuito a due, sostenuto da uno --------


def test_a_block_attributed_to_two_voices_drops_what_only_one_supports():
    ledger = provenance.build_ledger(URGENCY)

    violations = provenance.audit_answer(
        "Laura Conti e Paolo Marchetti riferiscono il contatto diretto col "
        "fornitore, con un ordine dei coinvolgimenti variabile.",
        ledger,
    )

    assert [item.owner for item in violations] == ["Paolo Marchetti"]


def test_the_same_block_split_in_two_sentences_passes():
    """La correzione richiesta e' esattamente questa: nucleo condiviso, poi
    l'aggiunta attribuita."""
    ledger = provenance.build_ledger(URGENCY)

    assert not provenance.audit_answer(
        "Entrambi riferiscono il contatto diretto col fornitore. "
        "Paolo Marchetti aggiunge che l'ordine dei coinvolgimenti e' variabile.",
        ledger,
    )


def test_an_answer_without_shared_claims_is_never_flagged():
    ledger = provenance.build_ledger(URGENCY)

    assert not provenance.audit_answer(
        "Paolo Marchetti riferisce il contatto diretto col fornitore, con un "
        "ordine dei coinvolgimenti variabile.",
        ledger,
    )


def test_a_ledger_without_exclusive_attributes_has_nothing_to_check():
    ledger = provenance.build_ledger(
        [_claim(claim="x", assertion="p", attributed_to="A")]
    )

    assert provenance.audit_answer("A e B concordano su tutto.", ledger) == []


def test_the_runtime_says_who_owns_what_when_the_prose_stays_wrong():
    ledger = provenance.build_ledger(AUTHORISATION)
    violations = provenance.audit_answer(
        "Piu' fonti concordano, anche per importi ridotti.", ledger
    )

    notice = provenance.render_attribution_notice(violations)

    assert "Francesca Neri" in notice
    assert "anche per importi ridotti" in notice


# --- C. cio' che sta fra virgolette e' il testo della fonte ----------------


def test_the_stored_quote_is_the_source_own_characters():
    """Chi estrae ricopia a memoria: maiuscole e punteggiatura cambiano.

    Il passaggio che resta e' quello della fonte, altrimenti a valle finisce
    fra virgolette una versione riscritta.
    """
    text = _source("a2_paolo_marchetti_manutenzione.md")

    span = provenance.exact_span(
        "mail sempre mail a laura", text
    )

    # Il taglio e' esattamente il passaggio richiesto, con i caratteri
    # della fonte: "Mail." e "Laura" con le loro maiuscole.
    assert span == "Mail. Sempre mail, a Laura"


def test_a_quote_that_is_not_in_the_source_yields_no_span():
    text = _source("a2_paolo_marchetti_manutenzione.md")

    assert provenance.exact_span("Paolo invia la richiesta via email a Laura", text) == ""
    assert not provenance.quote_is_grounded(
        "Paolo invia la richiesta via email a Laura", text
    )


def test_the_excerpt_keeps_the_original_casing_and_punctuation():
    """L'audit ritagliava sul testo normalizzato: mostrava minuscolo e ripulito
    cio' che spacciava per verbatim."""
    text = _source("a1_laura_conti_ufficio_tecnico.md")

    excerpt = provenance.excerpt_around("La passo ad Acquisti.", text, window=120)

    assert "La passo ad Acquisti." in excerpt
    assert excerpt != excerpt.lower()


def test_a_span_survives_a_dropped_comma_but_not_a_rewrite():
    text = _source("a3_francesca_neri_acquisti.md")

    assert provenance.exact_span(
        "Mi arrivano via mail quasi sempre da Laura", text
    ).startswith("Mi arrivano via mail")
    assert provenance.exact_span(
        "Le richieste mi arrivano quasi sempre via posta elettronica", text
    ) == ""


def test_the_span_offsets_point_at_the_original_text():
    text = _source("a2_paolo_marchetti_manutenzione.md")

    found = provenance.locate_span("Mail. Sempre mail, a Laura.", text)

    assert found is not None
    assert text[found[0] : found[1]] == "Mail. Sempre mail, a Laura."


# --- il nodo che scrive la risposta applica il controllo -------------------
#
# E' il punto che mancava: l'invariante viveva in un tool che l'agente puo' non
# chiamare. Qui si verifica sul nodo che parla davvero al consulente.


def _report_state(ledger_claims) -> dict:
    from langchain_core.messages import HumanMessage

    return {
        "messages": [HumanMessage(content="Riassumi cosa e' emerso.")],
        "process_name": "Acquisti indiretti",
        "specialist_findings": [{"owner": "evidence", "finding": "Due interviste lette."}],
        "evidence_ledger": {"status": "ok", "claims": list(ledger_claims), "count": 2},
        "process_claims": [],
        "contradictions": [],
        "missing_information": [],
    }


def _answer(replies: list[str], claims) -> str:
    from langchain_core.language_models.fake_chat_models import GenericFakeChatModel
    from langchain_core.messages import AIMessage

    from backend.graphs.process.graph import build_process_report

    model = GenericFakeChatModel(messages=iter([AIMessage(content=r) for r in replies]))
    result = build_process_report(model)(_report_state(claims), None)
    return result["messages"][0].content


def test_the_report_asks_for_a_correction_and_delivers_the_corrected_prose():
    """Prima passata fonde le due fonti, la seconda separa: consegna la seconda."""
    answer = _answer(
        [
            "Piu' fonti concordano che l'autorizzazione serve anche per importi ridotti.",
            "Entrambi riferiscono che un passaggio autorizzativo esiste. "
            "Francesca Neri aggiunge che vale anche per importi ridotti.",
        ],
        AUTHORISATION,
    )

    assert "Francesca Neri aggiunge" in answer
    assert "Precisazione sull'attribuzione" not in answer


def test_the_report_says_who_owns_what_when_the_prose_stays_wrong():
    """Una correzione sola. Se la prosa resta fusa, il runtime lo scrive: meglio
    una nota esplicita che una frase che il consulente legge come vera."""
    answer = _answer(
        [
            "Piu' fonti concordano che l'autorizzazione serve anche per importi ridotti.",
            "Entrambi concordano: serve una autorizzazione anche per importi ridotti.",
        ],
        AUTHORISATION,
    )

    assert "Precisazione sull'attribuzione" in answer
    assert "lo riferisce solo Francesca Neri" in answer


def test_a_clean_answer_is_delivered_untouched():
    answer = _answer(
        ["Entrambi riferiscono che un passaggio autorizzativo esiste."],
        AUTHORISATION,
    )

    assert "Precisazione sull'attribuzione" not in answer
    assert "Da dove viene" in answer


def test_a_singular_attribution_is_not_read_as_an_agreement():
    """"Francesca conferma X" attribuisce a una voce: non e' un accordo, e non
    deve far scattare il controllo su una frase corretta."""
    ledger = provenance.build_ledger(AUTHORISATION)

    assert not provenance.audit_answer(
        "Il documento interno conferma la soglia.", ledger
    )
