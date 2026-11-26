# Canvas patch: baseline locale

Misurata il 24 novembre 2026 sul checkout corrente con tre fixture pubbliche del
repository. Riprodurre con:

```powershell
uv run python -m scripts.benchmark_canvas_patch --repeat 5
```

Il benchmark normalizza il BPMN una volta come farebbe il salvataggio agentico,
poi rinomina una task sul modello normalizzato. Ogni ripetizione misura patch,
layout e validazione; la tabella riporta le mediane. Il controllo di integrita'
confronta tutti gli elementi semantici e i loro attributi, escluso il nome della
task rinominata e la geometria DI.

| Fixture | Nodi / flow | Prompt scope intero | Prompt scope patch | Patch | Layout | Validazione |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| purchase_layout | 8 / 9 | 3.832 token | 864 token | 0,63 ms | 43,24 ms | 2,52 ms |
| multibranch_layout | 10 / 11 | 4.181 token | 864 token | 0,58 ms | 20,20 ms | 2,28 ms |
| omg_issue_list | 6 / 6 | 2.696 token | 864 token | 0,43 ms | 10,89 ms | 1,36 ms |

Tokenizer: `o200k_base`. Tutti e tre i casi hanno preservato identificativi,
collegamenti, condizioni e altri dati semantici non modificati.

Con Postgres e Neo4j dello stack di test attivi, un secondo test salva tre rinomine
per fixture e rilegge ogni versione da Postgres. Ogni modifica crea esattamente
una versione e preserva la semantica non toccata. Mediana del tratto
`update_bpmn_model` + rilettura, su tre ripetizioni:

| Fixture | Salvataggio + rilettura |
| --- | ---: |
| purchase_layout | 96,33 ms |
| multibranch_layout | 99,55 ms |
| omg_issue_list | 45,60 ms |

Dopo l'aggiunta del gate XSD OMG, una nuova esecuzione locale dello stesso test
ha dato 180,93 / 83,03 / 64,66 ms rispettivamente. Con tre ripetizioni e
Postgres locale i tempi oscillano: non attribuire la differenza al solo gate.
Misurato isolatamente su 15 ripetizioni, il controllo locale + XSD su un
diagramma legacy invariato ha una mediana di 2,12 / 2,66 / 1,93 ms nei tre
casi. Per una conclusione sulla latenza del prodotto servono piu' ripetizioni
e il turno completo dell'agente.

Riprodurre con lo stack di test attivo:

```powershell
.venv\Scripts\python.exe -m pytest tests/evals/l0_deterministic/test_canvas_patch_persistence_baseline.py -q -s
```

La prima tabella descrive solo il lavoro Python in locale; la seconda include
Postgres locale. Non includono rete esterna, browser, costruzione completa del prompt, tool schema, chiamate LLM,
cache, retry o aggiornamento visibile del canvas. Il numero di token riguarda
solo il prompt di scope costruito per un fixture con XML e senza fonti o piano.
Non e' un benchmark P95 di produzione e non dimostra un risparmio sul costo
complessivo del turno.

La prossima baseline richiede un turno completo con lo stack dati attivo:
numero e durata delle chiamate LLM, token input/output/cache, tool call, versioni
create, tempo al canvas aggiornato e tempo alla verifica finale. Va ripetuta su
processi piu' grandi e su modifiche strutturali, con confronto contro le fonti.
