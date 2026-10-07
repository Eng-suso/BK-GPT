# Process Review — workspace enterprise Satin

As-Is descrive, Review interpreta, To-Be raccoglie le ipotesi di trasformazione.

La nuova vista Review ispeziona il modello salvato senza introdurre comandi di
modifica del diagramma. Selezionare un task apre una scheda breve ancorata al
nodo e un inspector con Overview, Evidenze, Impatti e Azioni. La scheda minima
contiene owner, input, output, problemi rilevati, impatti e suggerimento.

## Interazione e mascotte

Una mascotte SVG originale, costruita come una D ripiegata con un volto e
piccole estremità, appare nella bolla contestuale. Compie un giro breve
quando cambia il task selezionato o viene attivata; il movimento termina e
rispetta `prefers-reduced-motion`. Il canvas conserva zoom e posizione durante
la navigazione dei tab e il cambio del focus sulle dipendenze. Su schermi
compatti il dettaglio occupa il pannello di lavoro; chiuderlo restituisce il
canvas e il focus alla selezione dei task.

La scheda presenta il task come un dossier: titolo e posizione nella review,
owner, input/output affiancati, rilievi con un accento di stato discreto e un
perimetro delle dipendenze leggibile. Il suggerimento è specifico per il primo
campo da chiarire. I tab usano la variante `line` esistente. La navigazione
numerata al piede del canvas e i controlli precedente/successivo permettono di
ispezionare le attività in sequenza senza riaprire l'elenco; la voce selezionata
resta visibile anche quando il binario scorre su mobile.

Le quattro azioni rimangono nel footer dell'ispettore durante la navigazione
dei tab e lo scroll. Questo usa uno slot `footer` opzionale in
`WorkspaceInspector`, condivisibile dagli altri workspace senza cambiarne il
comportamento. Le ipotesi To-Be hanno un registro numerato con task di origine,
data e ritorno diretto alla relativa scheda.

Le quattro azioni sono Mostra evidenze, Chiedi chiarimento, Proponi modifica e
Ignora per ora. Le ultime tre registrano un'azione persistente. Chiedi
chiarimento registra la domanda per il consulente: questa versione non invia
messaggi e non esegue chiamate a un agente. Le candidate change compaiono nella
vista To-Be come ipotesi, senza applicare automaticamente modifiche al modello.

## Design system

Il layout riusa `CanvasWorkspaceShell`, `WorkspaceCommandBar`,
`WorkspaceInspector`, `WorkspaceDisclosure`, `Surface` e le primitive UI
esistenti. Palette, font, materiali, spaziatura e motion restano quelli del
[Satin design system](satin-design-system.md).

La direzione Apple Glass è tradotta nel materiale `Surface floating` già
presente: toolbar, navigazione numerata, bolla contestuale e controlli canvas.
L'inspector usa `panel`, i dati input/output `inset` e i tab la variante `line`.
`WorkspaceCommandBar` espone una scelta opzionale `material`; il default degli
altri workspace resta `toolbar`. Non vengono aggiunti palette, blur o ombre
locali. Diagramma e testo restano opachi; le superfici ereditano i fallback del
design system per trasparenza ridotta e assenza di supporto al backdrop filter.

### Confronto con riferimenti pubblici

Consultati il 7 ottobre 2026. Il confronto usa documentazione, immagini e
presentazioni pubbliche, senza accesso ai workspace autenticati. Le decisioni
per DeliR sono interpretazioni progettuali, non risultati di test sui prodotti.

