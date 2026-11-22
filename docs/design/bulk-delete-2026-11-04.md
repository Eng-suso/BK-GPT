# Cancellazione multipla del canvas

Riprodotto il difetto con LaneA, LaneB e TaskA selezionati in quest'ordine: il pulsante eliminava soltanto LaneA. Il ramo dedicato alle lane controllava il primo oggetto della selezione e terminava prima di gestire gli altri. Canc/Backspace avevano inoltre un percorso diverso e non rispondevano con il focus sulla barra della selezione.

Pulsante, menu contestuale e tastiera usano ora lo stesso comando del motore. Gli oggetti esplicitamente selezionati vengono eliminati prima di rimuovere le lane; il lavoro non selezionato viene conservato secondo il comportamento del comando delle lane. Un contenitore selezionato elimina i propri discendenti, senza tentare di eliminarli una seconda volta. Etichette e proprietari vengono deduplicati; le radici del documento rimangono protette. L'intera operazione occupa un solo passo nella cronologia.

Il menu multiplo usa il testo condiviso «Elimina selezione». Dopo la cancellazione il canvas riceve il focus. Nei campi di testo, nella rinomina e nei menu la tastiera mantiene il proprio significato: Backspace non elimina gli oggetti del modello.

Prove su fixture sintetiche, senza modificare o salvare il diagramma utente aperto:

- Sette casi Chromium: rettangolo di selezione, selezione mista lane/attività, eliminazione totale da pulsante, Canc, Backspace e menu; protezione di un campo di testo.
- Tre casi WebKit: selezione mista, Canc con focus sulla barra e menu contestuale.
- Dieci unit test mirati: normalizzazione della selezione, ordine di cancellazione, protezione delle radici e contratto XML.
- Undo riporta strutture, collegamenti ed etichette; dopo il salvataggio l'XML ripristinato coincide esattamente con la sorgente.

[Risultati, XML salvati e schermata](proofs/bulk-delete-2026-11-04) accompagnano le prove. `validation.json` distingue anche le regressioni delle lane, schema XML e controlli statici finali. La batteria iniziale ha riprodotto il ramo incompleto e il mancato inoltro della tastiera; le esecuzioni finali sono successive alle correzioni. Una prova intermedia del menu è stata interrotta dopo aver corretto il selettore al nuovo testo condiviso.

Formato BPMN XML, API e storage rimangono invariati. La ricerca UX di riferimento è già documentata nei rapporti [menu e lane](canvas-context-ux-2026-11-04.md) e [partizioni](pool-partitions-ux-2026-11-04.md); questa correzione riguarda l'esecuzione dei comandi DeliR. WebKit locale non certifica dispositivi iOS reali.
