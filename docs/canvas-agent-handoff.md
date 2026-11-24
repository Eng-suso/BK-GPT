# Canvas process agent: handoff per la PR

## Obiettivo di Sohay

Costruire un generatore e agente di processi nel canvas che minimizzi i token
senza perdere significato aziendale, dettagli BPMN o parti del modello durante
le modifiche. Il riferimento normativo e' OMG BPMN 2.0.2. Il prodotto deve
assorbire la complessita': il consulente lavora su passaggi, ruoli, decisioni e
fonti, non su XML, ID o path tecnici.

Target richiesti:

| KPI | Target |
| --- | ---: |
| Riduzione token della rappresentazione | >=85% |
| Riduzione token complessivi per operazione | >=50% |
| Riduzione token nelle modifiche locali | >=90% |
| Validita' BPMN dei modelli accettati | 100% sui controlli implementati |
| Conservazione delle informazioni nel round trip | 100% sui costrutti supportati |
| Modifiche collaterali non richieste | 0 |
| Accuratezza semantica | >= baseline XML |
| Hallucination rate | < baseline XML |

L1 syntax, L2 conformance BPMN, L3 comportamento, L4 fedelta' alle fonti e L5
integrita' delle modifiche vanno riportati separatamente. Nessun numero su un
solo livello certifica gli altri.

## Decisione architetturale

Leggere `docs/architecture/adr-001-canvas-process-representation.md` prima di
modificare l'architettura. Le evidenze e il `ProcessUnderstanding` versionato
sono la fonte del significato; BPMN 2.0 XML con DI e' il formato canonico
salvato; l'agente usa una mappa compatta di sola lettura per edit locali e
operazioni atomiche con ID stabili sul modello originale. DeliR DSL v1/v2 sono
esperimenti reversibili, **non** formati di scrittura LLM attivi. TOK e BPCF
restano comparatori; non incorporare codice TOK GPL nel prodotto.

Percorso implementato in questa PR:

1. `backend/agents/primary_scope.py` include la mappa completa nel prompt di
   modifica locale quando entra nel budget. Una mappa che verrebbe troncata
   viene omessa: il tool `manage_canvas_bpmn_model(map)` deve leggerla.
2. `backend/bpmn/compact_canvas_map.py` espone ID, tipi, etichette, lane e
   archi, senza pretendere di ricostruire tutto il BPMN.
3. `backend/bpmn/edit_integrity.py` controlla le differenze semantiche ammesse
   per update/add/delete/connect/reconnect/layout/clear prima della scrittura.
4. `backend/bpmn/omg_conformance.py` usa gli XSD OMG in `backend/bpmn/xsd/`.
   Nuove costruzioni complete e review approvate devono passare XSD e il
   controllo L3 del grafo principale. Gli edit locali di un modello legacy
   non possono introdurre nuovi errori XSD.
5. `backend/bpmn/xml_behavior.py` legge il BPMN effettivo, controlla
   raggiungibilita', uscite e confini dei sequence flow; i risultati L2 e L3
   sono separati nel report. Le bozze locali possono restare incomplete, ma
   un processo completato/approvato con nodi irraggiungibili viene rifiutato
   prima di XML, versione o stato approved.

## Misure gia' ottenute

Leggere `docs/canvas-representation-benchmark.md` e
`docs/canvas-patch-performance-baseline.md` per metodo e dettagli.

Sul corpus pubblico PMo 1.0.0, 55 modelli BPMN standardizzati:

- DeliR DSL v1: 55/55 round trip semantici esatti, riduzione token mediana
  76,3% rispetto all'XML completo. V2: 55/55, 77,02%. Nessuna raggiunge il
  target 85% come documento autonomo.
- Mappa locale: riduzione mediana 88,02%, 55/55 sopra l'85%. E' incompleta per
  definizione; conserva le informazioni perche' il runtime mantiene l'XML.
- TOK 1.0.4: riduzione mediana 88,8%, ma 0/55 round trip dell'intero albero
  semantico esatti. Questo non dimostra che tutti i 55 grafi siano alterati.
- Mermaid: 93,09% su 55 file pubblicati; JSON Branches: 91,28% sui 18 file
  disponibili. Il round trip semantico non e' verificato.
- 46/55 XML PMo passano gli XSD OMG; DeliR conserva questo stato nel round
  trip. 55/55 passano i soli controlli L3 di raggiungibilita' del grafo
  principale, non una prova formale di assenza deadlock.
- Prompt locale con mappa inline: riduzione mediana 76,86% rispetto al prompt
  canvas pieno. Prima, senza mappa inline, era 87,42%, ma l'agente doveva fare
  una chiamata tool aggiuntiva. I token dell'operazione completa non sono
  ancora misurati.

La prima prova LLM accoppiata XML/mappa (`scripts/benchmark_canvas_live_selection.py`)
non ha prodotto un risultato: sei chiamate hanno ricevuto `RateLimitError` dal
provider il 24/11/2026. Il benchmark ora si ferma al primo errore provider e
non lo conta come errore di accuratezza del modello.

