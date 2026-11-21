# Canvas DeliR: stato e decisioni per il primo video

## Verifica del testo ricevuto

Il testo descrive correttamente il problema di leggibilità, semantica e fluidità del percorso dimostrato, ma alcune informazioni sono superate. Il motore DeliR è già nel branch `codex/bpmn-canvas-ui` (PR #165): creazione, collegamento, rinomina, Undo, pool/lane e round trip XML sono implementati. Esistono già comandi per vista completa e vista leggibile, lista ricercabile degli elementi, azioni contestuali e proprietà dell'elemento. Il precedente riferimento alla PR come sola proposta non descrive più la quantità di lavoro già presente.

Il percorso in inglese aveva ancora titolo e descrizione della cronologia in italiano, oltre a uno stato di errore riconosciuto tramite la parola italiana `Errore`. La correzione usa stringhe localizzate e lo stato di errore effettivo. L'ispettore ora mostra il nome della lane BPMN separatamente dal responsabile operativo opzionale: un campo vuoto non suggerisce più che la task sia senza collocazione nel processo.

## Priorità ancora aperte

1. **P0: prova del video reale.** Eseguire tre volte il percorso procurement del testo allegato su una build congelata, a 1080p, verificando anche la visione su telefono. I test automatici non sostituiscono questa prova.
2. **P0: gate CI della PR #165.** La precedente esecuzione aveva quattro job Playwright cancellati e il gate finale non verde. Il push dei due commit di rifinitura ha avviato una nuova CI; integrare la PR solo dopo l'esito completo e la revisione del diff.
3. **P1: errori BPMN raggiungibili.** L'attuale errore testuale di salvataggio non porta sempre al nodo o al campo pertinente. Servono risultati classificati, selezione dell'elemento e spiegazione in linguaggio di processo.
4. **P1: proprietà pertinenti al tipo.** Condizioni, timer, gateway e task devono esporre solo i campi applicabili, distinguendo la semantica eseguibile dalle annotazioni DeliR.
5. **P1: precisione di impaginazione.** Snap, allineamento, distribuzione e routing dei casi complessi restano da progettare e verificare con XML realistici.
6. **P2: condivisione e navigazione.** Export visuale, minimappa e gerarchia navigabile aiutano i modelli grandi e la consegna al cliente, ma non risolvono i primi cinque punti.

## Riferimenti verificati

- [ProcessMind, Modeling Canvas](https://processmind.com/resources/docs/modeling/modeling-canvas): palette comprimibile, ricerca, minimappa, fit e comandi di allineamento della selezione.
- [Camunda, Fix problems in your diagram](https://docs.camunda.io/docs/components/modeler/web-modeler/modeling/fix-problems-in-your-diagram/): una riga di errore seleziona l'elemento e la proprietà interessata.
- [Miro, Toolbars](https://help.miro.com/hc/en-us/articles/360017730553-Toolbars): controlli di zoom, fit, minimappa, griglia e snap raccolti nell'area di navigazione.
- [ChatGPT release notes](https://help.openai.com/en/articles/6825453-chatgpt-browser): il pannello laterale può restare aperto con Canvas quando lo spazio lo permette. Per DeliR il principio utile è preservare l'area di lavoro e la camera durante l'apertura dei pannelli, non copiare l'aspetto del prodotto.

Questi riferimenti descrivono funzioni documentate, non una prova interattiva degli editor autenticati. Le evidenze REA precedenti del canvas DeliR e del demo bpmn.io sono in [canvas-audit-consistency-2026-11-05.md](canvas-audit-consistency-2026-11-05.md).

## Branch

`main` è ancora allineato a `origin/main`. `codex/bpmn-canvas-ui` contiene il nuovo motore e la rifinitura non ancora presenti su `main` ed è pubblicato su GitHub come PR #165 draft. Altri branch non integrati sono filoni indipendenti di simulazione, event log, LLM, test, pitch e documentazione: alcuni condividono storia e file. Non vanno sommati automaticamente al canvas o riscritti mentre i relativi worktree contengono lavoro locale.

La prova locale mirata sul branch corrente ha passato 32 test di viewport, XML e move rules, un test sul ruolo lane e TypeScript. Il test backend `test_manual_canvas_roundtrip.py` richiede lo stack Postgres di test, che qui era spento. La disponibilità del canvas per il video e la convergenza su `main` restano subordinate ai gate sopra.
