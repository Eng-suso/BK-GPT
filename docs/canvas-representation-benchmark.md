# Canvas: confronto iniziale delle rappresentazioni

Misurato il 24 novembre 2026 sui tre fixture BPMN pubblici del repository. Il
benchmark usa `o200k_base`, l'importatore/esportatore ufficiale TOK 1.0.4 tramite
`uvx`, e un codec sperimentale DeliR DSL v1. Nessuna libreria TOK viene incorporata
nel prodotto. Riprodurre con:

```powershell
.venv\Scripts\python.exe -m scripts.benchmark_canvas_representations --tok
.venv\Scripts\python.exe -m pytest tests/evals/l0_deterministic/test_canvas_representations.py -q
```

| Fixture | BPMN XML originale | XML semantico minimizzato | DeliR DSL v1 | TOK 1.0.4 |
| --- | ---: | ---: | ---: | ---: |
| purchase_layout | 845 | 767 | 520 | 312 |
| multibranch_layout | 920 | 839 | 600 | 346 |
| omg_issue_list | 545 | 429 | 280 | 152 |

I numeri sono token della sola rappresentazione, non del prompt completo o del
turno agentico. Il DSL DeliR conserva l'albero XML semantico, inclusi ID, flussi,
lane, associazioni, condizioni ed estensioni; esclude la geometria DI, che il
servizio di layout puo' rigenerare. I tre round trip sono identici sul piano
semantico e il BPMN ricostruito passa la validazione locale. **I tre fixture
originali non passano lo schema XSD OMG BPMN 2.0.2**, quindi il test non dimostra
conformita' normativa: preserva esattamente anche le loro anomalie. Il DSL e' ancora un
candidato sperimentale: non e' collegato alla generazione LLM o al salvataggio
del canvas e non e' stato testato su un corpus rappresentativo di clienti.
La v1 rifiuta contenuto XML misto e prefissi namespace usati nei valori QName,
perche' non puo' garantirne il round trip senza perdita.
Un fixture minimo conforme, `tests/fixtures/omg_valid_minimal.bpmn`, verifica
separatamente che il codec preservi la validita' XSD. Le nuove scritture
agentiche passano ora un gate XSD runtime; i diagrammi legacy non conformi
possono ricevere solo modifiche locali che non aggiungono errori XSD.

TOK ha prodotto testi piu' brevi, ma su `purchase_layout` l'esportazione fallisce:
il nodo finale non appartiene a una lane; l'importazione segnala inoltre una
associazione non conservata e modifica il messaggio collegato al message flow.
Negli altri due fixture l'esportazione riesce ma il round trip semantico non e'
identico: cambiano identificativi di lane o scompaiono elementi legati a eventi,
condizioni e dati. Questi casi non autorizzano l'uso di TOK come sostituzione
trasparente dell'XML del canvas. Le durate import/export includono l'avvio del
processo `uvx` e non sono confrontabili con la codifica DeliR in-process.

BPCF-Full e' incluso nel protocollo di valutazione ma non ha un importatore BPMN
XML nel repository ufficiale. Una trascrizione manuale dei fixture non sarebbe un
confronto controllato dello stesso modello. Per ora la dimensione e il round trip
su questi fixture sono **non misurati**. Il paper misura la generazione da testo e
dimostra compattezza su un proprio benchmark; quel risultato non certifica la
fedelta' di conversione dei modelli DeliR.

La prossima prova deve confrontare generazione, comprensione e modifica con gli
stessi input, modelli e budget, includendo token di prompt/output, chiamate,
latenza, fedelta' alle fonti, validita' BPMN e integrita' delle modifiche. I
linguaggi che non preservano i dettagli richiesti devono essere esclusi dal
percorso di modifica o usati solo per generazione su un sottoinsieme dichiarato.

