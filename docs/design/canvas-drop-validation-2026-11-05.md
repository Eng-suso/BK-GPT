# Trascinamento, adozione nella pool e associazioni diagonali

Il trasferimento di un gruppo nella pool era bloccato confrontando il contenitore iniziale con quello di destinazione, anche quando tutti gli estremi dei flussi erano selezionati. La nuova regola verifica il risultato dello spostamento: un sottografo completo può cambiare processo; un trasferimento parziale che lascerebbe una sequenza fra pool viene respinto. Le lane rimangono partizioni e non diventano estremi di flusso. Gli elementi devono rientrare nei limiti del contenitore di destinazione; non vengono convertiti automaticamente i tipi di collegamento.

Il salvataggio sposta anche i nodi XML già esistenti nel processo della pool, insieme alle sequenze interne. Prima questa assegnazione avveniva soltanto per elementi nuovi. Gli oggetti XML originali vengono riutilizzati per preservare ID, condizioni e payload di estensione. Le partizioni usano i rispettivi `flowNodeRef`. Nessun cambio di formato, API o storage.

Un trascinamento interrotto dalla perdita di focus, dalla cancellazione del puntatore o dal cambio di visibilità viene annullato. Se il mouse rientra senza il pulsante primario premuto, un eventuale spostamento rimasto attivo viene ripulito. La creazione e il collegamento con clic e successivo posizionamento mantengono il proprio comportamento.

## REA e riferimenti

Sul [demo bpmn.io](https://demo.bpmn.io/new) sono stati riprodotti un trascinamento valido dentro la pool e un rilascio non valido fuori dalla pool: il primo aggiorna la posizione; il secondo ripristina la posizione precedente, senza trascinatore residuo. Muovere poi il mouse non sposta più il nodo. I gesti sono eseguiti da Playwright; REA osserva passivamente il risultato. La ricevuta `ev_1e383be4dc3b9231d903c47b8b1dbdbc576dd3ebc17a225932076e741c399053`, la schermata con digest verificato e le coordinate prima/dopo sono in [proofs/canvas-drop-2026-11-05](proofs/canvas-drop-2026-11-05).

La guida ufficiale [Bizagi: Creating a process](https://help.bizagi.com/platform/en/creating_a_process.htm) documenta trascinamento dalla palette, lane dentro la pool e collegamento dal comando contestuale al secondo elemento. [Bizagi: Editing a process](https://help.bizagi.com/platform/en/edit_a_diagram.htm) documenta spostamento tramite trascinamento e cambio tipo nella stessa categoria. Sono riferimenti documentali, non prove di esecuzione sul client desktop Bizagi. Le regole di partecipanti e flussi restano vincolate a [OMG BPMN 2.0.2](https://www.omg.org/spec/BPMN/2.0.2/PDF).

L'obiettivo verificato è il comportamento di rilascio e contenimento, mantenendo la grafica DeliR. Non viene dichiarata equivalenza completa con tutti i modeler enterprise.

## Errore «Association attraversa tutti gli elementi»

Il test geometrico backend restituiva sempre `True` per qualunque segmento diagonale. Un'associazione libera poteva quindi produrre una violazione per ogni nodo del diagramma. Ora viene calcolata l'intersezione reale del segmento con l'interno del rettangolo. Un contatto sul bordo o su un solo angolo non è un attraversamento; un'intersezione reale resta bloccante. Non vengono disattivati i controlli né riscritto il percorso manuale.

## Verifica

- 5 E2E Chromium e 3 WebKit sui casi di adozione, maniglie mouse/touch, annotazioni e tasto destro. Il caso di adozione è ripassato su entrambi dopo l'estensione a selezione tramite Shift senza selezionare esplicitamente le linee e alla riapertura del modello.
- Il caso finale verifica: perdita di focus, recupero di un rilascio perso, rifiuto di uno spostamento parziale, selezione a rettangolo, adozione del gruppo, rilascio stabile, proprietà XML, Undo esatto, selezione dei soli nodi con Shift e riapertura.
- 26 unit test frontend distinti sui contratti XML, regole di spostamento, partizioni e collegamenti; 39 test Python di geometria e leggibilità. I test Python sono puri e usano `--confcutdir=tests/bpmn`, senza avviare fixture o database.
- TypeScript, ESLint e build produzione passati; resta il warning preesistente sul chunk simulazione.
- Il BPMN sintetico salvato supera gli XSD ufficiali e il vero gate `_canvas_xml_for_write`, che restituisce gli stessi byte. Il diagramma utente su 3030 non è stato modificato né salvato.

I rapporti JSON e lo screenshot del gruppo dentro la pool sono conservati nella cartella delle prove. Queste verifiche non certificano tutte le combinazioni BPMN, dispositivi touch fisici o il comportamento in assenza di risorse del sistema operativo.
