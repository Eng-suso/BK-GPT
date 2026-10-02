# Le tracce: chi le scrive, chi le legge, e perché sono due sistemi

Documento operativo. Se stai cercando «perché non vedo le mie tracce su
LangSmith», la risposta è quasi certamente qui sotto.

## La regola in una riga

**I test tracciano da noi, su file. Il prodotto traccia su LangSmith.**

## Perché, e cosa è successo il 6 settembre 2026

LangSmith ha una quota: 5.000 tracce al mese sul piano in uso, ed è un limite
del workspace, non della chiave — cambiare chiave non cambia niente.

`configure_langsmith_environment()` gira all'import di `backend.settings` e
accende il tracing se `.env` dice `LANGSMITH_TRACING=true`. Fino al 25/09 non
aveva **nessuna eccezione per i test**, quindi ogni passata di pytest tracciava.
Il registro d'uso di LangSmith racconta il resto:

| giorno | tracce | cumulato |
| --- | --- | --- |
| 2026-09-01 | 2.299 | 2.299 |
| 2026-09-02 | 1.370 | 3.669 |
| 2026-09-03 | 30 | 3.699 |
| 2026-09-04 | 42 | 3.741 |
| 2026-09-05 | 1.104 | 4.845 |
| 2026-09-06 | 224 | **5.069 — sopra il tetto** |

Dal 6 settembre ogni traccia viene rifiutata con `429`. Quei picchi da 2.299 in
un giorno non sono il prodotto: sono passate di test.

È lo stesso difetto di P0.1 — «un test non paga il modello vero» — su un
fornitore a cui nessuno aveva guardato. Con un aggravante: **il fallimento è
silenzioso**. Le chiamate al modello continuano a funzionare, solo le tracce
spariscono, e l'unico segnale è un errore che scorre via nel log. Il prodotto è
rimasto senza osservabilità per diciannove giorni senza che se ne accorgesse
nessuno.

## Come funziona adesso

### Nei test

`tests/conftest.py` spegne il tracing **prima** di importare `backend.settings`.
Deve stare lì e non in una fixture: l'import è quello che accende tutto.

Un test in `tests/llm/test_no_live_llm_by_default.py` protegge l'invariante, così
non torna in silenzio come la prima volta.

Al posto di LangSmith scrive `backend/llm/local_tracer.py`: un JSONL sotto
`data/traces/`, un file per giorno, una riga per evento — messaggi, risposta,
durata, token, errori. Si legge con `tail`, si cancella con `rm`.

### Nel prodotto

Traccia su LangSmith, con la quota tutta per sé. Il tracer locale si accende
**solo** quando LangSmith è spento: due tracce della stessa chiamata sarebbero
lavoro doppio per la stessa informazione.

È anche la rete di sicurezza: se la quota finisce di nuovo, o se il servizio non
risponde, la traccia locale resta. Una traccia che esiste solo su un servizio
esterno è una traccia che si perde proprio nel giorno storto.

## Le manopole

| variabile | effetto |
| --- | --- |
| `DELIR_TRACE_TESTS=1` | Riaccende LangSmith per una passata di test. Serve per gli eval col modello vero, dove vedere il giudizio è il punto. |
| `DELIR_LOCAL_TRACE=1` | Accende il tracer locale anche accanto a LangSmith. |
| `DELIR_LOCAL_TRACE=0` | Lo spegne anche senza LangSmith. |
| `DELIR_LOCAL_TRACE_PAYLOAD=0` | Tiene solo tempi, token ed esiti: niente prompt né risposte su disco. |
| `DELIR_LOCAL_TRACE_DIR` | Dove scrivere. Default `data/traces`. |

## Dalla spesa al contenuto

Il registro dei consumi dice **quanto** è costata una chiamata; la traccia dice
**cosa** le è stato mandato. Il campo che le unisce è `operation_id`:

```
uv run python scripts/llm_spend.py traccia <operation_id>
```

mette la riga di spesa e la traccia una sotto l'altra. Se la chiamata è avvenuta
con LangSmith acceso, la traccia locale non c'è e il comando lo dice: è
un'assenza, non un guasto.

## Privacy

I prompt contengono le interviste dei clienti. `data/` è gitignored, i testi si
troncano a 2.000 caratteri, e `DELIR_LOCAL_TRACE_PAYLOAD=0` toglie del tutto i
payload. I file non si potano da soli: sono per giorno, si cancellano per data.

## Quando la quota riparte

Il conteggio è mensile. Quella di settembre 2026 è esaurita dal giorno 6: fino
al 1° ottobre non arriva nessuna traccia su LangSmith, qualunque cosa si
configuri. Da ottobre le 5.000 sono tutte del prodotto, perché i test non le
toccano più.
