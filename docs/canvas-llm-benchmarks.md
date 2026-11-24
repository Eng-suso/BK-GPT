# Benchmark LLM accoppiati del canvas: ciclo di modifica e L4

Data: 24 novembre 2026. Prima misura con un modello vero dopo il tentativo
bloccato da `RateLimitError` (vedi `docs/canvas-agent-handoff.md`).

**Leggere i numeri come sonda, non come prova.** Un solo modello, una sola
ripetizione, 3 casi per il ciclo di modifica e 2 per L4. Servono piu'
ripetizioni, piu' casi e intervalli di confidenza prima di usarli per una
scelta di release (protocollo in ADR-001).

## Configurazione

- Modello: `gemini-3.5-flash-lite` via endpoint compatibile OpenAI di Google AI
  Studio, chiave di test (`DELIR_TEST_LLM_API_KEY`), temperatura 0.
- Free tier: 5 richieste al minuto, quindi `--min-interval 13`. La latenza
  misura solo la chiamata, non l'attesa.
- Ordine dei casi mescolato con seme fisso (20261124), stessi prompt e budget
  per ogni rappresentazione.
- Solo fixture sintetiche o pubbliche (`tests/fixtures/`); nessun dato cliente.

Comandi:

```bash
uv run python -m scripts.benchmark_canvas_edit_cycle --repeat 1 --min-interval 13 \
  --model gemini-3.5-flash-lite \
  --base-url https://generativelanguage.googleapis.com/v1beta/openai/
uv run python -m scripts.benchmark_canvas_source_fidelity --repeat 1 --min-interval 13 \
  --model gemini-3.5-flash-lite \
  --base-url https://generativelanguage.googleapis.com/v1beta/openai/
```

Il calcolo dei punteggi e' coperto da
`tests/evals/l0_deterministic/test_canvas_llm_benchmarks.py`, senza modello.

## Ciclo di modifica completo (`benchmark_canvas_edit_cycle`)

Richiesta del consulente, canvas come XML completo con DI oppure come mappa di
navigazione, due tool (`update_element`, `delete_element`) che chiamano le
funzioni di produzione e il controllo L5. Il ciclo finisce alla prima modifica
applicata o dopo 3 chiamate. Corretto = albero semantico risultante identico a
quello dell'operazione attesa.

| Rappresentazione | Corretti | Violazioni L5 | Chiamate (mediana) | Token input+output (mediana) |
| --- | ---: | ---: | ---: | ---: |
| XML completo | 3/3 | 0 | 1 | 3.530 |
| Mappa | 3/3 | 0 | 1 | 678 |

Riduzione mediana dei token per operazione: **80,79%**. Per caso: minimal
1.012 → 331, purchase (eliminazione) 3.530 → 678, multibranch 3.956 → 876.
Nessun token di cache riportato dal provider. In questo giro la latenza
registrata includeva l'attesa del pacing ed e' stata scartata; lo script e'
stato corretto dopo il giro.

Limiti: tool loop con le funzioni di produzione, non il runtime LangGraph
(prompt di sistema reale, schema di tutti i tool, scrittura nel database). I
token del prompt di sistema di produzione e degli schema tool non sono inclusi
e riducono la percentuale reale.

## L4, fedelta' alle fonti (`benchmark_canvas_source_fidelity`)

Stessa fonte e stesso modello BPMN, con un passaggio della fonte tolto e un
passaggio inventato aggiunto per costruzione. Il modello deve elencare cio' che
manca e cio' che la fonte non sostiene. Ogni altra segnalazione conta come
falso positivo.

| Rappresentazione | Omissione trovata | Passo inventato trovato | Falsi positivi | Token input (mediana) |
| --- | ---: | ---: | ---: | ---: |
| XML completo | 1/2 | 2/2 | 0 | 2.683 |
| DeliR DSL v1 | 2/2 | 2/2 | 0 | 825,5 |
| Mappa | 2/2 | 2/2 | 1 | 531 |

Lettura prudente: su questi due casi la rappresentazione compatta non ha
peggiorato il rilevamento rispetto all'XML; la mappa ha prodotto un falso
positivo. Due casi non bastano per confrontare hallucination rate.

## Secondo giro: Groq, piu' casi, ripetizioni, runtime vero

Chiave di test Groq (`gsk_`), endpoint `https://api.groq.com/openai/v1`. Free
tier: 8.000 token al minuto e circa 200.000 al giorno per modello (500.000 per
qwen). Il client (`scripts/live_llm_support.py`) aspetta il tempo chiesto dal
provider sui limiti al minuto, conta i retry e li toglie dalla latenza; si
ferma subito sui limiti giornalieri. Intervalli al 95% di Wilson.

### Tool loop, 7 casi x 3 ripetizioni, `openai/gpt-oss-20b`

Ai tre casi del primo giro si aggiungono una rinomina in purchase, una in un
modello inglese (omg_issue_list), un'eliminazione in multibranch e un caso
**ambiguo** (due "Verifica pratica principale"): li' e' corretto non
modificare e chiedere.

