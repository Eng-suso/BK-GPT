"""Le tracce delle chiamate al modello, scritte da noi, su disco.

Perche' esiste. Il tracing va a LangSmith, che ha una quota: 5.000 tracce al
mese sul piano in uso. Il 2026-09-25 il registro d'uso diceva che **i test**
avevano consumato 5.069 tracce fra l'1 e il 6 settembre, lasciando senza
osservabilita' tutto il resto del mese - le chiamate del prodotto continuavano a
funzionare, ma le loro tracce venivano rifiutate con 429 e nessuno le vedeva.

I test adesso non tracciano piu' su LangSmith (`tests/conftest.py`), e quella
quota resta intera per il prodotto. Ma «non tracciare» non vuol dire «non
vedere»: quando un test fallisce per come ha risposto il modello, la domanda
«cosa e' stato mandato e cosa e' tornato» serve lo stesso. Questo modulo la
risponde senza chiamare nessuno: un file JSONL sotto `data/traces/`, una riga
per evento.

**E' anche la rete di sicurezza del prodotto.** Se la quota LangSmith finisce di
nuovo - o se il servizio non risponde - le tracce locali restano. Una traccia
che esiste solo su un servizio esterno e' una traccia che si perde proprio nel
giorno storto.

**I payload sono dati veri**: i prompt contengono le interviste dei clienti.
`data/` e' gitignored, i testi sono troncati, e chi non li vuole affatto mette
`DELIR_LOCAL_TRACE_PAYLOAD=0` - restano tempi, token ed esiti, che sono la parte
che serve piu' spesso.
"""

from __future__ import annotations

import json
import os
import threading
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter
from typing import Any
from uuid import UUID

#: Quanto testo si tiene di un prompt o di una risposta. Abbastanza per
#: riconoscere cosa e' successo, non abbastanza per archiviare un'intervista.
MAX_PAYLOAD_CHARS = 2000

_GUARD = threading.Lock()
_AVVII: dict[str, float] = {}


def _acceso() -> bool:
    """Se scrivere le tracce locali.

    Di default si accendono quando LangSmith **non** e' attivo: e' il caso dei
    test, ed e' il caso di chi lavora senza chiave. Con
    `DELIR_LOCAL_TRACE=1` si accendono comunque, anche accanto a LangSmith.
    """
    esplicito = os.environ.get("DELIR_LOCAL_TRACE", "").strip().lower()
    if esplicito in {"1", "true", "yes", "on"}:
        return True
    if esplicito in {"0", "false", "no", "off"}:
        return False

    from backend.settings import langsmith_tracing_enabled

    return not langsmith_tracing_enabled()


def _con_payload() -> bool:
    return os.environ.get("DELIR_LOCAL_TRACE_PAYLOAD", "1").strip().lower() not in {
        "0",
        "false",
        "no",
        "off",
    }


def percorso_del_giorno() -> Path:
    """Il file di oggi. Un file per giorno: si cancella per data, non si pota."""
    cartella = Path(os.environ.get("DELIR_LOCAL_TRACE_DIR", "data/traces"))
    cartella.mkdir(parents=True, exist_ok=True)
    return cartella / f"{datetime.now(UTC):%Y-%m-%d}.jsonl"


def _tronca(valore: object) -> str:
    testo = valore if isinstance(valore, str) else repr(valore)
    if len(testo) <= MAX_PAYLOAD_CHARS:
        return testo
    return f"{testo[:MAX_PAYLOAD_CHARS]}... [troncato, {len(testo)} caratteri]"


def _scrivi(evento: dict[str, Any]) -> None:
    """Aggiunge una riga al file del giorno. Non solleva mai.

    Stessa regola del registro dei consumi: uno strumento di osservazione che
    rompe la cosa osservata viene spento al primo incidente, e allora non
    osserva piu' niente.
    """
    try:
        evento["ts"] = datetime.now(UTC).isoformat()
        evento.update(_lavoro())
        riga = json.dumps(evento, ensure_ascii=False, default=str)
        with _GUARD:
            with percorso_del_giorno().open("a", encoding="utf-8") as f:
                f.write(riga + "\n")
    except Exception:  # noqa: BLE001 - una traccia persa non vale un turno
        pass


def _chiave(run_id: UUID | None) -> str:
    return str(run_id) if run_id is not None else "?"


