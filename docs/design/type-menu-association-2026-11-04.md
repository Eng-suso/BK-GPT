# Tipi BPMN, icone e collegamenti delle annotazioni

Il cambio tipo era nascosto in Altre azioni → Cambia tipo. Le voci `replace.create.*` venivano inoltre riconosciute come azioni generiche prima di leggere il tipo, mostrando tutte la stessa icona delle impostazioni. Il menu destro ora espone direttamente i tipi compatibili; la barra contestuale ha un pulsante dedicato. Entrambi usano lo stesso selettore con tipo corrente indicato e navigazione da tastiera. Scegliere il tipo già impostato non crea una modifica.

## Riferimento REA e fonti

Nel [demo bpmn.io](https://demo.bpmn.io/new), caricato con un BPMN sintetico, sono stati osservati il selettore delle attività e i suoi simboli distinti per utente, servizio, invio/ricezione, manuale, regole, script, attività richiamata e sottoprocesso. I clic sono stati eseguiti con Playwright; REA ha osservato passivamente lo stato risultante. Ricevuta `ev_b1be39130752bb29cc25f72fb7017adab00a4b44628251a633eb4e87ca106492`, schermata e provenienza in [proofs/type-menu-association-2026-11-04](proofs/type-menu-association-2026-11-04).

Le icone provengono dal catalogo ufficiale [bpmn-font](https://github.com/bpmn-io/bpmn-font), versione npm fissata a 0.13.0, con [licenza SIL OFL 1.1](https://github.com/bpmn-io/bpmn-font/blob/main/LICENSE). La licenza viene distribuita in `frontend/public/third-party/bpmn-font-LICENSE.txt`, secondo il modello già usato per diagram-js. La dipendenza fornisce soltanto i simboli dell'interfaccia: modello, renderer e interazioni restano quelli DeliR. Non è stato aggiunto bpmn-js.

## Comportamento condiviso

- Libreria, inserimento del passaggio, menu destro, selettore della barra e ispettore usano la stessa risoluzione dei simboli.
- Task manuale, servizio, script e regole hanno pittogrammi distinti; gateway inclusivo, complesso e basato su eventi usano i simboli corretti del catalogo. Le varianti degli eventi mantengono i rispettivi marcatori.
- Il tipo corrente è una scelta radio accessibile. Il menu scorrevole è raggiungibile da tastiera anche su schermo stretto; dopo una scelta dalla barra il focus torna al canvas.
- L'attività richiamata mantiene il bordo spesso; il sottoprocesso compresso ha un bordo sottile. Il comportamento esistente del marcatore “+” viene conservato: [BPMN 2.0.2, §10.3.6](https://www.omg.org/spec/BPMN/2.0.2/PDF) prevede quel marcatore anche quando una Call Activity richiama un processo con dettagli nascosti. Non si tratta necessariamente di un pulsante o di un errore grafico.

Sono proposti i tipi compatibili già supportati dal motore; non viene dichiarata l'implementazione dell'intero standard BPMN attraverso questo menu. La sostituzione non permette di trasformare un sottoprocesso contenente lavoro in un task vuoto.

## Linea dell'annotazione

Lo sfondo di pool e lane poteva coprire associazioni o flussi disegnati nello stesso livello. Un ordinamento di presentazione mette i contenitori prima dei collegamenti e gli oggetti liberi dopo. Viene riapplicato dopo importazione e comandi; non cambia contenimento semantico, coordinate, ordine XML o riferimenti. Quando l'ordine è già corretto non vengono staccati e riattaccati i nodi SVG, per conservare i gesti in corso.

La prova sul tratto dell'associazione dentro la pool usa l'hit testing del browser prima e dopo lo spostamento del task, con le azioni flottanti chiuse per misurare il diagramma. La schermata dimostra la linea visibile attraverso il bordo della pool. Salvataggio e Undo verificano il ripristino esatto dell'XML iniziale.

## Verifiche

`validation.json` riporta le esecuzioni finali: menu su desktop/mobile, simboli degli eventi, distinzione attività richiamata/sottoprocesso, focus, accessibilità, visibilità dei collegamenti, regressioni dei comandi, pan/zoom e diagramma da 500 attività. Sono conservati XML sintetici e schermate; il diagramma utente su 3030 non è stato modificato o salvato durante le prove.

Le prime prove hanno corretto un menu scorrevole non raggiungibile da tastiera. La verifica della linea è stata affinata per evitare di scambiare una linea verticale con bounding box largo zero, o una barra flottante sopra la linea, per un problema dello sfondo della pool. WebKit locale non certifica dispositivi iOS fisici; il routing dei collegamenti rimane quello del motore esistente.
