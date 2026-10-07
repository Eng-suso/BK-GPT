"""Import di event log reali: lettura, mapping completo, qualita', KPI, abbinamento al BPMN."""

from collections import Counter
from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from pydantic import ValidationError

from backend.eventlog.bpmn_match import ModelElement, apply_confirmed, normalize, suggest_matches
from backend.eventlog.kpi import summarize, timing
from backend.eventlog.mapping import AttributeColumn, ColumnMapping, MappingError, NumberFormat, TimestampFormat, apply_mapping
from backend.eventlog.readers import EventLogFileError, read_csv, read_table, read_xes

ROME = ZoneInfo("Europe/Rome")

# Export "all'italiana": punto e virgola, date gg/mm/aaaa, virgola decimale.
ERP_CSV = """Ordine;Riga;Attivita;Inizio;Fine;Utente;Importo;Paese
PO-1;1;Ricevi richiesta;05/01/2026 09:00;05/01/2026 09:10;anna;1.200,50;IT
PO-1;1;Approva ordine;05/01/2026 11:00;05/01/2026 11:30;marco;1.200,50;IT
PO-1;1;Paga fornitore;06/01/2026 10:00;06/01/2026 10:05;anna;1.200,50;IT
PO-2;1;Ricevi richiesta;05/01/2026 09:30;05/01/2026 09:45;luca;300;DE
PO-2;1;Paga fornitore;05/01/2026 14:00;05/01/2026 14:20;anna;300;FR
PO-2;1;Paga fornitore;05/01/2026 14:00;05/01/2026 14:20;anna;300;FR
;1;Ricevi richiesta;05/01/2026 09:30;05/01/2026 09:45;luca;300;DE
PO-3;1;Ricevi richiesta;ieri;05/01/2026 09:45;luca;300;DE
PO-4;1;Ricevi richiesta;05/01/2026 10:00;05/01/2026 09:00;luca;abc;DE
"""

ERP_MAPPING = ColumnMapping(
    case_id=("Ordine", "Riga"),
    activity=("Attivita",),
    start="Inizio",
    end="Fine",
    resource="Utente",
    case_attributes=(
        AttributeColumn(column="Importo", name="importo", type="number"),
        AttributeColumn(column="Paese", name="paese", type="category"),
    ),
    timestamps=TimestampFormat(pattern="%d/%m/%Y %H:%M"),
    numbers=NumberFormat(decimal=",", thousands="."),
)


def _import(text: str = ERP_CSV, mapping: ColumnMapping = ERP_MAPPING):
    return apply_mapping(read_csv(text.encode("utf-8")), mapping, source_name="erp.csv")


# --------------------------------------------------------------------------- #
# Lettura
# --------------------------------------------------------------------------- #


def test_the_semicolon_of_an_italian_export_is_recognised():
    table = read_csv(ERP_CSV.encode("utf-8"))

    assert table.delimiter == ";"
    assert table.header[:3] == ("Ordine", "Riga", "Attivita")
    assert len(table.rows) == 9


def test_bom_and_windows_encoding_are_read():
    assert read_csv("﻿caso,attività\nA,Approvazione\n".encode("utf-8")).header == ("caso", "attività")
    assert read_csv("caso;attività\nA;Approvazione\n".encode("cp1252")).header == ("caso", "attività")


@pytest.mark.parametrize(
    "payload, message",
    [
        (b"", "vuoto"),
        (b"solo\nuna\ncolonna\n", "una sola colonna"),
        (b"a,a,b\n1,2,3\n", "stesso nome"),
    ],
)
def test_a_file_that_is_not_a_table_says_why(payload, message):
    with pytest.raises(EventLogFileError, match=message):
        read_csv(payload)


XES = b"""<?xml version="1.0" encoding="UTF-8"?>
<log xmlns="http://www.xes-standard.org/">
  <trace>
    <string key="concept:name" value="C1"/>
    <string key="tipo" value="premium"/>
    <event>
      <string key="concept:name" value="Ricevi"/>
      <string key="lifecycle:transition" value="start"/>
      <date key="time:timestamp" value="2026-01-05T09:00:00+01:00"/>
      <string key="org:resource" value="anna"/>
    </event>
    <event>
      <string key="concept:name" value="Ricevi"/>
      <string key="lifecycle:transition" value="complete"/>
      <date key="time:timestamp" value="2026-01-05T09:20:00+01:00"/>
    </event>
    <event>
      <string key="concept:name" value="Paga"/>
      <string key="lifecycle:transition" value="start"/>
      <date key="time:timestamp" value="2026-01-05T10:00:00+01:00"/>
    </event>
  </trace>
</log>"""


