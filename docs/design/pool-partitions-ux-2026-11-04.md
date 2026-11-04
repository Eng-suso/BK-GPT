# Pool e lane come partizioni solidali

Il difetto segnalato mostrava lane con margini interni e dimensioni indipendenti dalla pool. Il ridimensionamento generico di diagram-js cambiava soltanto il contenitore e calcolava un padding attorno alle lane come se fossero normali oggetti.

## Riferimenti verificati

- [OMG BPMN 2.0.2, §10.8, pagina 304](https://www.omg.org/spec/BPMN/2.0.2/PDF#page=334): una lane è una partizione del processo, spesso rappresentato dentro una pool, e ne percorre l'intera lunghezza. La didascalia di una lane foglia non deve avere un proprio separatore verticale.
- [Demo pubblico bpmn.io](https://demo.bpmn.io/new): verificato un aumento della pool da 800×544 a 890×610. Le lane arrivano al nuovo bordo destro; la lane finale assorbe l'estensione inferiore. Verificato anche il divisore interno: LaneA passa da 200 a 250, LaneB da 200 a 150, mentre la pool resta alta 610.
- [Bizagi: creazione di un processo](https://help.bizagi.com/platform/en/creating_a_process.htm): la lane viene trascinata dentro il processo; la pool si ridimensiona dai bordi.
- [Visual Paradigm: pool e lane](https://circle.visual-paradigm.com/docs/bpmn-and-process-mapping/business-process-diagram/using-bpmn-pool-and-lane/): relazione contenitore/partizioni, ridimensionamento solidale e lane annidate.

I gesti nel demo sono stati eseguiti con Playwright; REA ha osservato passivamente il risultato. Ricevute: `ev_bec309dbed45d32e95b197ba4c7e7e14579e9aa88f48a12894438953b8fa6f1a` e `ev_ae79093656b4b7b8645067d70c1a4e16ec6a2e05a9945c49fd7867f246fbf445`. Il primo estratto geometrico elenca soltanto due delle tre lane: la schermata e il secondo estratto includono anche la lane finale. Non si attribuiscono a REA i clic né una copertura completa del prodotto concorrente.

## Comportamento DeliR

- Bordo esterno della pool condiviso con tutte le lane: niente padding sopra, sotto o a destra; resta la fascia del titolo della pool.
- Un divisore interno modifica due partizioni adiacenti. Il bordo esterno di una lane modifica il contenitore e riallinea le altre partizioni.
- Il trascinamento dall'intestazione di una lane sposta il contenitore con attività, lane e collegamenti. La lane non può essere staccata come un rettangolo libero.
- Le lane aggiunte dalla libreria, anche sopra una lane esistente, appartengono alla stessa pool. Un processo vuoto non accetta nuove lane isolate; i BPMN importati con lane di processo senza partecipante disegnato restano supportati.
- Ridimensionamenti che attraversano attività o comprimono eccessivamente una partizione vengono rifiutati. Le lane annidate condividono i cambiamenti del loro contenitore.
- Rimossa la seconda linea verticale dalle lane foglia. Identità, colori e controlli DeliR rimangono condivisi.

La geometria viene gestita nel motore con comandi annullabili. I vecchi margini vengono ricomposti alla successiva modifica del contenitore o delle sue lane; il semplice caricamento non riscrive il documento. Non vengono modificati formato XML, API o storage. Undo deve ripristinare esattamente l'XML iniziale, compresa la geometria precedente.

## Prove e limiti

Schermate, geometrie misurate, XML sintetici e risultati sono in [proofs/pool-partitions-2026-11-04](proofs/pool-partitions-2026-11-04). `validation.json` riporta i risultati finali e distingue i controlli mirati dalle suite precedenti della PR.

Le prime esecuzioni delle nuove prove hanno evidenziato errori del relativo harness: coordinate sull'avviso di canvas vuoto, selettore errato delle maniglie e clic sul rettangolo visivo coperto dalla sua area di presa. Le prove finali usano veri eventi del mouse sulle coordinate della geometria visibile, senza clic forzati.

Questa verifica riguarda pool orizzontali e partizioni annidate orizzontali; non certifica pool verticali, coreografie o ogni combinazione BPMN. Non sono state eseguite modifiche o salvataggi sul diagramma utente aperto su 3030.
