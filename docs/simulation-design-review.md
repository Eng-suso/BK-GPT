# DeliR — revisione della simulazione e identità del prodotto

Data: 2 ottobre 2026. Sintesi proposta sulla base del feedback di Sohay, degli screenshot e dell’ispezione del codice. Non equivale a uno studio con consulenti esterni o a una certificazione di usabilità.

## Il problema di prodotto

Il consulente deve capire cosa rallenta il processo, formulare un’alternativa e dimostrarne l’impatto. Nella versione precedente vedeva molte funzioni con lo stesso peso visivo, in spazi che competevano fra loro. Aggiungere un grafico non rendeva più chiara la decisione.

| Criticità osservata | Conseguenza | Intervento |
| --- | --- | --- |
| Pannelli assoluti sopra KPI, comandi e canvas | Il contesto sparisce quando si apre il dettaglio | Pannello in una colonna dedicata; disposizione verticale su schermi stretti |
| Sei KPI in un pannello di circa 370 px | Etichette spezzate, valori troncati | Griglia adattiva: due colonne nel pannello desktop, una quando lo spazio non basta |
| Proposte in due colonne basate sulla larghezza della finestra | Ogni proposta diventa una striscia | Una colonna nel pannello, spazio per ipotesi e impatti |
| Intestazioni e spostamento separati | Il canvas sembra un dashboard statico | Intestazioni trascinabili, maniglie visibili e alternativa da tastiera |
| Nuovi elementi fuori dalla vista | L’utente non sa se l’aggiunta è riuscita | Raccolta accanto alla tela, coordinate del rilascio, centratura del nuovo elemento |
| Geometria iniziale incoerente | Grafici che si sovrappongono | Calcolo dello spazio laterale prima della fila inferiore; indice corretto quando non esiste la colonna laterale |
| Riepilogo A/B aperto sopra altri comandi | Il confronto aggiunge un’altra sovrapposizione | Dettaglio nel flusso della pagina e matrice dedicata |
| Troppe superfici con effetti e bordi simili | Nessuna gerarchia, identità anonima | Materiali distinti per strumenti, evidenze e selezione |

## Riferimenti verificati