def test_xes_is_flattened_with_trace_attributes_as_case_columns():
    table = read_xes(XES)

    assert {"case:concept:name", "case:tipo", "concept:name", "time:timestamp"} <= set(table.header)
    assert len(table.rows) == 3


def test_xes_with_entities_is_refused_not_expanded():
    hostile = b"""<?xml version="1.0"?><!DOCTYPE log [<!ENTITY x SYSTEM "file:///etc/passwd">]>
<log><trace><string key="concept:name" value="&x;"/></trace></log>"""

    with pytest.raises(EventLogFileError, match="non ammessi"):
        read_xes(hostile)


def test_unsupported_formats_are_refused():
    with pytest.raises(EventLogFileError, match="CSV o XES"):
        read_table("log.xlsx", b"x")


# --------------------------------------------------------------------------- #
# Mapping completo
# --------------------------------------------------------------------------- #


def test_the_full_mapping_builds_canonical_events():
    log, _ = _import()

    first = log.cases()["PO-1 · 1"][0]
    assert first.activity == "Ricevi richiesta"
    assert first.start == datetime(2026, 1, 5, 9, 0, tzinfo=ROME)
    assert first.end == datetime(2026, 1, 5, 9, 10, tzinfo=ROME)
    assert first.resource == "anna"
    assert log.case_attributes["PO-1 · 1"] == {"importo": 1200.5, "paese": "IT"}
    assert log.origin == "real"


def test_every_excluded_row_is_counted_with_its_line_in_the_file():
    _, report = _import()
    issues = {issue.code: issue for issue in report.issues}

    assert issues["missing_case_id"].rows == [8]
    assert issues["unreadable_timestamp"].rows == [9]
    assert issues["end_before_start"].rows == [10]
    assert issues["duplicate_event"].count == 1
    assert report.rows_read == 9
    assert report.events == 5
    assert report.cases == 2
    assert report.rows_excluded == 3


def test_a_case_attribute_that_changes_inside_a_case_is_flagged_and_the_first_kept():
    log, report = _import()

    assert log.case_attributes["PO-2 · 1"]["paese"] == "DE"
    assert "case_attribute_conflict" in {issue.code for issue in report.issues}


def test_the_report_covers_period_activities_and_resources():
    _, report = _import()

    assert report.period_start == datetime(2026, 1, 5, 9, 0, tzinfo=ROME)
    assert report.period_end == datetime(2026, 1, 6, 10, 5, tzinfo=ROME)
    assert (report.activities, report.resources) == (3, 3)
    assert report.events_without_start == 0


def test_lifecycle_transitions_are_paired_into_executions():
    mapping = ColumnMapping(
        case_id=("case:concept:name",),
        activity=("concept:name",),
        timestamp="time:timestamp",
        lifecycle="lifecycle:transition",
        resource="org:resource",
        case_attributes=(AttributeColumn(column="case:tipo", name="tipo", type="category"),),
    )

    log, report = apply_mapping(read_xes(XES), mapping)

    (receive,) = log.events
    assert receive.start == datetime.fromisoformat("2026-01-05T09:00:00+01:00")
    assert receive.end == datetime.fromisoformat("2026-01-05T09:20:00+01:00")
    assert receive.resource == "anna"  # dalla transizione di inizio
    assert [issue.code for issue in report.issues] == ["unpaired_start"]
    assert log.case_attributes["C1"] == {"tipo": "premium"}


def test_columns_missing_from_the_file_are_named():
    mapping = ERP_MAPPING.model_copy(update={"resource": "Operatore"})

    with pytest.raises(MappingError, match="Operatore"):
        _import(mapping=mapping)