| Rappresentazione | Corretti | IC 95% | Violazioni L5 | Chiamate (mediana) | Token (mediana) | Latenza (mediana) |
| --- | ---: | --- | ---: | ---: | ---: | ---: |
| XML completo | 21/21 | 0,845-1,0 | 0 | 1 | 3.478 | 769 ms |
| Mappa | 20/21 | 0,773-0,992 | 0 | 1 | 794 | 592 ms |

Riduzione mediana dei token: **77,17%**. L'unico errore e' sul caso ambiguo:
una volta su tre, con la mappa, il modello ha rinominato uno dei due passaggi
invece di chiedere. Con questo campione la differenza non e' significativa
(intervalli sovrapposti); va tenuta d'occhio. 40 retry per limite al minuto,
nessun errore del provider.

### Runtime di produzione (`benchmark_canvas_runtime`), una coppia, `openai/gpt-oss-120b`

Subgraph Patch/Edit vero, prompt e schema dei tool di produzione, scrittura
sullo stack di test. Un solo caso (eliminazione in multibranch):

- Mappa: corretto, 3 chiamate (due chiamate al tool del canvas, poi la
  risposta), 30.320 token di input in tutto, ~10.000 per chiamata sul
  tokenizer del provider. Quali operazioni abbia chiesto non era registrato
  in questo giro; ora lo script le salva (`tool_operations`).
- XML: eliminazione corretta e salvata in 2 chiamate (27.968 token di input),
  poi la richiesta successiva (8.079 token) e' stata rifiutata con 413 perche'
  supera il limite del free tier. Sul piano gratuito il percorso XML non
  arriva in fondo al turno.
- La risposta al consulente con la mappa riportava ID tecnici ("Task 0_B",
  "Gateway 0") nonostante il contratto del subgraph lo vieti.

Il free tier consente circa 6 giri di questo tipo al giorno per modello: la
misura accoppiata completa del runtime resta da fare con una quota maggiore.

### Dove vanno i token di una chiamata (`benchmark_canvas_prompt_budget`, senza modello)

Prima chiamata del Patch/Edit, token o200k, mediana su 4 fixture:

| Parte | XML | Mappa |
| --- | ---: | ---: |
| Prompt di scope (contiene il canvas) | 3.311 | 1.232 |
| Memoria procedurale | 1.295 | 1.295 |
| Schema dei tool | 1.040 | 1.040 |
| Contratto del subgraph | 747 | 747 |
| Richiesta | 15 | 15 |
| **Totale** | **6.408** | **4.330** |

La mappa riduce la prima chiamata del 32% (mediana). Nella chiamata con la
mappa il 71% e' prompt fisso. **Il target >=50% per operazione non si
raggiunge comprimendo ancora il canvas**: servono un prompt fisso piu' corto
per il Patch/Edit e meno chiamate (niente rilettura via tool quando la mappa e'
gia' nel prompt, risposta finale breve).

### L4, 5 casi x 3 ripetizioni, `qwen/qwen3.8-27b`

Due casi nuovi in italiano (purchase con il ramo urgente tolto, multibranch) e
uno in inglese (issue list senza l'invio). Rubrica rivista dopo aver letto le
risposte grezze: ogni omissione ha le formulazioni della fonte accettate, e le
conseguenze vere della modifica piantata (il ciclo del venerdi' sparisce con
l'invio) non contano come falsi positivi. `--rescore` ricalcola un report
salvato senza chiamare il modello.

Giro con la mappa `canvas-map 2` (associazioni e data association come archi):

| Rappresentazione | Omissioni trovate | Passi inventati trovati | Falsi positivi | Token input (mediana) |
| --- | ---: | ---: | ---: | ---: |
| XML completo | 15/15 (IC 0,80-1,0) | 15/15 | 0 | 3.647 |
| DeliR DSL v1 | 15/15 | 15/15 | 2 | 925 |
| Mappa | 15/15 | 15/15 | 3 | 608 |

Tutti i falsi positivi sono lo stesso: nel caso purchase il modello dice che
manca "allegando il documento di richiesta", che invece c'e'. Nel giro
precedente, con la mappa senza archi di dati, succedeva 3 volte su 3 con la
mappa e mai con DSL e XML. Aggiunti gli archi, resta 3/3 con la mappa e
compare 2/3 col DSL, che l'associazione l'ha sempre avuta. Quindi non e' solo
un'informazione mancante: nelle forme compatte il legame tra un passaggio e il
suo documento e' meno leggibile per il modello. E' l'unico segnale di
fedelta' peggiore delle forme compatte in questa sonda; casi sintetici, un
modello.

## Cosa resta da misurare

1. Runtime accoppiato completo (7 casi, ripetizioni) con una quota che regga
   ~30.000 token a giro.
2. L4 su fonti vere (PMo/PET deduplicati) e rubrica rivista da una persona.
3. Riduzione del prompt fisso del Patch/Edit, poi rimisura del KPI per
   operazione.