- [ProcessMind — dashboard personalizzate](https://processmind.com/resources/docs/process-dashboards/custom-dashboards): raccolta, contenitori, righe e configurazione contestuale. Applicazione DeliR: elementi componibili; la tela contiene anche il processo. Non copiare immagini, logo o interfaccia.
- [ProcessMind — confronto dei dati](https://processmind.com/resources/docs/analyzing-processes/comparing-data): dati principali, confronto e allineamento delle mappature. Applicazione: riferimento esplicito, identità delle esecuzioni e avviso sulle versioni diverse.
- [SAP Signavio — metriche dei risultati](https://help.sap.com/docs/signavio-process-manager/user-guide/simulation-result-metrics): costi, tempi, risorse e colli di bottiglia. Applicazione: ogni metrica deve aiutare una domanda operativa.
- [Bizagi — what-if](https://help.bizagi.com/platform/en/what_if_analysis.htm): selezione degli scenari e risultati confrontabili; suggerisce confronti a coppie per leggibilità. Applicazione: coppia A/B per il diagramma e matrice per valutare più alternative.
- [Figma — pannelli della tela](https://help.figma.com/hc/en-us/articles/360039832014-Design-prototype-and-explore-layer-properties-in-the-right-sidebar): navigazione, strumenti e proprietà hanno ruoli distinti. Applicazione: una sola pagina con spazi riconoscibili.
- [Miro — frame](https://help.miro.com/hc/en-us/articles/360018261813-Frames): organizzare e navigare i contenuti della board. Applicazione futura: frame tematici per processo, capacità e decisione, oltre alle sezioni già conservate.
- [Linear — revisione del marzo 2026](https://linear.app/now/behind-the-latest-design-refresh): gerarchia, posizioni prevedibili, separatori discreti e una navigazione che lascia emergere il contenuto. Applicazione: densità professionale, non tante card decorative.
- [Raycast — revisione del maggio 2026](https://www.raycast.com/blog/the-new-raycast): uso misurato di Liquid Glass e attenzione alle interazioni quotidiane. Applicazione: vetro discreto negli strumenti, azioni veloci e comprensibili.
- [Apple — materiali](https://developer.apple.com/design/human-interface-guidelines/materials): Liquid Glass per comandi e navigazione, materiali standard per il contenuto. DeliR è una PWA: l’effetto CSS è un’interpretazione dei principi, non il materiale nativo Apple.

## Identità proposta — adozione del sistema Satin esistente

Il sistema creato da Sohay è vincolante: [Satin design system](design/satin-design-system.md). Riutilizzare `Button`, `Checkbox`, `Surface`, `Table`, `StatTile` e le primitive esistenti; il CSS di dominio definisce disposizione, dimensioni e stati della simulazione. Non creare un secondo sistema di colori, componenti, bordi o ombre.

DeliR deve sembrare uno studio operativo di precisione: chiaro, calmo, curato e pronto per dati complessi.

1. **Ambiente**: neutri perla e grafite, griglia della tela discreta, margini regolari. Niente gradienti saturi dietro ai dati.
2. **Strumenti**: vetro leggero, bordo sottile, riflesso breve e ombra morbida. Usare le varianti `toolbar` e `chrome` nei comandi principali e nel trasporto. Le ricette e i fallback restano nel design system condiviso. Riutilizzare i token `material-*`, `glass-*` e le preferenze di accessibilità esistenti.
3. **Evidenze**: superfici opache, numeri tabulari, testo leggibile, tracciabilità dell’esecuzione. Processo e grafici restano il centro della pagina.
4. **Stati**: blu per azione e selezione; ambra per pressione e code; verde/rosso per miglioramento/peggioramento. Il significato è anche testuale.

Usare Geist già presente nel prodotto; non introdurre font remoti. Titoli, metadati e valori hanno dimensioni e pesi distinti. Le intestazioni degli oggetti mostrano tipo, titolo e ambito senza duplicare tutte le informazioni.

La firma del prodotto deve essere il processo collegato alle evidenze e alla decisione. Il vetro contribuisce alla cura, ma la riconoscibilità nasce soprattutto da questa relazione.

## Architettura dell’esperienza

**Osservare**: esecuzione scelta → processo e unità in movimento → KPI allo stesso clock → selezione di un’attività → analisi contestuale. Spostamento e composizione rimangono nella stessa pagina.

**Valutare**: scegliere il riferimento A → alternativa B → leggere il cambiamento del processo e dei KPI → aggiungere fino a quattro alternative alla matrice → ispezionarne una nel canvas. Il confronto usa risultati finali, non il clock istantaneo. A/B sono ruoli di confronto: non devono assegnare automaticamente AS-IS/TO-BE in base al nome.

**Proporre**: diagnosi → ipotesi esplicita → modifica dei parametri → esecuzione → risultato simulato → confronto con il riferimento. Le proposte attuali sono euristiche. La stima deve rimanere distinta dal risultato misurato.

## AS-IS, TO-BE e agenti: confini da risolvere

Per un confronto strutturale fra modelli diversi servono versioni BPMN recuperabili e mappatura delle attività; colorare lo stesso diagramma con identificatori non allineati sarebbe ingannevole. Per scenari proposti dagli agenti servono origine, agente/versione, riferimento, assunzioni, modifica proposta e stato di validazione nel contratto dati. Questi campi non sono disponibili in modo completo oggi: non inventare provenienza AI né chiamare simulata una proposta non eseguita.

Sono quindi distinti: confronto KPI fra esecuzioni disponibile; confronto strutturale completo fra versioni e provenienza delle proposte AI da progettare e implementare con il backend. La matrice non determina uno scenario vincente senza obiettivo dichiarato: tempo e costo possono avere un compromesso.

## Verifica

Percorsi richiesti: spostare processo e grafico a zoom diverso; annullare una sola modifica; aggiungere più elementi senza perderli; configurare una nota; salvare e ricaricare; aprire risultati/heatmap/insight senza intersezioni fra pannello e board; confrontare più esecuzioni; preservare il clock tornando all’osservazione. Verificare desktop, telefono, tastiera, contrasto, trasparenza ridotta e fallback del materiale.

I test automatici e la revisione visiva non sostituiscono una sessione di lavoro con consulenti. Il prossimo riscontro utile è chiedere a un consulente di preparare una raccomandazione AS-IS/TO-BE usando la pagina, osservando dove perde il contesto.

Verifica incrementale del 3 ottobre: corretti il collasso della tela con la raccolta aperta su telefono, la larghezza minima dei KPI e lo scorrimento del riepilogo A/B. Il riferimento della matrice resta fissato anche quando era selezionato implicitamente; i dati assenti sono indicati come non disponibili e non come invariati.
