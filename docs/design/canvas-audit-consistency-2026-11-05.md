# Revisione REA del canvas e contratto di consistenza

## Conclusione

Il divario principale è nella precisione dei comportamenti, nella visibilità della gerarchia BPMN e nella capacità di completare un'attività senza dover correggere manualmente l'interfaccia. Aggiungere altri riquadri o un catalogo più lungo non risolve questo divario.

La revisione combina osservazione della schermata DeliR aperta, analisi del codice disponibile, confronto sul demo bpmn.io tramite Playwright e osservazione passiva REA. Miro, Bizagi e ProcessMind sono stati consultati tramite documentazione ufficiale, senza dichiarare una prova interattiva dei loro editor autenticati. Le schermate conservate usano soltanto fixture sintetiche.

## Difetti corretti in questo aggiornamento

1. **Forme coperte dalla pool.** La schermata mostrava linee apparentemente staccate. L'ispezione DOM ha trovato percorsi corretti rispetto alle coordinate dei nodi, mentre la pool veniva dipinta dopo lane libere e relativo lavoro. Il precedente ordinamento trattava pool e lane allo stesso livello e non interveniva in assenza di collegamenti. Ora vengono prima i partecipanti, poi le lane, poi le linee e infine gli altri oggetti dello stesso contenitore. Un secondo ordinamento non genera mutazioni DOM. Questo corregge la visibilità, non assegna arbitrariamente lane a un processo diverso.
2. **Rinomina enorme sui contenitori.** Pool e lane usavano la larghezza della forma come un normale task e l'altezza del testo ruotato. L'editor ora usa un ingombro compatto vicino all'etichetta. Segue i cambi di geometria senza riselezionare il testo a ogni misura, non aggiorna lo stato se le misure sono identiche e ripristina l'etichetta quando viene chiuso.
3. **Catalogo incoerente.** Il raggruppamento leggeva frammenti dell'ID dello strumento. Varianti come `create.start-message` finivano fra le attività, il gateway basato su eventi fra gli eventi e i dati fra gli artefatti. Ora la categoria deriva dal tipo BPMN; i gruppi vuoti non vengono mostrati.
4. **Contratto condiviso dei pulsanti.** Un Button nativo senza tipo esplicito ora è `type="button"`. Solo un submit dichiarato invia il form; `asChild` conserva la semantica del figlio. Questo vale per tutti i consumatori del componente comune.
5. **Invii sovrapposti nei moduli.** FormDialog ora blocca un secondo submit sincronicamente, prima che il parent abbia aggiornato `isSubmitting`, e mantiene il blocco durante l'eventuale Promise del submit. Il blocco viene rilasciato al termine, per consentire un nuovo tentativo. Non equivale a deduplicazione delle richieste sul server.

## Cosa manca e cosa va rivisto

| Priorità | Area | Situazione verificata | Risultato richiesto |
| --- | --- | --- | --- |
| P0 | Gerarchia pool/lane | Possono esistere lane di un processo senza partecipante disegnato, sovrapposte graficamente a una pool appartenente a un altro processo. La sola vicinanza visiva non cambia l'XML. | Rendere esplicito l'owner nella struttura e offrire un'adozione deliberata con anteprima, controlli sui flussi e Undo; nessuna riparazione silenziosa all'apertura. |
| P1 | Precisione del disegno | Il canvas integra movimento e spazio, ma non carica snapping, allineamento e distribuzione; la selezione multipla espone soprattutto eliminazione e deselezione. | Guide di allineamento, aggancio regolabile, allinea/distribuisci e piccoli spostamenti da tastiera. |
| P1 | Collegamenti | La deviazione dagli ostacoli è locale, limitata ai nuovi percorsi e restituisce il percorso originario se non trova un'alternativa. | Casi complessi coperti, etichette leggibili, ripristino/ricalcolo esplicito e spiegazione del bersaglio rifiutato. Distinguere chiaramente il significato dei flussi esecutivi dalle associazioni documentali, conservando la preferenza di movimento. |
| P1 | Proprietà BPMN | L'ispettore presenta prevalentemente nome, documentazione e metadati DeliR; alcuni marcatori importati sono letti e disegnati senza corrispondenti controlli di modifica. | Campi pertinenti al tipo: condizione/default del flusso, timer, messaggi, loop/multiistanza e sottoprocesso. Distinguere metadati operativi da semantica eseguibile. |
| P1 | Errori utilizzabili | La validazione al salvataggio può restituire un elenco testuale di ID. Evidenze/provenienza sono già presenti e sono un problema diverso. | Elenco di problemi cliccabili, elemento evidenziato, spiegazione comprensibile e distinzione fra errore BPMN, collisione grafica e avviso. |
| P1 | Gerarchia dei pannelli | Libreria di creazione e lista degli elementi sono superfici diverse; la lista è piatta. Dettagli del processo e proprietà della selezione hanno accessi distinti. | Un accesso sinistro coerente per Crea/Struttura, gerarchia processo→pool→lane→nodo e un ispettore con contesto esplicito. Ridurre Recenti/Rapidi duplicati e mantenere camera e selezione stabili. |
| P1 | Menu contestuali | Le icone e i tipi diretti ci sono; il selettore è una lista senza ricerca. Sul demo bpmn.io sono visibili filtro e controlli dei marcatori. | Ricerca veloce mantenendo le voci dirette richieste, scelte compatibili e azioni primarie riconoscibili vicino alla selezione. |
| P2 | Contenuti e consegna | Dal canvas l'export è BPMN XML; non c'è un percorso completo di frame e export visuale. | Frame di presentazione, lettura pulita, export SVG/PNG/PDF con area e scala esplicite. I frame di presentazione non devono diventare pool BPMN o cambiare i flussi. |
| P2 | Revisione collaborativa | Chat, versioni e conflitto di salvataggio esistono già; non equivalgono a commenti ancorati e collaborazione sincrona. | Commenti legati a elementi, confronti visivi e gestione dei conflitti comprensibile; valutare presenza live in base all'uso reale. |

