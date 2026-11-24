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
le verifiche su questo worktree e sulla CI della PR**, che parte dal branch
remoto aggiornato. In particolare verificare la costruzione completa e le
review, la compatibilita' con gli altri lavori confluiti nel branch e il
comportamento di canvas vuoti, subprocessi ed eventi.

Priorita' successive:

1. Eseguire benchmark LLM accoppiati con provider disponibile: stessa
   richiesta, modello, budget e ordine randomizzato. Registrare token reali
   input/output/cache/tool, chiamate, retry, latenza e accuratezza per l'intero
   ciclo di modifica, non solo per la scelta dell'ID.
2. Misurare L4 su descrizioni e fonti con rubriche di elementi mancanti e claim
   senza supporto; confrontare XML e rappresentazioni compatte a parita' di
   input. PET/PMo possono sovrapporsi: deduplicare train/test.
3. Ampliare L3 con analisi conservativa di concorrenza e deadlock, senza
   chiamare sound una prova limitata alla raggiungibilita'.
4. Coprire costrutti XML/namespace non supportati dal DSL e casi concorrenti
   L5 prima di promuovere qualunque formato di scrittura.

Non attivare il DSL v1/v2 per scritture LLM per inseguire il solo target token:
la correttezza dei modelli accettati e la fedelta' alle fonti sono gate di
release. Non salvare dati cliente grezzi, segreti o credenziali nella PR.

## Contesto del branch

Questa PR e' basata su `origin/feat/sim-prosimos-import` aggiornato. Il checkout
locale originario era fermo a un commit piu' vecchio e conteneva anche modifiche
non committate a simulazione, MCP, `pyproject.toml` e `uv.lock`. Solo il lavoro
canvas e' stato trasferito qui; non includere quelle modifiche parallele.
