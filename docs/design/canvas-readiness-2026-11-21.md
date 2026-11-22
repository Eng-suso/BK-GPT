# Canvas DeliR: stato e decisioni per il primo video

## Verifica del testo ricevuto

Il testo descrive correttamente il problema di leggibilità, semantica e fluidità del percorso dimostrato, ma alcune informazioni sono superate. Il motore DeliR è già nel branch `codex/bpmn-canvas-ui` (PR #165): creazione, collegamento, rinomina, Undo, pool/lane e round trip XML sono implementati. Esistono già comandi per vista completa e vista leggibile, lista ricercabile degli elementi, azioni contestuali e proprietà dell'elemento. Il precedente riferimento alla PR come sola proposta non descrive più la quantità di lavoro già presente.

Il percorso in inglese aveva ancora titolo e descrizione della cronologia in italiano, oltre a uno stato di errore riconosciuto tramite la parola italiana `Errore`. La correzione usa stringhe localizzate e lo stato di errore effettivo. L'ispettore ora mostra il nome della lane BPMN separatamente dal responsabile operativo opzionale: un campo vuoto non suggerisce più che la task sia senza collocazione nel processo.

La lista degli elementi ora rispetta la gerarchia pool → lane → attività e conserva il contesto dei risultati di ricerca. La modalità focus libera il canvas dai pannelli laterali senza rimontare il modello; il pannello può essere riaperto con lo stesso stato. Le etichette delle attività sono state ingrandite per la leggibilità durante la registrazione.

## Priorità ancora aperte

1. **P0: prova del video reale.** Eseguire tre volte il percorso procurement del testo allegato su una build congelata, a 1080p, verificando anche la visione su telefono. I test automatici non sostituiscono questa prova.
2. **P0: gate CI della PR #165.** La precedente esecuzione aveva quattro job Playwright cancellati e il gate finale non verde. Integrare la PR solo dopo l'esito completo e la revisione del diff.
3. **P1: errori BPMN raggiungibili.** L'attuale errore testuale di salvataggio non porta sempre al nodo o al campo pertinente. Servono risultati classificati, selezione dell'elemento e spiegazione in linguaggio di processo.
4. **P1: proprietà pertinenti al tipo.** Condizioni, timer, gateway e task devono esporre solo i campi applicabili, distinguendo la semantica eseguibile dalle annotazioni DeliR.
5. **P1: precisione di impaginazione.** Snap, allineamento, distribuzione e routing dei casi complessi restano da progettare e verificare con XML realistici.
6. **P2: condivisione e navigazione.** Export visuale e minimappa aiutano i modelli grandi e la consegna al cliente. La gerarchia navigabile è stata implementata; va ancora provata su modelli cliente estesi.

## Riferimenti verificati

- [ProcessMind, Modeling Canvas](https://processmind.com/resources/docs/modeling/modeling-canvas): palette comprimibile, ricerca, minimappa, fit e comandi di allineamento della selezione.
- [Camunda, Fix problems in your diagram](https://docs.camunda.io/docs/components/modeler/web-modeler/modeling/fix-problems-in-your-diagram/): una riga di errore seleziona l'elemento e la proprietà interessata.
- [Miro, Toolbars](https://help.miro.com/hc/en-us/articles/360017730553-Toolbars): controlli di zoom, fit, minimappa, griglia e snap raccolti nell'area di navigazione.
- [ChatGPT release notes](https://help.openai.com/en/articles/6825453-chatgpt-browser): il pannello laterale può restare aperto con Canvas quando lo spazio lo permette. Per DeliR il principio utile è preservare l'area di lavoro e la camera durante l'apertura dei pannelli, non copiare l'aspetto del prodotto.

REA ha catturato direttamente il canvas documentato di ProcessMind (`ev_d1cb85d9f3d0901ba4746a491e2414bf3107c49d01295db8b5dac48c21a7c645`), il demo pubblico bpmn.io (`ev_acdc71286a9fbd8823777aceefd35005e83e3a1c7bb902`) e la guida Camunda agli errori (`ev_992c7cac87782f65a258b2e761df2134db5247cb33b17fc0346b82e744267686`). Miro ha presentato una challenge Cloudflare (`ev_e74234d03199da9607314a36ed1212977981f1e380167ed241ed649a157e29e7`); Bizagi è andato in timeout dopo il redirect (`ev_205f63ea8069ee78240c9f99657cbd10538b1e1fad186a8b00bc81b9bce77f66`); Signavio e ChatGPT Canvas hanno esposto soltanto un caricamento iniziale incompleto (`ev_6409bcbbea3fc03bad15a824ad1324d3525417b67020fc336e2d823017894771`, `ev_b3a9d93372aed3d1f7b65a37abe50c85669c853fed9eb93a4bc1595022803371`). Per questi ultimi prodotti i confronti si basano sulle guide ufficiali, non sull'uso interattivo degli editor autenticati. Le evidenze REA precedenti del canvas DeliR sono in [canvas-audit-consistency-2026-11-05.md](canvas-audit-consistency-2026-11-05.md).

## Branch

`main` è ancora allineato a `origin/main`. `codex/bpmn-canvas-ui` contiene il nuovo motore e la rifinitura non ancora presenti su `main` ed è pubblicato su GitHub come PR #165 draft. Altri branch non integrati sono filoni indipendenti di simulazione, event log, LLM, test, pitch e documentazione: alcuni condividono storia e file. Non vanno sommati automaticamente al canvas o riscritti mentre i relativi worktree contengono lavoro locale.

La prova locale mirata sul branch corrente ha passato 32 test di viewport, XML e move rules, un test sul ruolo lane, TypeScript e il nuovo test E2E Chromium del focus e della gerarchia. Lo screenshot a 1600×900 è stato controllato nel checkout pulito. Il test backend `test_manual_canvas_roundtrip.py` richiede lo stack Postgres di test, che qui era spento. La disponibilità del canvas per il video e la convergenza su `main` restano subordinate ai gate sopra.
