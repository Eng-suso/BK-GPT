"""Acquisizione strutturale di PDF, DOCX e PPTX: l'Evidence Bucket per i documenti.

La lettura la fa docling-serve (MIT, container in ops/docker-compose.yml):
layout, ordine di lettura, tabelle, OCR delle parti scansionate. Ritorna un
`DoclingDocument`, il formato di docling-core, che qui resta com'e': e' la
rappresentazione canonica del documento, con i riferimenti ufficiali di ogni
elemento (`#/texts/12`, `#/tables/0`) e la provenienza (pagina, riquadro).

Le porzioni citabili le produce il chunker gerarchico di docling-core: ogni
porzione porta il percorso dei titoli e gli elementi del documento da cui
viene. Corpo, intestazioni e pie' di pagina, note del relatore e commenti
sono tutti inclusi: un commento a margine e' un'evidenza come il testo.
"""

from __future__ import annotations

import time
from typing import Any

import httpx
from docling_core.transforms.chunker.hierarchical_chunker import (
    ChunkingDocSerializer,
    ChunkingSerializerProvider,
    HierarchicalChunker,
)
from docling_core.transforms.serializer.markdown import MarkdownParams
from docling_core.types.doc import ContentLayer, DoclingDocument

from backend.settings import settings
from backend.workspace_services.evidence.canonical import (
    AcquisitionIssue,
    Anchor,
    CanonicalSource,
    EvidenceSegment,
)

MAX_PDF_PAGES = 1_000
FORMATS = {".pdf": "pdf", ".docx": "docx", ".pptx": "pptx"}
_ALL_LAYERS = set(ContentLayer)
_POLL_SECONDS = 1.0
_UNEXPECTED = "Il servizio di lettura dei documenti ha risposto in modo inatteso."


class DocumentUnreadable(ValueError):
    """Il documento non si puo' aprire o supera i limiti."""


class DocumentServiceUnavailable(RuntimeError):
    """docling-serve non risponde: il documento non e' rotto, il servizio si'."""


class _AllLayersProvider(ChunkingSerializerProvider):
    def get_serializer(self, doc: DoclingDocument) -> ChunkingDocSerializer:
        return ChunkingDocSerializer(doc=doc, params=MarkdownParams(layers=_ALL_LAYERS))


def convert(
    filename: str,
    payload: bytes,
    *,
    transport: httpx.BaseTransport | None = None,
) -> tuple[DoclingDocument, list[str]]:
    """Fa convertire il file a docling-serve, con l'API asincrona.

    L'API sincrona tiene aperta la richiesta per tutta la conversione e scade
    sui PDF lunghi; quella asincrona restituisce un task da interrogare.

    Returns:
        Il documento e gli errori parziali riportati dal servizio.

    Raises:
        DocumentUnreadable: Il servizio ha rifiutato il file.
        DocumentServiceUnavailable: Il servizio non e' raggiungibile o non
            ha finito entro `docling_timeout_seconds`.
    """
    base = settings.docling_serve_url.rstrip("/")
    deadline = time.monotonic() + settings.docling_timeout_seconds
    try:
        with httpx.Client(timeout=60.0, transport=transport) as client:
            submitted = client.post(
                f"{base}/v1/convert/file/async",
                files={"files": (filename, payload)},
                data={
                    "to_formats": "json",
                    "do_ocr": "true",
                    "table_mode": "accurate",
                    "image_export_mode": "placeholder",
                    "abort_on_error": "false",
                },
            )
            # 4xx all'invio = il servizio ha rifiutato il file (formato, contenuto):
            # riprovare dara' lo stesso esito. Restano "servizio giu'" i 5xx, i
            # timeout (408) e il rate limit (429).
            if 400 <= submitted.status_code < 500 and submitted.status_code not in {408, 429}:
                raise DocumentUnreadable("Il documento non può essere letto.")
            submitted.raise_for_status()
            task_id = submitted.json().get("task_id")
            if not isinstance(task_id, str) or not task_id:
                raise DocumentServiceUnavailable(_UNEXPECTED)
            while True:
                status = client.get(f"{base}/v1/status/poll/{task_id}")
                status.raise_for_status()
                state = status.json().get("task_status")
                if state == "success":
                    break
                if state == "failure":
                    raise DocumentUnreadable("Il documento non può essere letto.")
                if time.monotonic() > deadline:
                    raise DocumentServiceUnavailable("La lettura del documento non è finita in tempo.")
                time.sleep(_POLL_SECONDS)
            result = client.get(f"{base}/v1/result/{task_id}")
            result.raise_for_status()
    except DocumentUnreadable:
        # E' un ValueError: senza questa riga diventerebbe "servizio giu'".
        raise
    except httpx.HTTPError as exc:
        raise DocumentServiceUnavailable("Il servizio di lettura dei documenti non è disponibile.") from exc
    except (ValueError, AttributeError) as exc:
        # Un corpo che non e' JSON, o JSON con un'altra forma: il servizio e'
        # cambiato o rotto, il file del consulente no.
        raise DocumentServiceUnavailable(_UNEXPECTED) from exc

    try:
        body = result.json()
        content = (body.get("document") or {}).get("json_content")
    except (ValueError, AttributeError) as exc:
        raise DocumentServiceUnavailable(_UNEXPECTED) from exc
    if body.get("status") == "failure" or not content:
        raise DocumentUnreadable("Il documento non può essere letto.")
    errors = [
        str(item.get("error_message") or item) if isinstance(item, dict) else str(item)
        for item in body.get("errors") or []
    ]
    try:
        return DoclingDocument.model_validate(content), errors
    except ValueError as exc:
        raise DocumentServiceUnavailable(_UNEXPECTED) from exc


