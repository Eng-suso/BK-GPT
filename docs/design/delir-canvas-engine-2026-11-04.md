# Canvas DeliR: motore, interazioni e collaborazione BPMN
Data: 4 novembre 2026. PR #165. Sostituisce la precedente descrizione «motore invariato» per questa PR.

Il renderer e il modeler BPMN bpmn-js sono stati rimossi. DeliR possiede importazione XML, grafica SVG, regole BPMN, palette, azioni, rinomina e proprietà. Il toolkit generico diagram-js 15.22.0 fornisce grafica, eventi e command stack con licenza MIT; la licenza è distribuita in public/third-party. Nessun marchio viene nascosto via CSS.

## Contratto del documento
BPMN XML resta il documento persistito. Nessuna nuova API o migrazione del formato. Il DOM originale è conservato; le modifiche esplicite vengono applicate su una copia. Apertura, selezione, navigazione e un gesto completamente annullato restituiscono la sorgente originale. ID, estensioni sconosciute, condizioni, metadati, colori DI e piani alternativi sono coperti dai test. I nuovi elementi ricevono ID distinti. Copia e incolla rimappano i riferimenti semantici interni senza interpretare payload vendor opachi.

Gli import non rappresentabili o malformati falliscono prima di sostituire il modello attuale. Questo non equivale a certificazione completa del linguaggio BPMN.

## Decisioni osservate con REA
| Fonte | Evidenza osservata | Applicazione DeliR |
| --- | --- | --- |
| [bpmn.io, demo](https://demo.bpmn.io/new) | Start con contorno circolare; append, connessione, cambio tipo e cancellazione nel contesto | Stesse categorie di operazioni in controlli DeliR accessibili |
| bpmn.io, doppio clic | Etichetta dello start modificata sotto il cerchio | Editor sul testo, niente card sopra il simbolo; Invio, Esc, F2 e annullamento |
| bpmn.io, partecipante | Azioni per inserire lane sopra/sotto e dividere in due/tre | Menu «Gestisci lane», un solo annullamento per operazione |
| [Figma, selezione](https://help.figma.com/hc/en-us/articles/360040449873-Select-layers-and-objects) | Dimostrazione ufficiale di selezione geometrica e selezione annidata | Distinzione fra oggetto, etichetta e gruppo; le etichette non raddoppiano il conteggio |
| [ProcessMind, canvas](https://processmind.com/resources/docs/modeling/modeling-canvas) | Guida ufficiale: rinomina in posizione, palette, connessione e azioni delle lane | Strumenti organizzati per compito e rinomina da tastiera |
| [Bizagi, creazione](https://help.bizagi.com/platform/en/creating_a_process.htm) | Guida ufficiale illustrata: pool, lane e collegamenti | Contenitori con significato, non rettangoli intercambiabili |

bpmn.io è stato esercitato nel demo pubblico con REA. Figma, ProcessMind e Bizagi sono guide e dimostrazioni ufficiali osservate nel browser, non sessioni autenticate nei loro editor. Un'ulteriore cattura ProcessMind ha restituito osservazioni parziali per cleanup non confermato; non è usata come prova di esecuzione completa. Miro ha richiesto un controllo Cloudflare e non viene presentato come test interattivo riuscito.

## Regole e gestione dei contenitori
Il riferimento normativo è [OMG BPMN 2.0.2](https://www.omg.org/spec/BPMN/2.0.2/PDF), sezioni 7.6 e 9.3. La [guida Bizagi](https://help.bizagi.com/platform/en/best_practices_in_modeling.htm) è un confronto applicativo, non sostituisce la norma.

- Sequence Flow fra Flow Node nello stesso ambito di processo, anche attraverso lane diverse. Pool e lane non sono estremi di sequenza.
- Message Flow fra partecipanti distinti, con estremi ammessi; gateway e lane esclusi. Eventi messaggio rispettano la direzione di invio/ricezione.
- Nessuna sequenza entrante in start/boundary o uscente da end; nessun attraversamento del confine di un sottoprocesso.
- Le stesse regole valgono per riconnettere un estremo.
- Message Flow appartiene alla collaboration XML; Sequence Flow al processo. Le connessioni non sono figli grafici delle lane.
- Inserimento e suddivisione di lane sono operazioni reversibili. «Rimuovi lane, mantieni le attività» trasferisce il lavoro, mantiene i collegamenti e fonde lo spazio nella lane vicina.
- Linee tratteggiate con scorrimento lineare continuo e periodo completo; animazione disabilitata con prefers-reduced-motion.

Il campione collaboration.xml salvato dai gesti E2E è stato validato con BPMN20.xsd, Semantic.xsd, BPMNDI.xsd, DC.xsd e DI.xsd ufficiali: zero errori. Schema valido e correttezza di tutte le possibili semantiche BPMN sono verifiche diverse.

## Identità e densità
Start verde, end rosso, gateway viola attraverso token semantici condivisi. L'alone di selezione segue il cerchio, il rombo o la forma dell'attività; hover neutro e più debole. Le attività non mostrano maniglie di ridimensionamento: il trascinamento sposta il nodo. I contenitori mantengono il ridimensionamento.

La chat del canvas ha larghezza minima 360 px e predefinita 400 px, regolabile. Conversazione, azione di modellazione e composer hanno righe distinte; la barra condivisa ActionPrompt risponde alla larghezza del contenitore. Nessuna card annidata per la modellazione. Le preferenze del composer restano leggibili nelle colonne strette.

## Verifica e limiti
- 25 E2E Chromium passati: desktop/mobile, creazione, proprietà, import, edit/save/reopen, selezione, mouse/trackpad, copia/incolla, rinomina e collaborazione pool/lane.
- 27 unit test mirati passati: documento, clipboard, regole di collegamento e viewport. I timeout iniziali di avvio dei worker sono stati rieseguiti con esito positivo.
- 16 schermate di prodotto e 6 stati del canvas: zero overflow, errori pagina o violazioni axe nei campioni verificati.
- TypeScript, ESLint e build produzione verificati. Resta l'avviso di bundle grande della simulazione.
- Test locali su Chromium; WebKit/Safari non verificati localmente. CI riportata separatamente nella PR.
- Verifiche della collaborazione su pool/lane orizzontali e normali processi/sottoprocessi. Coreografia, rotazione verticale dei partecipanti e navigazione interna dei sottoprocessi non sono certificate da questa matrice.
- Frame di presentazione e contenuti liberi restano una fase successiva.

Le prove sono in [proofs/delir-canvas-engine-2026-11-04](proofs/delir-canvas-engine-2026-11-04). Usano esclusivamente fixture sintetiche; nessun modello cliente o board privata.