@pytest.mark.parametrize(
    "fields, message",
    [
        ({"case_id": ("c",), "activity": ("a",)}, "colonna di fine"),
        ({"case_id": ("c",), "activity": ("a",), "end": "e", "timestamp": "t"}, "colonna di fine"),
        ({"case_id": ("c",), "activity": ("a",), "end": "e", "lifecycle": "l"}, "ciclo di vita"),
        ({"case_id": ("c",), "activity": ("a",), "end": "e",
          "timestamps": {"timezone": "Marte/Olimpo"}}, "fuso orario"),
        ({"case_id": ("c",), "activity": ("a",), "end": "e",
          "numbers": {"decimal": ",", "thousands": ","}}, "diversi"),
    ],
)
def test_an_inconsistent_mapping_is_refused_with_the_reason(fields, message):
    with pytest.raises(ValidationError, match=message):
        ColumnMapping(**fields)


# --------------------------------------------------------------------------- #
# KPI
# --------------------------------------------------------------------------- #


def test_kpis_use_the_same_definitions_as_the_simulation():
    log, _ = _import()

    summary = summarize(log)

    # PO-1: 05/01 09:00 -> 06/01 10:05 = 25h05m; PO-2: 09:30 -> 14:20 = 4h50m.
    po1, po2 = 25 * 3600 + 5 * 60, 4 * 3600 + 50 * 60
    assert summary["casesCompleted"] == 2
    assert summary["cycle"]["avg"] == pytest.approx((po1 + po2) / 2)
    assert summary["cycle"]["p95"] <= po1
    assert summary["timing"] == "start_and_end"
    assert summary["source"] == "real"


def test_what_a_real_log_does_not_know_is_absent_not_zero():
    log, _ = _import()

    summary = summarize(log)

    assert summary["cost"] is None
    assert summary["byResource"] == []
    assert "prosimosCrossCheck" not in summary


def test_a_log_with_only_completions_declares_it():
    mapping = ERP_MAPPING.model_copy(update={"start": None})
    log, report = _import(mapping=mapping)

    assert timing(log) == "complete_only"
    assert report.events_without_start == report.events
    assert summarize(log)["waiting"]["avg"] == 0


def test_event_costs_sum_into_the_case_cost():
    text = "caso,attivita,fine,costo\nA,X,2026-01-05T10:00:00,12.5\nA,Y,2026-01-05T11:00:00,7.5\n"
    mapping = ColumnMapping(case_id=("caso",), activity=("attivita",), end="fine", cost="costo")

    log, _ = apply_mapping(read_csv(text.encode()), mapping)

    assert summarize(log)["cost"] == {"total": 20.0, "perCase": 20.0, "eventsWithCost": 2}


# --------------------------------------------------------------------------- #
# Abbinamento al BPMN
# --------------------------------------------------------------------------- #

ELEMENTS = [
    ModelElement("T1", "Ricevi richiesta"),
    ModelElement("T2", "Approvazione ordine"),
    ModelElement("T3", "Paga fornitore"),
    ModelElement("T4", "Archivia"),
]


def test_identical_names_match_even_with_case_accents_and_spaces():
    assert normalize("  Àpprova   l'ordine! ") == "approva l ordine"

    report = suggest_matches(Counter({"ricevi  RICHIESTA": 3, "Paga fornitore": 2}), ELEMENTS)

    assert report.mapping() == {"ricevi  RICHIESTA": "T1", "Paga fornitore": "T3"}


def test_similar_but_different_names_are_left_to_the_consultant():
    report = suggest_matches(Counter({"Approva ordine": 5}), ELEMENTS)

    assert report.mapping() == {}
    assert report.unmatched_activities == ("Approva ordine",)
    assert {e.element_id for e in report.unobserved_elements} == {"T1", "T2", "T3", "T4"}


def test_two_elements_with_the_same_name_are_ambiguous():
    elements = [ModelElement("A", "Verifica"), ModelElement("B", "Verifica")]

    (match,) = suggest_matches(Counter({"Verifica": 1}), elements).matches

    assert match.reason == "ambiguous" and match.element_id is None


def test_the_confirmed_mapping_only_points_to_existing_elements():
    counts = Counter({"Approva ordine": 5, "Rumore": 1})

    report = apply_confirmed(counts, ELEMENTS, {"Approva ordine": "T2", "Rumore": None})

    assert report.mapping() == {"Approva ordine": "T2"}
    assert report.unmatched_activities == ("Rumore",)
    with pytest.raises(ValueError, match="T9"):
        apply_confirmed(counts, ELEMENTS, {"Approva ordine": "T9"})