| Riferimento | Osservazione dalla fonte | Scelta per DeliR |
| --- | --- | --- |
| [Apple Materials](https://developer.apple.com/design/human-interface-guidelines/materials) | Liquid Glass distingue controlli e navigazione dal contenuto. | Materiale flottante sui comandi; contenuto del processo leggibile su superfici stabili. |
| [SAP Signavio Process Modeler](https://www.signavio.com/products/process-modeler/) e [immagine ufficiale del modeler](https://cdn.signavio.com/uploads/2023/08/Process-Manager-Collaborative-process-modeling-1-1536x1018-1.png) | Il canvas occupa il centro, con strumenti al bordo e accesso laterale ad attributi e viste. | Canvas centrale, inspector contestuale, navigazione dei task al piede. |
| [Celonis Process Analysis](https://www.celonis.com/platform/process-analysis) | Process Explorer, analisi delle deviazioni e monitoraggio delle opportunità appartengono a funzioni distinte. Le immagini della pagina sono illustrazioni promozionali. | Evidenze e perimetro strutturale separati dalle ipotesi To-Be; nessun KPI non misurato. |
| [ARIS Platform](https://aris.com/platform/) e [guida di modellazione](https://docs.aris.com/latest/ypl-basic/en-us/43902-modeling-component-quick-start.html) | Modellazione, valutazione e confronto degli scenari sono passaggi distinti; l'illustrazione pubblica confronta scenari A/B/C. | Registro delle ipotesi con origine e data, collegamento alla simulazione esistente per verificarne gli effetti. |

Quattro ruoli in `frontend/styles/tokens/semantic.css` risolvono su token
semantici esistenti, mantenendo la catena verso i primitive token:

| Ruolo Review | Token esistente |
| --- | --- |
| `--review-color-selected` | `--color-action-primary` |
| `--review-surface-selected` | `--color-surface-selected` |
| `--review-color-upstream` | `--color-text-secondary` |
| `--review-color-downstream` | `--color-text-primary` |

Le dipendenze hanno anche bordi tratteggiati/punteggiati e una legenda. I task
collegati usano neutri; il blu identifica il task selezionato e le azioni. I
default del renderer BPMN leggono i token semantici a runtime e mantengono i
colori importati esplicitamente nel diagramma. I task
sono raggiungibili dalla lista con ricerca, senza dipendere dall'interazione
con l'SVG. Dialog e inspector gestiscono il ritorno del focus.

## Fonti, impatti e persistenza

Owner, input e output provengono dal piano canonico tramite riferimenti esatti
del compilatore; l'owner può essere letto anche dalla lane BPMN. I dati mancanti
restano dichiarati come non documentati. Le evidenze usano la provenienza
esistente; i rilievi generali rimangono distinti dall'analisi del singolo nodo.

La zona di impatto segue sequence flow, gateway, rami e cicli; collega inoltre
le associazioni documentali presenti nel BPMN. Controlli e regole sono collegati
tramite gli identificativi del piano. È un perimetro di dipendenza strutturale,
non una previsione dei tempi o una diagnosi misurata di colli di bottiglia.
Il pannello consente di aprire la simulazione esistente per approfondire.

`GET /v1/workspace/processes/{id}/impact-review` legge XML salvato, piano e
registro delle azioni. `POST .../impact-review/actions` aggiunge un'azione
tenant-scoped con UUID idempotente, autore e revisione della base. Una base
modificata restituisce 409 e conserva il testo nel dialog per la consultazione.
Il salvataggio blocca le righe della base durante la verifica e non aggiorna
XML o piano. La migrazione workspace `0029_impact_review_actions` aggiunge la
tabella con cancellazione a cascata del processo.

## Schermate del prodotto

Schermate generate da Playwright sulla vera UI con API simulate e dati
completamente sintetici. Non documentano un processo di un cliente.

- [Overview desktop e mascotte](process-review/overview-desktop.png)
- [Impatti desktop](process-review/impacts-desktop.png)
- [Evidenze desktop](process-review/evidence-desktop.png)
- [Ipotesi To-Be desktop](process-review/tobe-desktop.png)
- [Canvas mobile e mascotte](process-review/mascot-mobile.png)
- [Overview mobile](process-review/overview-mobile.png)
- [Dettaglio della mascotte DeliR](process-review/mascot-detail.png)

![Review desktop](process-review/overview-desktop.png)

## Verifica

Verifiche locali: lint, TypeScript, build produzione e budget bundle, Ruff e mypy;
356 test unit frontend, inclusi parser/modello Review e viewport BPMN; 8 test backend con Postgres
isolato; 6 scenari Playwright su Chromium desktop e mobile, con Axe su Overview,
dialog e To-Be. I controlli coprono persistenza, isolamento tenant, revisioni
obsolete, idempotenza, assenza di mutazioni As-Is, errori delle evidenze, focus,
layout compatto e movimento ridotto. Migrazione verificata su database nuovo e
con downgrade/upgrade della nuova revisione. La matrice Safari non è stata
eseguita in questa sessione.

Il passaggio di personalizzazione verifica inoltre la navigazione dei task,
il ritorno del focus al task corrente, la visibilità dell'azione principale nel
viewport e il ritorno dal registro To-Be al task associato.

Skill locali applicate: `frontend-dev-guidelines`, `react-ui-patterns`,
`ui-ux-designer`, `ui-ux-pro-max`, `tailwind-design-system`,
`ui-visual-validator`, `accessibility-compliance-accessibility-audit`, secondo
il routing di `AGENTS.md`.
