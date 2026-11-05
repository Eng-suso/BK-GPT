# DeliR — riferimenti enterprise per canvas e BPMN

Data: 3 novembre 2026. Stato: riferimenti e direzione; il primo intervento UI è descritto nel [resoconto di implementazione](canvas-ui-2026-11-03.md).
Obiettivo confermato: processi come punto di partenza, con possibilità di costruire anche presentazioni e contenuti visivi. Direzione estetica già scelta: materiali Apple Liquid Glass, capsule morbide, contrasto e gerarchia curati.

## Riferimenti principali e fonti

| Prodotto | Evidenza utile | Applicazione proposta a DeliR | Fonte primaria |
| --- | --- | --- | --- |
| Figma Design / FigJam | L'editor distingue canvas, strumenti e pannelli; le sezioni organizzano gli oggetti della lavagna. | Un'area di lavoro centrale, struttura navigabile e proprietà contestuali. La selezione determina quali comandi mostrare. | [Struttura dell'editor](https://help.figma.com/hc/en-us/articles/360039831974-Explore-the-navigation-bar-and-left-sidebar), [guida FigJam](https://help.figma.com/hc/en-us/articles/1500004362321-Guide-to-FigJam), [offerta Enterprise](https://www.figma.com/enterprise/) |
| Miro | I frame strutturano la lavagna, hanno un indice riordinabile e diventano slide nella presentazione. | Navigazione spaziale leggibile; frame per raccontare un processo; comando Presenta distinto dalla modifica. | [Frames e presentazione](https://help.miro.com/hc/en-us/articles/360018261813-Frames), [Miro Enterprise](https://miro.com/enterprise/) |
| Linear | Il redesign ufficiale rende coerenti header, navigazione, icone e controlli di vista, dando priorità al contenuto. | Riferimento per densità, tipografia, contrasto tra livelli e continuità tra schermate. | [UI refresh](https://linear.app/changelog/2026-03-12-ui-refresh), [Linear Enterprise](https://linear.app/enterprise) |
| Canva Enterprise | La suite comprende lavagne, presentazioni e creazione di contenuti, con gestione del brand. | Template e formati utili a trasformare i processi in materiali da presentare o pubblicare. | [Whiteboards](https://www.canva.com/online-whiteboard/), [Canva Enterprise](https://www.canva.com/enterprise/) |
| Lucidchart / Lucidspark | Le swimlane organizzano i processi; la modalità presentazione costruisce slide dal documento o dalla board. | Riferimento per gerarchia di pool/lane, leggibilità del diagramma e passaggio dal lavoro tecnico alla presentazione. | [Swimlane](https://help.lucid.co/hc/en-us/articles/16266057248660-Add-and-format-swim-lanes-in-Lucidchart), [presentazioni](https://help.lucid.co/hc/en-us/articles/15994195704596-Create-a-presentation-in-Lucid), [Enterprise](https://lucid.co/enterprise) |

n8n rimane un riferimento aggiuntivo per la comprensione operativa del nodo: il suo pannello INPUT consente di usare dati dei passaggi precedenti nei parametri. Per DeliR questo suggerisce una separazione chiara tra diagramma, parametri e dati di esecuzione. Fonti: [data mapping nella UI](https://docs.n8n.io/data/data-mapping/data-mapping-ui/), [workflow pubblico consultato](https://n8n.io/workflows/6270-build-your-first-ai-agent/).

Queste sono attribuzioni per ambito. L'applicazione concreta a DeliR è una proposta progettuale, non una funzionalità già implementata. La selezione non costituisce una classifica di mercato né implica che questi prodotti adottino tutti Liquid Glass.

## Osservazione diretta e limiti

- Miro: osservati nella sessione utente la toolbar di creazione, i controlli di zoom, il menu con minimappa/adatta allo schermo e il pannello Frames. La board aperta usa il piano Free; i controlli di amministrazione Enterprise non sono stati verificati. Nessun oggetto aggiunto o modificato. Contenuti e identificativi della board privata non sono salvati nel report.
- REA: sei scenari controllati su pagine pubbliche, con screenshot, accessibilità e URL. Per FigJam e Miro sono pagine prodotto; per Linear una pagina di changelog con immagini ufficiali; per Lucid documentazione. Non equivalgono a prove complete dei rispettivi editor autenticati.
- Canva: la navigazione automatizzata raggiunge una schermata di verifica. Le funzionalità indicate provengono dalle pagine ufficiali consultabili tramite ricerca web. L'editor non è stato osservato.
- n8n: osservata la pagina pubblica del template; in questa cattura il canvas incorporato non era presente. Non è una prova delle gesture dell'editor n8n.
- [Manifest REA](canvas-enterprise-benchmark-2026-11-03.json): identificativi, URL, digest e ambito di ogni osservazione. Lo stato tecnico completo della cattura non certifica l'accesso all'editor del prodotto.

## Direzione proposta per DeliR

Figma guida la struttura dell'editor; Miro la navigazione e il racconto tramite frame; Linear la gerarchia visiva; Canva i formati e la continuità dei contenuti; Lucid la chiarezza del diagramma di processo. Materiali e controlli confluiscono nel design system DeliR.

### Canvas e strumenti

Un solo viewport di lavoro. Un gruppo compatto contiene selezione, navigazione, collegamento, testo e frame; la libreria raccoglie gli elementi BPMN. Gli strumenti mostrano stato attivo e scorciatoia. Gli oggetti restano leggibili anche quando si aprono pannelli, con ingombri prevedibili e ridimensionabili.

Pan e zoom devono avere convenzioni stabili: trascinamento di navigazione, gesture da trackpad, zoom ancorato al puntatore, adatta al processo e adatta alla selezione. Una selezione non deve cambiare accidentalmente la camera. La navigazione deve recuperare un oggetto fuori vista senza azzerare il lavoro.

### Elementi BPMN e microinterazioni

Pool, lane, attività, eventi e gateway mantengono significati distinguibili. Etichette, collegamenti, spazi interni e stati di selezione seguono regole comuni. Il contenuto del pannello cambia in base al tipo e al numero di oggetti selezionati; campi tecnici avanzati restano organizzati separatamente dai dati operativi.

| Interazione | Criterio osservabile per DeliR |
| --- | --- |
| Selezione | Hover, selezione e focus da tastiera distinguibili; comandi validi per il tipo selezionato. |
| Spostamento | Guide di allineamento, riscontro durante il trascinamento, annullamento e ripristino coerenti. |
| Collegamento | Anteprima del percorso, destinazioni ammesse riconoscibili, annullamento prevedibile. |
| Modifica del testo | Editing vicino all'oggetto, conferma e annullamento chiari, nessuna perdita dopo la chiusura del pannello. |
| Più oggetti | Azioni comuni e proprietà miste esplicite, senza applicare silenziosamente valori incompatibili. |
| Tastiera | Accesso a strumenti e oggetti, ritorno del focus, scorciatoie documentate e movimento ridotto rispettato. |

### Processi e contenuti

I frame permettono di comporre un processo, titoli, spiegazioni e immagini in una sequenza presentabile. La vista Presenta mostra il contenuto con una gerarchia adatta a clienti e registrazioni. Formati di esportazione e template vanno scelti rispetto al risultato: documento, slide o contenuto visivo.

Gli elementi editoriali richiedono dati distinti dalla semantica eseguibile BPMN. Aggiungere una spiegazione o preparare una presentazione non deve introdurre attività, eventi o flussi nel processo. La relazione con la versione del modello va resa esplicita.

## Impatto sul canvas esistente

L'ispezione del repository mostra una base già parzialmente personalizzata:
- `ProcessBpmnCanvas.tsx` compone i controlli React.
- `BpmnCreationTools.tsx` espone una libreria DeliR, ma usa voci e icone legate al servizio palette.
- `useBpmnCanvas.ts` istanzia bpmn-js Modeler, registra i moduli del properties panel e inoltra l'attivazione degli strumenti.

La sostituzione della UI comprende strumenti di creazione, azioni contestuali, selezione, proprietà e presentazione. Vincolo confermato da Sohay: XML BPMN, motore, regole, import/export e pipeline di salvataggio restano invariati. Questo intervento sostituisce la presentazione dei controlli e inoltra i comandi ai servizi esistenti. Frame e contenuti editoriali restano una fase successiva: non viene introdotto alcun nuovo formato dati.

Prima dell'implementazione, la baseline deve includere i problemi E2E e di accessibilità rimasti aperti dopo il merge della PR #161. La verifica finale del nuovo canvas deve coprire i flussi reali, oltre alle schermate.