Fonti: [BPCF paper](https://aclanthology.org/2026.emnlp-industry.235/),
[repository BPCF](https://github.com/ankitagr01/bpcf-process-model-notation),
[documentazione TOK](https://tok-lang-bpm.github.io/),
[repository e licenza TOK](https://github.com/tok-lang-bpm/tok),
[specifica OMG BPMN 2.0.2](https://www.omg.org/spec/BPMN/2.0.2/).

## Corpus PMo 1.0.0: 55 processi

Il 24 novembre 2026 abbiamo eseguito lo stesso benchmark sui 55 file BPMN
standardizzati del [PMo Dataset](https://zenodo.org/records/15857589), letti
direttamente dal suo ZIP senza copiarli nel repository:

```powershell
.venv\Scripts\python.exe -m scripts.benchmark_canvas_representations --pmo-zip C:\percorso\pmo-dataset.zip --tok
```

| Misura | DeliR DSL v1 | TOK 1.0.4 |
| --- | ---: | ---: |
| Import/export o codifica completati | 55/55 | 55/55 |
| Round trip semantico esatto | 55/55 | 0/55 |
| Riduzione mediana rispetto all'XML BPMN completo | 76,3% | 88,8% |
| Riduzione mediana rispetto all'XML semantico minimizzato | 32,3% | 68,2% |

Una variante DeliR DSL v2 con tag abbreviati e dizionario dei valori ripetuti
mantiene 55/55 round trip esatti, ma migliora la riduzione mediana rispetto
all'XML completo solo al **77,02%**; nessun caso raggiunge l'85%. Non viene
attivata come formato di scrittura.

Per le **modifiche locali** e' disponibile `manage_canvas_bpmn_model(map)`: una
vista di navigazione di sola lettura con ID esatti, tipi, etichette, lane e
archi. Sul corpus PMo riduce i token della rappresentazione dell'**88,02%
mediano** rispetto all'XML completo; **55/55** casi superano l'85%. La mappa
non contiene tutti i metadati BPMN e non e' un codec round trip. Il runtime
mantiene l'XML canonico e applica solo operazioni atomiche controllate sul
modello originale. Questa misura riguarda il payload della mappa: il turno
completo dell'agente non raggiunge automaticamente lo stesso risparmio.

Il benchmark misura anche il prompt di scope realmente costruito dal runtime
per una modifica locale, con lo stesso BPMN corrente presente nello state.
Prima di includere la mappa nel prompt, la riduzione mediana del prompt compatto
era **87,42%** e 15/55 casi raggiungevano il 90%, ma l'agente doveva leggere
la mappa con una chiamata tool successiva. Ora la mappa completa e' inclusa nel
prompt locale quando entra nel budget: la riduzione mediana del prompt e'
**76,86%**, con 0/55 casi al 90%. Se non entra per intero, viene omessa e
l'agente deve usare il tool `map`; una mappa parziale non e' utilizzabile per
scegliere un ID. Il confronto dei token dell'intera operazione richiede anche
tool schema, messaggi, output, retry e cache del provider. La nuova forma punta
a evitare una chiamata LLM/tool, ma questo effetto non e' ancora misurato.

Lo ZIP PMo include anche rappresentazioni gia' pubblicate: Mermaid per 55/55
processi e JSON Branches per 18/55. Rispetto al BPMN XML completo, le riduzioni
mediane delle dimensioni sono rispettivamente **93,09%** e **91,28%** sui casi
disponibili. Il benchmark conta i token di quei file ma **non** verifica una
conversione reversibile, la conservazione di metadati o la fedelta' alle
descrizioni. Non sono quindi candidati approvati per modificare il modello
canonico solo in base alla loro lunghezza.

I 55 sorgenti PMo non sono tutti conformi all'XSD OMG usato dal gate runtime:
46/55 passano. Il DSL preserva il risultato XSD dei 46 conformi senza
introdurre una regressione. Le differenze TOK includono metadati e dettagli
semantici che il confronto dell'albero completo considera significativi;
non si puo' inferire da questo numero che 55 processi abbiano perso il grafo
di controllo. In 9 casi mancano identificativi originali nel BPMN riesportato.
Il risparmio TOK non soddisfa il requisito di round trip esatto per una
sostituzione trasparente del formato canonico. Nessuno dei 55 casi DeliR
raggiunge l'85% rispetto all'XML completo; il minimo e' 72,5%, il massimo 80,2%.

La misura non include prompt, LLM, task di generazione o modifica, ne' prova
accuratezza semantica rispetto a una descrizione aziendale. PMo include casi
PET: deduplicarli prima di un esperimento con train/test separati.

## Prima prova LLM accoppiata: stato

`scripts/benchmark_canvas_live_selection.py` confronta XML completo e mappa
locale con lo stesso modello e tre richieste sintetiche di selezione del
bersaglio di una rinomina. Registra token riportati dal provider, latenza,
parsing JSON e ID corretto. L'ordine delle coppie e' mescolato con seed fisso;
le richieste non usano dati cliente. Esecuzione:

```powershell
.venv\Scripts\python.exe -m scripts.benchmark_canvas_live_selection --repeat 1
```

Il 24 novembre 2026 il provider ha risposto `RateLimitError` a tutte le sei
chiamate tentate. **Non esiste quindi una misura valida** di accuratezza,
allucinazioni, token o latenza del modello. Il benchmark ora interrompe il run
al primo errore di quota/autenticazione e distingue gli errori provider dalle
risposte sbagliate. Anche quando potra' girare, questa prova misura una sola
scelta di ID, non l'intera operazione canvas con tool, validazione e salvataggio.

## Controllo L3 sul BPMN effettivo

Il canvas aveva gia' un analizzatore di controllo del flusso per il
`BPMNSemanticModel`; il report non controllava direttamente la raggiungibilita'
del BPMN XML mostrato. `backend/bpmn/xml_behavior.py` ora controlla per ogni
processo il grafo principale: inizio, fine, nodi irraggiungibili, nodi senza
percorso verso una fine e sequence flow fuori dal processo. Il full report e
`behavior_validation` espongono un risultato L3 distinto da `xml_valid`.
Sul corpus PMo standardizzato, **55/55** modelli passano questi soli controlli
di raggiungibilita'. La copertura e' dichiarata
`top_level_reachability_only`: sottoprocessi interni, concorrenza e deadlock
richiedono ulteriori controlli e non vengono certificati da questo esito.
Le costruzioni agentiche complete e le review approvate sono ora rifiutate
prima della scrittura se questi controlli falliscono o non riescono ad
analizzare il grafo. Le modifiche locali possono essere salvate come bozze
incomplete; il report L3 espone il problema finche' viene risolto.