def _lavoro() -> dict[str, Any]:
    """L'operazione dentro cui questa chiamata sta avvenendo, se c'e'.

    E' quello che cuce insieme i due sistemi. Il registro dei consumi dice che
    una chiamata e' costata tanto, dentro l'operazione X; la traccia dice cosa
    le e' stato mandato. Senza questo campo restano due file che parlano della
    stessa chiamata senza sapere l'uno dell'altro, e la domanda naturale -
    «questa riga cara, cosa aveva in pancia?» - non ha risposta.

    Best-effort: fuori da un'operazione (uno script, un notebook) si traccia lo
    stesso, senza il collegamento.
    """
    try:
        from backend.llm.operation import current_operation

        operazione = current_operation()
        if operazione is None:
            return {}
        return {
            "operation_id": operazione.id,
            "operation_kind": operazione.kind,
            "project_id": operazione.project_id,
        }
    except Exception:  # noqa: BLE001 - il collegamento e' un di piu', non un requisito
        return {}


def _handler_locale():
    """Il callback handler, costruito solo quando serve.

    L'import di `langchain_core` sta qui dentro perche' questo modulo viene
    importato dal gateway, che e' importato ovunque: farlo in cima
    allungherebbe l'avvio anche a chi le tracce non le scrive.
    """
    from langchain_core.callbacks.base import BaseCallbackHandler

    class TracciaLocale(BaseCallbackHandler):
        """Scrive su file quello che LangSmith avrebbe ricevuto.

        Non e' un clone di LangSmith e non prova a esserlo: niente interfaccia,
        niente ricerca, niente confronto fra run. Quello che da' e' la risposta
        alla domanda che serve mentre si sviluppa - cosa e' stato mandato, cosa
        e' tornato, quanto ci ha messo, quanti token - in un file che si legge
        con `tail` e si cancella con `rm`.
        """

        def on_llm_start(self, serialized, prompts, *, run_id=None, parent_run_id=None, **kw):
            with _GUARD:
                _AVVII[_chiave(run_id)] = perf_counter()
            evento: dict[str, Any] = {
                "evento": "llm_start",
                "run_id": _chiave(run_id),
                "parent_run_id": _chiave(parent_run_id) if parent_run_id else None,
                "modello": (serialized or {}).get("name") or kw.get("invocation_params", {}).get("model"),
                "n_prompt": len(prompts or []),
            }
            if _con_payload():
                evento["prompt"] = [_tronca(p) for p in (prompts or [])]
            _scrivi(evento)

        def on_chat_model_start(self, serialized, messages, *, run_id=None, parent_run_id=None, **kw):
            with _GUARD:
                _AVVII[_chiave(run_id)] = perf_counter()
            evento: dict[str, Any] = {
                "evento": "chat_start",
                "run_id": _chiave(run_id),
                "parent_run_id": _chiave(parent_run_id) if parent_run_id else None,
                "modello": kw.get("invocation_params", {}).get("model")
                or (serialized or {}).get("name"),
            }
            if _con_payload():
                evento["messaggi"] = [
                    [f"{type(m).__name__}: {_tronca(getattr(m, 'content', m))}" for m in gruppo]
                    for gruppo in (messages or [])
                ]
            _scrivi(evento)

        def on_llm_end(self, response, *, run_id=None, parent_run_id=None, **kw):
            evento: dict[str, Any] = {
                "evento": "llm_end",
                "run_id": _chiave(run_id),
                "parent_run_id": _chiave(parent_run_id) if parent_run_id else None,
                "durata_ms": self._durata(run_id),
            }
            uso = (getattr(response, "llm_output", None) or {}).get("token_usage")
            if uso:
                evento["token"] = uso
            if _con_payload():
                try:
                    evento["risposta"] = [
                        _tronca(gen.text or getattr(gen, "message", ""))
                        for gruppo in (response.generations or [])
                        for gen in gruppo
                    ]
                except Exception:  # noqa: BLE001 - forma inattesa: si perde il payload, non l'evento
                    evento["risposta"] = "[illeggibile]"
            _scrivi(evento)

        def on_llm_error(self, error, *, run_id=None, parent_run_id=None, **kw):
            _scrivi(
                {
                    "evento": "llm_error",
                    "run_id": _chiave(run_id),
                    "parent_run_id": _chiave(parent_run_id) if parent_run_id else None,
                    "durata_ms": self._durata(run_id),
                    "errore": type(error).__name__,
                    "messaggio": _tronca(str(error)),
                }
            )

        def _durata(self, run_id) -> int:
            with _GUARD:
                avvio = _AVVII.pop(_chiave(run_id), None)
            return int((perf_counter() - avvio) * 1000) if avvio is not None else 0

    return TracciaLocale()


def local_callbacks() -> list:
    """I callback da passare a un client, o una lista vuota.

    Chi costruisce un client nel gateway aggiunge questi: sono due punti soli -
    `_client` e `chat_client` - e non e' un caso, e' l'invariante L1 che dice
    che i client si costruiscono solo qui.
    """
    if not _acceso():
        return []
    return [_handler_locale()]
