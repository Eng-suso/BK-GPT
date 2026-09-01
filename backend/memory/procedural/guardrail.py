"""Guardrail sui playbook appresi prima della promozione ad 'active' (L2 / INV-13).

Il gate DB (`procedural_guardrail_gate`, migration 0003) impedisce a una riga
`procedural_memory` di diventare `status='active'` finche' `guardrail_status`
non e' `'clean'`. Questo modulo produce quel verdetto.

Rileva:
  - PII in chiaro (email, telefono, IBAN, partita IVA, codice fiscale, carte);
  - solo per scope='consultant': nomi di clienti del consulente rimasti nel
    corpo -> la generalizzazione client -> consultant non e' completa.

Regex-only di default (nessuna dipendenza da LLM/rete, cosi' i test girano
senza OPENAI_API_KEY). Un `llm` opzionale rafforza il check sullo scope
consultant. Ritorna `('clean' | 'flagged', findings)`.
"""

from __future__ import annotations

import json
import logging
import re
from typing import Any

logger = logging.getLogger(__name__)

_EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]{2,}\b")
# telefono: o con prefisso internazionale esplicito (+39 340 111 2233), o una
# sequenza di 9-12 cifre contigue. Stretto di proposito: un playbook di metodo
# cita passi numerati, non recapiti, e un falso positivo blocca la promozione.
_PHONE = re.compile(
    r"\+\d{1,3}[ .\-]?\d{2,4}(?:[ .\-]?\d{2,4}){1,4}|\b\d{9,12}\b"
)
_IBAN = re.compile(r"\b[A-Z]{2}\d{2}[A-Z0-9]{11,30}\b")
_VAT = re.compile(r"\b(?:IT)?\d{11}\b")
_FISCAL_CODE = re.compile(
    r"\b[A-Z]{6}\d{2}[A-Z]\d{2}[A-Z]\d{3}[A-Z]\b", re.IGNORECASE
)
_CARD = re.compile(r"\b(?:\d[ \-]?){13,19}\b")

_PII_CHECKS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("email", _EMAIL),
    ("telefono", _PHONE),
    ("iban", _IBAN),
    ("partita_iva", _VAT),
    ("codice_fiscale", _FISCAL_CODE),
    ("carta", _CARD),
)

# un nome cliente a parola singola sotto questa lunghezza e' troppo generico
# (rischio di falso positivo su parole comuni tipo "Delta", "Nord", "Sigma").
# I nomi multi-parola ("Rossi Manifattura") sono distintivi -> soglia piu' bassa.
_MIN_SINGLE_TOKEN_NAME = 6
_MIN_MULTI_TOKEN_NAME = 4


def _pii_findings(blob: str) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for label, pattern in _PII_CHECKS:
        for match in pattern.finditer(blob):
            out.append({"kind": "pii", "type": label, "match": match.group(0)[:80]})
    return out


def _client_reference_findings(
    blob: str, client_names: list[str]
) -> list[dict[str, str]]:
    low = blob.lower()
    out: list[dict[str, str]] = []
    for raw in client_names or []:
        name = (raw or "").strip()
        multi_token = len(name.split()) > 1
        min_len = _MIN_MULTI_TOKEN_NAME if multi_token else _MIN_SINGLE_TOKEN_NAME
        if len(name) < min_len:
            continue
        if re.search(rf"\b{re.escape(name.lower())}\b", low):
            out.append({"kind": "client_reference", "match": name})
    return out


def _llm_findings(blob: str, llm: Any) -> list[dict[str, str]]:
    try:
        from langchain_core.messages import HumanMessage, SystemMessage

        response = llm.invoke(
            [
                SystemMessage(
                    content=(
                        "Sei un guardrail di conformita'. Il testo e' un playbook di "
                        "metodo che deve restare generico: nessun nome di cliente, "
                        "nessun dato riservato, nessun numero sensibile. Rispondi solo "
                        'JSON: {"leak": true|false, "reason": "breve motivo"}.'
                    )
                ),
                HumanMessage(content=blob[:4000]),
            ]
        )
        content = str(getattr(response, "content", response) or "")
        match = re.search(r"\{.*\}", content, re.DOTALL)
        if not match:
            return []
        data = json.loads(match.group(0))
        if data.get("leak"):
            return [{"kind": "llm", "match": str(data.get("reason") or "leak")[:200]}]
    except Exception:  # noqa: BLE001 — il guardrail LLM e' un rinforzo, non deve rompere
        logger.warning("guardrail LLM check fallito", exc_info=True)
    return []


def check(
    *,
    body: str,
    title: str | None = None,
    applies_when: str | None = None,
    scope: str = "client",
    client_names: list[str] | None = None,
    llm: Any | None = None,
) -> tuple[str, list[dict[str, str]]]:
    """`('clean', [])` se il playbook e' promuovibile, altrimenti `('flagged', findings)`.

    Per scope='client' i riferimenti al cliente sono attesi: si controlla solo
    la PII in chiaro. Per scope='consultant' si controlla anche che nessun nome
    cliente sia sopravvissuto alla generalizzazione (INV-13).
    """
    blob = "\n".join(part for part in (title, applies_when, body) if part)
    findings = _pii_findings(blob)
    if scope == "consultant":
        findings += _client_reference_findings(blob, client_names or [])
        if llm is not None:
            findings += _llm_findings(blob, llm)
    return ("flagged" if findings else "clean", findings)
