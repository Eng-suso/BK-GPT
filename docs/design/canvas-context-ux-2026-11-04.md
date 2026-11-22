# Canvas: comandi contestuali e lane

4 novembre 2026 · seguito di 8434540c, PR #165.

## Difetti riprodotti e correzioni

1. I rettangoli esterni delle maniglie erano aree di presa che ereditavano un bordo blu. Il componente DeliR ora distingue grafica e hit area: piccoli cerchi agli angoli, indicatori sottili sui lati, colori neutri e dimensioni costanti durante lo zoom. La presa è esterna al contenitore, così non copre il nome della lane. Rimane ampia per mouse e touch.
2. Le operazioni sulle lane si interrompevano senza effetto quando il genitore era un processo senza pool grafica. Le lane di quel processo usano ora l'inviluppo delle partizioni come geometria; nessuna pool o collaboration viene aggiunta automaticamente all'XML. Aggiunta sopra/sotto e rimozione con conservazione del lavoro sono reversibili. La suddivisione in due/tre dimensiona le partizioni per contenere le attività e le loro etichette; quando occorre amplia il contenitore e sposta le partizioni successive. Gli oggetti vengono mantenuti dentro la partizione assegnata, con un solo annullamento per operazione.
3. La barra di selezione ripeteva il nome e mostrava menu generici permanenti. Ora segue l'oggetto: le lane espongono direttamente sopra/sotto; suddivisione e rimozione stanno nel menu secondario, con la rimozione separata in fondo. I nodi mostrano aggiunta e menu secondario; il collegamento rimane vicino al simbolo. Il cambio tipo è nel sottomenu. Nell'ispettore dei contenitori sono stati rimossi testi esplicativi e cancellazione duplicata.
4. Il destro era intercettato per lo spostamento, senza aprire un menu. Un clic destro apre ora le azioni dell'oggetto sotto il puntatore; un trascinamento col destro sposta soltanto la camera. Il menu è disponibile anche con Shift+F10 o il tasto Menu. Sullo sfondo offre creazione, annulla/ripeti e selezione; i comandi senza operazioni disponibili sono disabilitati.
5. I sottomenu potevano essere visibili ma ricevere clic sul diagramma sottostante in WebKit. DropdownMenuSubContent ora usa il Portal Radix nel componente condiviso, evitando il ritaglio da parte del contenitore del menu principale.

Le modifiche restano nel motore e nei componenti condivisi. BPMN XML, ID, estensioni e contratti API mantengono il formato esistente.

## Osservazione con REA

Nel [demo pubblico bpmn.io](https://demo.bpmn.io/new) è stato importato un BPMN sintetico. I gesti sono stati eseguiti con Playwright in un browser isolato; REA ha catturato passivamente i risultati via CDP.

Sulla lane sono stati osservati direttamente: inserimento sopra/sotto, suddivisione in due/tre, cancellazione e colore. L'inserimento sotto ha portato gli oggetti grafici da 8 a 9 e aggiunto una partizione al partecipante. Sono stati usati questi comportamenti per rendere più diretti i controlli DeliR. Per la suddivisione è stata osservata la disponibilità dei comandi; un tentativo di attivazione non si è completato e non viene presentato come prova riuscita della geometria di suddivisione del concorrente.

- REA lane: ev_0be5fa6ff76d63c0bcd1972eb04553f9bc2315bc506f1278f572be00761cf384.
- REA dopo inserimento: ev_09e2de7cfc41f74381976e51d67b2e0defe906aa554d41f7a36acbda8a93eeab.
- REA DeliR, menu destro: ev_38e6db272845083a2175c903c6261e440955f915db05b127261d912d39787f5a.

PNG, hash e limiti delle catture sono nelle ricevute in [proofs/canvas-context-2026-11-04](proofs/canvas-context-2026-11-04).

Altri riferimenti primari consultati:

- [Miro: working with objects](https://help.miro.com/hc/en-us/articles/360017730953-Working-with-objects): menu destro sull'oggetto e azioni secondarie nel menu con i tre punti.
- [Miro: toolbars](https://help.miro.com/hc/en-us/articles/360017730553-Toolbars): compiti distinti per strumenti, navigazione e contesto dell'oggetto; riduzione degli strumenti non necessari.
- [Bizagi: Pie Menu](https://help.bizagi.com/platform/en/the_pie_menu.htm): comandi vicino alla selezione e feedback sui collegamenti ammessi.

Miro e Bizagi sono riferimenti della documentazione ufficiale; non sessioni autenticate dei loro editor. La semplificazione visiva e i colori neutri sono scelte DeliR derivate dal confronto e dalla richiesta dell'utente.

## Verifica

45 E2E Chromium passati nella regressione del workspace; 2 casi lane rieseguiti con esito positivo dopo l’ultimo adeguamento della suddivisione. Sette casi unici WebKit passati: un timeout iniziale del menu destro è passato nel successivo controllo isolato con tracing. 39 unit test, TypeScript, ESLint e build produzione passati. Quattro BPMN sintetici salvati superano lo schema ufficiale BPMN 2.0.2 con zero errori. Sei stati visivi hanno zero overflow, errori pagina e violazioni axe rilevate. Esiti e matrice finali in validation.json nella cartella prove. Sono inclusi esecuzione dei comandi, XML dopo salvataggio/undo, lane senza partecipante grafico, mouse/touch, zoom 50/100/200%, destro per menu e pan, tastiera, sottomenu e regressione del workspace.

La scheda utente su 3030 è stata ispezionata in sola lettura, aprendo i menu. Nessun comando di modellazione o salvataggio è stato eseguito sul suo documento. Le modifiche ai modelli e le schermate versionate usano soltanto fixture sintetiche su 3040.

Limiti: questa verifica non certifica ogni combinazione BPMN, ogni contenimento annidato o dispositivi iOS reali. WebKit è stato esercitato su Windows. I risultati dei campioni restano distinti dalle certificazioni della specifica.
