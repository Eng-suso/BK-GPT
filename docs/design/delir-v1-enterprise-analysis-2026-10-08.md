# DeliR V1 → MVP: analisi di 23 schermate

Data: 8 ottobre 2026. Analisi visiva di **tutti i 23 JPG**, confrontata con i componenti del repository BK-GPT. Materiale di riferimento locale: `screenshots/delir-v1-2026-10-08/` (archivio esterno al checkout), con `GALLERIA.md`. Le immagini originali restano nella cartella indicata; questo documento non riproduce persone o dati delle schermate.

## Direzione

Conservare l’identità del MVP (Satin, tipografia, colori semantici, mascotte a forma di D, canvas bpmn-js) e trasferire le capacità operative osservate: libreria, metadati, review e tracciabilità. Uno screenshot dimostra la presenza di un controllo, non che questo salvi dati, applichi regole o chiami un backend. Gli stati vuoti di Evidence e Compare non dimostrano funzioni complete.

## Analisi schermata per schermata

| # / file | Osservazione visiva | Indicazione per il MVP |
| --- | --- | --- |
| 01 plan-mode | Conversazione a sinistra, riepilogo a destra, copertura evidenze, nuova chat e composer in basso. Il riepilogo è vuoto. | Mantenere la discussione come ingresso del processo; mostrare progresso verificabile e un passo successivo quando manca il piano. |
| 02 build-manual-mode | Palette verticale con ricerca, recenti e rapidi; toolbar; pool e flussi; miniature del diagramma. Etichette troncate nel rail stretto. | Libreria espandibile con ricerca, testi leggibili, strumenti compatti sempre disponibili. |
| 03 build-properties-context | Proprietà affiancate al canvas, tipo del nodo e sei schede; selezione evidenziata. | Inspector stabile, ridimensionabile e integrato nella shell già esistente. |
| 04 properties-details | Nome, task owner, ufficio competente, descrizione, checkbox di obbligatorietà, eliminazione in fondo. | Campi equivalenti con persistenza nel BPMN; distinguere annotazioni di business da semantica esecutiva. |
| 05 properties-rules | Note sulle regole, rischi e mitigazioni, SOP, suggerimenti AI vuoti. | Campi reali e accesso alla discussione; niente suggerimenti inventati. |
| 06 bpmn-palette-events | Ricerca, recenti, sei rapidi, eventi iniziali messaggio/timer/condizione. | Eventi tipizzati tramite il factory BPMN, non semplici icone. |
| 07 bpmn-palette-activities | Task, user, service, manual, script; numero della categoria. | Aggiungere anche business rule, send, receive, call e sottoprocessi. |
| 08 bpmn-palette-categories | Eventi, attività, gateway, flussi, dati, collaborazione, coreografia, conversazione, artefatti, marker. | Esportare solo categorie realmente supportate da bpmn-js. Flussi e marker usano connessione e menu di contesto; coreografia/conversazione richiedono un renderer dedicato. |
| 09 canvas-context | Pool con due attori, messaggi tra lane, task selezionato, toolbar, Evidence chiuso. | Conservare struttura BPMN, connessioni native e camera quando cambiano i pannelli. |
| 10 canvas | Griglia, select/move/data/note/attach/inspect, fit, minimappa. | Conservare pan, selezione, fit e zoom leggibile. Annotazioni e dati devono essere elementi BPMN; il caricamento allegati necessita di collegamento a documenti reali. |
| 11 review-mode | Finding a sinistra con evidenza e azioni Mostra/Applica/Ignora/Chiedi; avatar in alto a destra. | Rafforzare review contestuale già presente; avatar spostabile liberamente senza modificare il diagramma. |
| 12 evidence-layer | Drawer basso: Brief, Validation, Risks, Assumptions, Decisions, Documents, History; nessuna validation collegata. | Continuare a usare le evidenze reali del MVP. Eventuale drawer aggiuntivo va collegato a contratti backend, non popolato con dati dimostrativi. |
| 13 compare-versions | Avviso “Baseline incomplete”, confronto senza diff disponibile. | Confronto solo tra versioni reali, con azione per creare/selezionare le baseline mancanti. |
| 14 home-dashboard | Attività prioritarie, progetti, scadenze, incontri e promemoria. | Portafoglio operativo alimentato da dati reali; calendario e notifiche hanno dipendenze proprie. |
| 15 projects | Tabella filtrabile, stato/fase/owner/scadenza e dettaglio progetto laterale con milestone. | Riutilizzare portfolio e inspector del MVP; priorità ai filtri e all’azione successiva. |
| 16 project-home | Obiettivo, perimetro, avanzamento per processo, fonti, decisioni, stakeholder. | Tenere distinti completamento attività e qualità/completezza delle evidenze. |
| 17 information-evidence | Fonti per tipo, confermate/in valutazione/conflitti, estratto con origine. | Tracciabilità e risoluzione dei conflitti sono capacità enterprise; non basta esibire percentuali di confidenza. |
| 18 process-map | Raggruppamento governance/core, owner e avanzamento; governance vuota. | Evoluzione del portfolio multi-processo: tassonomia esplicita e collegamenti navigabili. |
| 19 process-summary | Sintesi, attori, documenti, confini e metriche. | Riepilogo dal piano validato; distinguere informazioni confermate e ipotesi. |
| 20 as-is | Versione approvata, catena di attività, problemi di validazione, matrice RACI. | Esplicitare baseline e approvazione; RACI richiede responsabilità documentate. |
| 21 to-be | Versione draft, attività AUTO, benefici attesi e controlli. | Proposte separate dall’As-Is; badge di automazione solo se la proposta specifica il meccanismo. |
| 22 kpi-dashboard | Baseline, attuale, target, simulato, soglie e provenienza. | Mantenere separate misure reali, stime e simulazioni. Non copiare numeri o trend dimostrativi. |
| 23 manager-view | Ambito progetto/processo, As-Is/To-Be e benefici per stakeholder. | Vista sintetica futura collegata a versioni, fonti e risultati reali. |

