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

## Cosa resta da misurare

1. Ripetizioni (>= 5) e piu' casi, con intervalli di confidenza; un secondo
   modello per controllare che il risultato non dipenda dal provider.
2. Il ciclo nel runtime LangGraph vero, con prompt di sistema e schema dei tool
   di produzione, e con scrittura nel database di test.
3. L4 su un dataset con fonti vere (PMo, PET deduplicati) e rubrica di claim.
