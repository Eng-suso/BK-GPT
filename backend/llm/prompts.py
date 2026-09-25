"""La versione di un prompt, per il registro dei consumi (L5).

Un cambio di prompt cambia la spesa: piu' contesto, piu' token in ingresso; una
richiesta piu' aperta, piu' token in uscita. Senza una versione nel registro la
spesa di prima e quella di dopo sono la stessa colonna, e non si riesce a dire
**quale** cambio l'ha cambiata - che e' l'unica domanda utile quando il costo
sale di colpo.

**Perche' un hash e non un numero scritto a mano.** Un `"@3"` incrementato da chi
modifica il prompt si dimentica, e una versione che resta ferma mentre il testo
cambia e' peggio di nessuna versione: dichiara «stesso prompt» e mente, e chi
legge il registro conclude che la spesa e' salita da sola. L'hash del testo non
si puo' dimenticare, perche' non lo scrive nessuno.

**Perche' il template e non il messaggio finale.** Il messaggio che parte
contiene i dati della singola chiamata - l'intervista, i candidati da
riconciliare - quindi il suo hash sarebbe diverso a ogni chiamata e la colonna
diventerebbe rumore, con tante versioni quante righe. Si versiona la parte
**stabile**: il template, le istruzioni di sistema, lo schema di risposta.

Il nome davanti serve a leggere: `plan_extraction@a3f21b9c` dice in un colpo
quale prompt e quale sua versione, e due righe con lo stesso nome e hash diverso
sono lo stesso prompt prima e dopo una modifica.
"""

from __future__ import annotations

import hashlib
from functools import lru_cache

LUNGHEZZA_HASH = 8


@lru_cache(maxsize=256)
def _impronta(testo: str) -> str:
    return hashlib.sha256(testo.encode("utf-8")).hexdigest()[:LUNGHEZZA_HASH]


def prompt_version(nome: str, *parti: str) -> str:
    """`nome@hash` a partire dalle parti stabili di un prompt.

    Le parti si concatenano nell'ordine in cui sono passate, separate da un
    marcatore: due prompt fatti degli stessi pezzi in ordine diverso sono due
    prompt diversi, e devono avere due versioni diverse.

    I fine riga si normalizzano a `\\n` **prima** dell'hash. Non e' cosmesi: su
    Windows git puo' consegnare gli stessi identici file con `\\r\\n`, e senza
    questa normalizzazione la stessa versione di prompt avrebbe due hash a
    seconda della macchina che l'ha eseguito. Il resto degli spazi si lascia
    stare, perche' l'indentazione dentro un prompt la legge anche il modello.

    Args:
        nome: Come si chiama il prompt. Per convenzione e' il valore del compito
            (`LlmTask`) a cui appartiene, o il suo nome piu' un suffisso quando
            un compito ne ha piu' d'uno.
        *parti: I pezzi stabili: sistema, istruzioni, formato della risposta.
            **Non** i dati della chiamata.

    Returns:
        Una stringa come `plan_extraction@a3f21b9c`, pronta per `prompt_version`
        di `llm.run`.

    Raises:
        ValueError: Se non viene passata nessuna parte. Un prompt senza testo
            non ha una versione, e restituirne una finta metterebbe nel registro
            un'etichetta che non corrisponde a niente.
    """
    if not parti:
        raise ValueError(f"prompt_version({nome!r}): serve almeno una parte di testo da versionare")
    unito = "\x00".join(parte.replace("\r\n", "\n") for parte in parti)
    return f"{nome}@{_impronta(unito)}"


def schema_part(output: type) -> str:
    """Lo schema di risposta, come parte versionabile del prompt.

    Un campo aggiunto a un modello di uscita e' un cambio di prompt a tutti gli
    effetti: il fornitore lo riceve insieme alle istruzioni e il modello produce
    piu' token per riempirlo. Se la versione ignorasse lo schema, quel costo in
    piu' comparirebbe nel registro sotto la stessa etichetta di prima, cioe'
    esattamente nel modo in cui un aumento diventa inspiegabile.

    Args:
        output: Il modello pydantic che il compito si aspetta indietro.

    Returns:
        Lo schema in forma stabile - chiavi ordinate, cosi' due esecuzioni dello
        stesso schema danno la stessa stringa - o il nome della classe quando
        non e' un modello pydantic e uno schema non c'e'.
    """
    import json

    schema = getattr(output, "model_json_schema", None)
    if schema is None:
        return getattr(output, "__name__", str(output))
    return json.dumps(schema(), sort_keys=True, ensure_ascii=False)