## Implementazione in questa PR

- Libreria BPMN espandibile con ricerca, recenti, elementi rapidi e categorie Eventi / Attività / Gateway / Dati / Collaborazione / Artefatti. Comprende eventi iniziali, intermedi, finali e boundary tipizzati; task utente, servizio, manuale, script, regole, invio e ricezione; gateway parallelo/inclusivo/complesso/a eventi; call activity, lane, annotazione e sottoprocesso compresso. Mantiene pool, dati, sottoprocesso espanso, gruppi e strumenti nativi. Le lane si posizionano nei pool e gli eventi boundary sul bordo delle attività.
- Proprietà in sei schede: Dettagli, Regole, Dati, File, Cronologia, AI. Nome e descrizione usano le proprietà standard; owner, ufficio, obbligatorietà annotativa, regole, rischi, SOP, input/output, sistemi e riferimenti documentali usano un’estensione BPMN `delir`. Seguono salvataggio, import/export e command stack. Le proprietà BPMN tecniche restano in una sezione espandibile.
- File contiene **riferimenti documentali**, non upload fittizi. Cronologia mostra le versioni disponibili **dell’intero disegno**, non un audit per singolo campo. AI porta alla discussione del processo; la conversazione specifica del task è in Review.
- Avatar del MVP spostabile con grip, Pointer Events, touch e frecce. Home ripristina l’ancoraggio automatico; la posizione manuale resta cambiando task e aprendo/chiudendo la chat, ed è limitata al canvas quando si ridimensiona la finestra. La posizione dura per la workspace aperta; non è una coordinata BPMN e non viene salvata nel modello.
- Chat: separazione dei componenti per task, stream associato al thread selezionato (anche dopo “Nuova chat”), blocco dell’invio duplicato durante la creazione del thread, Stop durante l’apertura, conservazione di trascritto/coda quando si cancella un errore, parsing dell’ultima riga NDJSON senza newline e protezione dai run concorrenti sullo stesso thread. Le risposte in Review non forzano la sostituzione di bozze del canvas aperte altrove.

## Backlog derivato, con dipendenze

1. Evidence drawer multi-sezione con contratti reali per rischi, assunzioni e decisioni; confronto versioni con baseline e diff deterministico.
2. Allegati strutturati collegati a documenti del progetto, audit per campo e suggerimenti AI persistiti con fonti.
3. Minimappa navigabile accessibile, flussi guidati e catalogo completo di varianti BPMN. Coreografia e conversazione necessitano di supporto di modellazione dedicato; i conteggi “48 eventi” della vecchia UI non provano la correttezza dei 48 elementi.
4. Sintesi manageriale, RACI, KPI con provenienza e portfolio multi-processo alimentati da dati effettivi.

## Criteri di verifica

Verificare viewport desktop e mobile, ricerca/stati vuoti della libreria, creazione reale di task di servizio ed evento timer, serializzazione e ricaricamento dei metadati, eliminazione/undo, tastiera, scansioni Axe, movimento e limiti dell’avatar, task distinti durante uno stream e retry. Nessuna promessa “chat senza bug”: i risultati valgono per i percorsi coperti dai test, con trasporti API sintetici. Gli esiti dell’esecuzione sono riportati nella PR.

## Esiti verificati

- Lint, typecheck e build di produzione riusciti. La build mantiene l’avviso sulla dimensione del bundle del workspace; nessuna dipendenza aggiunta.
- Suite mirata chat e BPMN: **23 file, 134 test unitari passati**, inclusi retry, nuova chat, coda durante apertura, Stop e risposta di errore tardiva.
- Chromium: 13 casi distinti del workspace/review passati nelle esecuzioni di regressione; i sei casi di libreria, proprietà, avatar, isolamento e retry sono stati rieseguiti sulla versione finale.
- WebKit e Chrome mobile: sei casi per browser verificati; dopo le correzioni di resize e fixture CORS sono stati rieseguiti proprietà desktop/mobile e avatar, tutti passati.
- Controlli Axe inclusi nei percorsi esercitati e revisione visiva degli screenshot desktop/mobile. Le API sono simulate nei test browser: questi esiti non certificano un backend live, tutte le varianti BPMN o l’assenza assoluta di bug.