def check_pdf(payload: bytes) -> None:
    """Rifiuta subito, senza scomodare il servizio, un PDF rotto, cifrato o troppo lungo."""
    import pypdfium2

    if not payload.startswith(b"%PDF"):
        raise DocumentUnreadable("Il contenuto non corrisponde a un PDF valido.")
    try:
        document = pypdfium2.PdfDocument(payload)
    except pypdfium2.PdfiumError as exc:
        if "password" in str(exc).lower():
            raise DocumentUnreadable("Il PDF è protetto da password.") from exc
        raise DocumentUnreadable("Il PDF non può essere letto.") from exc
    try:
        if len(document) > MAX_PDF_PAGES:
            raise DocumentUnreadable("Il PDF supera il limite di 1.000 pagine.")
    finally:
        document.close()


def evidence_from(document: DoclingDocument, *, format: str, service_errors: list[str] | None = None) -> CanonicalSource:
    """Le porzioni citabili del documento, dal chunker di docling-core."""
    segments: list[EvidenceSegment] = []
    for chunk in HierarchicalChunker(serializer_provider=_AllLayersProvider()).chunk(document):
        items = list(chunk.meta.doc_items)
        if not items or not chunk.text.strip():
            continue
        provenance = [
            {"page": prov.page_no, "bbox": prov.bbox.model_dump(mode="json"), "charspan": list(prov.charspan)}
            for item in items
            for prov in item.prov
        ]
        layers = sorted({item.content_layer.value for item in items})
        attributes: dict[str, Any] = {"labels": sorted({item.label.value for item in items})}
        if layers != ["body"]:
            attributes["layers"] = layers
        segments.append(
            EvidenceSegment(
                anchor=Anchor(
                    kind="docling_chunk",
                    ref=items[0].self_ref,
                    locator={
                        "doc_items": [item.self_ref for item in items],
                        "headings": list(chunk.meta.headings or []),
                        "provenance": provenance,
                    },
                ),
                text=chunk.text.strip(),
                value_type="text",
                value=chunk.text.strip(),
                attributes=attributes,
            )
        )

    issues = [
        AcquisitionIssue(code="conversion_partial", severity="partial", message=message)
        for message in service_errors or []
    ]
    if document.pictures:
        issues.append(
            AcquisitionIssue(
                code="pictures_not_described",
                severity="partial",
                message=f"{len(document.pictures)} immagini: il contenuto visivo (grafici, schemi) non è descritto.",
            )
        )

    return CanonicalSource(
        format=format,
        parser="docling-serve",
        segments=tuple(segments),
        structure={"pages": len(document.pages) or None, "docling": document.export_to_dict()},
        issues=tuple(issues),
    )


def render_text(document: DoclingDocument) -> str:
    """Il testo leggibile del documento, come lo esporta docling-core."""
    return document.export_to_markdown(included_content_layers=_ALL_LAYERS)
