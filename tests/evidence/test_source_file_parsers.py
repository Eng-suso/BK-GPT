from __future__ import annotations

import io
import zipfile

import pytest
from openpyxl import Workbook

from backend.workspace_services.source_ingestion import SourceFileError, parse_source_file


def _workbook(value: str) -> bytes:
    workbook = Workbook()
    workbook.active["A1"] = value
    stream = io.BytesIO()
    workbook.save(stream)
    return stream.getvalue()


def _office_file(path: str, xml: str) -> bytes:
    stream = io.BytesIO()
    with zipfile.ZipFile(stream, "w") as archive:
        archive.writestr(path, xml)
    return stream.getvalue()


@pytest.mark.parametrize(
    ("name", "payload", "expected"),
    [
        ("note.md", b"# Ordini\nApprovazione CFO", "Approvazione CFO"),
        ("eventi.csv", b"case,activity\n1,Approve", "case\tactivity"),
        ("registro.xlsx", _workbook("Ordine 42"), "Ordine 42"),
    ],
)
def test_priority_formats_produce_readable_text(name: str, payload: bytes, expected: str):
    parsed = parse_source_file(name, payload, "application/octet-stream")
    assert expected in parsed.text
    assert len(parsed.content_hash) == 64


def test_a_malformed_csv_is_refused_not_a_crash():
    payload = b'case,note\n1,"' + b"x" * 200_000
    with pytest.raises(SourceFileError, match="CSV non"):
        parse_source_file("eventi.csv", payload, "text/csv")


def test_extension_and_content_are_both_checked():
    with pytest.raises(SourceFileError, match="PDF valido"):
        parse_source_file("falso.pdf", b"not a pdf", "application/pdf")
    with pytest.raises(SourceFileError, match="Formato non supportato"):
        parse_source_file("script.exe", b"MZ", "application/octet-stream")

    unsafe_docx = _office_file(
        "word/document.xml",
        '<!DOCTYPE x [<!ENTITY a "boom">]><w:document xmlns:w="urn:w"><w:t>&a;</w:t></w:document>',
    )
    with pytest.raises(SourceFileError, match="XML non sicuro"):
        parse_source_file("procedura.docx", unsafe_docx, None)


def test_xlsx_resolves_shared_string_indexes_into_cell_values():
    parsed = parse_source_file("registro.xlsx", _workbook("Ordine approvato"), None)
    assert "A=Ordine approvato" in parsed.text
    assert "A=0" not in parsed.text


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("Procedura_Acquisti_v3.pdf", ["process_evidence", "policy"]),
        ("ISO 9001 manuale qualita.docx", ["process_evidence", "policy"]),
        ("Verbale riunione COO.docx", ["process_evidence"]),
        ("intervista-paola-rinaldi.md", ["process_evidence"]),
        ("ordini_2026.xlsx", ["operational_data"]),
        ("eventi.csv", ["operational_data"]),
        ("presentazione.pptx", None),
        ("decisione steering.docx", None),
    ],
)
def test_a_role_is_proposed_from_the_name_and_the_format(name: str, expected: list[str] | None):
    from backend.workspace_services.source_ingestion import suggest_roles

    assert suggest_roles(name) == expected

