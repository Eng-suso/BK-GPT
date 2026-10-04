"""Validazione, custodia ed estrazione testuale dei file caricati in Fonti."""

from __future__ import annotations

import csv
import hashlib
import io
import re
from dataclasses import dataclass
from pathlib import Path

from backend.security import get_current_tenant_id
from backend.workspace_services.blob_store import (
    BlobKeyError,
    BlobNotFound,
    source_blob_store,
    source_key,
)
from backend.workspace_services.evidence import documents, plaintext
from backend.workspace_services.evidence.canonical import CanonicalSource
from backend.workspace_services.evidence.xlsx import WorkbookUnreadable, check_ooxml_archive, parse_xlsx
from backend.workspace_services.evidence.xlsx import render_text as render_workbook_text

MAX_FILE_BYTES = 25 * 1024 * 1024
MAX_EXTRACTED_CHARACTERS = 5_000_000
SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".csv", ".txt", ".md", ".pptx"}
# Testo semplice: leggerlo costa millisecondi, e mandarlo in coda costerebbe al
# consulente secondi di attesa (lease, giro della lista) per niente. Si legge
# dentro la richiesta e la fonte risponde gia' "pronta". PDF, Office ed Excel
# restano al worker.
READ_IN_REQUEST = {".txt", ".md", ".csv"}
MIME_BY_EXTENSION = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    ".csv": "text/csv",
    ".txt": "text/plain",
    ".md": "text/markdown",
}


SOURCE_ROLES = ("context", "process_evidence", "policy", "operational_data")

# Parole nel nome del file che dicono a cosa serve. E' una proposta che il
# consulente accetta o cambia con un clic sulla card, non una decisione: per
# questo bastano regole leggibili, e nessun modello.
# Le parole corte hanno i confini: "iso" non deve scattare dentro "decisione".
_POLICY = re.compile(r"procedur|policy|regolament|istruzion|manual|\bnorm[ae]\b|\biso\b|linee.guida")
_EVIDENCE = re.compile(r"intervist|verbal|riunion|meeting|\bcall\b|trascri|workshop|\bnote\b")


def suggest_roles(filename: str) -> list[str] | None:
    """A cosa sembra servire un file, dal nome e dal formato.

    Returns:
        I ruoli proposti, nell'ordine canonico, o `None` se il nome non dice
        niente: allora resta il ruolo che la chat ha dato.
    """
    name = Path(filename).stem.lower().replace("_", " ")
    extension = Path(filename).suffix.lower()
    if extension in {".xlsx", ".csv"}:
        return ["operational_data"]
    if _POLICY.search(name):
        return ["process_evidence", "policy"]
    if _EVIDENCE.search(name):
        return ["process_evidence"]
    return None


class SourceFileError(ValueError):
    pass


class SourceFileTooLarge(SourceFileError):
    """Oltre MAX_FILE_BYTES: la risposta e' 413."""


class SourceFileUnsupported(SourceFileError):
    """Formato non accettato: la risposta e' 415."""


@dataclass(frozen=True)
class ParsedSource:
    content_hash: str
    byte_size: int
    mime_type: str
    extension: str
    text: str
    parser: str
    # Le evidenze ancorate, per i formati che hanno gia' un parser strutturale.
    # `text` per questi formati e' una vista di `evidence`, non un'altra lettura.
    evidence: CanonicalSource | None = None


def _plain_text(payload: bytes) -> str:
    for encoding in ("utf-8-sig", "utf-8", "cp1252"):
        try:
            return payload.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise SourceFileError("Il testo non usa una codifica supportata.")


@dataclass(frozen=True)
class UploadedFile:
    """Cio' che si sa di un file appena arrivato, prima di leggerlo."""

    content_hash: str
    byte_size: int
    mime_type: str
    extension: str