## Contratto applicabile ai componenti condivisi

- Apertura, chiusura, focus, hover, selezione e rendering non modificano il documento.
- Applicare nuovamente una misura o uno stato già corrente non crea nuovi elementi, listener, editor o comandi.
- Una conferma produce una sola operazione durante il suo intervallo di esecuzione. Un tentativo successivo deliberato rimane possibile.
- Ogni gesto termina con un commit oppure con la pulizia completa dell'anteprima; blur, cancellazione ed Escape non lasciano oggetti agganciati.
- Undo ripristina la geometria e l'XML di partenza; i cicli di pannelli ripristinano la stessa camera.
- Le proiezioni grafiche non cambiano l'owner BPMN. Creare due nodi con due azioni deliberate resta un comportamento intenzionale: l'obiettivo è impedire duplicazioni involontarie, non rendere inerti i comandi.
- Il contratto va verificato sui consumatori dei componenti comuni. Non costituisce una certificazione dell'intera applicazione o dell'idempotenza di tutte le API backend.

## Fonti

- [bpmn.io, demo pubblico](https://demo.bpmn.io/new): selettore dei task, ricerca e marcatori; gesti Playwright, screenshot passivo REA `ev_71651e5bd1a869d9733882af26ee31c9e483c163f555afc8ef320d9ea26a45e1`. La prova di rinomina di lane nel demo non ha prodotto l'editor atteso e non è usata come conferma del relativo comportamento.
- [Bizagi, Ribbon](https://help.bizagi.com/platform/en/the_ribbon.htm): allineamento/distribuzione, validazione, zoom sulla selezione e pubblicazione.
- [Miro, Structuring board content](https://help.miro.com/hc/en-us/articles/360017730973-Structuring-board-content): allineamento, raggruppamento e frame destinati a navigazione, export e presentazione.
- [ProcessMind, Modeling Canvas](https://processmind.com/resources/docs/modeling/modeling-canvas) e [Element Settings](https://processmind.com/resources/docs/modeling/element-settings): proprietà contestuali e navigazione del modeler.

Le prove ripetute, le schermate sintetiche e gli esiti sono in [proofs/canvas-consistency-2026-11-05](proofs/canvas-consistency-2026-11-05).

## Verifica

- **Test frontend:** 769 test distinti superati in 141 file. La prima esecuzione ha completato 759 test senza errori di asserzione, ma due file non sono partiti per timeout dei worker sotto carico; gli altri 10 test dei due file sono passati nell'esecuzione isolata. Il primo comando ha quindi restituito codice 1, il secondo codice 0.
- **Browser:** due nuovi scenari sintetici e quattro regressioni esistenti passati su Chromium; le regressioni coprono trasferimento fra pool, libreria/proprietà, rinomina e menu destro. Su WebKit il caso delle forme coperte è passato subito; il caso con cicli ripetuti ha superato il limite iniziale di 150 secondi mentre il sistema era carico, poi è passato isolato con un limite di 300 secondi.
- **Cicli ripetuti:** apertura e chiusura dei pannelli, annullamento della rinomina e movimento con Undo sono stati eseguiti cinque volte ciascuno. I test confrontano camera, percorsi dei collegamenti e XML; verificano anche che l'editor non resti aperto e che il documento non diventi modificato per una mera interazione di lettura.
- **Controlli statici:** TypeScript, ESLint e build di produzione superati. Le verifiche usano XML di prova; il diagramma aperto dall'utente è stato soltanto osservato, senza salvarlo o modificarlo.

Il riepilogo verificabile e i report sono in [validation.json](proofs/canvas-consistency-2026-11-05/validation.json).