## Verifiche e prossimi lavori per l'agente

Nel checkout originario sono passati 436 test BPMN prima dell'ultimo gate L3,
poi 70 test mirati dopo il gate; Ruff e `git diff --check` erano verdi. **Rifare
le verifiche sulla CI della PR** dopo ogni modifica. In particolare verificare la costruzione completa e le
review, la compatibilita' con gli altri lavori confluiti nel branch e il
comportamento di canvas vuoti, subprocessi ed eventi.

Stato del lavoro aperto della PR (aggiornato il 24/11/2026, secondo giro):

1. **Benchmark LLM accoppiati sul ciclo di modifica**: harness
   `scripts/benchmark_canvas_edit_cycle.py` (tool loop con funzioni di
   produzione e controllo L5). Prima sonda su `gemini-3.5-flash-lite`: 6/6
   corretti, 1 chiamata per caso, token -80,79% mediano con la mappa. Risultati
   e limiti in `docs/canvas-llm-benchmarks.md`. **Aperto**: ripetizioni, piu'
   casi, secondo modello, runtime LangGraph vero con prompt e schema tool di
   produzione.
2. **L4**: harness `scripts/benchmark_canvas_source_fidelity.py` con
   omissione e passo inventato piantati, XML vs DSL v1 vs mappa. Prima sonda su
   2 casi, nessuna regressione evidente della forma compatta. **Aperto**:
   dataset con fonti vere (PMo/PET deduplicati) e campione sufficiente.
3. **L3 concorrenza e deadlock**: fatto. `backend/bpmn/xml_behavior.py`
   esplora il grafo come gioco dei token limitato e rifiuta, nelle costruzioni
   complete e nelle approvazioni, deadlock, mancata sincronizzazione e
   esecuzioni che non terminano. Fuori ambito dichiarato: gateway
   inclusivi/complessi, uscite condizionali da attivita', interni dei
   subprocessi, budget di stati superato.
4. **Costrutti XML/namespace e L5 concorrente**: fatto. Il DSL conserva i
   prefissi usati nei QName; L5 provato su Postgres per tutte le operazioni
   locali e per scritture concorrenti. Trovato e corretto un difetto: eliminare
   un'attivita' collegata a un dato lasciava un'associazione pendente e il
   salvataggio falliva. **Aperto**: promozione di un formato di scrittura
   ancora bloccata dai gate L4/L5 su campioni piu' ampi.
5. **Gate al salvataggio verso il consulente**: fatto. `BpmnSaveRejected`
   porta una frase per il consulente (nomi dei passaggi, nessun ID o path XSD)
   e il dettaglio tecnico per l'agente. Spec full-stack
   `e2e-fullstack/save-gate.spec.ts` sul processo "Approvazione fatture" del
   seed.

Terzo giro (24/11/2026, chiave Groq di test):

- Benchmark su tre modelli Groq con client che aspetta i limiti al minuto e
  conta i retry: tool loop `gpt-oss-20b` 7 casi x 3 (XML 21/21, mappa 20/21,
  token -77,17%), L4 `qwen3.8-27b` 5 casi x 3 (recall 15/15 ovunque, falsi
  positivi XML 0 / DSL 2 / mappa 3), runtime di produzione su una coppia.
- `benchmark_canvas_prompt_budget`: nel Patch/Edit la prima chiamata con mappa
  e' per il 71% prompt fisso. E' qui il prossimo margine sul KPI per
  operazione, non nella rappresentazione del canvas.
- La mappa ora porta associazioni e data association (`canvas-map 2`).
- Da sistemare nel prodotto: nel giro runtime la risposta al consulente
  conteneva ID tecnici, contro il contratto del subgraph.

Non attivare il DSL v1/v2 per scritture LLM per inseguire il solo target token:
la correttezza dei modelli accettati e la fedelta' alle fonti sono gate di
release. Non salvare dati cliente grezzi, segreti o credenziali nella PR.

## Contesto del branch

Questa PR parte da `origin/main` (40edf62d, dopo #174) e punta a `main`. Il
lavoro e' nato in un checkout fermo su `feat/sim-prosimos-import` (gia'
mergiato con #169) insieme a modifiche parallele su simulazione e MCP. Qui c'e'
solo il lavoro canvas; il server MCP ha una PR separata. Non includere
modifiche a simulazione, `pyproject.toml` o `uv.lock`.

Verifica del primo giro (24/11/2026): 518 test superati
(`tests/bpmn`, `tests/agents/test_canvas_graph.py`,
`tests/agents/test_context_budget.py`, `tests/evals/l0_deterministic/test_canvas_*`)
sullo stack di test 55301; Ruff e `git diff --check` verdi. Nessuna migrazione
Alembic nuova.

Verifica del secondo giro (24/11/2026): 602 test superati sullo stesso
perimetro piu' i test agent canvas collegati, su uno stack di test proprio
(porta 55375); suite e2e full-stack 8/8 con la nuova spec; Ruff verde. Nessuna
migrazione Alembic nuova.
