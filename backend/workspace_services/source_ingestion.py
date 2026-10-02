"""Validazione, custodia ed estrazione testuale dei file caricati in Fonti."""

from __future__ import annotations

import csv
import hashlib
import io
import os
import uuid
from dataclasses import dataclass
from pathlib import Path

from backend.security import get_current_tenant_id
from backend.workspace_services.evidence import documents
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
            document, service_errors = documents.convert(filename, payload)
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
        parser = "text"

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
    tenant_key = hashlib.sha256(get_current_tenant_id().encode()).hexdigest()[:20]
    relative = Path("source_uploads") / tenant_key / f"{parsed.content_hash}{parsed.extension}"
    destination = Path("data") / relative
    destination.parent.mkdir(parents=True, exist_ok=True)
    # Il nome e' l'hash del contenuto: un file gia' presente e integro non si
    # riscrive. Uno troncato da un crash o da un disco pieno si', altrimenti ogni
    # caricamento successivo dello stesso file servirebbe i byte rotti.
    if destination.exists() and hashlib.sha256(destination.read_bytes()).hexdigest() == parsed.content_hash:
        return relative.as_posix()
    # Scrittura atomica: chi legge vede il file vecchio o quello completo, mai
    # uno a meta', anche con due caricamenti dello stesso file in parallelo.
    temporary = destination.with_name(f"{destination.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_bytes(payload)
        os.replace(temporary, destination)
    finally:
        temporary.unlink(missing_ok=True)
    return relative.as_posix()


def original_path(storage_key: str) -> Path:
    root = (Path("data") / "source_uploads").resolve()
    candidate = (Path("data") / storage_key).resolve()
    if root not in candidate.parents:
        raise SourceFileError("Percorso della fonte non valido.")
    return candidate
