# Collegamenti del canvas DeliR

4 novembre 2026 · PR #165 · seguito del motore introdotto in 06604881.

Aggiornamento successivo: [menu destro, lane e selezione più discreta](canvas-context-ux-2026-11-04.md).

## Problema e risultato

Il collegamento precedente non mostrava l'anteprima e poteva terminare al centro di un'attività. Il comando era lontano dal nodo. Ora selezionare un simbolo rende disponibile un solo comando vicino alla sua forma: si può trascinarlo sul bersaglio oppure fare clic e poi scegliere il bersaglio. La linea segue il puntatore; il bersaglio indica se il collegamento è ammesso. Esc o il pulsante di annullamento ripristinano la selezione senza creare una linea.

Il comando segue posizione, zoom e dimensioni del canvas. I bersagli vietati non creano collegamenti. Il suggerimento mobile occupa una riga sotto gli strumenti. Pool, lane e flussi hanno simboli e nomi distinti; l'ispettore dei contenitori spiega il loro ruolo e non presenta campi del responsabile di un'attività.

## Fonti e metodo REA

| Fonte primaria | Comportamento usato |
| --- | --- |
| [Demo bpmn.io](https://demo.bpmn.io/new) | Selezione, azione contestuale accanto al nodo, collegamento con anteprima e aggancio al bordo |
| [Miro: connection lines](https://help.miro.com/hc/en-us/articles/360017730733-Connection-lines) | Clic o trascinamento dal controllo del nodo; riaggancio degli estremi; percorso aggiornato quando un oggetto si sposta |
| [ProcessMind: modeling canvas](https://processmind.com/resources/docs/modeling/modeling-canvas) | Connessione vicina all'oggetto e gestione delle partizioni nel contesto |
| [Bizagi: creating a process](https://help.bizagi.com/platform/en/creating_a_process.htm) | Pool come partecipante, lane come suddivisione e collegamento dal contesto |
| [OMG BPMN 2.0.2](https://www.omg.org/spec/BPMN/2.0.2/PDF) | Distinzione fra sequenza nel processo e messaggio fra partecipanti; lane escluse dagli estremi |

Il gesto nel demo pubblico bpmn.io è stato eseguito con Playwright in un browser isolato. REA ha osservato passivamente l'anteprima tramite CDP; non viene attribuita a REA l'esecuzione del gesto. Le altre fonti sono documentazione ufficiale, non prove di sessioni autenticate nei loro editor. Le azioni automatizzate di capture_browser_scenario di REA non hanno completato la cattura: un timeout MCP di 450 secondi e poi un errore del provider. Il controllo read-only doctor ha trovato la registrazione Codex allineata. Nessuna riconfigurazione REA eseguita.

Prova REA riferimento: ev_7d04d53d1354733344346bfb6acdd6e2bedc5524be192889e16c5a2956e27978. Prova REA DeliR: ev_e40757bf6b5940fd057abca705eafc4d1d257f9571b9cdc64aa87034945c2874. PNG, hash e limiti della cattura sono nelle ricevute in [proofs/canvas-connection-2026-11-04](proofs/canvas-connection-2026-11-04).

## Geometria, prestazioni e documento

- Un percorso ortogonale condiviso fra anteprima e creazione; il docking usa il cerchio, il rombo e il rettangolo arrotondato effettivi.
- Creazione, modifica dei punti e layout tagliano gli estremi al contorno. La riconnessione usa il layout nel command stack, mantenendo annullamento e geometria precedente.
- Importare DI con un estremo dentro un nodo corregge la rappresentazione senza rendere il documento modificato: apertura e annullamento completo mantengono la sorgente XML originale.
- Gli spostamenti aggiornano i collegamenti incidenti. È stato rimosso il ricalcolo globale che poteva riscrivere le pieghe di linee estranee.
- I nuovi collegamenti cercano deviazioni attorno alle attività con un massimo di 16 canali candidati; nessuna ricerca DOM per il routing. I percorsi modificati manualmente non vengono sostituiti da questo passaggio.
- Un annullamento immediato dopo Salva viene ora riconosciuto come modifica: il controllo viene ripetuto alla fine della finestra di salvataggio.
- BPMN XML resta il documento persistito. Contratti API, storage, ID ed estensioni non cambiano formato. Le modifiche esplicite aggiornano il modello e la relativa DI.

## Verifica

41 E2E Chromium e 5 E2E mirati WebKit passati; 35 unit test su documento, clipboard, regole, routing e viewport passati. TypeScript, ESLint e build produzione passati. Il BPMN sintetico collaboration.xml salvato dai gesti passa lo schema ufficiale BPMN 2.0.2 con zero errori. Resta il warning preesistente del bundle simulazione oltre 500 kB. I dettagli sono nella ricevuta validation.json della cartella prove. La matrice copre clic, trascinamento, Esc, annullamento touch, zoom, chiusura e riapertura dell'ispettore, target lane vietato, sequenza fra lane, messaggio fra pool, riconnessione con salvataggio/undo, pieghe estranee e documento sintetico da 500 attività.

Le schermate desktop/mobile sono state ispezionate visivamente. Cinque stati hanno zero overflow orizzontali, zero errori pagina e zero violazioni axe WCAG A/AA rilevate. La sovrapposizione iniziale del suggerimento mobile è stata corretta e ricatturata; axe da solo non rilevava quel difetto.

Limiti: le deviazioni sono locali e limitate, non garantiscono una soluzione ottima per ogni grafo o per nodi sovrapposti. Il campione da 500 attività verifica funzionamento e reversibilità; il tempo registrato include Playwright e non misura gli FPS. WebKit su Windows non certifica un dispositivo iOS reale. Coreografie, pool verticali e tutte le combinazioni della specifica BPMN non sono certificate. Nessun modello del workspace utente su 3030 è stato modificato durante le prove; sono state usate fixture sintetiche su 3040.
