# Golden set

Processi veri, con la mappa AS-IS che un consulente avrebbe disegnato, per
misurare quanto DeliR mappa bene - in numeri, e sempre con lo stesso metro.

Due misure diverse, e la differenza e' il punto:

| tratto | dove si misura | quando | puo' essere esatto? |
| --- | --- | --- | --- |
| piano → disegno (compilatore) | `tests/test_golden_graph_metrics.py` | ogni CI | si', e deve esserlo |
| interviste → piano (estrattore LLM) | `tests/evals/test_golden_set.py` | job notturno, `DELIR_GOLDEN_EVAL=1` | no: si misura e si difende dalle regressioni |

## Un caso

```
tests/golden/<case_id>/
  sources/            le fonti, cosi' come sono state raccolte
  expected.json       la mappa di riferimento
  ideal_plan.json     il piano che un estrattore perfetto produrrebbe
```

### `expected.json`

| campo | cosa dice |
| --- | --- |
| `status` | `draft_da_validare` finche' un consulente non l'ha firmato; poi `validated`. Solo i casi `validated` fanno fallire il job notturno |
| `lanes` | corsie, con gli alias con cui un modello potrebbe chiamarle |
| `activities` | attivita' con alias e corsia; `required: false` per cio' che e' corretto ma facoltativo disegnare |
| `gateways` | le decisioni che devono diventare punti di decisione |
| `edges` | l'ordine: `[a, b]` significa "b viene subito dopo a", attraversando gateway ed eventi |
| `forbidden` | cio' che le fonti **non** dicono e un modello tende a inventare, con il perche'. Un elemento vietato rende il modello disonesto, senza tolleranza |
| `open_gaps` | domande che le fonti lasciano aperte; `closed_by_aliases` sono le attivita' che le chiuderebbero inventando |
| `compiler_known_gaps` | cio' che il compilatore oggi non sa esprimere per questo caso. Il test del compilatore su quel caso e' `xfail` **strict**: quando il compilatore migliora il test fallisce finche' la voce non viene tolta |

Gli alias si confrontano per radice di parola (le prime 5 lettere delle parole
di contenuto), non con un modello: "verifico la richiesta" corrisponde a
"verifica richiesta". Scriverne tre o quattro per attivita' basta.

### Scrivere un caso

1. Fonti vere, anonimizzate. Nessun dato cliente non anonimizzato nel repository.
2. La mappa la scrive chi conosce il processo, **dalle fonti e solo da quelle**:
   se una cosa non e' detta non entra fra le attivita', e se un modello tende a
   inventarla va fra i `forbidden`.
3. Il piano ideale nella rappresentazione del contratto dell'estrattore:
   `main_success_path`, decisioni con `outcome_details`, `alternative_paths`.
   `uv run pytest tests/test_golden_graph_metrics.py` deve dare 1.0 su tutte le
   metriche; se non ci arriva, o il piano e' sbagliato o il compilatore ha un
   limite, e va scritto in `compiler_known_gaps`.
4. Un consulente rilegge `expected.json` contro le fonti e porta `status` a
   `validated`.
5. Il primo run notturno sul caso validato produce `reports/<case_id>.json`: se il
   risultato e' accettabile, i suoi numeri entrano in `baseline.json`.

## Perche' i due casi di partenza sono una coppia

`esaote_ciclo_passivo` e `facility_segnalazioni_guasti` sono speculari su un
punto preciso: nel primo la soglia di autorizzazione **non e' detta** (Francesca
rifiuta di dare la cifra) e disegnarla e' un'invenzione; nel secondo la soglia di
5.000 euro e' detta da tre voci ed e' giusto disegnarla. Un estrattore che ha
imparato "le soglie di approvazione esistono" invece di leggere le fonti passa
uno dei due casi e fallisce l'altro.

Due casi non sono un golden set. Servono 20-30 processi di domini diversi,
presi dagli incarichi veri, perche' un numero su due casi e' un aneddoto.