def inspect_upload(filename: str, payload: bytes) -> UploadedFile:
    """I controlli che costano millisecondi, fatti dentro la richiesta.

    Formato, dimensione, PDF integro e non cifrato, archivio Office senza XML
    pericoloso: un file che non passa qui non entra nemmeno in coda. La lettura
    vera - layout, tabelle, OCR - la fa il worker con `parse_source_file`.

    Raises:
        SourceFileError: Il file va rifiutato, con il motivo.
    """
    extension = Path(filename).suffix.lower()
    if extension not in SUPPORTED_EXTENSIONS:
        raise SourceFileUnsupported("Formato non supportato. Usa PDF, DOCX, XLSX, CSV, PPTX, TXT o MD.")
    if not payload:
        raise SourceFileError("Il file è vuoto.")
    if len(payload) > MAX_FILE_BYTES:
        raise SourceFileTooLarge("Il file supera il limite di 25 MB.")
    try:
        if extension == ".pdf":
            documents.check_pdf(payload)
        elif extension in {".docx", ".pptx"}:
            check_ooxml_archive(payload, "Office")
        elif extension == ".xlsx":
            check_ooxml_archive(payload, "Excel")
    except (documents.DocumentUnreadable, WorkbookUnreadable) as exc:
        raise SourceFileError(str(exc)) from exc
    return UploadedFile(
        content_hash=hashlib.sha256(payload).hexdigest(),
        byte_size=len(payload),
        mime_type=MIME_BY_EXTENSION[extension],
        extension=extension,
    )


def parse_source_file(filename: str, payload: bytes, _declared_mime: str | None) -> ParsedSource:
    """Legge il file: testo e, dove esiste un parser strutturale, evidenze ancorate.

    Raises:
        SourceFileError: Il file non e' leggibile; riprovare non cambia l'esito.
        documents.DocumentServiceUnavailable: Il lettore dei documenti non
            risponde; riprovare piu' tardi puo' riuscire.
    """
    upload = inspect_upload(filename, payload)
    extension = upload.extension

    evidence: CanonicalSource | None = None
    if extension in documents.FORMATS:
        try:
            # DOCX e PPTX hanno gia' il testo; un PDF solo se non e' una scansione.
            ocr = extension == ".pdf" and documents.needs_ocr(payload)
            document, service_errors = documents.convert(filename, payload, do_ocr=ocr)
        except documents.DocumentUnreadable as exc:
            raise SourceFileError(str(exc)) from exc
        evidence = documents.evidence_from(
            document, format=documents.FORMATS[extension], service_errors=service_errors
        )
        text = documents.render_text(document)
        parser = evidence.parser
    elif extension == ".xlsx":
        try:
            evidence = parse_xlsx(payload)
        except WorkbookUnreadable as exc:
            raise SourceFileError(str(exc)) from exc
        text = render_workbook_text(evidence)
        parser = evidence.parser
    else:
        text = _plain_text(payload)
        if extension == ".csv":
            try:
                rows = list(csv.reader(io.StringIO(text)))
            except csv.Error as exc:
                # Virgolette non chiuse o un campo oltre il limite del lettore:
                # e' il file a non essere un CSV valido, non il server a rompersi.
                raise SourceFileError("Il CSV non è valido: controlla virgolette e separatori.") from exc
            text = "\n".join("\t".join(cell.strip() for cell in row) for row in rows)
            evidence = plaintext.csv_rows(rows)
        else:
            evidence = plaintext.paragraphs(text.replace("\x00", ""), format=extension.lstrip("."))
        parser = evidence.parser

    cleaned = text.replace("\x00", "").strip()
    if not cleaned:
        raise SourceFileError("Il file non contiene testo leggibile.")
    if len(cleaned) > MAX_EXTRACTED_CHARACTERS:
        raise SourceFileError("Il testo estratto è troppo grande.")
    return ParsedSource(
        content_hash=upload.content_hash,
        byte_size=upload.byte_size,
        mime_type=upload.mime_type,
        extension=extension,
        text=cleaned,
        parser=parser,
        evidence=evidence,
    )


def store_original(parsed: UploadedFile | ParsedSource, payload: bytes) -> str:
    """Conserva l'originale nell'archivio delle fonti e ne restituisce la chiave."""
    key = source_key(get_current_tenant_id(), parsed.content_hash, parsed.extension)
    source_blob_store().put(key, payload, content_hash=parsed.content_hash)
    return key


def read_original(storage_key: str) -> bytes:
    """I byte dell'originale. `SourceFileError` se la chiave non vale o il file manca."""
    try:
        return source_blob_store().get(storage_key)
    except BlobKeyError as exc:
        raise SourceFileError("Percorso della fonte non valido.") from exc
    except BlobNotFound as exc:
        raise SourceFileError("File originale non trovato.") from exc


def delete_original(storage_key: str) -> None:
    """Rimuove l'originale; un file gia' assente non e' un errore."""
    try:
        source_blob_store().delete(storage_key)
    except BlobKeyError as exc:
        raise SourceFileError("Percorso della fonte non valido.") from exc
